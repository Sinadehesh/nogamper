"""The endpoint that answers "is it the database, the app, or upstream".

Written because the same symptom — every market reading "this price is
updating" — has now had two entirely different causes that presented
identically: a Postgres advisory lock stranded behind a session pooler, then a
price sync pass with no deadline whose lease heartbeat held the job shut. Both
times the app told players it was updating and told the operator nothing.

What is under test here is the *mapping*, not the numbers. Each state of the
world has to produce the verdict that sends somebody to the right place, and
these are the states worth distinguishing — an empty feed, a job that will not
finish, a job nobody is running, an upstream returning nothing, and a cache
that has lost prices the database still holds.

A wrong verdict is worse than no verdict: it sends the operator to the wrong
layer with false confidence, which is exactly how the second outage cost two
days.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from conftest import TEST_ADMIN_TELEGRAM_ID, authorise

from backend import db
from backend.repositories import diagnostics

DIAG = "/v1/admin/diagnostics"


async def seed_market(*, priced_secs_ago: int = 0, status: str = "ACTIVE") -> uuid.UUID:
    """One market with a price of a chosen age, without running discovery."""
    async with db.transaction() as conn:
        event_id = await conn.fetchval(
            """
            INSERT INTO market_events (polymarket_event_id, slug, title, title_source,
                                       category, end_date)
            VALUES ($1, $1, 'e', 'e', 'Crypto', NOW() + INTERVAL '10 days')
            RETURNING id
            """,
            f"evt-{uuid.uuid4()}",
        )
        return await conn.fetchval(
            """
            INSERT INTO markets (event_id, polymarket_market_id, condition_id, question,
                                 category, yes_token_id, no_token_id, raw_yes_prob,
                                 lock_at, end_date, question_source, status,
                                 price_updated_at)
            VALUES ($1, $2, $2, 'q?', 'Crypto', $2 || '-y', $2 || '-n', 0.5,
                    NOW() + INTERVAL '9 days', NOW() + INTERVAL '10 days', 'q?',
                    $3::market_status, NOW() - make_interval(secs => $4))
            RETURNING id
            """,
            event_id,
            f"mkt-{uuid.uuid4()}",
            status,
            float(priced_secs_ago),
        )


async def hold_lease(job: str, *, held_for_secs: float) -> None:
    async with db.transaction() as conn:
        await conn.execute(
            """
            INSERT INTO job_leases (job_name, holder, acquired_at, expires_at, holder_note)
            VALUES ($1, gen_random_uuid(), NOW() - make_interval(secs => $2),
                    NOW() + INTERVAL '2 minutes', 'test-worker:1')
            """,
            job,
            held_for_secs,
        )


async def warm_cache(*market_ids) -> None:
    """Put the markets in Redis, as a real sync pass would.

    Without this a directly-seeded market is fresh in Postgres and absent from
    the cache, which is a state the endpoint deliberately treats as benign —
    so a test meaning "everything is fine" has to actually make it fine.
    """
    from decimal import Decimal

    from backend.cache import prices as price_cache

    await price_cache.write_many(
        [(mid, Decimal("0.5"), "CLOB_MIDPOINT", datetime.now(UTC)) for mid in market_ids],
        ttl_seconds=300,
    )


async def diag(client, headers):
    return (await client.get(DIAG, headers=headers)).json()


async def test_a_player_cannot_read_the_diagnostics(app_client):
    """It reports market counts, job holders and container names. None of that
    is a player's business, and the holder note names infrastructure."""
    headers = await authorise(app_client, telegram_id=4242)
    assert (await app_client.get(DIAG, headers=headers)).status_code == 404


async def test_an_empty_database_points_at_discovery(app_client):
    """The very first launch failure: the app came up with no markets at all
    and the feed was simply empty."""
    headers = await authorise(app_client, telegram_id=TEST_ADMIN_TELEGRAM_ID)
    body = await diag(app_client, headers)

    assert body["layer"] == "discovery"
    assert "no markets at all" in body["advice"]


async def test_everything_locked_and_nothing_active_points_at_discovery(app_client):
    """Distinct from an empty database, and a different fix: markets were
    ingested once and have all since expired, so discovery has stopped keeping
    up rather than never having run."""
    headers = await authorise(app_client, telegram_id=TEST_ADMIN_TELEGRAM_ID)
    await seed_market(status="LOCKED")

    body = await diag(app_client, headers)

    assert body["layer"] == "discovery"
    assert body["markets_locked"] == 1
    assert body["markets_active"] == 0


async def test_a_job_holding_its_lease_too_long_points_at_the_worker(app_client):
    """The second outage, and the one that cost the most.

    The lease is working exactly as designed; the job inside it is not
    finishing. That distinction is the whole finding, so the advice says it in
    as many words rather than leaving somebody to conclude "stuck lock" again.
    """
    headers = await authorise(app_client, telegram_id=TEST_ADMIN_TELEGRAM_ID)
    await seed_market(priced_secs_ago=1800)
    await hold_lease("polymarket_price_sync", held_for_secs=1800)

    body = await diag(app_client, headers)

    assert body["layer"] == "worker"
    assert "not a stuck lock" in body["advice"]
    assert body["leases"][0]["job_name"] == "polymarket_price_sync"
    assert body["leases"][0]["held_for_seconds"] >= 1800


async def test_stale_prices_with_no_lease_at_all_points_at_the_worker(app_client):
    """Nothing is running the job — a worker that never started, or
    WORKERS_ENABLED left false. Reads differently from a job that is running
    and stuck, and the fix is somewhere else entirely."""
    headers = await authorise(app_client, telegram_id=TEST_ADMIN_TELEGRAM_ID)
    await seed_market(priced_secs_ago=1800)

    body = await diag(app_client, headers)

    assert body["layer"] == "worker"
    assert "no job holds a lease" in body["advice"]
    assert body["leases"] == []


async def test_a_running_job_that_lands_no_prices_points_upstream(app_client):
    """The job ticks, the lease cycles normally, and still nothing arrives.

    That is the CLOB returning nothing usable, which is neither the database
    nor the app — and is the case that would otherwise be misread as either.
    """
    headers = await authorise(app_client, telegram_id=TEST_ADMIN_TELEGRAM_ID)
    await seed_market(priced_secs_ago=1800)
    await hold_lease("polymarket_price_sync", held_for_secs=5)

    body = await diag(app_client, headers)

    assert body["layer"] == "upstream"
    assert "getting nothing usable" in body["advice"]


async def test_fresh_prices_report_healthy(app_client):
    headers = await authorise(app_client, telegram_id=TEST_ADMIN_TELEGRAM_ID)
    await warm_cache(await seed_market(priced_secs_ago=5))

    body = await diag(app_client, headers)

    assert body["layer"] == "healthy"
    assert body["markets_fresh"] == 1
    assert body["markets_stale"] == 0


async def test_a_partly_truncated_pass_reads_as_degraded_not_broken(app_client):
    """Some markets past the window while the newest is current is the
    deadline doing its job under load, not a fault. Calling it an outage would
    train the operator to ignore this endpoint."""
    headers = await authorise(app_client, telegram_id=TEST_ADMIN_TELEGRAM_ID)
    await warm_cache(await seed_market(priced_secs_ago=5), await seed_market(priced_secs_ago=600))

    body = await diag(app_client, headers)

    assert body["layer"] == "degraded"
    assert body["markets_fresh"] == 1
    assert body["markets_stale"] == 1
    assert "truncating at its deadline" in body["advice"]


async def test_a_cold_cache_on_fresh_markets_is_not_called_a_fault(app_client):
    """A market discovered thirty seconds ago is fresh in Postgres and absent
    from Redis, because discovery stamps price_updated_at on insert and the
    sync does not reach it until the next tick.

    Ranking that as a cache fault would fire on every deploy and teach the
    operator to ignore this endpoint — so it reads as degraded, and the advice
    says outright that it is harmless if the markets are new.
    """
    headers = await authorise(app_client, telegram_id=TEST_ADMIN_TELEGRAM_ID)
    await seed_market(priced_secs_ago=5)

    body = await diag(app_client, headers)

    assert body["layer"] == "degraded"
    assert body["cache_hits"] == 0
    assert "Harmless if" in body["advice"]


def _health(**overrides) -> diagnostics.PriceHealth:
    base = dict(
        markets_total=10,
        markets_active=10,
        markets_locked=0,
        markets_fresh=10,
        newest_price_at=datetime.now(UTC),
        oldest_price_at=datetime.now(UTC) - timedelta(seconds=30),
        seconds_since_newest=5.0,
        cache_reachable=True,
        cache_hits=10,
        cache_sampled=10,
        leases=[],
    )
    return diagnostics.PriceHealth(**{**base, **overrides})


def test_an_unreachable_cache_is_named_even_when_the_database_is_fine():
    """The failure that looks worst and is least serious: every price current
    in Postgres, Redis down, and the app flagging everything stale on the
    fallback path."""
    layer, advice = diagnostics.explain(
        _health(cache_reachable=False, cache_hits=0), staleness_seconds=90
    )
    assert layer == "cache"
    assert "Redis is not answering" in advice


def test_a_reachable_but_empty_cache_is_reported_without_being_alarming():
    """Redis answers and holds nothing. Either the cache write is failing or
    the markets were just discovered, and the endpoint cannot tell which — so
    it says both rather than guessing, and does not claim an outage."""
    layer, advice = diagnostics.explain(_health(cache_hits=0), staleness_seconds=90)
    assert layer == "degraded"
    assert "price cache write failed" in advice
    assert "Harmless if" in advice


def test_a_real_outage_outranks_a_cold_cache():
    """Ordering, stated as a test. A stuck job with an empty cache is a stuck
    job — reporting the cache would send the operator to the wrong layer, which
    is exactly how the last outage cost two days."""
    stuck = diagnostics.JobLease("polymarket_price_sync", "srv-1", 1200.0, 60.0)
    layer, _ = diagnostics.explain(
        _health(cache_hits=0, seconds_since_newest=1800.0, markets_fresh=0, leases=[stuck]),
        staleness_seconds=90,
    )
    assert layer == "worker"


def test_the_runaway_threshold_matches_the_lock_module():
    """Two places decide "this job has been running too long" — the heartbeat
    that logs it and this endpoint that reports it. They must agree, or the
    operator reads one number in the log and a different verdict here."""
    from backend.workers import locks

    assert diagnostics.RUNAWAY_SECONDS == locks.RUNAWAY_AFTER_SECONDS


async def record_run(job: str, *, outcome: str = "ok", detail: dict, seconds: float = 12.0) -> None:
    from datetime import timedelta

    from backend.workers import runlog

    await runlog.record(
        job,
        started_at=datetime.now(UTC) - timedelta(seconds=seconds),
        seconds=seconds,
        outcome=outcome,
        detail=detail,
    )


async def test_the_failure_census_reaches_the_operator(app_client):
    """The sentence that has been missing every time.

    "No price has landed" says a pass is failing. "40x ReadTimeout" says what
    to do about it, and that number lived only in a log line.
    """
    headers = await authorise(app_client, telegram_id=TEST_ADMIN_TELEGRAM_ID)
    await seed_market(priced_secs_ago=1800)
    await hold_lease("polymarket_price_sync", held_for_secs=5)
    await record_run(
        "polymarket_price_sync",
        detail={
            "markets_considered": 42,
            "prices_fetched": 0,
            "failure_reasons": {"ReadTimeout": 40, "HTTPStatusError": 2},
        },
    )

    body = await diag(app_client, headers)

    assert body["layer"] == "upstream"
    assert "40x ReadTimeout" in body["advice"]
    assert "0 of 42" in body["advice"]

    run = next(r for r in body["runs"] if r["job_name"] == "polymarket_price_sync")
    assert run["outcome"] == "ok"
    assert run["detail"]["failure_reasons"]["ReadTimeout"] == 40


async def test_a_job_that_raised_says_so_rather_than_going_quiet(app_client):
    """A run that raises is the one most worth having a record of, and it is
    the one a report-shaped log line never covered."""
    headers = await authorise(app_client, telegram_id=TEST_ADMIN_TELEGRAM_ID)
    await seed_market(priced_secs_ago=1800)
    await hold_lease("polymarket_price_sync", held_for_secs=5)
    await record_run(
        "polymarket_price_sync",
        outcome="error",
        detail={"error": "ConnectError: [Errno -2] Name or service not known"},
    )

    body = await diag(app_client, headers)

    assert "The last pass raised" in body["advice"]
    assert "Name or service not known" in body["advice"]


async def test_never_having_finished_a_pass_is_said_out_loud(app_client):
    """Distinct from a failing pass and a different fix: nothing has completed
    since the container started, so there is no census to show."""
    headers = await authorise(app_client, telegram_id=TEST_ADMIN_TELEGRAM_ID)
    await seed_market(priced_secs_ago=1800)
    await hold_lease("polymarket_price_sync", held_for_secs=5)

    body = await diag(app_client, headers)

    assert "No run has been recorded yet" in body["advice"]
    assert body["runs"] == []


async def test_a_stuck_job_reports_what_its_last_completed_pass_did(app_client):
    """The eighty-six minute discovery run. The lease said which job; only the
    report says what it had been doing when it last got through."""
    headers = await authorise(app_client, telegram_id=TEST_ADMIN_TELEGRAM_ID)
    await seed_market(priced_secs_ago=1800)
    await hold_lease("polymarket_discovery", held_for_secs=5200)
    await record_run(
        "polymarket_discovery",
        outcome="deadline",
        detail={"error": "deadline_exceeded"},
        seconds=240.0,
    )

    body = await diag(app_client, headers)

    assert body["layer"] == "worker"
    assert "abandoned at its deadline" in body["advice"]
