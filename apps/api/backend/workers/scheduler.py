"""APScheduler wiring.

`max_instances=1` plus `coalesce=True` means a slow run delays the next tick
rather than stacking on top of it, and a scheduler that was paused catches up
with one run instead of a backlog. The lease in `locks.py` covers the other
direction: several replicas ticking at the same moment.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from ..config import Settings
from . import economy as economy_jobs
from . import polymarket_discovery as discovery
from . import polymarket_sync as sync
from . import resolution
from .runlog import did_run, recorded

logger = logging.getLogger(__name__)

CATCH_UP_JOB_ID = "startup_catch_up"

START_UP_TRIES = 8
START_UP_PAUSE_SECONDS = 30.0
"""How long a start-up job waits for its turn: three and a half minutes in
all. A lease outlives a holder that was stopped mid-run by up to two
(locks.LEASE_SECONDS), so this is long enough to outlast one, with room for
the old container's last seconds before it is stopped."""


async def when_free(
    name: str,
    job: Callable[..., Awaitable[Any]],
    *args: object,
    tries: int = START_UP_TRIES,
    pause: float = START_UP_PAUSE_SECONDS,
) -> Any:
    """Run a start-up job, waiting its turn if another replica is mid-run.

    A deploy starts the new container while the old one is still alive, and
    the old one is often in the middle of exactly these jobs: it may itself
    have been woken a moment ago, by the same push, and be reading the market
    for the first time in hours. Turned away once and never tried again, the
    new container went without its first read until the hourly tick — which a
    server that goes back to sleep first never reaches. That is how a release
    that added a column came up with every row of it empty.

    So a start-up job that finds the lease held waits and asks again. The
    ticks do not need this: they come round by themselves.
    """
    report: Any = None
    for attempt in range(1, tries + 1):
        report = await recorded(name, job)(*args)
        if did_run(report):
            return report
        if attempt < tries:
            logger.info(
                "start-up %s: another replica is mid-run; asking again in %.0fs (%d of %d)",
                name,
                pause,
                attempt,
                tries,
            )
            await asyncio.sleep(pause)

    logger.warning(
        "start-up %s did not get its turn in %.0fs and is left to its next tick",
        name,
        pause * (tries - 1),
    )
    return report


async def catch_up(client: httpx.AsyncClient, settings: Settings) -> None:
    """One run of each job that keeps the game current, in order, at startup.

    For a process that has not been running. Left to their own ticks, prices
    would stay older than the staleness window for the first minute, finished
    forecasts would wait five to settle, and the standings would wait for the
    hour to turn — which a server that goes back to sleep first never sees.

    In order because each feeds the next: nothing can be forecast against a
    stale price, settlement is what changes the standings, and the rollup
    counts what settlement has just written. A step that fails is logged and
    the others still run. Each takes its own lease, so a tick that arrives in
    the middle of this is turned away rather than doubled — and a step that is
    itself turned away, because the container being replaced is still running
    it, waits its turn before the next one starts (`when_free`).
    """
    steps = (
        (sync.JOB_NAME, sync.run_price_sync, (client, settings)),
        (resolution.JOB_NAME, resolution.run_resolution, (client, settings)),
        (economy_jobs.JOB_NAME, economy_jobs.run_leaderboard_rollup, (settings,)),
    )
    for name, job, args in steps:
        try:
            await when_free(name, job, *args)
        except Exception:  # noqa: BLE001 - one step failing must not skip the rest
            logger.exception("startup catch-up: %s failed", name)


def build_scheduler(client: httpx.AsyncClient, settings: Settings) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(
        timezone="UTC",
        job_defaults={
            "max_instances": 1,
            "coalesce": True,
            "misfire_grace_time": 30,
        },
    )

    scheduler.add_job(
        recorded(discovery.JOB_NAME, discovery.run_discovery),
        trigger=IntervalTrigger(
            minutes=settings.discovery_interval_minutes,
            jitter=120,
        ),
        args=(client, settings),
        id=discovery.JOB_NAME,
        name="Polymarket discovery (Gamma)",
    )

    scheduler.add_job(
        recorded(sync.JOB_NAME, sync.run_price_sync),
        trigger=IntervalTrigger(seconds=settings.price_sync_interval_seconds),
        args=(client, settings),
        id=sync.JOB_NAME,
        name="Polymarket price sync (CLOB)",
    )

    scheduler.add_job(
        recorded(resolution.JOB_NAME, resolution.run_resolution),
        trigger=IntervalTrigger(minutes=settings.resolution_interval_minutes),
        args=(client, settings),
        id=resolution.JOB_NAME,
        name="Polymarket resolution and settlement",
    )

    scheduler.add_job(
        recorded(economy_jobs.JOB_NAME, economy_jobs.run_leaderboard_rollup),
        # Hourly, on the hour in the economy timezone. It was once a day while
        # it shared a job with a nightly charge; on its own there is no reason
        # for standings to be up to a day behind the slips they summarise, and
        # the midnight run is still the one that closes a finished season.
        trigger=CronTrigger(minute=0, timezone=settings.economy_timezone),
        args=(settings,),
        id=economy_jobs.JOB_NAME,
        name="Leaderboard rollup",
    )

    if settings.run_discovery_on_startup:
        scheduler.add_job(
            when_free,
            args=(discovery.JOB_NAME, discovery.run_discovery, client, settings),
            id=f"{discovery.JOB_NAME}_startup",
            name="Polymarket discovery (startup)",
        )

    if settings.catch_up_on_startup:
        scheduler.add_job(
            catch_up,
            args=(client, settings),
            id=CATCH_UP_JOB_ID,
            name="Catch up after a start (prices, settlement, standings)",
        )

    return scheduler
