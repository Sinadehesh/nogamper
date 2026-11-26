"""Every scheduled run writes down how it went.

Written after the fourth outage whose cause was legible only in a worker log.
The wrapper lives in the scheduler rather than inside each job so that a job
added later cannot quietly escape it, and so a run that *raises* is recorded —
which is the run most worth having a record of and the one a report-shaped log
line never covered.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend import db
from backend.workers.runlog import recorded


@dataclass
class FakeReport:
    ran: bool = True
    prices_fetched: int = 7
    failure_reasons: dict | None = None


async def stored(job: str) -> dict | None:
    async with db.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM job_runs WHERE job_name = $1", job)
    return dict(row) if row else None


async def test_a_completed_run_is_written_down(resources):
    async def job():
        return FakeReport(failure_reasons={"ReadTimeout": 3})

    await recorded("job-a", job)()

    row = await stored("job-a")
    assert row["outcome"] == "ok"
    assert row["duration_seconds"] >= 0
    import json

    detail = json.loads(row["detail"]) if isinstance(row["detail"], str) else row["detail"]
    assert detail["failure_reasons"] == {"ReadTimeout": 3}


async def test_a_run_that_raises_is_recorded_and_still_raises(resources):
    """Recorded, because that is the run worth having. Still raised, because
    swallowing it would turn a broken job into a silent one — which is the
    failure mode this whole module exists to end."""
    import pytest

    async def job():
        raise ValueError("upstream went away")

    with pytest.raises(ValueError):
        await recorded("job-b", job)()

    row = await stored("job-b")
    assert row["outcome"] == "error"
    assert "upstream went away" in str(row["detail"])


async def test_a_skipped_run_does_not_overwrite_the_last_real_one(resources):
    """Every replica ticks and all but one return without the lease. Writing
    those would replace the last real run with "somebody else is doing it",
    which is exactly the information nobody needs."""

    async def did_work():
        return FakeReport(prices_fetched=99)

    async def skipped():
        return FakeReport(ran=False, prices_fetched=0)

    await recorded("job-c", did_work)()
    await recorded("job-c", skipped)()

    assert "99" in str(await stored("job-c"))


async def test_recording_never_costs_a_completed_run(resources, monkeypatch):
    """A diagnostics write that breaks the thing it observes is worse than no
    diagnostics: the pass has already done its real work by then."""
    from backend.workers import runlog

    class Exploding:
        async def __aenter__(self):
            raise RuntimeError("the database is having a moment")

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(runlog.db, "transaction", lambda *a, **k: Exploding())

    async def job():
        return FakeReport(prices_fetched=5)

    report = await recorded("job-d", job)()
    assert report.prices_fetched == 5


async def test_the_deadline_outcome_is_told_apart_from_a_failure(resources):
    """A pass abandoned at its own time limit is the system working as
    designed; a pass that raised is not. Same silence, different fix."""

    @dataclass
    class Abandoned:
        ran: bool = True
        error: str = "deadline_exceeded"

    async def job():
        return Abandoned()

    await recorded("job-e", job)()
    assert (await stored("job-e"))["outcome"] == "deadline"
