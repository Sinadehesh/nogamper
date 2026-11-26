"""The job lease, and the outage it exists to prevent.

This was a Postgres advisory lock until it wedged production twice in one day.
An advisory lock dies with its session, which is right — until a session-mode
pooler outlives the worker that took it. Then nothing releases it, every
subsequent tick is refused, and price sync stops for an hour while the app
tells every player "this price is updating". Restarting the worker does not
help; only a human running pg_terminate_backend does.

So the tests that matter here are not about mutual exclusion, which was never
broken. They are about what happens when a holder dies.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

import pytest

from backend import db
from backend.workers import locks


@pytest.fixture(autouse=True)
def _clear_skip_history():
    locks._skipping_since.clear()
    yield
    locks._skipping_since.clear()


async def lease_row(name: str = "test_job"):
    async with db.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM job_leases WHERE job_name = $1", name)


async def expire_lease(name: str = "test_job") -> None:
    """Age a lease past its expiry, which is what a dead holder looks like:
    a row nobody is extending any more."""
    async with db.acquire() as conn:
        await conn.execute(
            "UPDATE job_leases SET expires_at = NOW() - INTERVAL '1 second' WHERE job_name = $1",
            name,
        )


async def test_only_one_caller_runs(resources):
    async with locks.single_flight("test_job") as first:
        assert first is True
        async with locks.single_flight("test_job") as second:
            assert second is False


async def test_the_lease_is_released_afterwards(resources):
    async with locks.single_flight("test_job") as owner:
        assert owner is True
    assert await lease_row() is None, "a finished job must not leave its lease behind"

    async with locks.single_flight("test_job") as owner:
        assert owner is True


async def test_an_exception_still_releases(resources):
    with pytest.raises(RuntimeError):
        async with locks.single_flight("test_job") as owner:
            assert owner is True
            raise RuntimeError("job blew up")

    async with locks.single_flight("test_job") as owner:
        assert owner is True, "a failed job wedged its own lease"


async def test_different_jobs_do_not_block_each_other(resources):
    async with locks.single_flight("job_a") as a:
        assert a is True
        async with locks.single_flight("job_b") as b:
            assert b is True


async def test_acquisition_is_atomic(resources):
    """Sixteen callers, one statement, one winner.

    Nobody releases, so this measures only what it claims to: whether the
    upsert can hand the lease to two callers at once. It cannot — the loser's
    `WHERE job_leases.expires_at < NOW()` finds a live expiry and the upsert
    touches nothing.
    """
    winners = await asyncio.gather(*(locks._acquire("test_job", uuid.uuid4()) for _ in range(16)))
    assert sum(winners) == 1


async def test_only_one_job_runs_while_the_lease_is_held(resources):
    """The property that matters, made deterministic with a barrier.

    The obvious version of this — five attempts, the winner sleeps briefly,
    count the winners — is a race the *test* loses rather than the lock. The
    winner's release lands while a straggler is still mid-acquire (asyncpg
    opening a new pooled connection can outlast any sleep you pick), and that
    straggler then wins, correctly. It was measuring "how many jobs ran during
    this window", which for a working lock is legitimately more than one.

    The barrier removes the window: nobody leaves the block until all five
    have been told yes or no.
    """
    decided = asyncio.Barrier(5)

    async def attempt() -> bool:
        async with locks.single_flight("test_job") as owner:
            await decided.wait()
            return owner

    results = await asyncio.gather(*(attempt() for _ in range(5)))
    assert sum(results) == 1


async def test_the_next_job_may_take_the_lease_once_it_is_released(resources):
    """The flip side, and the behaviour the flaky test was accidentally
    observing: a released lease is immediately available. Serialising N runs
    is what the lock is *for*; refusing them all would be the bug."""
    for _ in range(3):
        async with locks.single_flight("test_job") as owner:
            assert owner is True


async def test_a_lapsed_lease_is_taken_over(resources):
    """The whole reason this is not an advisory lock.

    A worker killed mid-job — a deploy, an OOM — leaves a lease nobody is
    extending. The next tick must simply take it. Under the advisory lock
    behind a session pooler this was unrecoverable without an operator.
    """
    holder = uuid.uuid4()
    assert await locks._acquire("test_job", holder) is True

    await expire_lease()

    async with locks.single_flight("test_job") as owner:
        assert owner is True, "a dead holder wedged the job — this is the outage"


async def test_a_live_lease_is_not_stolen(resources):
    """The expiry must not be a free pass to trample a working job."""
    holder = uuid.uuid4()
    assert await locks._acquire("test_job", holder) is True

    async with locks.single_flight("test_job") as owner:
        assert owner is False

    row = await lease_row()
    assert row["holder"] == holder, "a running job lost its lease to a rival"


async def test_a_superseded_holder_cannot_delete_the_new_lease(resources):
    """After a takeover, the old worker may still finish and try to release.

    It must not remove the lease its successor now holds, or the job loses its
    lock while somebody is still using it.
    """
    old = uuid.uuid4()
    assert await locks._acquire("test_job", old) is True
    await expire_lease()

    new = uuid.uuid4()
    assert await locks._acquire("test_job", new) is True

    await locks._release("test_job", old)

    row = await lease_row()
    assert row is not None, "the superseded holder deleted the live lease"
    assert row["holder"] == new


async def test_a_superseded_holder_cannot_extend_the_new_lease(resources):
    old = uuid.uuid4()
    assert await locks._acquire("test_job", old) is True
    await expire_lease()

    new = uuid.uuid4()
    assert await locks._acquire("test_job", new) is True

    async with db.acquire() as conn:
        extended = await conn.fetchval(locks._HEARTBEAT, "test_job", old, 120.0)
    assert extended is None, "a stale holder extended someone else's lease"


async def test_a_skipped_tick_is_visible_at_warning(resources, caplog):
    """DEBUG was invisible under the deployed LOG_LEVEL, which is how an hour
    of stopped price syncing produced no log line at all."""
    with caplog.at_level(logging.WARNING):
        async with locks.single_flight("test_job") as first:
            assert first is True
            async with locks.single_flight("test_job") as second:
                assert second is False

    assert "test_job skipped" in caplog.text


async def test_a_job_skipped_for_too_long_names_the_holder(resources, caplog):
    """A lease cannot leak, so this now means a rival keeps re-taking it —
    and the useful thing to print is who, not how to force an unlock."""
    async with locks.single_flight("test_job") as first:
        assert first is True
        with caplog.at_level(logging.WARNING):
            async with locks.single_flight("test_job") as second:
                assert second is False
            locks._skipping_since["test_job"] -= locks.STUCK_AFTER_SECONDS + 1
            async with locks.single_flight("test_job") as third:
                assert third is False

    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert errors, "a job stuck for a quarter of an hour must be an error"
    assert "lease held by" in errors[-1].getMessage()


async def test_acquiring_clears_the_skip_history(resources):
    """A job alternating between busy and free must never trip the alarm."""
    async with locks.single_flight("test_job") as first:
        assert first is True
        async with locks.single_flight("test_job") as second:
            assert second is False
    assert "test_job" in locks._skipping_since

    async with locks.single_flight("test_job") as owner:
        assert owner is True
    assert "test_job" not in locks._skipping_since


async def test_the_lease_records_who_holds_it(resources):
    """The first question in an incident is which container is doing the work."""
    async with locks.single_flight("test_job") as owner:
        assert owner is True
        row = await lease_row()
    assert row["holder_note"] == locks._INSTANCE
    assert row["expires_at"] > row["acquired_at"]


async def test_the_heartbeat_keeps_a_long_job_alive(resources, monkeypatch):
    """Without it, any job outlasting LEASE_SECONDS would hand its lock away
    mid-run. Discovery legitimately runs for minutes."""
    monkeypatch.setattr(locks, "HEARTBEAT_SECONDS", 0.05)
    monkeypatch.setattr(locks, "LEASE_SECONDS", 1.0)

    async with locks.single_flight("test_job") as owner:
        assert owner is True
        first = (await lease_row())["expires_at"]
        await asyncio.sleep(0.3)
        later = (await lease_row())["expires_at"]

    assert later > first, "the lease was not being extended while the job ran"


async def test_lock_keys_are_stable_for_the_old_advisory_diagnostics():
    """Nothing acquires with these now, but a database that lived through the
    advisory-lock era can still hold a stranded one, and the incident notes
    tell people to grep pg_locks for exactly these numbers."""
    assert locks.lock_key("polymarket_price_sync") == -3729812357810346130
    assert locks.lock_key("polymarket_discovery") == -6819422047807790119


async def test_a_job_that_never_finishes_is_named_by_its_own_heartbeat(
    resources, caplog, monkeypatch
):
    """The gap that cost two days of misdiagnosis.

    A heartbeat will extend a lease forever, so a job that hangs presents
    exactly like the wedged advisory lock this table replaced: every tick
    refused, nothing refreshing, and — crucially — not one line in the log
    saying which of the two it is. The price sync outage was read as a lock
    bug on the strength of that resemblance while the lock was working
    perfectly and the job simply was not returning.

    The holder is the only party that knows how long it has been running, so
    it is the one that has to say so.
    """
    monkeypatch.setattr(locks, "HEARTBEAT_SECONDS", 0.05)
    monkeypatch.setattr(locks, "RUNAWAY_AFTER_SECONDS", 0.12)

    with caplog.at_level(logging.ERROR):
        async with locks.single_flight("test_job") as owner:
            assert owner is True
            await asyncio.sleep(0.4)

    errors = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
    assert errors, "a job that ran away held its lease in silence"
    assert "not a stuck lock" in errors[0]
    assert "test_job" in errors[0]
    assert len(errors) == 1, "the alarm repeated on every beat and would bury the log"
