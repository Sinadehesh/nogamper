"""The shipped economy, checked as shipped.

conftest pins every money constant to the scale the rest of the suite was
written against, so that 491 assertions about ledger arithmetic do not have to
be retyped whenever the currency is redenominated. That is the right trade for
those tests and it leaves exactly one gap: nothing else in the suite ever sees
the numbers a deployment actually runs on.

This file is that check. It reads the **declared defaults** off the Settings
class rather than instantiating it, because instantiating would pick up
conftest's pins and the file would then verify the pins rather than the
product.

The currency is the toman, rescaled so roughly 200,000 of them buy one US
dollar. The tests below are about coherence between the constants — nothing
here has an opinion about whether 200,000 is the right rate, only that every
number moved together when it changed. A constant left behind by a
redenomination does not fail loudly; it just quietly means something else.
"""

from __future__ import annotations

import pytest

from backend.config import Settings

TOMAN_PER_DOLLAR_MINOR = 2_500_000_000
MINOR_PER_TOMAN = 100


def shipped(name: str):
    """A field's declared default, uncontaminated by the test environment."""
    field = Settings.model_fields[name]
    return field.default_factory() if field.default_factory else field.default


def _settings() -> Settings:
    """Settings carrying the *shipped* economy, not this suite's pinned one.

    conftest pins the money scale so the tests are readable, which is exactly
    what makes it unable to catch a bad shipped number — so the values under
    test are passed explicitly, and init arguments outrank the environment.
    """
    return Settings(
        vig_rate=shipped("vig_rate"),
        parlay_bonus_by_legs=shipped("parlay_bonus_by_legs"),
        telegram_bot_token="test",
        jwt_secret="x" * 40,
    )


def test_the_house_seed_is_one_dollar():
    """The number the whole risk model rests on.

    HOUSE_SEED_MINOR is the most the house can be down on a single market, so
    the worst case across the book is this times the number of open markets.
    It is written as a dollar figure on purpose, and a redenomination that
    left it behind would multiply real exposure by the redenomination factor
    without anybody touching a setting called risk.
    """
    assert shipped("house_seed_minor") == TOMAN_PER_DOLLAR_MINOR


def test_stake_bounds_are_ordered_and_reachable():
    low = shipped("min_stake_minor")
    high = shipped("max_stake_minor")
    opening = shipped("signup_bonus_minor")

    assert 0 < low < high
    assert low <= opening, "a new player cannot afford the smallest allowed bet"


def test_a_new_player_can_place_several_bets_before_topping_up():
    """A signup bonus worth one bet is a signup bonus that teaches nothing.

    The opening balance has to cover enough plays for somebody to understand
    the product before they are asked for money.
    """
    opening = shipped("signup_bonus_minor")
    smallest = shipped("min_stake_minor")

    assert opening // smallest >= 10


def test_the_payout_cap_is_above_the_largest_possible_stake():
    """Otherwise the cap binds on the stake itself and a winning bet returns
    less than it cost, which is not a cap, it is a confiscation."""
    assert shipped("payout_cap_minor") > shipped("max_stake_minor")


def test_the_daily_drip_is_a_meaningful_fraction_of_a_bet():
    """Free coins are the retention lever and the monetisation lever at once.

    Too small and a returning player cannot do anything with their day's
    claim; too large and the drip covers the vig for everybody and nobody ever
    buys. "At least one minimum bet, at most a fraction of the opening
    balance" is the band that keeps both true.
    """
    drip = shipped("daily_drip_minor")
    assert drip >= shipped("min_stake_minor")
    assert drip < shipped("signup_bonus_minor")


def test_the_house_edge_compounds_with_the_leg_count():
    """1 - (1 - vig)^n x bonus, not the bare vig.

    The vig is charged per leg and the legs multiply, so a three-leg slip is
    worth nearly three times a single to the house even after the parlay bonus
    gives some of it back. Anything reasoning about the take — break-even most
    of all — has to use this rather than vig_rate.
    """
    settings = _settings()
    vig = shipped("vig_rate")

    assert settings.house_edge_at(1) == pytest.approx(vig, abs=1e-9)
    assert settings.house_edge_at(3) == pytest.approx(0.1635, abs=1e-4)
    assert settings.house_edge_at(5) == pytest.approx(0.2487, abs=1e-4)
    assert settings.house_edge_at(3) > vig * 2.3


def test_the_parlay_bonus_never_gives_back_more_than_the_vig_takes():
    """The invariant that keeps the bonus a promotion rather than a leak.

    The bonus makes a longer slip pay better, and it has to stay under the
    edge the extra legs earn. A bonus of 1.35 at five legs looks generous and
    is a *negative* 4.5% edge — the house paying players to build parlays,
    which is the opposite of why parlays are encouraged. The margin compounds
    fast enough that this is easy to cross by eye.
    """
    settings = _settings()
    for legs in range(1, shipped("max_legs") + 1):
        assert settings.house_edge_at(legs) > 0, f"{legs} legs is a losing product"


def test_a_longer_slip_is_still_worth_more_to_the_house():
    """Otherwise the bonus argues against the behaviour it exists to
    encourage: the app would be pushing players toward its own worst bet."""
    settings = _settings()
    edges = [settings.house_edge_at(n) for n in range(1, shipped("max_legs") + 1)]
    assert edges == sorted(edges), edges


def test_break_even_sits_between_a_small_bet_and_a_large_one():
    """(drip + max streak) / house edge — the stake rate at which a player
    never has to spend a Star.

    Below the minimum stake it would be unreachable and everyone would pay;
    above the maximum, nobody ever would. Either end means the dial has been
    turned past the point where it does anything.
    """
    free_per_day = shipped("daily_drip_minor") + shipped("streak_bonus_max_minor")
    edge = 1 - (1 - shipped("vig_rate")) ** shipped("min_legs")
    break_even = free_per_day / edge

    a_heavy_day = shipped("max_stake_minor") * 20

    assert shipped("min_stake_minor") < break_even < a_heavy_day


def test_the_streak_bonus_builds_from_its_own_step():
    step = shipped("streak_bonus_step_minor")
    cap = shipped("streak_bonus_max_minor")

    assert 0 < step < cap
    assert cap % step == 0, "the cap is not reachable by whole steps"


def test_the_decay_floor_leaves_a_playable_balance():
    """Decay exists to reclaim idle coins, not to strand a returning player
    below the price of a single bet."""
    assert shipped("decay_floor_minor") >= shipped("min_stake_minor")


def test_liability_headroom_sits_above_the_seed():
    """The seed bounds the loss; the gross cap bounds one grotesque position.
    A gross cap below the seed would fire first and make the seed unreachable,
    which would mean the number described as the risk limit was not the one
    doing the limiting."""
    assert shipped("max_market_liability_minor") > shipped("house_seed_minor")


def test_singles_are_allowed():
    """Forcing a minimum bought the parlay edge by refusing the bet the player
    came to make. `parlay_bonus_by_legs` earns the same behaviour by paying
    better for longer slips, which is a reason rather than a rule."""
    assert shipped("min_legs") == 1
    assert shipped("min_legs") <= shipped("max_legs")


def test_there_is_a_bonus_for_every_allowed_leg_count():
    """A slip of a length with no entry falls back to no bonus, which would
    silently make the longest slips the worst-paid ones."""
    assert len(shipped("parlay_bonus_by_legs")) == shipped("max_legs")


def test_insurance_only_appears_above_the_leg_minimum():
    """Cover that unlocks below the shortest allowed slip would advertise
    itself on slips that cannot exist."""
    assert shipped("insurance_min_legs") >= shipped("min_legs")


def test_amounts_are_whole_toman():
    """Minor units exist so the ledger can be exact, not so the product can
    price things in fractions of a toman. A constant that is not a whole
    number of toman renders as a rounded figure the player can never match."""
    for name in (
        "signup_bonus_minor",
        "min_stake_minor",
        "max_stake_minor",
        "house_seed_minor",
        "daily_drip_minor",
        "streak_bonus_step_minor",
        "streak_bonus_max_minor",
        "decay_floor_minor",
    ):
        assert shipped(name) % MINOR_PER_TOMAN == 0, f"{name} is a fraction of a toman"


def test_a_granted_coin_comes_back_in_a_handful_of_turns():
    """How much play it takes to reclaim what the house gives away.

    There is no cash-out, so a granted coin returns with probability 1 — the
    balance is a supermartingale with an absorbing barrier at zero. The only
    question is *how fast*, and the answer is grant / edge: at a 16.35% edge
    the house has its signup bonus back after about six times that much
    turnover, where the old 9.12% needed eleven.

    That number decides whether a player ever reaches the buy screen, which
    makes it the most consequential figure in this file. Pinned loosely,
    because the exact value is a tuning decision — but a ladder that drifted
    past ten would mean grants are effectively permanent.
    """
    settings = _settings()
    turns = 1 / settings.house_edge_at(3)

    assert turns < 10, f"a grant takes {turns:.1f}x its own size in turnover to reclaim"
    assert turns > 2, "an edge this steep would start to show in the prices"


def test_the_drip_cannot_outrun_the_edge():
    """The faucet against the drain.

    At 10,000 toman a day this failed in simulation: 99.9% of players betting
    singles were still going after ninety days, because the drip refilled them
    faster than the margin took it back. A player who never runs low never has
    a reason to buy, and a grant that is never recovered in play funded
    nothing.

    The test is the shape of that rather than the simulation: a day's drip
    must be a small fraction of the signup bonus, so the faucet is a reason to
    open the app rather than a second grant every day.
    """
    assert shipped("daily_drip_minor") * 10 <= shipped("signup_bonus_minor")
