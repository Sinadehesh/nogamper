"""Why are the prices stale? — answered from live state, in one query.

This exists because the same symptom has now been investigated three times and
produced three different causes:

  1. A Postgres advisory lock stranded by a session-mode pooler, so every tick
     was refused. Cured by a human running pg_terminate_backend.
  2. A price sync pass with no deadline, running for minutes against a slow
     upstream while its lease heartbeat held the job shut. It looked exactly
     like (1) and was not.
  3. — whatever comes next.

Each time, the app told every player "this price is updating" and told the
operator nothing at all. The evidence needed to tell those cases apart is
small, cheap to read, and was never anywhere: how long since a price last
landed, whether the job is holding its lease, and whether the cache and the
database agree.

So the point of this module is not to fix a cause. It is to make the *next*
recurrence a single request instead of two days of reading code.

## What each shape means

    no ACTIVE markets              discovery is not ingesting
    lease held far too long        the job is running and not finishing
    no lease, prices old           nothing is running the job at all
    more markets than the budget   the catalogue outgrew the pricing budget
    lease cycling, prices old      the CLOB is returning nothing usable
    Redis unreachable              reads fall back and flag everything stale
    some markets past the window   the pass truncated at its deadline
    everything fresh               prices are fine; look elsewhere

`explain()` returns the *first* of those that matches, in that order, because
an operator needs somewhere to start rather than a survey — and because a
lower-severity finding reported over a real outage is worse than silence. A
cold-but-reachable cache is deliberately last: it is equally what a market
discovered thirty seconds ago looks like.

That mapping is the whole value, and it belongs next to the numbers rather
than in an incident note somebody has to find.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime

import asyncpg

_MARKETS = """
SELECT count(*) FILTER (WHERE status = 'ACTIVE')                    AS active,
       count(*) FILTER (WHERE status = 'ACTIVE'
                          AND price_updated_at > NOW() - make_interval(secs => $1)) AS fresh,
       max(price_updated_at) FILTER (WHERE status = 'ACTIVE')       AS newest,
       min(price_updated_at) FILTER (WHERE status = 'ACTIVE')       AS oldest,
       EXTRACT(EPOCH FROM (NOW() - max(price_updated_at)
               FILTER (WHERE status = 'ACTIVE')))                   AS since_newest,
       count(*) FILTER (WHERE status = 'LOCKED')                    AS locked,
       count(*)                                                     AS total
  FROM markets
"""

_LEASES = """
SELECT job_name,
       holder_note,
       EXTRACT(EPOCH FROM (NOW() - acquired_at)) AS held_for,
       EXTRACT(EPOCH FROM (expires_at - NOW()))  AS expires_in
  FROM job_leases
 ORDER BY job_name
"""

_RUNS = """
SELECT job_name, outcome, duration_seconds, detail, holder_note,
       EXTRACT(EPOCH FROM (NOW() - finished_at)) AS finished_ago
  FROM job_runs
 ORDER BY job_name
"""

_SAMPLE_ACTIVE = """
SELECT id FROM markets WHERE status = 'ACTIVE' ORDER BY price_updated_at DESC LIMIT $1
"""


@dataclass(frozen=True, slots=True)
class JobLease:
    job_name: str
    holder_note: str | None
    held_for_seconds: float
    expires_in_seconds: float


@dataclass(frozen=True, slots=True)
class JobRun:
    job_name: str
    outcome: str
    duration_seconds: float
    finished_ago_seconds: float
    detail: dict
    holder_note: str | None


@dataclass(frozen=True, slots=True)
class PriceHealth:
    markets_total: int
    markets_active: int
    markets_locked: int
    markets_fresh: int
    newest_price_at: datetime | None
    oldest_price_at: datetime | None
    seconds_since_newest: float | None
    cache_reachable: bool
    cache_hits: int
    cache_sampled: int
    leases: list[JobLease]
    runs: list[JobRun] = field(default_factory=list)

    @property
    def markets_stale(self) -> int:
        return self.markets_active - self.markets_fresh


async def read_price_health(
    conn: asyncpg.Connection, *, staleness_seconds: int, sample: int = 20
) -> tuple[PriceHealth, list]:
    row = await conn.fetchrow(_MARKETS, float(staleness_seconds))
    leases = [
        JobLease(
            job_name=r["job_name"],
            holder_note=r["holder_note"],
            held_for_seconds=float(r["held_for"]),
            expires_in_seconds=float(r["expires_in"]),
        )
        for r in await conn.fetch(_LEASES)
    ]
    runs = [
        JobRun(
            job_name=r["job_name"],
            outcome=r["outcome"],
            duration_seconds=float(r["duration_seconds"]),
            finished_ago_seconds=float(r["finished_ago"]),
            detail=json.loads(r["detail"]) if isinstance(r["detail"], str) else dict(r["detail"]),
            holder_note=r["holder_note"],
        )
        for r in await conn.fetch(_RUNS)
    ]
    sampled = [r["id"] for r in await conn.fetch(_SAMPLE_ACTIVE, sample)]
    return (
        PriceHealth(
            markets_total=int(row["total"]),
            markets_active=int(row["active"]),
            markets_locked=int(row["locked"]),
            markets_fresh=int(row["fresh"]),
            newest_price_at=row["newest"],
            oldest_price_at=row["oldest"],
            seconds_since_newest=(
                float(row["since_newest"]) if row["since_newest"] is not None else None
            ),
            cache_reachable=False,
            cache_hits=0,
            cache_sampled=0,
            leases=leases,
            runs=runs,
        ),
        sampled,
    )


RUNAWAY_SECONDS = 1200.0
"""Mirror of locks.RUNAWAY_AFTER_SECONDS — the heartbeat logs it, this reports
it, and an operator reading both must not see two different verdicts."""


def _capacity_advice(health: PriceHealth, *, staleness_seconds: int, max_markets: int) -> str:
    return (
        f"{health.markets_active} markets are ACTIVE but the price sync is budgeted for "
        f"{max_markets}. A pass cannot come back round to all of them inside the "
        f"{staleness_seconds}s window, so most of the app reads 'this price is updating' "
        "however well the sync runs — nothing here has failed. Discovery retires the "
        "surplus on its next run; if it comes back, lower DISCOVERY_MAX_PAGES."
    )


def last_run(health: PriceHealth, job_name: str) -> JobRun | None:
    return next((r for r in health.runs if r.job_name == job_name), None)


def _census(run: JobRun | None) -> str:
    """The failure census from the last pass, in words.

    This is the sentence that has been missing every time. "No price has
    landed" says a pass is failing; "40 ReadTimeout, 12 HTTPStatusError" says
    what to do about it, and until now it existed only in a log line.
    """
    if run is None:
        return " No run has been recorded yet — the worker has not completed a pass since deploy."

    if run.outcome == "error":
        return f" The last pass raised: {run.detail.get('error', 'unknown')}."
    if run.outcome == "deadline":
        return f" The last pass was abandoned at its deadline after {run.duration_seconds:.0f}s."

    reasons = run.detail.get("failure_reasons") or {}
    fetched = run.detail.get("prices_fetched")
    considered = run.detail.get("markets_considered")
    parts = []
    if considered is not None:
        parts.append(f"last pass fetched {fetched} of {considered} in {run.duration_seconds:.0f}s")
    if reasons:
        named = ", ".join(f"{count}x {name}" for name, count in sorted(reasons.items()))
        parts.append(f"failures: {named}")
    return f" ({'; '.join(parts)})." if parts else ""


def explain(
    health: PriceHealth, *, staleness_seconds: int, max_markets: int | None = None
) -> tuple[str, str]:
    """One line naming the layer at fault, and one saying what to do.

    Ordered by what would be checked first by hand, and deliberately returning
    the *first* thing that is wrong rather than a list: an operator reading
    this at two in the morning needs somewhere to start, not a survey.
    """
    if health.markets_total == 0:
        return (
            "discovery",
            "There are no markets at all. Discovery has never ingested — check the "
            "worker's logs for the Gamma fetch and DISCOVERY_CATEGORIES.",
        )

    if health.markets_active == 0:
        return (
            "discovery",
            f"{health.markets_locked} market(s) are locked and none are active, so "
            "there is nothing to price. Discovery is not keeping up with expiry.",
        )

    stuck = [job for job in health.leases if job.held_for_seconds >= RUNAWAY_SECONDS]
    if stuck:
        names = ", ".join(f"{j.job_name} ({j.held_for_seconds / 60:.0f}m)" for j in stuck)
        return (
            "worker",
            f"A job has been holding its lease far too long: {names}. This is not a "
            "stuck lock — the lock is working. The job itself is not finishing, so "
            "every later tick is being refused." + _census(last_run(health, stuck[0].job_name)),
        )

    if health.seconds_since_newest is not None and health.seconds_since_newest > staleness_seconds:
        if not health.leases:
            return (
                "worker",
                f"No price has landed for {health.seconds_since_newest / 60:.0f} minutes and "
                "no job holds a lease, so nothing is running the sync. Check that a "
                "container has WORKERS_ENABLED=true and that its scheduler started.",
            )
        if max_markets is not None and health.markets_active > max_markets:
            return (
                "capacity",
                _capacity_advice(
                    health, staleness_seconds=staleness_seconds, max_markets=max_markets
                ),
            )
        return (
            "upstream",
            f"The job is running but no price has landed for "
            f"{health.seconds_since_newest / 60:.0f} minutes. The sync is reaching the "
            "CLOB and getting nothing usable." + _census(last_run(health, "polymarket_price_sync")),
        )

    if not health.cache_reachable:
        return (
            "cache",
            "Redis is not answering. Reads fall back to Postgres and are flagged stale, "
            "so the app looks broken while the data is fine. Check REDIS_URL and the "
            "Upstash connection limits.",
        )

    if health.markets_stale and max_markets is not None and health.markets_active > max_markets:
        return (
            "capacity",
            _capacity_advice(health, staleness_seconds=staleness_seconds, max_markets=max_markets),
        )

    if health.markets_stale:
        return (
            "degraded",
            f"{health.markets_stale} of {health.markets_active} markets are past the "
            f"{staleness_seconds}s window while the newest is current. The pass is "
            "truncating at its deadline — expected under load, and the stalest are "
            "priced first on the next tick.",
        )

    if health.cache_sampled and health.cache_hits == 0:
        return (
            "degraded",
            "Prices are current in the database but absent from Redis. Harmless if "
            "these markets were just discovered — the next sync fills the cache. If it "
            "persists, the cache write is failing while the durable write succeeds: "
            "check the worker log for 'price cache write failed'.",
        )

    return ("healthy", "Prices are current. If the app says otherwise, the problem is not here.")
