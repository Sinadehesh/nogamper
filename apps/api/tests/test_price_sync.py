"""Price sync against a real database, a real Redis and a mocked CLOB."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
from conftest import mock_http_client
from fixtures import gamma_events as fx

from backend import db
from backend.cache import prices as price_cache
from backend.repositories import markets as markets_repo
from backend.workers import polymarket_discovery as discovery
from backend.workers import polymarket_sync as sync


def clob_serving(prices: dict[str, str], *, fail: set[str] | None = None):
    """Answer /midpoint per token id; `fail` names tokens that 503."""
    calls: list[str] = []
    inflight = 0
    peak = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal inflight, peak
        token = request.url.params["token_id"]
        calls.append(token)
        inflight += 1
        peak = max(peak, inflight)
        try:
            await asyncio.sleep(0.005)
            if fail and token in fail:
                return httpx.Response(503, json={})
            return httpx.Response(200, json={"mid": prices.get(token, "0.5")})
        finally:
            inflight -= 1

    handler.calls = calls  # type: ignore[attr-defined]
    handler.peak = lambda: peak  # type: ignore[attr-defined]
    return handler


async def seed_markets(settings, count: int = 3) -> list[dict]:
    events = [
        fx.event(str(i), markets=[fx.binary_market(f"7{i:04d}", prices=["0.50", "0.50"])])
        for i in range(count)
    ]

    def gamma(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("offset", 0))
        return httpx.Response(200, json=events if offset == 0 else [])

    async with mock_http_client(gamma) as client:
        await discovery.run_discovery(client, settings)

    async with db.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM markets ORDER BY polymarket_market_id")
    return [dict(r) for r in rows]


async def test_a_run_writes_redis_postgres_and_the_snapshot_series(resources):
    markets = await seed_markets(resources, count=2)
    prices = {m["yes_token_id"]: "0.7100" for m in markets}

    async with mock_http_client(clob_serving(prices)) as client:
        report = await sync.run_price_sync(client, resources)

    assert report.prices_fetched == 2
    assert report.rows_updated == 2
    assert report.snapshots_written == 2
    assert report.failures == 0

    cached = await price_cache.read_many([m["id"] for m in markets])
    assert len(cached) == 2
    assert all(c.probability == Decimal("0.7100") for c in cached.values())
    assert all(c.source == "CLOB_MIDPOINT" for c in cached.values())

    async with db.acquire() as conn:
        rows = await conn.fetch("SELECT raw_yes_prob, price_updated_at FROM markets")
        snaps = await conn.fetch("SELECT market_id, yes_prob, source FROM market_price_snapshots")
    assert {r["raw_yes_prob"] for r in rows} == {Decimal("0.710000")}
    assert all(r["price_updated_at"] > datetime.now(UTC) - timedelta(minutes=1) for r in rows)
    assert len(snaps) == 2


async def test_cached_entries_expire_rather_than_going_stale_forever(resources):
    markets = await seed_markets(resources, count=1)
    async with mock_http_client(clob_serving({markets[0]["yes_token_id"]: "0.44"})) as client:
        await sync.run_price_sync(client, resources)

    ttl = await price_cache.get_client().ttl(price_cache.key_for(markets[0]["id"]))
    assert 0 < ttl <= resources.price_cache_ttl_seconds


async def test_fan_out_stays_within_the_concurrency_limit(resources):
    resources.price_sync_concurrency = 5
    markets = await seed_markets(resources, count=20)
    handler = clob_serving({m["yes_token_id"]: "0.5" for m in markets})

    async with mock_http_client(handler) as client:
        report = await sync.run_price_sync(client, resources)

    assert report.prices_fetched == 20
    assert handler.peak() <= 5


async def test_one_bad_market_does_not_cost_the_batch(resources):
    markets = await seed_markets(resources, count=3)
    doomed = markets[1]["yes_token_id"]
    handler = clob_serving({m["yes_token_id"]: "0.6" for m in markets}, fail={doomed})

    async with mock_http_client(handler) as client:
        report = await sync.run_price_sync(client, resources)

    assert report.prices_fetched == 2
    assert report.failures == 1
    assert report.failure_reasons == {"UpstreamUnavailable": 1}

    async with db.acquire() as conn:
        updated = await conn.fetchval("SELECT count(*) FROM markets WHERE raw_yes_prob = 0.6")
    assert updated == 2

    async with db.acquire() as conn:
        untouched = await conn.fetchval(
            "SELECT raw_yes_prob FROM markets WHERE yes_token_id = $1", doomed
        )
    assert untouched == Decimal("0.500000")


async def test_snapshots_are_throttled_to_real_movement(resources):
    """A market that has not moved should not write a row every minute."""
    markets = await seed_markets(resources, count=1)
    token = markets[0]["yes_token_id"]

    async def snapshot_count() -> int:
        async with db.acquire() as conn:
            return await conn.fetchval("SELECT count(*) FROM market_price_snapshots")

    async with mock_http_client(clob_serving({token: "0.60"})) as client:
        await sync.run_price_sync(client, resources)
    assert await snapshot_count() == 1

    async with mock_http_client(clob_serving({token: "0.60"})) as client:
        report = await sync.run_price_sync(client, resources)
    assert report.snapshots_written == 0
    assert await snapshot_count() == 1

    async with mock_http_client(clob_serving({token: "0.6051"})) as client:
        report = await sync.run_price_sync(client, resources)
    assert report.snapshots_written == 1
    assert await snapshot_count() == 2


async def test_the_heartbeat_records_a_flat_market_eventually(resources):
    markets = await seed_markets(resources, count=1)
    token = markets[0]["yes_token_id"]

    async with mock_http_client(clob_serving({token: "0.60"})) as client:
        await sync.run_price_sync(client, resources)

    async with db.transaction() as conn:
        await conn.execute(
            "UPDATE markets SET price_updated_at = NOW() - make_interval(secs => $1)",
            resources.snapshot_heartbeat_seconds + 60,
        )

    async with mock_http_client(clob_serving({token: "0.60"})) as client:
        report = await sync.run_price_sync(client, resources)

    assert report.snapshots_written == 1


async def test_expired_markets_are_locked_and_dropped_from_the_sync_set(resources):
    markets = await seed_markets(resources, count=2)
    async with db.transaction() as conn:
        await conn.execute(
            "UPDATE markets SET lock_at = NOW() - INTERVAL '1 minute' WHERE id = $1",
            markets[0]["id"],
        )

    handler = clob_serving({m["yes_token_id"]: "0.5" for m in markets})
    async with mock_http_client(handler) as client:
        report = await sync.run_price_sync(client, resources)

    assert report.markets_locked == 1
    assert report.markets_considered == 1
    assert markets[0]["yes_token_id"] not in handler.calls

    async with db.acquire() as conn:
        status = await conn.fetchval("SELECT status FROM markets WHERE id = $1", markets[0]["id"])
    assert status == "LOCKED"


async def test_a_redis_outage_still_updates_the_database(resources):
    """The cache is an optimisation. Losing it must not lose the price."""
    markets = await seed_markets(resources, count=1)
    token = markets[0]["yes_token_id"]

    await price_cache.disconnect()

    async with mock_http_client(clob_serving({token: "0.33"})) as client:
        report = await sync.run_price_sync(client, resources)

    assert report.rows_updated == 1

    async with db.acquire() as conn:
        stored = await conn.fetchval("SELECT raw_yes_prob FROM markets")
    assert stored == Decimal("0.330000")

    await price_cache.connect(resources)


async def test_only_one_replica_syncs_a_tick(resources):
    markets = await seed_markets(resources, count=2)
    handler = clob_serving({m["yes_token_id"]: "0.5" for m in markets})

    async with mock_http_client(handler) as client:
        reports = await asyncio.gather(
            sync.run_price_sync(client, resources),
            sync.run_price_sync(client, resources),
        )

    assert sum(1 for r in reports if r.ran) == 1
    assert len(handler.calls) == 2


async def test_an_empty_market_list_is_a_no_op(resources):
    async with mock_http_client(clob_serving({})) as client:
        report = await sync.run_price_sync(client, resources)

    assert report.ran is True
    assert report.markets_considered == 0
    assert report.prices_fetched == 0


def clob_that_hangs(prices: dict[str, str], *, slow: set[str], delay: float = 30.0):
    """Answer instantly for most tokens and never for the ones named in `slow`.

    A real upstream does this under load: most requests fine, a handful
    parked. The point is that the handful must not cost the batch.
    """

    async def handler(request: httpx.Request) -> httpx.Response:
        token = request.url.params["token_id"]
        if token in slow:
            await asyncio.sleep(delay)
        return httpx.Response(200, json={"mid": prices.get(token, "0.5")})

    return handler


async def test_a_slow_market_does_not_freeze_every_other_price(resources):
    """The bug, stated as the property it broke.

    One market parked on a slow upstream used to mean nothing at all was
    written — not the market, not the other two, not anything. The prices that
    *did* arrive must be written regardless.
    """
    markets = await seed_markets(resources, count=3)
    prices = {m["yes_token_id"]: "0.7100" for m in markets}
    stuck = {markets[0]["yes_token_id"]}

    resources.price_sync_deadline_seconds = 0.5

    async with mock_http_client(clob_that_hangs(prices, slow=stuck)) as client:
        report = await sync.run_price_sync(client, resources)

    assert report.abandoned == 1
    assert report.prices_fetched == 2
    assert report.rows_updated == 2, "the fast markets were held hostage by the slow one"

    async with db.acquire() as conn:
        rows = {r["id"]: r for r in await conn.fetch("SELECT * FROM markets")}

    for market in markets[1:]:
        assert rows[market["id"]]["raw_yes_prob"] == Decimal("0.7100")
        assert rows[market["id"]]["price_updated_at"] > market["price_updated_at"]


async def test_the_pass_never_outlives_its_deadline(resources):
    """A job on a 60-second tick must not run for minutes.

    Without this the pass ran until the upstream let go, the heartbeat held
    the lease throughout, and every subsequent tick was skipped.
    """
    markets = await seed_markets(resources, count=3)
    prices = {m["yes_token_id"]: "0.5" for m in markets}
    everything = {m["yes_token_id"] for m in markets}

    resources.price_sync_deadline_seconds = 0.5

    started = time.monotonic()
    async with mock_http_client(clob_that_hangs(prices, slow=everything, delay=30.0)) as client:
        report = await sync.run_price_sync(client, resources)
    elapsed = time.monotonic() - started

    assert elapsed < 5.0, f"the pass ran for {elapsed:.1f}s against a 0.5s deadline"
    assert report.abandoned == 3
    assert report.failure_reasons == {"DeadlineExceeded": 3}


async def test_the_lease_is_released_after_a_deadlined_pass(resources):
    """The recurrence people actually reported: it works, then it does not.

    A pass that abandons work must still let go, or the next tick is refused
    and the app is right back to "this price is updating" — the outage the
    deadline was added to end.
    """
    markets = await seed_markets(resources, count=2)
    prices = {m["yes_token_id"]: "0.5" for m in markets}
    resources.price_sync_deadline_seconds = 0.3

    async with mock_http_client(
        clob_that_hangs(prices, slow={m["yes_token_id"] for m in markets})
    ) as client:
        await sync.run_price_sync(client, resources)

    async with db.acquire() as conn:
        held = await conn.fetchrow("SELECT * FROM job_leases WHERE job_name = $1", sync.JOB_NAME)
    assert held is None, "a deadlined pass kept the lease and will block the next tick"


async def test_a_throttled_upstream_costs_one_deadline_not_the_retry_budget(resources):
    """Retries are paid for out of every other market's freshness.

    With the old shared budget (3 attempts, Retry-After honoured up to 30s) a
    single throttled token could burn 90 seconds — longer than the tick and
    longer than the staleness window — so the whole app went stale to retry
    one price. One attempt, no sleeps: the next tick is 60 seconds away and
    will ask again.
    """
    await seed_markets(resources, count=2)
    requests: list[str] = []

    async def throttled(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.params["token_id"])
        return httpx.Response(429, json={}, headers={"Retry-After": "30"})

    started = time.monotonic()
    async with mock_http_client(throttled) as client:
        report = await sync.run_price_sync(client, resources)
    elapsed = time.monotonic() - started

    assert len(requests) == 2, f"one attempt per market, got {len(requests)}"
    assert elapsed < 2.0, f"the pass slept on Retry-After for {elapsed:.1f}s"
    assert report.failures == 2


async def test_the_stalest_market_is_priced_first(resources):
    """Starvation, which the deadline would otherwise have introduced.

    A truncated pass ordered by lock_at prices the same head of the list every
    tick and never reaches the tail — those markets are permanently stale,
    which is the original bug wearing a smaller hat.
    """
    markets = await seed_markets(resources, count=3)
    forgotten = markets[-1]

    async with db.acquire() as conn:
        await conn.execute(
            "UPDATE markets SET price_updated_at = NOW() - INTERVAL '1 hour' WHERE id = $1",
            forgotten["id"],
        )
        syncable = await markets_repo.list_syncable_markets(conn)

    assert syncable[0].id == forgotten["id"], "the stalest market was not first in line"

    prices = {m["yes_token_id"]: "0.6" for m in markets}
    others = {m["yes_token_id"] for m in markets if m["id"] != forgotten["id"]}
    resources.price_sync_deadline_seconds = 0.5

    async with mock_http_client(clob_that_hangs(prices, slow=others)) as client:
        report = await sync.run_price_sync(client, resources)

    assert report.prices_fetched == 1
    async with db.acquire() as conn:
        row = await conn.fetchrow("SELECT raw_yes_prob FROM markets WHERE id = $1", forgotten["id"])
    assert row["raw_yes_prob"] == Decimal("0.6000"), "the stalest market was starved again"
