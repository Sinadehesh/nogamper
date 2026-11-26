"""The odds engine.

Pure arithmetic: no database, no cache, no clock. Everything here is a
function of the probabilities handed to it.

## The arithmetic

For a pick on a side with probability `p`:

    odds = 1 / p

That is the whole of it. There is no margin: the price of an outcome is the
reciprocal of how likely the market thinks it is, so a pick is worth exactly
its stake on average, and so is any combination of picks:

    combined   = Π odds_i
    E[return]  = Π p_i x Π odds_i  =  1

A player ends up ahead of where they started only by being right more often
than the crowd they are forecasting against. Nothing is skimmed on the way.

## What used to be here

This module once priced `(1 - vig) / p`, multiplied in promotional boosts and
a bonus for longer slips, and sold cover against a near miss at a loaded
premium. The margin compounded per pick — 5% on a single became 22.6% on five
— which is the mechanism that makes an accumulator the most profitable thing
a bookmaker sells. `bookmaker_take` at the bottom of this file keeps that one
formula, because the reality check uses it to show a player what the same
record would have cost somewhere that charges it.

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
    "OddsError",
    "PricedLeg",
    "PricedSlip",
    "bookmaker_take",
    "price_leg",
    "price_slip",
]

_ODDS_PLACES = Decimal("0.000001")
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
    """The probability of the *selected* side."""
    locked_odds: Decimal
    """Quantised to the column scale — this is what settlement will multiply."""


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
    true_probability: Decimal = Decimal(1)
    """Product of the legs' probabilities: the chance this slip comes in."""


def price_leg(
    *,
    market_id: str,
    side: str,
    raw_yes_prob: Decimal,
    min_prob: Decimal,
    max_prob: Decimal,
) -> PricedLeg:
    """The fair price of one outcome, or a refusal if it has none worth offering.

    **Outside the band is refused, not clamped.** Clamping looks harmless and
    is not: an outcome the market puts at 99.7% would be priced as though it
    were 99%, which pays more than fair on something that almost always
    happens — a slow, riskless way to manufacture points, and the first thing
    anyone optimising a leaderboard would find. The other end fails the other
    way, quietly paying less than fair. A question that is all but settled is
    simply not one there is a forecast left to make on.

    Truncated, not rounded: rounding up would pay a sliver more than fair on
    half of all prices. Truncation errs by at most one millionth, always in
    the same direction.

    The band is also what keeps the result storable. `max_prob` below 1 means
    odds strictly above 1.0, which the column demands — a "win" that returns
    only the stake is not a price — and `min_prob` above 0 bounds the longest
    price a single pick can carry.
    """
    if side not in {"YES", "NO"}:
        raise OddsError("bad_side", f"{side!r} is not YES or NO.")

    selected = raw_yes_prob if side == "YES" else _ONE - raw_yes_prob
    if selected > max_prob:
        raise OddsError("leg_unpriceable", "This outcome is too close to certain to forecast.")
    if selected < min_prob:
        raise OddsError("leg_unpriceable", "This outcome is too unlikely to carry a fair price.")

    locked = (_ONE / selected).quantize(_ODDS_PLACES, rounding=ROUND_DOWN)

    return PricedLeg(
        market_id=market_id,
        side=side,
        raw_prob=raw_yes_prob,
        true_prob=selected,
        locked_odds=locked,
    )


def price_slip(
    legs: tuple[PricedLeg, ...],
    *,
    stake_minor: int,
    payout_cap_minor: int,
    max_combined_odds: Decimal,
) -> PricedSlip:
    if not legs:
        raise OddsError("no_legs", "A slip needs at least one pick.")

    exact_product = _ONE
    true_probability = _ONE
    for leg in legs:
        exact_product *= leg.locked_odds
        true_probability *= leg.true_prob

    if exact_product > max_combined_odds:
        raise OddsError(
            "odds_exceed_maximum",
            f"Combined odds {exact_product:.2f} exceed the maximum of {max_combined_odds:.0f}.",
        )

    gross = int((Decimal(stake_minor) * exact_product).quantize(_ONE, rounding=ROUND_HALF_UP))
    potential = min(gross, payout_cap_minor)

    return PricedSlip(
        legs=legs,
        stake_minor=stake_minor,
        combined_odds=exact_product.quantize(_ODDS_PLACES, rounding=ROUND_DOWN),
        gross_payout_minor=gross,
        payout_cap_minor=payout_cap_minor,
        potential_payout_minor=potential,
        capped=gross > payout_cap_minor,
        true_probability=true_probability,
    )


def bookmaker_take(margin: Decimal, legs: int) -> Decimal:
    """The share of a stake a margin of `margin` per pick removes, on average.

        take = 1 - (1 - margin)^legs

    Not used to price anything here. It is the arithmetic of the product this
    one replaces, kept so the reality check can put a number on it: 5% a pick
    is 5% on a single, 9.8% on a double and 22.6% on five.
    """
    if legs < 1:
        return Decimal(0)
    return _ONE - (_ONE - margin) ** legs
