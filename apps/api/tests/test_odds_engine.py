"""The pricing arithmetic, with nothing else in the way.

One property matters more than the rest, and it gets the first test: the price
of an outcome is the reciprocal of its probability, so nothing is taken.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.engine import odds

D = Decimal

BAND = {"min_prob": D("0.01"), "max_prob": D("0.99")}


def leg(prob: str, side: str = "YES", market: str = "m") -> odds.PricedLeg:
    return odds.price_leg(market_id=market, side=side, raw_yes_prob=D(prob), **BAND)


def slip(legs, *, stake=10_000, cap=10**12, ceiling="1000000"):
    return odds.price_slip(
        tuple(legs), stake_minor=stake, payout_cap_minor=cap, max_combined_odds=D(ceiling)
    )


# ----- one pick -------------------------------------------------------------


@pytest.mark.parametrize(
    ("prob", "expected"),
    [("0.50", "2.000000"), ("0.25", "4.000000"), ("0.80", "1.250000"), ("0.10", "10.000000")],
)
def test_the_price_is_the_reciprocal_of_the_probability(prob, expected):
    assert leg(prob).locked_odds == D(expected)


@pytest.mark.parametrize("prob", ["0.02", "0.13", "0.37", "0.5", "0.61", "0.88", "0.97"])
def test_a_pick_is_worth_its_stake_on_average(prob):
    """The whole claim of the product, as arithmetic: p x odds = 1.

    Truncating to six places can only ever shave the price, so the product
    lands a hair under one and never over it.
    """
    priced = leg(prob)
    expected_return = priced.true_prob * priced.locked_odds
    assert D("0.999999") <= expected_return <= D(1)


def test_the_two_sides_of_a_question_are_priced_from_one_number():
    """NO is 1 - YES, not a second price that could drift from the first."""
    yes, no = leg("0.30", "YES"), leg("0.30", "NO")
    assert yes.true_prob + no.true_prob == D(1)
    assert yes.locked_odds == D("3.333333")
    assert no.locked_odds == D("1.428571")


def test_prices_are_truncated_never_rounded_up():
    """1/3 is 3.333333…; rounding half-up at six places would not change it,
    but 1/0.6 = 1.6666666… would become 1.666667 and pay a sliver over fair."""
    assert leg("0.60").locked_odds == D("1.666666")


def test_every_price_is_storable():
    """The column demands odds strictly above 1.0. The band guarantees it."""
    assert leg("0.99").locked_odds == D("1.010101")
    assert leg("0.01").locked_odds == D("100.000000")


@pytest.mark.parametrize(("prob", "side"), [("0.995", "YES"), ("0.005", "NO"), ("0.9901", "YES")])
def test_an_outcome_that_is_all_but_certain_has_no_price(prob, side):
    """Refused, not clamped. Pricing a 99.5% outcome as though it were 99%
    would pay more than fair on something that almost always happens — points
    for nothing, and the first thing anyone farming a leaderboard would find."""
    with pytest.raises(odds.OddsError) as refused:
        odds.price_leg(market_id="m", side=side, raw_yes_prob=D(prob), **BAND)
    assert refused.value.code == "leg_unpriceable"


@pytest.mark.parametrize(("prob", "side"), [("0.005", "YES"), ("0.995", "NO")])
def test_an_outcome_that_is_all_but_impossible_has_no_price_either(prob, side):
    with pytest.raises(odds.OddsError) as refused:
        odds.price_leg(market_id="m", side=side, raw_yes_prob=D(prob), **BAND)
    assert refused.value.code == "leg_unpriceable"


def test_a_side_that_is_neither_yes_nor_no_is_refused():
    with pytest.raises(odds.OddsError) as refused:
        odds.price_leg(market_id="m", side="MAYBE", raw_yes_prob=D("0.5"), **BAND)
    assert refused.value.code == "bad_side"


# ----- several picks --------------------------------------------------------


def test_a_slip_multiplies_its_picks_and_nothing_else():
    priced = slip([leg("0.50", market="a"), leg("0.25", market="b"), leg("0.80", market="c")])

    assert priced.combined_odds == D("10.000000")
    assert priced.true_probability == D("0.1")
    assert priced.gross_payout_minor == 100_000
    assert priced.potential_payout_minor == 100_000
    assert priced.capped is False


@pytest.mark.parametrize("count", [1, 2, 3, 4, 5])
def test_a_longer_slip_costs_nothing_extra(count):
    """Where a margin compounds per pick, five picks cost far more than one.
    Here the expected return is one at every length."""
    legs = [leg("0.40", market=str(i)) for i in range(count)]
    priced = slip(legs)

    expected_return = priced.true_probability * priced.combined_odds
    assert D("0.9999") < expected_return <= D(1)


def test_the_payout_is_computed_from_the_stored_prices():
    """Settlement multiplies the `locked_odds` it finds on each leg. If the
    quote multiplied anything more precise, a winning slip would pay a
    different number than the one the player was shown."""
    legs = [leg("0.60", market="a"), leg("0.70", market="b")]
    priced = slip(legs, stake=12_345)

    product = legs[0].locked_odds * legs[1].locked_odds
    assert priced.gross_payout_minor == int((D(12_345) * product).quantize(D(1), "ROUND_HALF_UP"))


def test_a_payout_over_the_cap_is_capped_and_says_so():
    priced = slip([leg("0.01")], stake=100_000, cap=5_000_000)

    assert priced.gross_payout_minor == 10_000_000
    assert priced.potential_payout_minor == 5_000_000
    assert priced.capped is True


def test_a_slip_longer_than_the_ceiling_is_refused():
    """Fair odds on a handful of long shots multiply into lottery numbers.
    The ceiling is what keeps the game from becoming one."""
    legs = [leg("0.05", market=str(i)) for i in range(3)]  # 20 x 20 x 20 = 8000

    with pytest.raises(odds.OddsError) as refused:
        slip(legs, ceiling="1000")
    assert refused.value.code == "odds_exceed_maximum"

    assert slip(legs, ceiling="8000").combined_odds == D("8000.000000")


def test_an_empty_slip_is_refused():
    with pytest.raises(odds.OddsError) as refused:
        slip([])
    assert refused.value.code == "no_legs"


# ----- what a margin would have taken ---------------------------------------


@pytest.mark.parametrize(
    ("legs", "expected"),
    [(1, "0.05"), (2, "0.0975"), (3, "0.142625"), (5, "0.2262190625")],
)
def test_a_margin_compounds_with_every_pick(legs, expected):
    """Not used to price anything here — this is the arithmetic of the product
    this one replaces, kept so the reality check can show its cost."""
    assert odds.bookmaker_take(D("0.05"), legs) == D(expected)


def test_no_picks_means_nothing_taken():
    assert odds.bookmaker_take(D("0.05"), 0) == D(0)
