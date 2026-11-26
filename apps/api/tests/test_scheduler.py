"""Scheduler wiring, and the claim that workers do not block the API."""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager

import httpx
from apscheduler.triggers.interval import IntervalTrigger
from conftest import authorise, mock_http_client
from fixtures import gamma_events as fx

from backend import db
from backend.config import get_settings
from backend.workers import polymarket_discovery as discovery
from backend.workers import polymarket_sync as sync
from backend.workers.locks import lock_key
from backend.workers.scheduler import build_scheduler


@asynccontextmanager
async def started_scheduler(settings):
    """Start paused, so job defaults resolve without any job actually firing.

    APScheduler leaves jobs pending — and job_defaults unapplied — until the
    scheduler starts, so inspecting them before that tests nothing.
    """
    async with mock_http_client(lambda r: httpx.Response(200, json=[])) as client:
        scheduler = build_scheduler(client, settings)
        scheduler.start(paused=True)
        try:
            yield scheduler
        finally:
            scheduler.shutdown(wait=False)


async def test_both_jobs_are_registered_at_the_configured_cadence():
    settings = get_settings()
    async with started_scheduler(settings) as scheduler:
        jobs = {job.id: job for job in scheduler.get_jobs()}
        assert discovery.JOB_NAME in jobs
        assert sync.JOB_NAME in jobs

        price_trigger = jobs[sync.JOB_NAME].trigger
        assert isinstance(price_trigger, IntervalTrigger)
        assert price_trigger.interval.total_seconds() == settings.price_sync_interval_seconds

        discovery_trigger = jobs[discovery.JOB_NAME].trigger
        assert (
            discovery_trigger.interval.total_seconds() == settings.discovery_interval_minutes * 60
        )


async def test_a_slow_run_delays_the_next_tick_instead_of_stacking():
    """max_instances=1 plus coalesce: a run that overruns its interval must
    not spawn a second copy of itself competing for the same rows."""
    settings = get_settings()
    async with started_scheduler(settings) as scheduler:
        for job in scheduler.get_jobs():
            assert job.max_instances == 1
            assert job.coalesce is True


async def test_a_startup_run_is_scheduled_so_a_fresh_replica_is_not_empty():
    settings = get_settings()
    settings.run_discovery_on_startup = True
    async with started_scheduler(settings) as scheduler:
        assert f"{discovery.JOB_NAME}_startup" in {job.id for job in scheduler.get_jobs()}


def test_lock_keys_are_stable_distinct_and_fit_in_a_bigint():
    a, b = lock_key(discovery.JOB_NAME), lock_key(sync.JOB_NAME)
    assert a != b
    assert lock_key(discovery.JOB_NAME) == a
    assert all(-(2**63) <= k < 2**63 for k in (a, b))


async def test_the_api_keeps_serving_while_a_worker_is_mid_run(app_client):
    """The whole point of AsyncIOScheduler here: jobs share the API's event
    loop, so they must yield on I/O rather than hold it."""
    events = [fx.event(str(i), markets=[fx.binary_market(f"9{i:04d}")]) for i in range(12)]

    def gamma(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("offset", 0))
        return httpx.Response(200, json=events if offset == 0 else [])

    settings = get_settings()
    async with mock_http_client(gamma) as client:
        await discovery.run_discovery(client, settings)

    async with db.acquire() as conn:
        count = await conn.fetchval("SELECT count(*) FROM markets")
    assert count == 12

    auth = await authorise(app_client)

    async def slow_clob(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.15)
        return httpx.Response(200, json={"mid": "0.5"})

    latencies: list[float] = []

    async def poll_api() -> None:
        for _ in range(8):
            started = time.monotonic()
            response = await app_client.get("/v1/markets?limit=5", headers=auth)
            latencies.append(time.monotonic() - started)
            assert response.status_code == 200
            await asyncio.sleep(0.02)

    async with mock_http_client(slow_clob) as client:
        worker = asyncio.create_task(sync.run_price_sync(client, settings))
        await poll_api()
        report = await worker

    assert report.prices_fetched == 12
    assert max(latencies) < 0.1, f"API stalled during the worker run: {latencies}"
