"""The free economy: the daily top-up and the leaderboard."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import httpx
from conftest import (
    OVERLAP_SECONDS,
    authorise,
    balance_of,
    email_for,
    mock_http_client,
    user_id_for,
)

from backend import db
from backend.config import Settings, get_settings
from backend.services import economy
from backend.workers import economy as economy_jobs


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


def test_a_day_starts_at_local_midnight(monkeypatch):
    """What a daily limit is measured from — the same boundary as the top-up,
    so a player sees one "day" and not two that disagree."""
    monkeypatch.setenv("ECONOMY_TIMEZONE", _TEST_TZ)
    get_settings.cache_clear()
    try:
        settings = get_settings()
        late_evening_utc = datetime(2026, 8, 3, 21, 0, tzinfo=UTC)  # already the 4th locally

        start = economy.day_start(settings, late_evening_utc)
        assert start == datetime(2026, 8, 4, 0, 0, tzinfo=ZoneInfo(_TEST_TZ))
        assert start <= late_evening_utc < start + timedelta(days=1)
    finally:
        get_settings.cache_clear()


# ----- the daily top-up -----------------------------------------------------


async def test_the_top_up_credits_a_flat_amount(app_client):
    auth = await authorise(app_client)

    response = await app_client.post("/v1/economy/claim", headers=auth)
    assert response.status_code == 200

    body = response.json()
    assert body["amount"] == {"minor": 25_000, "display": "250"}
    assert body["balance"]["minor"] == 125_000
    assert await balance_of() == 125_000
    assert await drift() == 0


async def test_a_second_claim_the_same_day_is_refused(app_client):
    auth = await authorise(app_client)
    await app_client.post("/v1/economy/claim", headers=auth)

    again = await app_client.post("/v1/economy/claim", headers=auth)
    assert again.status_code == 409
    assert again.json()["code"] == "already_claimed"
    assert await balance_of() == 125_000


async def test_concurrent_claims_credit_once(app_client):
    auth = await authorise(app_client)

    results = await asyncio.gather(
        *(app_client.post("/v1/economy/claim", headers=auth) for _ in range(5))
    )

    assert sorted(r.status_code for r in results) == [200, 409, 409, 409, 409]
    assert await balance_of() == 125_000


async def test_the_top_up_is_the_same_on_every_day_however_many_in_a_row(app_client):
    """There is no streak. Ten consecutive days pay exactly what one does, and
    a missed day costs nothing — which is the difference between a top-up and
    a reason to come back."""
    await authorise(app_client)
    me = await user_id_for()
    settings = get_settings()
    start = date(2026, 3, 1)

    amounts = []
    async with db.transaction() as conn:
        for offset in (0, 1, 2, 3, 4, 9, 10):  # five in a row, a gap, two more
            result = await economy.claim_daily_topup(
                conn, user_id=me, settings=settings, today=start + timedelta(days=offset)
            )
            amounts.append(result.amount_minor)

    assert amounts == [25_000] * 7

    async with db.acquire() as conn:
        bonuses = await conn.fetchval(
            "SELECT count(*) FROM ledger_entries WHERE entry_type = 'STREAK_BONUS_CREDIT'"
        )
        rows = await conn.fetch("SELECT DISTINCT streak_bonus, streak_after FROM daily_claims")
    assert bonuses == 0
    assert [(r["streak_bonus"], r["streak_after"]) for r in rows] == [(0, 1)]


async def test_the_profile_says_when_the_next_top_up_opens(app_client):
    auth = await authorise(app_client)

    before = (await app_client.get("/v1/me", headers=auth)).json()
    assert before["can_claim_daily"] is True
    assert before["next_claim_at"] is None
    assert before["daily_topup"]["minor"] == 25_000

    claimed = (await app_client.post("/v1/economy/claim", headers=auth)).json()
    after = (await app_client.get("/v1/me", headers=auth)).json()

    assert after["can_claim_daily"] is False
    assert after["next_claim_at"] is not None
    assert datetime.fromisoformat(after["next_claim_at"]) == datetime.fromisoformat(
        claimed["next_claim_at"]
    )


async def test_the_ledger_entry_is_keyed_by_day_and_written_in_english(app_client):
    auth = await authorise(app_client)
    await app_client.post("/v1/economy/claim", headers=auth)

    async with db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT idempotency_key, metadata FROM ledger_entries "
            " WHERE entry_type = 'DAILY_DRIP_CREDIT'"
        )

    assert row["idempotency_key"].startswith("drip:")
    assert row["idempotency_key"].endswith(economy.economy_date(get_settings()).isoformat())
    metadata = json.loads(row["metadata"])
    assert metadata == {"reason": "daily_topup"}
    assert row["metadata"].isascii()


async def test_a_restricted_account_cannot_claim(app_client):
    auth = await authorise(app_client)
    async with db.transaction() as conn:
        await conn.execute("UPDATE users SET status = 'RESTRICTED'")

    response = await app_client.post("/v1/economy/claim", headers=auth)
    assert response.status_code == 403
    assert response.json()["code"] == "account_restricted"


async def test_claiming_requires_authentication(app_client):
    assert (await app_client.post("/v1/economy/claim")).status_code == 401


async def test_points_never_expire_however_long_an_account_sits(app_client):
    """There used to be a charge on accounts that had gone quiet. Nothing in
    the schedule touches a dormant balance now."""
    await authorise(app_client)
    async with db.acquire() as conn:
        await conn.execute(
            "UPDATE users SET created_at = NOW() - INTERVAL '400 days',"
            "                 last_seen_at = NOW() - INTERVAL '400 days'"
        )

    await economy_jobs.run_leaderboard_rollup(get_settings())

    assert await balance_of() == 100_000
    async with db.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM decay_events") == 0
        debits = await conn.fetchval(
            "SELECT count(*) FROM ledger_entries WHERE entry_type = 'INACTIVITY_DECAY_DEBIT'"
        )
    assert debits == 0


# ----- the leaderboard ------------------------------------------------------


async def settled_slip(player: int, *, staked: int, returned: int, won: bool):
    async with db.transaction() as conn:
        user_id = await conn.fetchval(
            "INSERT INTO users (email, password_hash, first_name)"
            " VALUES ($1, '$argon2id$stub', 'Pat')"
            " ON CONFLICT (email) WHERE email IS NOT NULL DO UPDATE SET first_name = 'Pat'"
            " RETURNING id",
            email_for(player),
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
            f"lb-{player}-{uuid.uuid4()}",
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
            r["email"]: dict(r)
            for r in await conn.fetch(
                "SELECT u.email, e.* FROM leaderboard_entries e JOIN users u ON u.id = e.user_id"
            )
        }

    winner = rows[email_for(7201)]
    assert winner["slips_settled"] == 2
    assert winner["slips_won"] == 1
    assert winner["total_staked"] == 1_000_000
    assert winner["total_returned"] == 900_000
    assert winner["net_profit"] == -100_000
    assert rows[email_for(7202)]["net_profit"] == -100_000


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
            r["email"]: dict(r)
            for r in await conn.fetch(
                "SELECT u.email, e.rank, e.score, e.net_profit, e.total_staked"
                "  FROM leaderboard_entries e JOIN users u ON u.id = e.user_id"
            )
        }

    thin, grinder = rows[email_for(7203)], rows[email_for(7204)]
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
            r["email"]: dict(r)
            for r in await conn.fetch(
                "SELECT u.email, e.rank, e.net_profit FROM leaderboard_entries e"
                " JOIN users u ON u.id = e.user_id"
            )
        }
    assert rows[email_for(7205)]["rank"] is None
    assert rows[email_for(7205)]["net_profit"] == 49_000
    assert rows[email_for(7206)]["rank"] == 1


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
            "INSERT INTO users (email, password_hash, first_name)"
            " VALUES ('player7208@example.test', '$argon2id$stub', 'P') RETURNING id"
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


async def test_a_season_is_counted_once_more_before_it_closes(resources):
    """Whatever settled between the last count and the end of the season
    belongs to that season. The run that closes it is the last chance to say
    so — an hour's worth on a server that never stops, and everything since
    it last had a visitor on one that sleeps between them."""
    await settled_slip(7210, staked=500_000, returned=900_000, won=True)
    async with db.transaction() as conn:
        await economy.roll_up_leaderboard(conn, resources)

    late = await settled_slip(7211, staked=300_000, returned=600_000, won=True)
    await settled_slip(7210, staked=100_000, returned=0, won=False)

    async with db.transaction() as conn:
        await conn.execute("UPDATE leaderboard_seasons SET ends_at = NOW()")
    async with db.transaction() as conn:
        report = await economy.roll_up_leaderboard(conn, resources)

    assert report.seasons_finalized == 1
    async with db.acquire() as conn:
        season = await conn.fetchrow("SELECT id, is_finalized FROM leaderboard_seasons")
        entries = {
            r["user_id"]: r
            for r in await conn.fetch(
                "SELECT user_id, slips_settled, total_staked, rank FROM leaderboard_entries"
                " WHERE season_id = $1",
                season["id"],
            )
        }
    assert season["is_finalized"] is True
    assert len(entries) == 2
    assert entries[late]["slips_settled"] == 1
    assert entries[late]["rank"] is not None
    first = next(row for user, row in entries.items() if user != late)
    assert first["slips_settled"] == 2
    assert first["total_staked"] == 600_000


async def test_a_closed_season_is_left_exactly_as_it_closed(resources):
    """The last count happens once. A slip that somehow lands inside a closed
    season afterwards does not reopen it."""
    await settled_slip(7212, staked=500_000, returned=900_000, won=True)
    async with db.transaction() as conn:
        await conn.execute("UPDATE leaderboard_seasons SET ends_at = NOW()")
    async with db.transaction() as conn:
        await economy.roll_up_leaderboard(conn, resources)
        await conn.execute("UPDATE leaderboard_seasons SET ends_at = NOW()")
    async with db.transaction() as conn:
        await economy.roll_up_leaderboard(conn, resources)
    async with db.acquire() as conn:
        before = await conn.fetch("SELECT * FROM leaderboard_entries ORDER BY user_id")

    await settled_slip(7213, staked=500_000, returned=900_000, won=True)
    async with db.transaction() as conn:
        await conn.execute(
            "UPDATE predictions SET settled_at = (SELECT starts_at FROM leaderboard_seasons)"
        )
        report = await economy.roll_up_leaderboard(conn, resources)

    assert report.seasons_finalized == 0
    async with db.acquire() as conn:
        after = await conn.fetch("SELECT * FROM leaderboard_entries ORDER BY user_id")
    assert [dict(r) for r in after] == [dict(r) for r in before]


async def test_the_leaderboard_endpoint_shows_the_player_their_standing(app_client):
    auth = await authorise(app_client, 5000)
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


async def test_nothing_a_player_typed_reaches_the_leaderboard(app_client):
    """Rank 1 is the most-viewed row on the page, and a display name is free
    text a stranger chose. Only an initial is shown — never the name, and
    never the address."""
    auth = await authorise(app_client, 5000)
    await settled_slip(7211, staked=900_000, returned=2_000_000, won=True)
    async with db.acquire() as conn:
        await conn.execute(
            "UPDATE users SET first_name = 'Totally Not Appropriate' WHERE email = $1",
            email_for(7211),
        )

    async with db.transaction() as conn:
        await economy.roll_up_leaderboard(conn, get_settings())

    response = await app_client.get("/v1/economy/leaderboard", headers=auth)

    assert "Appropriate" not in response.text
    assert email_for(7211) not in response.text
    assert "player7211" not in response.text
    assert response.json()["rows"][0]["player"] == "T."


async def test_an_erased_player_leaves_the_standings(app_client):
    auth = await authorise(app_client, 5000)
    gone = await settled_slip(7212, staked=900_000, returned=2_000_000, won=True)
    async with db.transaction() as conn:
        await economy.roll_up_leaderboard(conn, get_settings())

    from backend.repositories import auth as auth_repo

    async with db.transaction() as conn:
        await auth_repo.erase_account(conn, gone)

    body = (await app_client.get("/v1/economy/leaderboard", headers=auth)).json()
    assert body["rows"] == []


# ----- the scheduled job ----------------------------------------------------


async def test_the_rollup_job_reports_what_it_did(resources):
    await settled_slip(7302, staked=500_000, returned=900_000, won=True)

    report = await economy_jobs.run_leaderboard_rollup(resources)

    assert report.ran is True
    assert report.error is None
    assert report.leaderboard["entries"] == 1


async def test_only_one_replica_runs_the_rollup(resources, monkeypatch):
    """The lease turns the other two away — provided they arrive while the
    first is still working, which a roll-up of one slip is too quick to
    guarantee. It is held open here for the reason `slowed` gives for the
    workers that talk to an upstream; this one has no upstream to slow."""
    await settled_slip(7303, staked=500_000, returned=900_000, won=True)
    roll_up = economy.roll_up_leaderboard

    async def unhurried(*args, **kwargs):
        await asyncio.sleep(OVERLAP_SECONDS)
        return await roll_up(*args, **kwargs)

    monkeypatch.setattr(economy, "roll_up_leaderboard", unhurried)

    reports = await asyncio.gather(
        economy_jobs.run_leaderboard_rollup(resources),
        economy_jobs.run_leaderboard_rollup(resources),
        economy_jobs.run_leaderboard_rollup(resources),
    )

    assert sum(1 for r in reports if r.ran) == 1


async def test_a_failing_rollup_is_contained_and_reported(resources, monkeypatch):
    """A job that throws must not take the scheduler with it."""

    async def boom(*args, **kwargs):
        raise RuntimeError("rollup exploded")

    monkeypatch.setattr(economy, "roll_up_leaderboard", boom)
    report = await economy_jobs.run_leaderboard_rollup(resources)

    assert report.ran is True
    assert "rollup exploded" in report.error
    assert await drift() == 0


async def test_the_rollup_is_scheduled_on_the_hour_in_the_economy_timezone():
    """A season closes at local midnight, so the tick that closes it has to
    land on the player's hour boundary and not the server's."""
    from backend.workers.scheduler import build_scheduler

    settings = Settings(jwt_secret="y" * 40, economy_timezone=_TEST_TZ)
    async with mock_http_client(lambda r: httpx.Response(200, json=[])) as client:
        scheduler = build_scheduler(client, settings)
        scheduler.start(paused=True)
        try:
            job = scheduler.get_job(economy_jobs.JOB_NAME)
            assert str(job.trigger.timezone) == _TEST_TZ
        finally:
            scheduler.shutdown(wait=False)


async def test_nothing_is_scheduled_that_exists_to_bring_people_back():
    """The whole schedule, by name. A charge on quiet accounts, a generator of
    short-lived better prices and a payments sweeper used to be on it."""
    from backend.workers.scheduler import build_scheduler

    settings = Settings(
        jwt_secret="y" * 40, run_discovery_on_startup=False, catch_up_on_startup=False
    )
    async with mock_http_client(lambda r: httpx.Response(200, json=[])) as client:
        scheduler = build_scheduler(client, settings)
        scheduler.start(paused=True)
        try:
            jobs = sorted(job.id for job in scheduler.get_jobs())
        finally:
            scheduler.shutdown(wait=False)

    assert jobs == [
        "leaderboard_rollup",
        "polymarket_discovery",
        "polymarket_price_sync",
        "polymarket_resolution",
    ]


async def test_the_runs_at_startup_are_the_same_jobs_and_nothing_else():
    """Starting up adds one early run of work already on the schedule. It is
    not a place for a new kind of job to arrive unannounced."""
    from backend.workers.scheduler import build_scheduler

    settings = Settings(jwt_secret="y" * 40)
    async with mock_http_client(lambda r: httpx.Response(200, json=[])) as client:
        scheduler = build_scheduler(client, settings)
        scheduler.start(paused=True)
        try:
            jobs = sorted(job.id for job in scheduler.get_jobs())
        finally:
            scheduler.shutdown(wait=False)

    assert jobs == [
        "leaderboard_rollup",
        "polymarket_discovery",
        "polymarket_discovery_startup",
        "polymarket_price_sync",
        "polymarket_resolution",
        "startup_catch_up",
    ]
