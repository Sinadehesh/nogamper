"""The odds engine, tested as arithmetic.

No database, no cache. If the house edge is wrong, it is wrong here.
"""

from __future__ import annotations

import itertools
from decimal import Decimal

import pytest

from backend.engine import odds

VIG = Decimal("0.05")
MIN_P, MAX_P = Decimal("0.01"), Decimal("0.99")
MIN_LEG_ODDS = Decimal("1.010000")


def leg(prob: str, side: str = "YES", boost: str = "1", market_id: str = "m") -> odds.PricedLeg:
    return odds.price_leg(
        market_id=market_id,
        side=side,
        raw_yes_prob=Decimal(prob),
        vig_rate=VIG,
        min_prob=MIN_P,
        max_prob=MAX_P,
        boost_multiplier=Decimal(boost),
    )


def cover(legs, stake=10000, *, requested=True, min_legs=4, covers=1):
    return odds.price_insurance(
        legs,
        stake,
        load=Decimal("0.35"),
        min_rate=Decimal("0.05"),
        max_rate=Decimal("0.60"),
        min_legs=min_legs,
        covers_failed_legs=covers,
        requested=requested,
    )


def slip(legs, stake=10000, cap=500_000_000, insurance=None):
    return odds.price_slip(
        tuple(legs),
        stake_minor=stake,
        payout_cap_minor=cap,
        max_combined_odds=Decimal(1_000_000),
        insurance=insurance or cover(tuple(legs), stake, requested=False),
    )


def test_a_leg_is_priced_at_the_fair_odds_less_the_vig():
    priced = leg("0.50")
    assert priced.fair_odds == Decimal("2.000000")
    assert priced.locked_odds == Decimal("1.900000")


def test_the_no_side_uses_the_complement():
    priced = leg("0.62", side="NO")
    assert priced.true_prob == Decimal("0.38")
    assert priced.locked_odds == Decimal("2.500000")


def test_both_sides_carry_the_same_vig():
    """A consequence of pricing from the midpoint: p_yes + p_no == 1."""
    yes, no = leg("0.62"), leg("0.62", side="NO")
    assert yes.true_prob + no.true_prob == 1
    assert yes.true_prob * yes.locked_odds == pytest.approx(Decimal("0.95"), abs=Decimal("1e-6"))
    assert no.true_prob * no.locked_odds == pytest.approx(Decimal("0.95"), abs=Decimal("1e-6"))


def test_extreme_probabilities_are_clamped():
    assert leg("0.0001").true_prob == MIN_P

    priced = odds.price_leg(
        market_id="m",
        side="YES",
        raw_yes_prob=Decimal("0.9999"),
        vig_rate=VIG,
        min_prob=MIN_P,
        max_prob=Decimal("0.90"),
    )
    assert priced.true_prob == Decimal("0.90")


def test_a_market_too_likely_to_price_gets_the_floor_rather_than_a_refusal():
    """Above p ~ 0.94 a 5% vig leaves no payout — the taxed price falls below
    even money — and this used to raise `leg_unpriceable`.

    Refusing was the wrong answer to give a player. Someone picking likely
    outcomes was told their bet could not be priced, which reads as the app
    being broken rather than careful, and there is a perfectly good price to
    offer: the floor. A real book quotes a short price there.
    """
    priced = leg("0.9999")
    assert priced.locked_odds == MIN_LEG_ODDS
    assert priced.locked_odds > 1

    assert leg("0.9999", side="NO").locked_odds > 10


def test_the_floor_never_costs_the_house_money():
    """Why clamping is safe rather than merely kind.

    `max_prob` caps the probability before the price is taxed, so the worst
    case is the ceiling: 0.99 x 1.01 = 0.9999 returned to the player. Thin,
    and never negative. Without that cap the clamp would be handing out
    positive-EV bets on near-certainties.
    """
    ceiling = Decimal("0.99")
    priced = odds.price_leg(
        market_id="m",
        side="YES",
        raw_yes_prob=Decimal("0.9999"),
        vig_rate=VIG,
        min_prob=MIN_P,
        max_prob=ceiling,
    )
    expected_return = priced.true_prob * priced.locked_odds
    assert priced.true_prob == ceiling
    assert expected_return < 1


def test_a_boost_multiplies_the_taxed_odds():
    assert leg("0.10", boost="1.4").locked_odds == Decimal("9.500000") * Decimal("1.4")


def test_leg_odds_are_quantised_to_the_column_scale():
    """More places than NUMERIC(12,6) holds would let Postgres round to a
    number this module never computed."""
    priced = leg("0.37")
    assert priced.locked_odds == Decimal("2.567567")
    assert -priced.locked_odds.as_tuple().exponent == 6


@pytest.mark.parametrize(
    ("n", "expected_bps"),
    [(1, 500), (2, 975), (3, 1426), (4, 1855), (5, 2262)],
)
def test_house_edge_compounds_as_one_minus_point_nine_five_to_the_n(n, expected_bps):
    priced = slip([leg("0.50", market_id=f"m{i}") for i in range(n)])
    assert priced.house_edge_bps == pytest.approx(expected_bps, abs=2)


@pytest.mark.parametrize("prob", ["0.05", "0.20", "0.50", "0.80", "0.90"])
@pytest.mark.parametrize("legs_count", [1, 2, 3, 5])
def test_the_edge_is_the_vig_regardless_of_which_legs_are_chosen(prob, legs_count):
    """The player cannot pick their way to an advantage: at true odds the
    edge is exactly 1 - 0.95^n whatever the probabilities."""
    priced = odds.price_slip(
        tuple(leg(prob, market_id=f"m{i}") for i in range(legs_count)),
        stake_minor=10000,
        payout_cap_minor=500_000_000,
        max_combined_odds=Decimal(10**12),
        insurance=cover((), requested=False),
    )
    expected = (1 - Decimal("0.95") ** legs_count) * 10000
    assert abs(priced.house_edge_bps - expected) <= 2


def test_a_boost_can_take_the_edge_negative_which_is_the_point():
    boosted = slip([leg("0.08", boost="1.4")])
    assert boosted.house_edge_bps < 0


def test_payout_is_the_product_of_the_stored_leg_odds():
    """Settlement multiplies prediction_legs.locked_odds. The quoted payout
    must come from exactly those numbers, or a winning slip pays a different
    amount than the player was shown."""
    legs = [leg("0.50", market_id="a"), leg("0.35", market_id="b")]
    priced = slip(legs, stake=10000)

    product = legs[0].locked_odds * legs[1].locked_odds
    assert priced.gross_payout_minor == int(
        (Decimal(10000) * product).quantize(Decimal(1), rounding="ROUND_HALF_UP")
    )


def test_the_payout_cap_binds_and_is_reported():
    priced = slip([leg("0.01") for _ in range(3)], stake=10000, cap=50_000)
    assert priced.capped is True
    assert priced.potential_payout_minor == 50_000
    assert priced.gross_payout_minor > 50_000


def test_absurd_parlays_are_refused_rather_than_silently_capped():
    """Five clamped longshots compound past 7 billion. Selling that as a
    capped payout would be selling a number we never intend to pay."""
    with pytest.raises(odds.OddsError) as exc:
        slip([leg("0.01", market_id=f"m{i}") for i in range(5)])
    assert exc.value.code == "odds_exceed_maximum"


def test_combined_odds_fit_the_column():
    priced = slip([leg("0.02", market_id=f"m{i}") for i in range(3)])
    digits = priced.combined_odds.as_tuple()
    assert len(digits.digits) + digits.exponent <= 8


def test_the_failure_distribution_is_exact_for_a_fair_coin():
    distribution = odds.failure_distribution([Decimal("0.5")] * 5)
    assert distribution[0] == Decimal("0.5") ** 5
    assert distribution[1] == 5 * Decimal("0.5") ** 5
    assert sum(distribution) == 1


def test_the_flat_fifteen_percent_premium_would_have_lost_money():
    """The original model priced cover at a flat 15%, reasoning from
    P(exactly one of five coin flips fails) = 15.625%. That holds only at
    p=0.5, and players parlay favourites."""
    favourites = odds.failure_distribution([Decimal("0.80")] * 5)[1]
    coinflips = odds.failure_distribution([Decimal("0.50")] * 5)[1]
    longshots = odds.failure_distribution([Decimal("0.30")] * 5)[1]

    assert favourites == pytest.approx(Decimal("0.4096"), abs=Decimal("1e-6"))
    assert coinflips == pytest.approx(Decimal("0.15625"), abs=Decimal("1e-6"))
    assert longshots == pytest.approx(Decimal("0.02835"), abs=Decimal("1e-6"))

    flat = Decimal("0.15")
    assert favourites > flat * Decimal("2.7")
    assert coinflips > flat


def test_the_premium_tracks_the_legs_actually_chosen():
    favourites = cover(tuple(leg("0.80", market_id=f"m{i}") for i in range(5)))
    longshots = cover(tuple(leg("0.30", market_id=f"m{i}") for i in range(5)))

    assert favourites.rate > longshots.rate * 5
    assert favourites.rate == pytest.approx(Decimal("0.5530"), abs=Decimal("1e-3"))


@pytest.mark.parametrize("n", [4, 5])
def test_expected_house_margin_is_never_negative_across_the_parameter_space(n):
    """The property that matters: for every constructible insured slip, the
    premium charged is at least the probability of paying it out."""
    grid = [Decimal(p) / 100 for p in range(2, 99, 7)]
    checked = 0

    for combo in itertools.product(grid, repeat=n):
        legs = tuple(
            odds.price_leg(
                market_id=f"m{i}",
                side="YES",
                raw_yes_prob=p,
                vig_rate=VIG,
                min_prob=MIN_P,
                max_prob=MAX_P,
            )
            for i, p in enumerate(combo)
        )
        quote = cover(legs, 1_000_000)
        if quote.available:
            assert quote.rate >= quote.fair_rate, (combo, quote.rate, quote.fair_rate)
        else:
            assert quote.unavailable_reason == "cover_too_expensive_for_these_legs"
        checked += 1

    assert checked > 100


def test_cover_is_refused_below_the_minimum_leg_count():
    quote = cover(tuple(leg("0.5", market_id=f"m{i}") for i in range(3)))
    assert quote.available is False
    assert quote.unavailable_reason == "too_few_legs"
    assert quote.premium_minor == 0


def test_cover_that_would_refund_every_outcome_is_refused():
    legs = tuple(leg("0.5", market_id=f"m{i}") for i in range(4))
    quote = cover(legs, min_legs=4, covers=4)
    assert quote.available is False
    assert quote.unavailable_reason == "cover_exceeds_slip"


def test_a_stake_too_small_to_round_to_a_premium_cannot_buy_cover():
    """The schema requires insurance_premium > 0 on an insured slip."""
    legs = tuple(leg("0.02", market_id=f"m{i}") for i in range(4))
    quote = cover(legs, stake=1)
    assert quote.available is False
    assert quote.unavailable_reason == "stake_too_small_for_cover"


def test_quoting_without_requesting_prices_the_cover_but_charges_nothing():
    legs = tuple(leg("0.6", market_id=f"m{i}") for i in range(5))
    quote = cover(legs, requested=False)
    assert quote.available is True
    assert quote.rate > 0
    assert quote.premium_minor == 0


def test_cover_for_two_failed_legs_costs_more_than_for_one():
    """Compared on the fair rate: at these legs the two-leg cover prices past
    the ceiling and is declined outright, which is the point of the ceiling."""
    legs = tuple(leg("0.6", market_id=f"m{i}") for i in range(5))
    wider, narrower = cover(legs, covers=2), cover(legs, covers=1)

    assert wider.fair_rate > narrower.fair_rate
    assert narrower.available is True
    assert wider.available is False


def test_cover_is_declined_rather_than_sold_below_cost():
    """Found by the property test above: one near-certain loser among four
    favourites drives P(exactly one fails) to ~0.63, past the rate ceiling.
    Clamping the premium to 0.60 there would price cover below its own
    payout probability."""
    legs = (
        leg("0.02", market_id="m0"),
        leg("0.79", market_id="m1"),
        leg("0.93", market_id="m2"),
        leg("0.93", market_id="m3"),
        leg("0.93", market_id="m4"),
    )
    quote = cover(legs)

    assert quote.fair_rate > Decimal("0.60")
    assert quote.available is False
    assert quote.unavailable_reason == "cover_too_expensive_for_these_legs"
    assert quote.premium_minor == 0


def test_the_rate_floor_only_ever_raises_a_premium():
    """Clamping up is safe; clamping down is what loses money."""
    legs = tuple(leg("0.02", market_id=f"m{i}") for i in range(4))
    quote = cover(legs)
    assert quote.available is True
    assert quote.rate >= quote.fair_rate
    assert quote.rate == Decimal("0.050000")
