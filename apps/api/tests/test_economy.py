"""The engagement economy: drip, decay, boosts, leaderboard."""

from __future__ import annotations

import asyncio
import json
import random
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import httpx
import pytest
from conftest import authorise, mock_http_client
from fixtures import gamma_events as fx

from backend import db
from backend.config import Settings, get_settings
from backend.services import economy
from backend.workers import economy as economy_jobs
from backend.workers import polymarket_discovery as discovery


async def user_id_for(telegram_id: int = 5000) -> uuid.UUID:
    async with db.acquire() as conn:
        return await conn.fetchval("SELECT id FROM users WHERE telegram_id = $1", telegram_id)


async def balance(telegram_id: int = 5000) -> int:
    async with db.acquire() as conn:
        return await conn.fetchval(
            "SELECT coin_balance FROM users WHERE telegram_id = $1", telegram_id
        )


async def drift() -> int:
    async with db.acquire() as conn:
        return await conn.fetchval("SELECT count(*) FROM v_balance_reconciliation")


_TEST_TZ = "Etc/GMT-5"


def test_the_day_boundary_follows_the_economy_timezone(monkeypatch):
    """A UTC boundary rolls the daily claim over mid-evening for an audience
    east of it, quietly cutting someone's streak in half."""
    monkeypatch.setenv("ECONOMY_TIMEZONE", _TEST_TZ)
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.economy_timezone == _TEST_TZ

        late = datetime(2026, 8, 23, 22, 0, tzinfo=UTC)
        assert economy.economy_date(settings, late) == date(2026, 8, 24)
        assert economy.economy_date(settings, datetime(2026, 8, 23, 17, 0, tzinfo=UTC)) == date(
            2026, 8, 23
        )
    finally:
        get_settings.cache_clear()


def test_the_next_claim_opens_at_local_midnight(monkeypatch):
    monkeypatch.setenv("ECONOMY_TIMEZONE", _TEST_TZ)
    get_settings.cache_clear()
    try:
        settings = get_settings()
        opens = economy.next_claim_at(settings, date(2026, 8, 23))
        assert opens == datetime(2026, 8, 24, tzinfo=ZoneInfo(_TEST_TZ))
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize(
    ("streak", "expected"), [(1, 0), (2, 5_000), (3, 10_000), (11, 50_000), (40, 50_000)]
)
def test_the_streak_bonus_grows_then_caps(streak, expected):
    assert economy.streak_bonus_for(streak, get_settings()) == expected


async def test_the_first_claim_credits_the_base_drip(app_client):
    auth = await authorise(app_client)
    response = await app_client.post("/v1/economy/claim", headers=auth)

    assert response.status_code == 200
    body = response.json()
    assert body["base"]["minor"] == 25_000
    assert body["streak_bonus"]["minor"] == 0
    assert body["streak"] == 1
    assert body["total"]["minor"] == 25_000
    assert await balance() == 100_000 + 25_000
    assert await drift() == 0


async def test_a_second_claim_the_same_day_is_refused(app_client):
    auth = await authorise(app_client)
    assert (await app_client.post("/v1/economy/claim", headers=auth)).status_code == 200

    second = await app_client.post("/v1/economy/claim", headers=auth)
    assert second.status_code == 409
    assert second.json()["code"] == "already_claimed"
    assert await balance() == 125_000


async def test_concurrent_claims_credit_once(app_client):
    """A double-tapped button on flaky mobile data is the normal case."""
    auth = await authorise(app_client)
    results = await asyncio.gather(
        *(app_client.post("/v1/economy/claim", headers=auth) for _ in range(4))
    )

    assert sorted(r.status_code for r in results) == [200, 409, 409, 409]
    assert await balance() == 125_000

    async with db.acquire() as conn:
        claims = await conn.fetchval("SELECT count(*) FROM daily_claims")
        credits = await conn.fetchval(
            "SELECT count(*) FROM ledger_entries WHERE entry_type = 'DAILY_DRIP_CREDIT'"
        )
    assert claims == 1
    assert credits == 1


async def test_claiming_on_consecutive_days_builds_a_streak(app_client):
    auth = await authorise(app_client)
    settings = get_settings()
    user_id = await user_id_for()
    today = economy.economy_date(settings)

    async with db.transaction() as conn:
        first = await economy.claim_daily_drip(
            conn, user_id=user_id, settings=settings, today=today - timedelta(days=1)
        )
    assert first.streak == 1
    assert first.streak_bonus_minor == 0

    response = await app_client.post("/v1/economy/claim", headers=auth)
    body = response.json()
    assert body["streak"] == 2
    assert body["streak_bonus"]["minor"] == 5_000
    assert body["total"]["minor"] == 30_000

    async with db.acquire() as conn:
        kinds = await conn.fetch(
            "SELECT entry_type, amount FROM ledger_entries"
            " WHERE entry_type IN ('DAILY_DRIP_CREDIT','STREAK_BONUS_CREDIT') ORDER BY id"
        )
    assert [(k["entry_type"], k["amount"]) for k in kinds] == [
        ("DAILY_DRIP_CREDIT", 25_000),
        ("DAILY_DRIP_CREDIT", 25_000),
        ("STREAK_BONUS_CREDIT", 5_000),
    ]


async def test_a_missed_day_resets_the_streak(app_client):
    auth = await authorise(app_client)
    settings = get_settings()
    user_id = await user_id_for()
    today = economy.economy_date(settings)

    async with db.transaction() as conn:
        await economy.claim_daily_drip(
            conn, user_id=user_id, settings=settings, today=today - timedelta(days=3)
        )
        await conn.execute("UPDATE users SET streak_count = 7 WHERE id = $1", user_id)

    assert (await app_client.post("/v1/economy/claim", headers=auth)).json()["streak"] == 1


async def test_the_ledger_carries_a_code_and_farsi_prose(app_client):
    """The code keeps the history machine-readable; the note keeps it readable
    to the people whose money it is."""
    auth = await authorise(app_client)
    await app_client.post("/v1/economy/claim", headers=auth)

    async with db.acquire() as conn:
        entry = await conn.fetchrow(
            "SELECT metadata, idempotency_key FROM ledger_entries"
            " WHERE entry_type = 'DAILY_DRIP_CREDIT'"
        )

    metadata = json.loads(entry["metadata"])
    assert metadata["reason"] == "daily_drip"
    assert metadata["note"] == "هدیهٔ روزانه"
    assert entry["idempotency_key"].startswith("drip:")
    assert economy.economy_date(get_settings()).isoformat() in entry["idempotency_key"]


async def test_a_restricted_account_cannot_claim(app_client):
    auth = await authorise(app_client)
    async with db.transaction() as conn:
        await conn.execute("UPDATE users SET status = 'RESTRICTED'")

    response = await app_client.post("/v1/economy/claim", headers=auth)
    assert response.status_code == 403
    assert response.json()["code"] == "account_restricted"


async def test_claiming_requires_authentication(app_client):
    assert (await app_client.post("/v1/economy/claim")).status_code == 401


async def make_dormant(telegram_id: int, *, balance_minor: int, days: int) -> uuid.UUID:
    async with db.transaction() as conn:
        user_id = await conn.fetchval(
            "INSERT INTO users (telegram_id, first_name, last_prediction_at)"
            " VALUES ($1, 'Dormant', NOW() - make_interval(days => $2)) RETURNING id",
            telegram_id,
            days,
        )
        await conn.execute(
            "INSERT INTO ledger_entries (user_id, entry_type, amount, idempotency_key)"
            " VALUES ($1, 'SIGNUP_BONUS_CREDIT', $2, $3)",
            user_id,
            balance_minor,
            f"seed:{telegram_id}",
        )
    return user_id


@pytest.mark.parametrize(
    ("balance_minor", "expected"),
    [
        (1_000_000, 50_000),
        (60_000, 3_000),
        (52_000, 2_000),
        (50_000, 0),
        (10_000, 0),
    ],
)
def test_decay_never_digs_below_the_floor(balance_minor, expected):
    assert economy.decay_amount(balance_minor, get_settings()) == expected


async def test_a_dormant_player_is_charged_once_a_day(resources):
    await make_dormant(7101, balance_minor=1_000_000, days=5)

    async with db.transaction() as conn:
        first = await economy.run_inactivity_decay(conn, resources)
    assert first.users_charged == 1
    assert first.total_decayed_minor == 50_000
    assert await balance(7101) == 950_000

    async with db.transaction() as conn:
        second = await economy.run_inactivity_decay(conn, resources)
    assert second.users_charged == 0
    assert await balance(7101) == 950_000
    assert await drift() == 0


async def test_an_active_player_is_left_alone(resources):
    await make_dormant(7102, balance_minor=1_000_000, days=1)
    async with db.transaction() as conn:
        report = await economy.run_inactivity_decay(conn, resources)
    assert report.users_charged == 0
    assert await balance(7102) == 1_000_000


async def test_a_player_with_coins_on_the_table_is_not_charged(resources, app_client):
    """Decay exists to push dormant players back. Someone with an open slip is
    already engaged; charging them punishes the behaviour it wants."""
    markets = await seed_markets(1)
    auth = await authorise(app_client, telegram_id=7103)

    response = await app_client.post(
        "/v1/predictions",
        json={
            "legs": [{"market_id": str(markets[0]["id"]), "side": "YES"}],
            "stake": 10_000,
            "insurance": False,
        },
        headers={**auth, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 201

    async with db.transaction() as conn:
        await conn.execute(
            "UPDATE users SET last_prediction_at = NOW() - INTERVAL '10 days'"
            " WHERE telegram_id = 7103"
        )
        report = await economy.run_inactivity_decay(conn, get_settings())

    assert report.users_charged == 0
    assert await balance(7103) == 90_000


async def test_a_player_who_never_predicted_gets_the_same_grace_period(resources):
    """A brand-new account that has not started yet should not be charged for
    not having started."""
    async with db.transaction() as conn:
        user_id = await conn.fetchval(
            "INSERT INTO users (telegram_id, first_name) VALUES (7104, 'New') RETURNING id"
        )
        await conn.execute(
            "INSERT INTO ledger_entries (user_id, entry_type, amount, idempotency_key)"
            " VALUES ($1, 'SIGNUP_BONUS_CREDIT', 1000000, 'seed:7104')",
            user_id,
        )
        fresh = await economy.run_inactivity_decay(conn, resources)
    assert fresh.users_charged == 0

    async with db.transaction() as conn:
        await conn.execute(
            "UPDATE users SET created_at = NOW() - INTERVAL '10 days' WHERE telegram_id = 7104"
        )
        aged = await economy.run_inactivity_decay(conn, resources)
    assert aged.users_charged == 1


async def test_a_restricted_account_is_not_decayed(resources):
    await make_dormant(7105, balance_minor=1_000_000, days=10)
    async with db.transaction() as conn:
        await conn.execute("UPDATE users SET status = 'SELF_EXCLUDED' WHERE telegram_id = 7105")
        report = await economy.run_inactivity_decay(conn, resources)
    assert report.users_charged == 0


async def test_the_decay_ledger_entry_is_keyed_by_day(resources):
    user_id = await make_dormant(7106, balance_minor=1_000_000, days=10)
    async with db.transaction() as conn:
        await economy.run_inactivity_decay(conn, resources)

    async with db.acquire() as conn:
        entry = await conn.fetchrow(
            "SELECT amount, metadata, idempotency_key FROM ledger_entries"
            " WHERE entry_type = 'INACTIVITY_DECAY_DEBIT'"
        )
    assert entry["amount"] == -50_000
    assert json.loads(entry["metadata"])["note"] == "کسر به دلیل بی‌فعالیتی"
    assert entry["idempotency_key"] == (
        f"decay:{user_id}:{economy.economy_date(resources).isoformat()}"
    )


async def seed_markets(count: int = 3, probability: str = "0.50", volume: float = 220000.5):
    events = [
        fx.event(
            str(i),
            markets=[fx.binary_market(f"9{i:04d}", prices=[probability, "0.5"], volumeNum=volume)],
        )
        for i in range(count)
    ]

    def gamma(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("offset", 0))
        return httpx.Response(200, json=events if offset == 0 else [])

    async with mock_http_client(gamma) as client:
        await discovery.run_discovery(client, get_settings())

    async with db.acquire() as conn:
        return [dict(r) for r in await conn.fetch("SELECT * FROM markets ORDER BY lock_at")]


@pytest.mark.parametrize(
    ("yes_prob", "expected"),
    [("0.05", "YES"), ("0.95", "NO"), ("0.10", "YES"), ("0.50", None), ("0.30", None)],
)
def test_only_a_genuine_longshot_side_is_boostable(yes_prob, expected):
    """A randomly chosen side would be inert half the time: the quoting layer
    refuses to apply a boost whose side is likelier than max_raw_prob."""
    assert economy.longshot_side(Decimal(yes_prob), Decimal("0.10")) == expected


async def test_boosts_are_created_on_longshot_sides(resources):
    await seed_markets(3, probability="0.05")

    async with db.transaction() as conn:
        report = await economy.generate_boosts(conn, resources, rng=random.Random(7))

    assert report.created == resources.boosts_per_run

    async with db.acquire() as conn:
        boosts = await conn.fetch("SELECT * FROM odds_boosts")
    assert len(boosts) == resources.boosts_per_run
    for boost in boosts:
        assert boost["side"] == "YES"
        assert Decimal("1.10") <= boost["boost_multiplier"] <= Decimal("1.50")
        assert boost["max_total_stake"] == resources.boost_max_total_stake_minor
        assert boost["is_active"] is True


async def test_a_coin_flip_market_is_never_boosted(resources):
    await seed_markets(3, probability="0.50")
    async with db.transaction() as conn:
        report = await economy.generate_boosts(conn, resources, rng=random.Random(7))

    assert report.created == 0
    assert report.no_longshot_side == 3


async def test_a_quiet_market_is_not_boosted(resources):
    """A boost on a market nobody watches buys no engagement."""
    await seed_markets(2, probability="0.05", volume=100.0)
    async with db.transaction() as conn:
        report = await economy.generate_boosts(conn, resources, rng=random.Random(7))
    assert report.candidates == 0
    assert report.created == 0


async def test_a_market_that_already_has_a_boost_is_skipped(resources):
    markets = await seed_markets(1, probability="0.05")
    async with db.transaction() as conn:
        first = await economy.generate_boosts(conn, resources, rng=random.Random(1))
    assert first.created == 1

    async with db.transaction() as conn:
        second = await economy.generate_boosts(conn, resources, rng=random.Random(2))
    assert second.created == 0

    async with db.acquire() as conn:
        assert (
            await conn.fetchval(
                "SELECT count(*) FROM odds_boosts WHERE market_id = $1", markets[0]["id"]
            )
            == 1
        )


async def test_a_generated_boost_actually_applies_when_quoting(app_client):
    """The end the generator exists for: a boost that the odds engine picks up."""
    markets = await seed_markets(1, probability="0.05")
    async with db.transaction() as conn:
        await economy.generate_boosts(conn, get_settings(), rng=random.Random(3))

    auth = await authorise(app_client)
    quote = (
        await app_client.post(
            "/v1/predictions/quote",
            json={
                "legs": [{"market_id": str(markets[0]["id"]), "side": "YES"}],
                "stake": 10_000,
                "insurance": False,
            },
            headers=auth,
        )
    ).json()

    assert quote["legs"][0]["boosted"] is True
    assert Decimal(quote["legs"][0]["boost_multiplier"]) > 1


async def settled_slip(telegram_id: int, *, staked: int, returned: int, won: bool):
    async with db.transaction() as conn:
        user_id = await conn.fetchval(
            "INSERT INTO users (telegram_id, first_name, username)"
            " VALUES ($1, 'P', $2) ON CONFLICT (telegram_id) DO UPDATE SET first_name='P'"
            " RETURNING id",
            telegram_id,
            f"player{telegram_id}",
        )
        await conn.execute(
            """
            INSERT INTO predictions (user_id, idempotency_key, request_fingerprint, type,
                leg_count, stake, combined_odds, gross_potential_payout, payout_cap,
                potential_payout, status, settled_payout, settled_at)
            VALUES ($1, $2, 'fp', 'SINGLE', 1, $3, 2.0, $4, 500000000, $4,
                    $5::slip_status, $6, NOW())
            """,
            user_id,
            f"lb-{telegram_id}-{uuid.uuid4()}",
            staked,
            max(returned, 1),
            "WON" if won else "LOST",
            returned,
        )
    return user_id


async def test_the_rollup_aggregates_a_season(resources):
    await settled_slip(7201, staked=500_000, returned=900_000, won=True)
    await settled_slip(7201, staked=500_000, returned=0, won=False)
    await settled_slip(7202, staked=200_000, returned=100_000, won=False)

    async with db.transaction() as conn:
        report = await economy.roll_up_leaderboard(conn, resources)

    assert report.entries == 2
    assert report.season_code == datetime.now(ZoneInfo(resources.economy_timezone)).strftime(
        "%Y-%m"
    )

    async with db.acquire() as conn:
        rows = {
            r["telegram_id"]: dict(r)
            for r in await conn.fetch(
                "SELECT u.telegram_id, e.* FROM leaderboard_entries e"
                " JOIN users u ON u.id = e.user_id"
            )
        }

    winner = rows[7201]
    assert winner["slips_settled"] == 2
    assert winner["slips_won"] == 1
    assert winner["total_staked"] == 1_000_000
    assert winner["total_returned"] == 900_000
    assert winner["net_profit"] == -100_000
    assert rows[7202]["net_profit"] == -100_000


async def test_roi_is_damped_by_volume_so_a_thin_hot_streak_cannot_top_the_board(resources):
    """A hard floor alone just moves the exploit to one coin above it.

    Both players here clear the floor. The thin one has a far better ROI but
    less profit; the grinder should win, and does *because* ROI's contribution
    is scaled by how much was actually staked. Undamped, the thin player wins.
    """
    await settled_slip(7203, staked=150_000, returned=900_000, won=True)
    await settled_slip(7204, staked=3_000_000, returned=4_200_000, won=True)

    async with db.transaction() as conn:
        await economy.roll_up_leaderboard(conn, resources)

    async with db.acquire() as conn:
        rows = {
            r["telegram_id"]: dict(r)
            for r in await conn.fetch(
                "SELECT u.telegram_id, e.rank, e.score, e.net_profit, e.total_staked"
                "  FROM leaderboard_entries e JOIN users u ON u.id = e.user_id"
            )
        }

    thin, grinder = rows[7203], rows[7204]
    assert grinder["rank"] == 1
    assert thin["rank"] == 2

    roi_thin = Decimal(thin["net_profit"]) / Decimal(thin["total_staked"])
    undamped_thin = Decimal(thin["net_profit"]) / 100 + (roi_thin * 10000) * Decimal(
        str(resources.leaderboard_roi_weight)
    )
    assert undamped_thin > grinder["score"]


async def test_below_the_volume_floor_a_player_is_unranked_but_still_listed(resources):
    await settled_slip(7205, staked=1_000, returned=50_000, won=True)
    await settled_slip(7206, staked=500_000, returned=600_000, won=True)

    async with db.transaction() as conn:
        report = await economy.roll_up_leaderboard(conn, resources)

    assert report.entries == 2
    assert report.ranked == 1

    async with db.acquire() as conn:
        rows = {
            r["telegram_id"]: dict(r)
            for r in await conn.fetch(
                "SELECT u.telegram_id, e.rank, e.net_profit FROM leaderboard_entries e"
                " JOIN users u ON u.id = e.user_id"
            )
        }
    assert rows[7205]["rank"] is None
    assert rows[7205]["net_profit"] == 49_000
    assert rows[7206]["rank"] == 1


async def test_the_rollup_is_idempotent(resources):
    await settled_slip(7207, staked=500_000, returned=900_000, won=True)

    async with db.transaction() as conn:
        await economy.roll_up_leaderboard(conn, resources)
        first = await conn.fetchrow("SELECT * FROM leaderboard_entries")
    async with db.transaction() as conn:
        await economy.roll_up_leaderboard(conn, resources)
        second = await conn.fetchrow("SELECT * FROM leaderboard_entries")

    assert first["net_profit"] == second["net_profit"]
    assert first["score"] == second["score"]

    async with db.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM leaderboard_entries") == 1


async def test_pending_slips_are_not_counted(resources):
    async with db.transaction() as conn:
        user_id = await conn.fetchval(
            "INSERT INTO users (telegram_id, first_name) VALUES (7208, 'P') RETURNING id"
        )
        await conn.execute(
            """
            INSERT INTO predictions (user_id, idempotency_key, request_fingerprint, type,
                leg_count, stake, combined_odds, gross_potential_payout, payout_cap,
                potential_payout)
            VALUES ($1, 'open', 'fp', 'SINGLE', 1, 500000, 2.0, 1000000, 500000000, 1000000)
            """,
            user_id,
        )
        report = await economy.roll_up_leaderboard(conn, resources)

    assert report.entries == 0


async def test_a_finished_season_stops_being_recomputed(resources):
    await settled_slip(7209, staked=500_000, returned=900_000, won=True)
    async with db.transaction() as conn:
        await economy.roll_up_leaderboard(conn, resources)
        await conn.execute("UPDATE leaderboard_seasons SET ends_at = NOW() - INTERVAL '1 day'")
        report = await economy.roll_up_leaderboard(conn, resources)

    assert report.seasons_finalized == 1
    async with db.acquire() as conn:
        seasons = await conn.fetch("SELECT code, is_finalized FROM leaderboard_seasons")
    assert any(s["is_finalized"] for s in seasons)


async def test_the_leaderboard_endpoint_shows_the_player_their_standing(app_client):
    auth = await authorise(app_client, telegram_id=5000)
    me = await user_id_for(5000)
    async with db.transaction() as conn:
        await conn.execute(
            """
            INSERT INTO predictions (user_id, idempotency_key, request_fingerprint, type,
                leg_count, stake, combined_odds, gross_potential_payout, payout_cap,
                potential_payout, status, settled_payout, settled_at)
            VALUES ($1, 'mine', 'fp', 'SINGLE', 1, 500000, 2.0, 900000, 500000000, 900000,
                    'WON', 900000, NOW())
            """,
            me,
        )
    await settled_slip(7210, staked=900_000, returned=2_000_000, won=True)

    async with db.transaction() as conn:
        await economy.roll_up_leaderboard(conn, get_settings())

    body = (await app_client.get("/v1/economy/leaderboard", headers=auth)).json()

    assert body["season"]
    assert len(body["rows"]) == 2
    assert body["rows"][0]["rank"] == 1
    assert body["my_rank"] == 2
    assert body["my_net_profit"]["minor"] == 400_000
    assert sum(1 for r in body["rows"] if r["is_me"]) == 1


async def test_a_players_telegram_username_never_reaches_the_leaderboard(app_client):
    """Rank 1 is the most-viewed row on this page. Showing the real Telegram
    handle there used to make the top of the leaderboard the single most
    exposed spot in the app for whoever happened to have a username set."""
    auth = await authorise(app_client, telegram_id=5000)
    await settled_slip(7211, staked=900_000, returned=2_000_000, won=True)

    async with db.transaction() as conn:
        await economy.roll_up_leaderboard(conn, get_settings())

    response = await app_client.get("/v1/economy/leaderboard", headers=auth)

    assert "player7211" not in response.text
    assert response.json()["rows"][0]["player"] == "P."


async def test_the_daily_job_runs_decay_and_the_rollup(resources):
    await make_dormant(7301, balance_minor=1_000_000, days=10)
    await settled_slip(7302, staked=500_000, returned=900_000, won=True)

    report = await economy_jobs.run_daily_economy(resources)

    assert report.ran is True
    assert report.errors == []
    assert report.decay["users_charged"] == 1
    assert report.leaderboard["entries"] == 1
    assert await balance(7301) == 950_000


async def test_only_one_replica_runs_the_daily_job(resources):
    await make_dormant(7303, balance_minor=1_000_000, days=10)

    reports = await asyncio.gather(
        economy_jobs.run_daily_economy(resources),
        economy_jobs.run_daily_economy(resources),
        economy_jobs.run_daily_economy(resources),
    )

    assert sum(1 for r in reports if r.ran) == 1
    assert await balance(7303) == 950_000


async def test_a_failing_rollup_does_not_roll_back_decay(resources, monkeypatch):
    await make_dormant(7304, balance_minor=1_000_000, days=10)

    async def boom(*args, **kwargs):
        raise RuntimeError("rollup exploded")

    monkeypatch.setattr(economy, "roll_up_leaderboard", boom)
    report = await economy_jobs.run_daily_economy(resources)

    assert report.decay["users_charged"] == 1
    assert any("leaderboard" in e for e in report.errors)
    assert await balance(7304) == 950_000
    assert await drift() == 0


async def test_the_boost_job_is_contained_when_it_fails(resources, monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("boosts exploded")

    monkeypatch.setattr(economy, "generate_boosts", boom)
    report = await economy_jobs.run_boost_generation(resources)

    assert report.ran is True
    assert report.error is not None


async def test_the_daily_job_is_scheduled_in_the_economy_timezone():
    """Midnight for the player, not midnight for the server."""
    from backend.workers.scheduler import build_scheduler

    settings = Settings(telegram_bot_token="x", jwt_secret="y")
    async with mock_http_client(lambda r: httpx.Response(200, json=[])) as client:
        scheduler = build_scheduler(client, settings)
        scheduler.start(paused=True)
        try:
            job = scheduler.get_job(economy_jobs.DAILY_JOB_NAME)
            assert str(job.trigger.timezone) == settings.economy_timezone
            assert scheduler.get_job(economy_jobs.BOOST_JOB_NAME) is not None
        finally:
            scheduler.shutdown(wait=False)
