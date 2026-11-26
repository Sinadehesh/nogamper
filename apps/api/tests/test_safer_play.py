"""The brakes a player sets for themselves, and the mirror they can look in.

Two properties are the point of everything here, and most of these tests are
one or the other: a limit or a break is **easy to tighten and slow to
loosen**, and both are enforced on the server at the moment a forecast is
placed — not suggested by the page.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from conftest import authorise, balance_of, email_for
from test_predictions import body, place, seed_markets

from backend import db
from backend.config import get_settings


async def set_limit(client, auth, minor):
    return await client.put("/v1/me/limits", json={"daily_limit_minor": minor}, headers=auth)


async def take_break(client, auth, hours):
    return await client.post("/v1/me/break", json={"hours": hours}, headers=auth)


async def age_limit(hours: float, player: int = 5000) -> None:
    """Make the current limit look as though it was set `hours` ago."""
    async with db.acquire() as conn:
        await conn.execute(
            "UPDATE users SET daily_limit_set_at = NOW() - make_interval(secs => $2) "
            " WHERE email = $1",
            email_for(player),
            hours * 3600.0,
        )


async def settle(slip_id: str, *, won: bool) -> None:
    async with db.transaction() as conn:
        await conn.execute(
            "UPDATE prediction_legs SET status = $2::leg_status, settled_at = NOW() "
            " WHERE prediction_id = $1",
            uuid.UUID(slip_id),
            "WON" if won else "LOST",
        )
        await conn.fetchval("SELECT fn_settle_prediction($1)", uuid.UUID(slip_id))


# ----- the daily limit ------------------------------------------------------


async def test_a_new_player_has_no_limit_and_no_break(app_client):
    auth = await authorise(app_client)

    limits = (await app_client.get("/v1/me/limits", headers=auth)).json()
    assert limits["daily_limit"] is None
    assert limits["daily_spent"]["minor"] == 0
    assert limits["daily_limit_loosen_at"] is None
    assert limits["break_until"] is None
    assert limits["break_options_hours"] == [24, 72, 168, 720]


async def test_setting_a_limit_takes_effect_at_once(app_client):
    markets = await seed_markets(2)
    auth = await authorise(app_client)

    response = await set_limit(app_client, auth, 15_000)
    assert response.status_code == 200
    assert response.json()["daily_limit"] == {"minor": 15_000, "display": "150"}

    assert (await place(app_client, auth, body(markets[:1], stake=10_000))).status_code == 201

    refused = await place(app_client, auth, body(markets[1:], stake=10_000))
    assert refused.status_code == 403
    assert refused.json()["code"] == "daily_limit_reached"
    assert await balance_of() == 100_000 - 10_000


async def test_the_limit_counts_what_was_staked_today_whatever_happened_to_it(app_client):
    """A limit on *staking* is spent by staking. A slip that has since won
    does not hand the allowance back."""
    markets = await seed_markets(2)
    auth = await authorise(app_client)
    await set_limit(app_client, auth, 15_000)

    slip = (await place(app_client, auth, body(markets[:1], stake=10_000))).json()
    await settle(slip["id"], won=True)

    refused = await place(app_client, auth, body(markets[1:], stake=10_000))
    assert refused.json()["code"] == "daily_limit_reached"

    limits = (await app_client.get("/v1/me/limits", headers=auth)).json()
    assert limits["daily_spent"]["minor"] == 10_000


async def test_yesterdays_stakes_do_not_count_against_today(app_client):
    markets = await seed_markets(2)
    auth = await authorise(app_client)
    await set_limit(app_client, auth, 15_000)
    await place(app_client, auth, body(markets[:1], stake=10_000))

    async with db.acquire() as conn:
        await conn.execute("UPDATE predictions SET placed_at = placed_at - INTERVAL '1 day'")

    assert (await place(app_client, auth, body(markets[1:], stake=10_000))).status_code == 201


async def test_a_limit_can_be_tightened_immediately(app_client):
    auth = await authorise(app_client)
    await set_limit(app_client, auth, 50_000)

    tighter = await set_limit(app_client, auth, 20_000)
    assert tighter.status_code == 200
    assert tighter.json()["daily_limit"]["minor"] == 20_000


async def test_a_fresh_limit_cannot_be_raised_or_removed(app_client):
    """The moment somebody most wants a limit gone is the moment it is doing
    its job."""
    auth = await authorise(app_client)
    await set_limit(app_client, auth, 20_000)

    for looser in (50_000, None):
        refused = await set_limit(app_client, auth, looser)
        assert refused.status_code == 409
        assert refused.json()["code"] == "limit_locked"
        until = datetime.fromisoformat(refused.json()["until"])
        assert timedelta(hours=23) < until - datetime.now(UTC) <= timedelta(hours=24)

    limits = (await app_client.get("/v1/me/limits", headers=auth)).json()
    assert limits["daily_limit"]["minor"] == 20_000
    assert limits["daily_limit_loosen_at"] is not None


async def test_a_limit_that_has_stood_a_day_can_be_raised(app_client):
    auth = await authorise(app_client)
    await set_limit(app_client, auth, 20_000)
    await age_limit(25)

    raised = await set_limit(app_client, auth, 50_000)
    assert raised.status_code == 200
    assert raised.json()["daily_limit"]["minor"] == 50_000
    # And the new, looser limit starts its own day before it can go further.
    assert raised.json()["daily_limit_loosen_at"] is not None
    assert (await set_limit(app_client, auth, None)).status_code == 409


async def test_a_limit_that_has_stood_a_day_can_be_removed(app_client):
    auth = await authorise(app_client)
    await set_limit(app_client, auth, 20_000)
    await age_limit(25)

    removed = await set_limit(app_client, auth, None)
    assert removed.status_code == 200
    assert removed.json()["daily_limit"] is None
    assert removed.json()["daily_limit_loosen_at"] is None


async def test_tightening_restarts_the_wait(app_client):
    """Otherwise the lock could be sidestepped: wait a day at a loose limit,
    tighten for show, loosen again straight away."""
    auth = await authorise(app_client)
    await set_limit(app_client, auth, 50_000)
    await age_limit(25)

    await set_limit(app_client, auth, 20_000)
    assert (await set_limit(app_client, auth, 50_000)).status_code == 409


async def test_saving_the_same_limit_again_does_not_restart_the_wait(app_client):
    auth = await authorise(app_client)
    await set_limit(app_client, auth, 20_000)
    await age_limit(25)

    assert (await set_limit(app_client, auth, 20_000)).status_code == 200
    assert (await set_limit(app_client, auth, 50_000)).status_code == 200


@pytest.mark.parametrize("bad", [0, -500])
async def test_a_limit_must_be_a_positive_amount(app_client, bad):
    auth = await authorise(app_client)
    assert (await set_limit(app_client, auth, bad)).status_code == 422


async def test_two_slips_arriving_together_cannot_both_slip_under_the_limit(app_client):
    """The check and the stake happen under one lock on the player's row."""
    markets = await seed_markets(4)
    auth = await authorise(app_client)
    await set_limit(app_client, auth, 15_000)

    results = await asyncio.gather(
        *(place(app_client, auth, body([market], stake=10_000)) for market in markets)
    )

    assert sorted(r.status_code for r in results) == [201, 403, 403, 403]
    assert await balance_of() == 100_000 - 10_000


# ----- breaks ---------------------------------------------------------------


async def test_a_break_refuses_forecasts_until_it_ends(app_client):
    markets = await seed_markets(1)
    auth = await authorise(app_client)

    started = await take_break(app_client, auth, 24)
    assert started.status_code == 200
    until = datetime.fromisoformat(started.json()["break_until"])
    assert timedelta(hours=23, minutes=59) < until - datetime.now(UTC) <= timedelta(hours=24)

    refused = await place(app_client, auth, body(markets))
    assert refused.status_code == 403
    assert refused.json()["code"] == "on_break"
    assert datetime.fromisoformat(refused.json()["until"]) == until
    assert await balance_of() == 100_000


async def test_a_break_does_not_lock_the_player_out_of_their_account(app_client):
    """It is a break from forecasting. The record, the settings and the daily
    top-up all stay reachable — stepping away should not cost anything."""
    await seed_markets(1)
    auth = await authorise(app_client)
    await take_break(app_client, auth, 24)

    assert (await app_client.get("/v1/me", headers=auth)).status_code == 200
    assert (await app_client.get("/v1/markets", headers=auth)).status_code == 200
    assert (await app_client.get("/v1/predictions", headers=auth)).status_code == 200
    assert (await app_client.post("/v1/economy/claim", headers=auth)).status_code == 200


async def test_a_break_can_be_extended(app_client):
    auth = await authorise(app_client)
    first = (await take_break(app_client, auth, 24)).json()["break_until"]

    longer = (await take_break(app_client, auth, 168)).json()["break_until"]
    assert datetime.fromisoformat(longer) > datetime.fromisoformat(first)


async def test_a_break_cannot_be_shortened(app_client):
    """There is no request a player can make that brings the end closer."""
    auth = await authorise(app_client)
    week = (await take_break(app_client, auth, 168)).json()["break_until"]

    shorter = await take_break(app_client, auth, 24)
    assert shorter.status_code == 200
    assert shorter.json()["break_until"] == week


async def test_there_is_no_route_that_ends_a_break(app_client):
    auth = await authorise(app_client)
    await take_break(app_client, auth, 24)

    assert (await app_client.delete("/v1/me/break", headers=auth)).status_code == 405
    for hours in (0, -24):
        assert (await take_break(app_client, auth, hours)).status_code == 422


async def test_only_the_offered_lengths_are_accepted(app_client):
    auth = await authorise(app_client)

    refused = await take_break(app_client, auth, 5)
    assert refused.status_code == 400
    assert refused.json()["code"] == "bad_break_length"


async def test_forecasting_resumes_when_the_break_is_over(app_client):
    markets = await seed_markets(1)
    auth = await authorise(app_client)
    await take_break(app_client, auth, 24)

    async with db.acquire() as conn:
        await conn.execute("UPDATE users SET cooloff_until = NOW() - INTERVAL '1 minute'")

    assert (await place(app_client, auth, body(markets))).status_code == 201
    assert (await app_client.get("/v1/me/limits", headers=auth)).json()["break_until"] is None


async def test_a_break_started_in_another_tab_binds_this_one_too(app_client):
    """The row is read again, under a lock, inside the placement transaction —
    not taken from the copy the request was authenticated with."""
    markets = await seed_markets(1)
    here = await authorise(app_client)
    elsewhere = await authorise(app_client)

    await take_break(app_client, elsewhere, 24)

    assert (await place(app_client, here, body(markets))).json()["code"] == "on_break"


async def test_the_profile_carries_the_limits(app_client):
    auth = await authorise(app_client)
    await set_limit(app_client, auth, 30_000)
    await take_break(app_client, auth, 72)

    limits = (await app_client.get("/v1/me", headers=auth)).json()["limits"]
    assert limits["daily_limit"]["minor"] == 30_000
    assert limits["break_until"] is not None


async def test_limits_are_per_player(app_client):
    markets = await seed_markets(1)
    cautious = await authorise(app_client, 7001)
    other = await authorise(app_client, 7002)
    await take_break(app_client, cautious, 24)

    assert (await place(app_client, other, body(markets))).status_code == 201


async def test_a_guest_can_use_the_same_brakes(app_client):
    guest = await app_client.post("/v1/auth/guest")
    auth = {"Authorization": f"Bearer {guest.json()['access_token']}"}

    assert (await set_limit(app_client, auth, 10_000)).status_code == 200
    assert (await take_break(app_client, auth, 24)).status_code == 200


# ----- the reality check ----------------------------------------------------


async def test_an_empty_record_is_all_zeroes(app_client):
    auth = await authorise(app_client)

    check = (await app_client.get("/v1/me/reality-check", headers=auth)).json()
    assert check["slips_placed"] == 0
    assert check["net"]["minor"] == 0
    assert check["margin_cost"]["minor"] == 0
    assert check["reference_margin"] == "0.05"
    assert [b["picks"] for b in check["calibration"]] == [0, 0, 0, 0, 0]


async def test_the_record_adds_up(app_client):
    markets = await seed_markets(4)
    auth = await authorise(app_client)

    won = (await place(app_client, auth, body(markets[:1], stake=10_000))).json()
    lost = (await place(app_client, auth, body(markets[1:2], stake=20_000))).json()
    await place(app_client, auth, body(markets[2:3], stake=5_000))  # still open
    await settle(won["id"], won=True)
    await settle(lost["id"], won=False)

    check = (await app_client.get("/v1/me/reality-check", headers=auth)).json()

    assert check["slips_placed"] == 3
    assert check["slips_open"] == 1
    assert check["slips_settled"] == 2
    assert (check["slips_won"], check["slips_lost"]) == (1, 1)
    assert (check["picks_settled"], check["picks_correct"]) == (2, 1)
    # Open slips are not in the totals: their outcome is not known yet.
    assert check["staked"]["minor"] == 30_000
    assert check["returned"]["minor"] == 20_000
    assert check["net"]["minor"] == -10_000
    assert check["active_days_30d"] == 1
    assert check["slips_30d"] == 3


async def test_the_margin_cost_is_what_a_bookmaker_would_have_kept(app_client):
    """A single won at fair odds of 2.0 paid 20,000. At a 5% margin the same
    pick is priced 1.9 and pays 19,000 — the 1,000 difference is the cost."""
    markets = await seed_markets(1)
    auth = await authorise(app_client)
    slip = (await place(app_client, auth, body(markets, stake=10_000))).json()
    await settle(slip["id"], won=True)

    check = (await app_client.get("/v1/me/reality-check", headers=auth)).json()

    assert check["net"]["minor"] == 10_000
    assert check["margin_cost"]["minor"] == 1_000
    assert check["net_with_margin"]["minor"] == 9_000


async def test_the_margin_compounds_on_a_longer_slip(app_client):
    """Three picks at 2.0 pay 80,000 fair. At 5% a pick the same slip pays
    0.95^3 of that: 68,590. The margin took 11,410 — 14.3%, not 5%."""
    markets = await seed_markets(3)
    auth = await authorise(app_client)
    slip = (await place(app_client, auth, body(markets, stake=10_000))).json()
    await settle(slip["id"], won=True)

    check = (await app_client.get("/v1/me/reality-check", headers=auth)).json()
    assert check["margin_cost"]["minor"] == 11_410


async def test_a_losing_slip_costs_the_same_with_or_without_a_margin(app_client):
    """The margin is taken out of winnings. A lost stake is lost either way."""
    markets = await seed_markets(1)
    auth = await authorise(app_client)
    slip = (await place(app_client, auth, body(markets, stake=10_000))).json()
    await settle(slip["id"], won=False)

    check = (await app_client.get("/v1/me/reality-check", headers=auth)).json()
    assert check["margin_cost"]["minor"] == 0
    assert check["net"]["minor"] == check["net_with_margin"]["minor"] == -10_000


async def test_the_illustration_follows_the_configured_margin(app_client):
    get_settings().reference_margin = 0.10
    markets = await seed_markets(1)
    auth = await authorise(app_client)
    slip = (await place(app_client, auth, body(markets, stake=10_000))).json()
    await settle(slip["id"], won=True)

    check = (await app_client.get("/v1/me/reality-check", headers=auth)).json()
    assert check["reference_margin"] == "0.1"
    assert check["margin_cost"]["minor"] == 2_000


async def test_calibration_buckets_picks_by_the_price_that_was_paid(app_client):
    """Backing NO at a YES price of 30% is a 70% pick, and is counted as one."""
    markets = await seed_markets(2, probability="0.30")
    auth = await authorise(app_client)

    yes = (await place(app_client, auth, body(markets[:1], sides=["YES"]))).json()
    no = (await place(app_client, auth, body(markets[1:], sides=["NO"]))).json()
    await settle(yes["id"], won=False)
    await settle(no["id"], won=True)

    buckets = (await app_client.get("/v1/me/reality-check", headers=auth)).json()["calibration"]
    by_low = {b["low"]: b for b in buckets}

    assert (by_low["0.20"]["picks"], by_low["0.20"]["correct"]) == (1, 0)
    assert by_low["0.20"]["expected"] == "0.3000"
    assert (by_low["0.60"]["picks"], by_low["0.60"]["correct"]) == (1, 1)
    assert by_low["0.60"]["expected"] == "0.7000"
    assert sum(b["picks"] for b in buckets) == 2


async def test_one_players_record_is_not_anothers(app_client):
    markets = await seed_markets(1)
    busy = await authorise(app_client, 7001)
    quiet = await authorise(app_client, 7002)
    await place(app_client, busy, body(markets))

    check = (await app_client.get("/v1/me/reality-check", headers=quiet)).json()
    assert check["slips_placed"] == 0


async def test_these_routes_need_a_session(app_client):
    assert (await app_client.get("/v1/me/limits")).status_code == 401
    assert (await app_client.get("/v1/me/reality-check")).status_code == 401
    assert (await app_client.post("/v1/me/break", json={"hours": 24})).status_code == 401
