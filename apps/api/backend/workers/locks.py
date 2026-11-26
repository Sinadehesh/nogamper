"""Cross-replica job locking, on a lease that expires by itself.

The scheduler is attached to the API's lifespan, so every replica would
otherwise run every job on every tick — N replicas doing N identical discovery
runs and N sets of writes. One of them should do the work and the rest should
return immediately.

**This used to be a Postgres advisory lock, and it wedged production twice.**
An advisory lock dies with the session that took it, which is the right
property — a crashed worker should not hold the job forever. But that property
does not survive a session-mode pooler. Through Supavisor the *server* session
can outlive the client, so a deploy that replaced the worker mid-job left the
lock held by a session with nobody behind it. The new worker asked, was
refused, and skipped. Every tick. The first occurrence stopped price sync for
over an hour and turned every market in the app into "this price is updating";
the cure was a human running pg_terminate_backend, and it came straight back
on the next deploy.

A lease has no session to outlive. It is a row with an expiry: the holder
extends it while it works, and if the holder dies nobody extends it, so the
next tick takes over the moment it lapses. Nothing to clean up, nobody to
page.

The cost is a bounded window in which a dead holder still looks alive. The
heartbeat keeps that to seconds, and the jobs already tolerate an overlap —
single_flight makes extra replicas safe rather than free, and every ledger
write is idempotent — so a brief double-run is wasteful, not wrong. An hour of
silence was neither.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import os
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from .. import db

logger = logging.getLogger(__name__)

LEASE_SECONDS = 120.0

HEARTBEAT_SECONDS = 30.0

STUCK_AFTER_SECONDS = 900.0

RUNAWAY_AFTER_SECONDS = 1200.0
"""When a still-running job stops being slow and starts being the story.

Kept looser than DISCOVERY_DEADLINE_SECONDS on purpose. Discovery abandons
itself at its own deadline, so a pass that reaches this one is a job with no
deadline of its own or a deadline that did not fire — either way something the
operator has to look at. Raised alongside that deadline when translation moved
the honest length of a pass from seconds into minutes; leaving it at 300 would
have logged "this job is not finishing" over every healthy run and taught the
operator to scroll past it.

diagnostics.RUNAWAY_SECONDS reports the same threshold and must match.
"""

_skipping_since: dict[str, float] = {}

_INSTANCE = f"{os.getenv('RENDER_INSTANCE_ID') or os.uname().nodename}:{os.getpid()}"


def instance_note() -> str:
    """Which container is speaking. Shared with runlog so a lease and the run
    it covers name the same replica during an incident."""
    return _INSTANCE


_ACQUIRE = """
INSERT INTO job_leases (job_name, holder, expires_at, holder_note)
VALUES ($1, $2, NOW() + make_interval(secs => $3), $4)
ON CONFLICT (job_name) DO UPDATE
   SET holder      = EXCLUDED.holder,
       acquired_at = NOW(),
       expires_at  = EXCLUDED.expires_at,
       holder_note = EXCLUDED.holder_note
 WHERE job_leases.expires_at < NOW()
RETURNING holder
"""

_HEARTBEAT = """
UPDATE job_leases
   SET expires_at = NOW() + make_interval(secs => $3)
 WHERE job_name = $1 AND holder = $2
RETURNING holder
"""

_RELEASE = "DELETE FROM job_leases WHERE job_name = $1 AND holder = $2"

_DESCRIBE = """
SELECT holder_note, expires_at - NOW() AS remaining
  FROM job_leases WHERE job_name = $1
"""


def lock_key(name: str) -> int:
    """Kept for the advisory-lock era's diagnostics and tests.

    Nothing acquires with this any more, but a database that lived through the
    old scheme may still have a stranded advisory lock, and the incident notes
    tell people to grep pg_locks for these numbers.
    """
    digest = hashlib.blake2b(name.encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big", signed=True)


async def _acquire(name: str, holder: uuid.UUID) -> bool:
    async with db.acquire() as conn:
        won = await conn.fetchval(_ACQUIRE, name, holder, LEASE_SECONDS, _INSTANCE)
    return won is not None


async def _release(name: str, holder: uuid.UUID) -> None:
    try:
        async with db.acquire() as conn:
            await conn.execute(_RELEASE, name, holder)
    except Exception:
        logger.warning("could not release the lease for job %s; it will expire", name)


async def _heartbeat(name: str, holder: uuid.UUID) -> None:
    """Extend the lease while the job runs.

    Losing it mid-run is not fatal — the work is idempotent and an overlap is
    tolerated — but it is worth an error, because it means the job ran longer
    than LEASE_SECONDS without a successful heartbeat and somebody else may
    now be doing the same work.

    It also complains about the opposite case, which is the one that actually
    bit. A heartbeat is perfectly happy to extend a lease forever, so a job
    that hangs looks — from the lease table, from the logs, from the app —
    exactly like the wedged advisory lock this replaced: every tick refused,
    nothing refreshing, no error anywhere. A price sync that ran for minutes
    was misread as a lock bug for two days on the strength of that
    resemblance. A holder still going after RUNAWAY_AFTER_SECONDS is not doing
    its job; it is the story.
    """
    started = time.monotonic()
    warned_runaway = False

    while True:
        await asyncio.sleep(HEARTBEAT_SECONDS)
        held_for = time.monotonic() - started
        try:
            async with db.acquire() as conn:
                still_ours = await conn.fetchval(_HEARTBEAT, name, holder, LEASE_SECONDS)
            if still_ours is None:
                logger.error(
                    "job %s lost its lease mid-run; another worker may have taken over",
                    name,
                )
                return

            if held_for >= RUNAWAY_AFTER_SECONDS and not warned_runaway:
                warned_runaway = True
                logger.error(
                    "job %s has been running for %.0f minutes and its heartbeat is "
                    "still holding the lease, so every other tick is being refused. "
                    "This is not a stuck lock — the lock is working. The job itself "
                    "is not finishing; look at what it is waiting on.",
                    name,
                    held_for / 60,
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("heartbeat failed for job %s; lease still has time", name)


async def _note_skip(name: str, now: float) -> None:
    started = _skipping_since.setdefault(name, now)
    skipped_for = now - started

    if skipped_for < STUCK_AFTER_SECONDS:
        logger.warning("job %s skipped: lease held elsewhere (%.0fs)", name, skipped_for)
        return

    holder_note, remaining = None, None
    with contextlib.suppress(Exception):
        async with db.acquire() as conn:
            row = await conn.fetchrow(_DESCRIBE, name)
        if row is not None:
            holder_note, remaining = row["holder_note"], row["remaining"]

    logger.error(
        "job %s has been skipped for %.0f minutes — lease held by %s, expiring in %s. "
        "A lease cannot leak, so this is a worker that keeps re-taking it: check for "
        "more than one instance running workers.",
        name,
        skipped_for / 60,
        holder_note or "unknown",
        remaining or "unknown",
    )


@asynccontextmanager
async def single_flight(name: str) -> AsyncIterator[bool]:
    """Yield True to the one caller holding the lease, False to everyone else."""
    holder = uuid.uuid4()

    if not await _acquire(name, holder):
        await _note_skip(name, time.monotonic())
        yield False
        return

    _skipping_since.pop(name, None)
    beat = asyncio.create_task(_heartbeat(name, holder))
    try:
        yield True
    finally:
        beat.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await beat
        await _release(name, holder)
