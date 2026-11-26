"""APScheduler wiring.

`max_instances=1` plus `coalesce=True` means a slow run delays the next tick
rather than stacking on top of it, and a scheduler that was paused catches up
with one run instead of a backlog. The advisory lock in `locks.py` covers the
other direction: several replicas ticking at the same moment.
"""

from __future__ import annotations

import logging

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from ..config import Settings
from . import economy as economy_jobs
from . import invoice_sweeper, resolution
from . import polymarket_discovery as discovery
from . import polymarket_sync as sync
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
        recorded(invoice_sweeper.JOB_NAME, invoice_sweeper.sweep_invoices),
        trigger=IntervalTrigger(minutes=settings.invoice_sweep_interval_minutes, jitter=60),
        args=(client, settings),
        id=invoice_sweeper.JOB_NAME,
        name="Reconcile dropped payments and expire invoices",
    )

    scheduler.add_job(
        recorded(economy_jobs.DAILY_JOB_NAME, economy_jobs.run_daily_economy),
        trigger=CronTrigger(hour=0, minute=0, timezone=settings.economy_timezone),
        args=(settings,),
        id=economy_jobs.DAILY_JOB_NAME,
        name="Daily economy (decay + leaderboard)",
    )

    scheduler.add_job(
        recorded(economy_jobs.BOOST_JOB_NAME, economy_jobs.run_boost_generation),
        trigger=IntervalTrigger(minutes=settings.boost_generation_interval_minutes, jitter=180),
        args=(settings,),
        id=economy_jobs.BOOST_JOB_NAME,
        name="Odds boost generation",
    )

    if settings.run_discovery_on_startup:
        scheduler.add_job(
            recorded(discovery.JOB_NAME, discovery.run_discovery),
            args=(client, settings),
            id=f"{discovery.JOB_NAME}_startup",
            name="Polymarket discovery (startup)",
        )

    return scheduler
