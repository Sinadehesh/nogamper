"""The shipped game, checked as shipped.

conftest pins every point amount to the scale the rest of the suite was
written against, so that hundreds of assertions about ledger arithmetic do not
have to be retyped whenever a default is retuned. That is the right trade for
those tests and it leaves exactly one gap: nothing else in the suite ever sees
the numbers a deployment actually runs on.

This file is that check. It reads the **declared defaults** off the Settings
class rather than instantiating it, because instantiating would pick up
conftest's pins and the file would then verify the pins rather than the
product.

The tests are about coherence between the constants — nothing here has an
opinion about whether 1,000 points is the right opening balance, only that the
numbers still make a game that can be played when one of them moves.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.config import Settings

MINOR_PER_POINT = 100


def shipped(name: str):
    """A field's declared default, uncontaminated by the test environment."""
    field = Settings.model_fields[name]
    return field.default_factory() if field.default_factory else field.default


# ----- what must not exist --------------------------------------------------


@pytest.mark.parametrize(
    "gone",
    [
        "vig_rate",
        "min_legs",
        "parlay_bonus_by_legs",
        "house_seed_minor",
        "max_market_liability_minor",
        "uncapped_below_probability",
        "insurance_load",
        "boost_max_multiplier",
        "boosts_per_run",
        "decay_rate",
        "streak_bonus_step_minor",
        "referral_bonus_minor",
        "invoice_ttl_seconds",
        "telegram_bot_token",
        "telegram_webhook_secret",
        "translation_provider",
    ],
)
def test_there_is_no_setting_for_what_the_product_no_longer_does(gone):
    """Removed, not zeroed. A product that says it takes nothing should not be
    one environment variable away from taking something — and the same goes
    for selling points, paying for streaks and charging for absence."""
    assert gone not in Settings.model_fields


def test_an_old_environment_cannot_switch_any_of_it_back_on(monkeypatch):
    """A deployment that still carries the old variables boots fine and they
    do nothing: unknown settings are ignored, not honoured."""
    for name, value in {
        "VIG_RATE": "0.07",
        "MIN_LEGS": "3",
        "DECAY_RATE": "0.05",
        "BOOSTS_PER_RUN": "3",
        "TELEGRAM_BOT_TOKEN": "123:abc",
        "TRANSLATION_PROVIDER": "openai",
    }.items():
        monkeypatch.setenv(name, value)

    settings = Settings(jwt_secret="x" * 40)
    settings.require_secrets()
    for attribute in ("vig_rate", "min_legs", "decay_rate", "telegram_bot_token"):
        assert not hasattr(settings, attribute)


# ----- stakes and balances --------------------------------------------------


def test_stake_bounds_are_ordered_and_reachable():
    assert 0 < shipped("min_stake_minor") <= shipped("max_stake_minor")
    assert shipped("min_stake_minor") <= shipped("signup_bonus_minor"), (
        "a new player could not afford the smallest forecast"
    )


def test_a_new_player_can_make_many_forecasts_before_running_out():
    """The opening balance should be an afternoon, not three clicks."""
    assert shipped("signup_bonus_minor") // shipped("min_stake_minor") >= 50


def test_the_daily_top_up_is_enough_to_keep_playing():
    """Nothing is ever sold, so the top-up is the only way back from zero. It
    has to buy several of the smallest forecast, or "free" means "stuck"."""
    assert shipped("daily_topup_minor") // shipped("min_stake_minor") >= 10


def test_the_top_up_does_not_dwarf_the_opening_balance():
    """Large enough to continue, small enough that a week away is not the
    best strategy on the board."""
    assert shipped("daily_topup_minor") * 2 <= shipped("signup_bonus_minor")


def test_one_forecast_cannot_spend_more_than_a_handful_of_opening_balances():
    assert shipped("max_stake_minor") <= shipped("signup_bonus_minor") * 10


def test_the_payout_cap_is_above_the_largest_possible_stake():
    assert shipped("payout_cap_minor") > shipped("max_stake_minor")


@pytest.mark.parametrize(
    "name",
    [
        "signup_bonus_minor",
        "daily_topup_minor",
        "min_stake_minor",
        "max_stake_minor",
        "payout_cap_minor",
        "leaderboard_min_volume_minor",
        "leaderboard_full_credit_volume_minor",
    ],
)
def test_amounts_are_whole_points(name):
    """Balances are shown floored to a whole point, so a default with a
    fraction in it is a number the page can never display exactly."""
    assert shipped(name) % MINOR_PER_POINT == 0


# ----- prices ---------------------------------------------------------------


def test_the_probability_band_is_symmetrical():
    """YES at p and NO at 1 - p are the same pick, so one must be priceable
    exactly when the other is."""
    assert Decimal(str(shipped("min_prob"))) + Decimal(str(shipped("max_prob"))) == 1
    assert 0 < shipped("min_prob") < shipped("max_prob") < 1


def test_the_longest_single_price_fits_under_the_ceiling():
    """Otherwise a single pick the band allows would be refused by the cap,
    and the page would offer a button that can never work."""
    longest_single = 1 / Decimal(str(shipped("min_prob")))
    assert longest_single <= Decimal(str(shipped("max_combined_odds")))


def test_the_ceiling_keeps_the_game_from_being_a_lottery():
    """Fair odds on five long shots multiply into nine digits. The ceiling is
    deliberately far below that."""
    assert shipped("max_combined_odds") <= 10_000
    assert 1 <= shipped("max_legs") <= 5, "the schema stores at most five picks"


# ----- safer play -----------------------------------------------------------


def test_a_limit_must_stand_for_a_meaningful_time_before_it_can_be_loosened():
    assert shipped("limit_loosen_delay_seconds") >= 12 * 3600


def test_the_breaks_on_offer_run_from_a_day_to_a_month():
    options = shipped("break_options_hours")
    assert options == sorted(options)
    assert options[0] >= 24
    assert options[-1] >= 24 * 28


def test_the_illustrated_margin_is_a_plausible_bookmaker_margin():
    """It is labelled as an illustration, but an implausible one would make
    the reality check a scare tactic rather than arithmetic."""
    assert 0.02 <= shipped("reference_margin") <= 0.10


# ----- accounts -------------------------------------------------------------


def test_passwords_are_hashed_at_or_above_the_owasp_minimum():
    """Argon2id: at least 19 MiB with two passes."""
    assert shipped("password_hash_memory_kib") >= 19_456
    assert shipped("password_hash_time_cost") >= 2
    assert shipped("password_min_length") >= 10


def test_a_session_outlives_a_weekend_away():
    """A guest's cookie is the only key to their account."""
    assert shipped("session_ttl_seconds") >= 7 * 24 * 3600


def test_sign_in_is_throttled_by_default():
    assert 0 < shipped("login_rate_max") <= 20
    assert 0 < shipped("signup_ip_rate_max") <= 50


# ----- the leaderboard ------------------------------------------------------


def test_the_leaderboard_thresholds_are_ordered():
    assert (
        0
        < shipped("leaderboard_min_volume_minor")
        < shipped("leaderboard_full_credit_volume_minor")
    )


def test_a_new_player_can_reach_the_leaderboard_on_their_opening_balance():
    assert shipped("leaderboard_min_volume_minor") <= shipped("signup_bonus_minor")
