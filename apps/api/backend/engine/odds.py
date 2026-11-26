"""The odds engine.

Pure arithmetic: no database, no cache, no clock. Everything here is a
function of the probabilities handed to it, which is what makes the house
edge auditable rather than a matter of trust.

## The arithmetic

For a leg on a side with true probability `p`:

    fair   = 1 / p                      what a zero-margin book would pay
    taxed  = (1 - vig) / p              our price
    locked = taxed x boost              after any promotional boost

Above roughly `p = (1 - vig) / min_leg_odds` there is no price to offer: the
margin consumes the entire payout and the player would lose money by winning.
Those legs are refused rather than quoted.

For a slip of n legs, the payout multiplier is the product of the legs, and
the house's expected share follows directly:

    combined  = Π locked_i
    E[house]  = 1 - Π p_i x Π locked_i  =  1 - Π ((1 - vig) x boost_i)

With no boosts that is `1 - (1 - vig)^n` — 5% on a single, 22.6% on a five-leg
parlay. The compounding is the product; nothing else is doing any work.

## Rounding is not cosmetic here

`fn_settle_prediction` recomputes the payout from the `locked_odds` stored on
each leg. If this module quantises differently from the database, a slip that
wins every leg pays a different number than the one the player was shown.
So legs are quantised to the column's own scale *first*, and the payout is
computed from the product of those quantised values, half-up, exactly as
Postgres `round()` does.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

__all__ = [
    "InsuranceQuote",
    "OddsError",
    "PricedLeg",
    "PricedSlip",
    "failure_distribution",
    "price_insurance",
    "price_leg",
    "price_slip",
]

_ODDS_PLACES = Decimal("0.000001")
_RATE_PLACES = Decimal("0.000001")
_ONE = Decimal(1)


class OddsError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass(frozen=True, slots=True)
class PricedLeg:
    market_id: str
    side: str
    raw_prob: Decimal
    """The market's YES probability, as fetched."""
    true_prob: Decimal
    """The probability of the *selected* side, clamped."""
    vig_rate: Decimal
    boost_multiplier: Decimal
    boost_id: str | None
    locked_odds: Decimal
    """Quantised to the column scale — this is what settlement will multiply."""

    @property
    def fair_odds(self) -> Decimal:
        return (_ONE / self.true_prob).quantize(_ODDS_PLACES, rounding=ROUND_DOWN)


@dataclass(frozen=True, slots=True)
class InsuranceQuote:
    available: bool
    rate: Decimal
    premium_minor: int
    covers_failed_legs: int
    min_legs: int
    fair_rate: Decimal
    """Probability of a covered near-miss, before the margin load. Kept for
    risk reporting: `rate - fair_rate` is the margin actually charged."""
    unavailable_reason: str | None = None


@dataclass(frozen=True, slots=True)
class PricedSlip:
    legs: tuple[PricedLeg, ...]
    stake_minor: int
    combined_odds: Decimal
    """Product of the legs, quantised for storage/display."""
    gross_payout_minor: int
    payout_cap_minor: int
    potential_payout_minor: int
    capped: bool
    house_edge_bps: int
    insurance: InsuranceQuote
    parlay_bonus: Decimal = _ONE
    """Slip-wide multiplier for building a longer slip. Stored on the
    prediction and applied by fn_effective_parlay_odds, so settlement agrees with
    the quote."""
    true_probability: Decimal = Decimal(1)
    """Product of the legs' true probabilities: the chance this slip wins.

    Kept because two decisions read it — whether the payout cap applies, and
    whether the liability guard does — and both need the same number."""
    uncapped: bool = False
    """Paid in full because it is too unlikely to be exposure. See
    Settings.uncapped_below_probability."""

    @property
    def total_cost_minor(self) -> int:
        return self.stake_minor + self.insurance.premium_minor


def _clamp(value: Decimal, low: Decimal, high: Decimal) -> Decimal:
    return min(max(value, low), high)


def price_leg(
    *,
    market_id: str,
    side: str,
    raw_yes_prob: Decimal,
    vig_rate: Decimal,
    min_prob: Decimal,
    max_prob: Decimal,
    min_leg_odds: Decimal = Decimal("1.01"),
    boost_multiplier: Decimal = _ONE,
    boost_id: str | None = None,
) -> PricedLeg:
    if side not in {"YES", "NO"}:
        raise OddsError("bad_side", f"{side!r} is not YES or NO.")

    selected = raw_yes_prob if side == "YES" else _ONE - raw_yes_prob
    true_prob = _clamp(selected, min_prob, max_prob)

    taxed = (_ONE - vig_rate) / true_prob
    locked = (taxed * boost_multiplier).quantize(_ODDS_PLACES, rounding=ROUND_DOWN)

    locked = max(locked, min_leg_odds)

    return PricedLeg(
        market_id=market_id,
        side=side,
        raw_prob=raw_yes_prob,
        true_prob=true_prob,
        vig_rate=vig_rate,
        boost_multiplier=boost_multiplier,
        boost_id=boost_id,
        locked_odds=locked,
    )


def failure_distribution(probabilities: list[Decimal]) -> list[Decimal]:
    """P(exactly k legs fail), for k = 0..n. A Poisson-binomial, computed
    exactly by convolution because the legs have different probabilities."""
    distribution = [_ONE]
    for p in probabilities:
        q = _ONE - p
        updated = [Decimal(0)] * (len(distribution) + 1)
        for k, weight in enumerate(distribution):
            updated[k] += weight * p
            updated[k + 1] += weight * q
        distribution = updated
    return distribution


def price_insurance(
    legs: tuple[PricedLeg, ...],
    stake_minor: int,
    *,
    load: Decimal,
    min_rate: Decimal,
    max_rate: Decimal,
    min_legs: int,
    covers_failed_legs: int,
    requested: bool,
) -> InsuranceQuote:
    """Price near-miss cover from the legs actually on the slip.

    A flat rate cannot work. The cover pays when between 1 and
    `covers_failed_legs` legs fail, and that probability swings by more than
    an order of magnitude with the legs chosen:

        five legs at p=0.30  ->  P(exactly one fails) = 2.8%
        five legs at p=0.50  ->  15.6%
        five legs at p=0.80  ->  41.0%

    A flat 15% premium is nearly free money on longshots and catastrophic on
    the favourites players actually parlay. Charging `(1 + load)` times the
    real probability makes the expected margin `stake x P x load`, which is
    non-negative for every slip that can be constructed.
    """
    unavailable = _insurance_unavailable_reason(legs, min_legs, covers_failed_legs)
    if unavailable is not None:
        return InsuranceQuote(
            available=False,
            rate=Decimal(0),
            premium_minor=0,
            covers_failed_legs=covers_failed_legs,
            min_legs=min_legs,
            fair_rate=Decimal(0),
            unavailable_reason=unavailable,
        )

    distribution = failure_distribution([leg.true_prob for leg in legs])
    fair_rate = sum(distribution[1 : covers_failed_legs + 1], Decimal(0))
    loaded = (_ONE + load) * fair_rate

    if loaded > max_rate:
        return InsuranceQuote(
            available=False,
            rate=Decimal(0),
            premium_minor=0,
            covers_failed_legs=covers_failed_legs,
            min_legs=min_legs,
            fair_rate=fair_rate,
            unavailable_reason="cover_too_expensive_for_these_legs",
        )

    rate = max(loaded, min_rate).quantize(_RATE_PLACES, rounding=ROUND_HALF_UP)

    premium = 0
    if requested:
        premium = int((Decimal(stake_minor) * rate).quantize(_ONE, rounding=ROUND_HALF_UP))
        if premium <= 0:
            return InsuranceQuote(
                available=False,
                rate=rate,
                premium_minor=0,
                covers_failed_legs=covers_failed_legs,
                min_legs=min_legs,
                fair_rate=fair_rate,
                unavailable_reason="stake_too_small_for_cover",
            )

    return InsuranceQuote(
        available=True,
        rate=rate,
        premium_minor=premium,
        covers_failed_legs=covers_failed_legs,
        min_legs=min_legs,
        fair_rate=fair_rate,
    )


def _insurance_unavailable_reason(
    legs: tuple[PricedLeg, ...], min_legs: int, covers_failed_legs: int
) -> str | None:
    if len(legs) < min_legs:
        return "too_few_legs"
    if covers_failed_legs < 1:
        return "cover_disabled"
    if covers_failed_legs >= len(legs):
        return "cover_exceeds_slip"
    return None


def price_slip(
    legs: tuple[PricedLeg, ...],
    *,
    stake_minor: int,
    payout_cap_minor: int,
    max_combined_odds: Decimal,
    insurance: InsuranceQuote,
    uncapped_below_probability: Decimal = Decimal(0),
    parlay_bonus: Decimal = _ONE,
) -> PricedSlip:
    """Price a whole slip.

    **The payout cap is waived below a probability, not below an odds.** The
    two look interchangeable and are not: odds carry the vig and the boost, so
    an odds threshold would waive the cap on a slip made expensive by a
    promotion rather than by being unlikely. The chance the house actually
    pays is the product of the legs' true probabilities, and that is what
    decides.
    """
    if not legs:
        raise OddsError("no_legs", "A slip needs at least one leg.")

    exact_product = _ONE
    for leg in legs:
        exact_product *= leg.locked_odds

    exact_product *= parlay_bonus

    if exact_product > max_combined_odds:
        raise OddsError(
            "odds_exceed_maximum",
            f"Combined odds {exact_product:.2f} exceed the maximum of {max_combined_odds:.0f}.",
        )

    true_probability = _ONE
    for leg in legs:
        true_probability *= leg.true_prob

    gross = int((Decimal(stake_minor) * exact_product).quantize(_ONE, rounding=ROUND_HALF_UP))

    uncapped = uncapped_below_probability > 0 and true_probability <= uncapped_below_probability

    effective_cap = gross if uncapped else payout_cap_minor
    potential = min(gross, effective_cap)

    expected_return = parlay_bonus
    for leg in legs:
        expected_return *= leg.true_prob * leg.locked_odds
    edge_bps = int(((_ONE - expected_return) * 10000).quantize(_ONE, rounding=ROUND_HALF_UP))

    return PricedSlip(
        legs=legs,
        stake_minor=stake_minor,
        combined_odds=exact_product.quantize(_ODDS_PLACES, rounding=ROUND_DOWN),
        gross_payout_minor=gross,
        payout_cap_minor=effective_cap,
        potential_payout_minor=potential,
        capped=not uncapped and gross > payout_cap_minor,
        true_probability=true_probability,
        uncapped=uncapped,
        parlay_bonus=parlay_bonus,
        house_edge_bps=edge_bps,
        insurance=insurance,
    )
