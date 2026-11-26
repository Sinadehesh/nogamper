"""Price sync worker — CLOB API into Redis, Postgres and the snapshot series.

Runs every 60 seconds. Fetches a live probability for every ACTIVE market
under a bounded-concurrency fan-out, then writes the results in three places
with different jobs to do:

  * Redis    — what the API serves, with a TTL so it cannot go stale silently.
  * markets  — the durable fallback when Redis is cold or down.
  * snapshots— the time series the boost engine and dispute handling read.

One market failing must not cost the batch, so failures are collected rather
than raised, and a run that loses most of its fetches says so loudly.

**A pass is bounded in time, and that is the point.** This job runs on a
60-second tick against a 90-second staleness window, so a pass that runs longer
than its own tick is not slow — it is an outage. It used to be possible: the
fan-out waited for the slowest fetch and `apply_prices` ran only once, at the
end, so a single parked request froze `price_updated_at` for *every* market at
once and the whole app answered "this price is updating". The lease heartbeat
kept extending throughout, so every later tick was refused too, and it looked
exactly like the wedged advisory lock that lease had just replaced.

Now the fan-out gets `price_sync_deadline_seconds` and no more. What finished
is written; what did not is cancelled and picked up next tick, stalest first.
Prices also get their own one-attempt retry budget, because a retry here is
paid for out of every other market's freshness. See config.py for the numbers
for the measurements.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Coroutine
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

import httpx

from .. import db
from ..cache import prices as price_cache
from ..clients import clob
from ..config import Settings
from ..repositories import markets as markets_repo
from .locks import single_flight

logger = logging.getLogger(__name__)

JOB_NAME = "polymarket_price_sync"

_UNHEALTHY_SUCCESS_RATE = 0.5


@dataclass
class SyncReport:
    ran: bool
    duration_seconds: float = 0.0
    markets_considered: int = 0
    prices_fetched: int = 0
    failures: int = 0
    rows_updated: int = 0
    snapshots_written: int = 0
    markets_locked: int = 0
    abandoned: int = 0
    failure_reasons: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class _Fetched:
    market: markets_repo.SyncableMarket
    price: clob.TokenPrice


async def _fetch_one(
    client: httpx.AsyncClient,
    settings: Settings,
    market: markets_repo.SyncableMarket,
    semaphore: asyncio.Semaphore,
) -> _Fetched | Exception:
    async with semaphore:
        try:
            price = await clob.fetch_token_price(client, market.yes_token_id, settings)
        except Exception as exc:  # noqa: BLE001 - one bad market must not fail the batch
            return exc
        return _Fetched(market=market, price=price)


async def _gather_within_deadline(
    coros: list[Coroutine[object, object, _Fetched | Exception]],
    deadline_seconds: float,
) -> tuple[list[_Fetched], dict[str, int], int]:
    """Run the fan-out, but never for longer than `deadline_seconds`.

    This is the difference between a degraded pass and an outage.

    `asyncio.gather` is all-or-nothing: it returns when the slowest fetch
    returns, however long that takes. That is what turned a slow upstream into
    "this price is updating" across the whole app — the pass ran for minutes,
    `apply_prices` never got to run, so *no* market's price_updated_at advanced
    and every one of them aged past the staleness window. Meanwhile the lease
    heartbeat kept extending, so every later tick was refused too, and it looked
    from outside exactly like the old wedged advisory lock.

    `asyncio.wait` returns what finished and hands back what did not, so a slow
    upstream costs only the markets it was slow about. The rest are written and
    the next tick picks up the remainder — which it will, because
    list_syncable_markets serves the stalest first.
    """
    tasks = [asyncio.create_task(coro) for coro in coros]
    done, pending = await asyncio.wait(tasks, timeout=deadline_seconds)

    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)

    fetched: list[_Fetched] = []
    failure_reasons: dict[str, int] = {}

    def note(reason: str) -> None:
        failure_reasons[reason] = failure_reasons.get(reason, 0) + 1

    for task in done:
        try:
            outcome = task.result()
        except Exception as exc:  # noqa: BLE001 - a fetch that escaped _fetch_one
            note(type(exc).__name__)
            continue
        if isinstance(outcome, Exception):
            note(type(outcome).__name__)
        else:
            fetched.append(outcome)

    if pending:
        failure_reasons["DeadlineExceeded"] = len(pending)

    return fetched, failure_reasons, len(pending)


def _should_snapshot(
    market: markets_repo.SyncableMarket, probability: Decimal, settings: Settings, now: datetime
) -> bool:
    """Snapshot on a real move, or on a heartbeat if nothing has moved.

    Writing every market every minute is ~300k near-identical rows a day. The
    threshold keeps the series readable; the heartbeat keeps it continuous, so
    a flat market still has evidence it was flat.
    """
    if abs(probability - market.raw_yes_prob) >= Decimal(str(settings.snapshot_min_delta)):
        return True
    age = (now - market.price_updated_at).total_seconds()
    return age >= settings.snapshot_heartbeat_seconds


async def run_price_sync(client: httpx.AsyncClient, settings: Settings) -> SyncReport:
    async with single_flight(JOB_NAME) as owner:
        if not owner:
            return SyncReport(ran=False)

        started = time.monotonic()

        async with db.transaction() as conn:
            locked = await markets_repo.lock_expired_markets(conn)
            syncable = await markets_repo.list_syncable_markets(
                conn, limit=settings.price_sync_max_markets
            )
            backlog = await markets_repo.count_active_markets(conn)

        if not syncable:
            logger.warning(
                "price sync found no ACTIVE markets to price; "
                "every market will read as stale within %ss",
                settings.price_staleness_seconds,
            )
            return SyncReport(
                ran=True,
                duration_seconds=round(time.monotonic() - started, 3),
                markets_locked=locked,
            )

        if backlog > settings.price_sync_max_markets:
            logger.error(
                "price sync is budgeted for %d markets but %d are ACTIVE; the surplus "
                "cannot be refreshed inside the %ss staleness window, so most of the app "
                "will read as updating however well this job runs. Discovery retires the "
                "surplus on its next run — if this persists, lower DISCOVERY_MAX_PAGES.",
                settings.price_sync_max_markets,
                backlog,
                settings.price_staleness_seconds,
            )

        semaphore = asyncio.Semaphore(settings.price_sync_concurrency)
        fetched, failure_reasons, abandoned = await _gather_within_deadline(
            [_fetch_one(client, settings, market, semaphore) for market in syncable],
            settings.price_sync_deadline_seconds,
        )

        now = datetime.now(UTC)

        cache_entries: list[tuple[uuid.UUID, Decimal, str, datetime]] = []
        db_updates: list[tuple[uuid.UUID, Decimal]] = []
        snapshots: list[tuple[uuid.UUID, Decimal, str]] = []

        for item in fetched:
            probability = item.price.probability
            cache_entries.append(
                (item.market.id, probability, item.price.source, item.price.fetched_at)
            )
            db_updates.append((item.market.id, probability))
            if _should_snapshot(item.market, probability, settings, now):
                snapshots.append((item.market.id, probability, item.price.source))

        try:
            await price_cache.write_many(
                cache_entries, ttl_seconds=settings.price_cache_ttl_seconds
            )
        except Exception:
            logger.exception("price cache write failed; database still updated")

        async with db.transaction() as conn:
            rows_updated = await markets_repo.apply_prices(conn, db_updates)
            snapshots_written = await markets_repo.record_snapshots(conn, snapshots)

        report = SyncReport(
            ran=True,
            duration_seconds=round(time.monotonic() - started, 3),
            markets_considered=len(syncable),
            prices_fetched=len(fetched),
            failures=len(syncable) - len(fetched),
            rows_updated=rows_updated,
            snapshots_written=snapshots_written,
            markets_locked=locked,
            abandoned=abandoned,
            failure_reasons=failure_reasons,
        )

        success_rate = len(fetched) / len(syncable)
        if success_rate < _UNHEALTHY_SUCCESS_RATE:
            logger.error("price sync degraded: %s", asdict(report))
        else:
            logger.info("price sync complete: %s", asdict(report))

        if report.duration_seconds > settings.price_staleness_seconds:
            logger.error(
                "price sync took %.0fs for %d markets, past the %ss staleness window, "
                "with a %.0fs fan-out deadline. The fetches are capped, so the overrun "
                "is in the writes: check the database (DB_POOL_MAX starves a worker "
                "running six jobs) and Redis. Failures: %s",
                report.duration_seconds,
                report.markets_considered,
                settings.price_staleness_seconds,
                settings.price_sync_deadline_seconds,
                failure_reasons or "none",
            )
        elif abandoned:
            logger.warning(
                "price sync hit its %.0fs deadline with %d of %d markets unfetched; "
                "they are stalest-first so the next tick takes them first",
                settings.price_sync_deadline_seconds,
                abandoned,
                report.markets_considered,
            )

        return report
