"""APScheduler wiring.

`max_instances=1` plus `coalesce=True` means a slow run delays the next tick
rather than stacking on top of it, and a scheduler that was paused catches up
with one run instead of a backlog. The lease in `locks.py` covers the other
direction: several replicas ticking at the same moment.
"""

from __future__ import annotations

import logging

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from ..config import Settings
from . import economy as economy_jobs
from . import polymarket_discovery as discovery
from . import polymarket_sync as sync
from . import resolution
from .runlog import recorded

logger = logging.getLogger(__name__)


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
            recorded(discovery.JOB_NAME, discovery.run_discovery),
            args=(client, settings),
            id=f"{discovery.JOB_NAME}_startup",
            name="Polymarket discovery (startup)",
        )

    return scheduler
