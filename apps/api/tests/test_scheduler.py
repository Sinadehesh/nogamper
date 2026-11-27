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
from backend.workers import economy as economy_jobs
from backend.workers import polymarket_discovery as discovery
from backend.workers import polymarket_sync as sync
from backend.workers import resolution
from backend.workers import scheduler as scheduler_module
from backend.workers.locks import lock_key, single_flight
from backend.workers.runlog import did_run
from backend.workers.scheduler import CATCH_UP_JOB_ID, build_scheduler, catch_up, when_free


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


async def test_a_start_also_schedules_one_catch_up_unless_it_is_switched_off():
    settings = get_settings()
    settings.catch_up_on_startup = True
    async with started_scheduler(settings) as scheduler:
        job = scheduler.get_job(CATCH_UP_JOB_ID)
        assert job is not None
        # No trigger of its own: it runs once, as soon as the scheduler does.
        assert not isinstance(job.trigger, IntervalTrigger)

    settings.catch_up_on_startup = False
    async with started_scheduler(settings) as scheduler:
        assert scheduler.get_job(CATCH_UP_JOB_ID) is None
    settings.catch_up_on_startup = True


def _stand_ins(monkeypatch, ran: list[str], *, failing: str | None = None):
    """Replace the three jobs with ones that only say they were called."""

    def stand_in(name: str):
        async def job(*args, **kwargs):
            ran.append(name)
            if name == failing:
                raise RuntimeError(f"{name} fell over")
            return {"ran": True}

        return job

    monkeypatch.setattr(sync, "run_price_sync", stand_in("prices"))
    monkeypatch.setattr(resolution, "run_resolution", stand_in("settlement"))
    monkeypatch.setattr(economy_jobs, "run_leaderboard_rollup", stand_in("standings"))


async def test_catching_up_runs_prices_then_settlement_then_standings(resources, monkeypatch):
    """Each feeds the next. Standings counted before settlement has run would
    be the standings from before the server went to sleep."""
    ran: list[str] = []
    _stand_ins(monkeypatch, ran)

    async with mock_http_client(lambda r: httpx.Response(200, json=[])) as client:
        await catch_up(client, resources)

    assert ran == ["prices", "settlement", "standings"]
    async with db.acquire() as conn:
        recorded = await conn.fetch("SELECT job_name, outcome FROM job_runs ORDER BY job_name")
    assert {(r["job_name"], r["outcome"]) for r in recorded} == {
        (economy_jobs.JOB_NAME, "ok"),
        (sync.JOB_NAME, "ok"),
        (resolution.JOB_NAME, "ok"),
    }


async def test_one_step_failing_does_not_cost_the_steps_after_it(resources, monkeypatch):
    ran: list[str] = []
    _stand_ins(monkeypatch, ran, failing="prices")

    async with mock_http_client(lambda r: httpx.Response(200, json=[])) as client:
        await catch_up(client, resources)

    assert ran == ["prices", "settlement", "standings"]
    async with db.acquire() as conn:
        outcome = await conn.fetchval(
            "SELECT outcome FROM job_runs WHERE job_name = $1", sync.JOB_NAME
        )
    assert outcome == "error"


async def test_catching_up_on_an_empty_database_does_nothing_and_does_not_fail(resources):
    """The first start of a new deployment: no questions yet, nothing to
    settle, nobody to rank. The real jobs, against a source that has nothing."""
    async with mock_http_client(lambda r: httpx.Response(200, json=[])) as client:
        await catch_up(client, resources)

    async with db.acquire() as conn:
        outcomes = {
            r["job_name"]: r["outcome"]
            for r in await conn.fetch("SELECT job_name, outcome FROM job_runs")
        }
    assert outcomes == {
        economy_jobs.JOB_NAME: "ok",
        sync.JOB_NAME: "ok",
        resolution.JOB_NAME: "ok",
    }


# ----- a start-up job waits its turn -----------------------------------------------
#
# A deploy starts the new container while the old one is still alive, often in
# the middle of these very jobs. A start-up job that was turned away once and
# never asked again left a new release without its first read of the market
# until the hourly tick — which a server that sleeps first never reaches.


def _turned_away(times: int, calls: list[int]):
    """A job another replica holds for its first `times` askings."""

    async def job(*args, **kwargs):
        calls.append(len(calls) + 1)
        return sync.SyncReport(ran=len(calls) > times)

    return job


async def test_a_start_up_job_that_is_turned_away_asks_again_until_it_runs(resources):
    calls: list[int] = []

    report = await when_free("prices", _turned_away(2, calls), tries=5, pause=0)

    assert calls == [1, 2, 3]
    assert report.ran is True


async def test_a_start_up_job_that_never_gets_its_turn_gives_up_quietly(resources, caplog):
    """It is left to its next tick. Not an error, and not a loop."""
    calls: list[int] = []

    with caplog.at_level("WARNING"):
        report = await when_free("prices", _turned_away(99, calls), tries=3, pause=0)

    assert calls == [1, 2, 3]
    assert report.ran is False
    assert "left to its next tick" in caplog.text


async def test_a_job_that_runs_first_time_is_not_asked_twice(resources):
    calls: list[int] = []

    await when_free("prices", _turned_away(0, calls), tries=5, pause=0)

    assert calls == [1]


async def test_catching_up_waits_for_prices_before_it_settles(resources, monkeypatch):
    """The order still holds when the first step has to wait: nothing is
    settled, or counted, against prices the old container was still reading."""
    monkeypatch.setattr(scheduler_module, "START_UP_PAUSE_SECONDS", 0)
    ran: list[str] = []
    _stand_ins(monkeypatch, ran)
    asked: list[int] = []

    async def prices(*args, **kwargs):
        asked.append(1)
        ran.append("prices" if len(asked) > 1 else "prices turned away")
        return sync.SyncReport(ran=len(asked) > 1)

    monkeypatch.setattr(sync, "run_price_sync", prices)

    async with mock_http_client(lambda r: httpx.Response(200, json=[])) as client:
        await catch_up(client, resources)

    assert ran == ["prices turned away", "prices", "settlement", "standings"]


async def test_the_real_job_runs_once_the_other_replica_lets_go(resources):
    """Against the real lease: discovery held elsewhere, then released."""
    holding = asyncio.Event()
    let_go = asyncio.Event()

    async def the_container_being_replaced():
        async with single_flight(discovery.JOB_NAME) as owner:
            assert owner
            holding.set()
            await let_go.wait()

    other = asyncio.create_task(the_container_being_replaced())
    await holding.wait()
    # Released a moment after the new container first asks.
    asyncio.get_running_loop().call_later(0.15, let_go.set)

    async with mock_http_client(lambda r: httpx.Response(200, json=[])) as client:
        report = await when_free(
            discovery.JOB_NAME, discovery.run_discovery, client, resources, tries=20, pause=0.05
        )
    await other

    assert report.ran is True
    async with db.acquire() as conn:
        outcome = await conn.fetchval(
            "SELECT outcome FROM job_runs WHERE job_name = $1", discovery.JOB_NAME
        )
    assert outcome == "ok"


async def test_the_start_up_read_of_the_market_is_one_that_waits_its_turn():
    settings = get_settings()
    settings.run_discovery_on_startup = True
    async with started_scheduler(settings) as scheduler:
        job = scheduler.get_job(f"{discovery.JOB_NAME}_startup")
        assert job.func is when_free
        assert job.args[:2] == (discovery.JOB_NAME, discovery.run_discovery)


def test_turned_away_is_told_from_ran_however_a_job_reports():
    assert did_run(sync.SyncReport(ran=False)) is False
    assert did_run({"ran": False}) is False
    assert did_run(sync.SyncReport(ran=True)) is True
    assert did_run({"ran": True, "error": "something else went wrong"}) is True
    assert did_run(None) is True, "a job that reports nothing is taken to have run"


async def test_a_run_that_was_turned_away_is_not_written_down(resources):
    """Whatever shape the job reports in. A dictionary saying so used to be
    recorded as a successful run, over the top of the last real one."""
    from backend.workers.runlog import recorded

    async def turned_away():
        return {"ran": False}

    await recorded("some_job", turned_away)()

    async with db.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM job_runs") == 0


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
