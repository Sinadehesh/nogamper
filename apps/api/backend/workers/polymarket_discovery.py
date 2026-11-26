"""Discovery worker — Gamma API into `market_events` / `markets`.

Runs hourly. Pages through Polymarket's active events, keeps the ones in the
configured categories, keeps only genuinely binary markets inside them, and
upserts what survives. Everything it drops is counted and logged by reason, so
a change in Gamma's shape shows up as a number rather than as an empty market
list.

Market text is stored as Polymarket wrote it, in English. There was once a
translation step between the normaliser and the upsert; the site is
English-only now and the step is gone.

**A pass ingests only what the app can price, and is bounded in time.**

Both of those were learned the same way. Discovery read its full page budget —
twenty pages of a hundred — and upserted every market it found: 7,268 of them.
`upsert_events` costs two sequential round trips per market, and all of it ran
inside a single transaction with no deadline. One run took eighty-six minutes,
and because the lease heartbeat extends while a run continues, it held
discovery shut against every later tick for all of it.

The waste was the worse half. The price sync can only keep a few hundred
markets inside the staleness window, so `retire_surplus_markets` immediately
parked 6,868 of the 7,268 that had just been written. The fix is not to do
that work faster — it is not to do it. Gamma is read volume-first, and the
trim keeps the highest-volume markets, so the top of the feed *is* the set
that survives. Taking only that many is the same answer for a fraction of the
cost.

The trim stays, because the database can hold markets this pass never saw.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import asdict, dataclass

import httpx

from .. import db
from ..clients import gamma
from ..config import Settings
from ..repositories import markets as markets_repo
from .locks import single_flight

logger = logging.getLogger(__name__)

JOB_NAME = "polymarket_discovery"


@dataclass
class DiscoveryReport:
    ran: bool
    duration_seconds: float = 0.0
    events_upserted: int = 0
    markets_created: int = 0
    markets_updated: int = 0
    markets_retired: int = 0
    markets_considered: int = 0
    stats: dict | None = None
    error: str | None = None


def _within_budget(events: list, budget: int, *, priority: str | None = None) -> list:
    """Take events from the top of the feed until the market budget is spent.

    Whole events, never a partial one: the markets under an event are the
    outcomes of the same question, and offering three of a five-way race would
    show players a board with legs missing. So the cut lands on an event
    boundary and the last event is taken in full even if it goes slightly over.

    Order is Gamma's, which is trading volume descending — the same key
    `retire_surplus_markets` ranks by. That is what makes this a saving rather
    than a different answer: the markets dropped here are the ones the trim
    would have parked seconds later, after paying to write them.

    The priority category is exempt from the cut. Ranking by volume is the
    right default and the wrong answer for the one category the feed is built
    around: a regional tag carries a fraction of the volume of the crypto and
    macro markets it is being ranked against, so a budget large enough to
    matter would still spend itself before reaching it. Those events are taken
    first and in full, and the budget is what is left over for the rest. The
    cost is bounded by how few events the tag has, which is the same reason it
    loses on volume.
    """
    preferred = [e for e in events if priority and e.category == priority]
    rest = events if not preferred else [e for e in events if e not in preferred]

    kept: list = list(preferred)
    markets = sum(len(e.markets) for e in preferred)
    for event in rest:
        if markets >= budget:
            break
        kept.append(event)
        markets += len(event.markets)
    return kept


async def run_discovery(client: httpx.AsyncClient, settings: Settings) -> DiscoveryReport:
    async with single_flight(JOB_NAME) as owner:
        if not owner:
            return DiscoveryReport(ran=False)

        started = time.monotonic()
        try:
            async with asyncio.timeout(settings.discovery_deadline_seconds):
                return await _discover(client, settings, started)
        except TimeoutError:
            elapsed = time.monotonic() - started
            logger.error(
                "discovery abandoned at its %.0fs deadline after %.0fs. No markets were "
                "written. If this repeats, the pass is doing more work than an hourly "
                "job can afford — lower PRICE_SYNC_MAX_MARKETS or raise "
                "DISCOVERY_DEADLINE_SECONDS.",
                settings.discovery_deadline_seconds,
                elapsed,
            )
            return DiscoveryReport(
                ran=True,
                duration_seconds=round(elapsed, 3),
                error="deadline_exceeded",
            )


async def _discover(
    client: httpx.AsyncClient,
    settings: Settings,
    started: float,
) -> DiscoveryReport:
    """One pass, with the lock and the deadline held by the caller."""
    stats = gamma.DiscoveryStats()

    try:
        raw_events = await gamma.fetch_events(client, settings)
    except Exception as exc:
        logger.exception("discovery could not reach Gamma")
        return DiscoveryReport(
            ran=True, duration_seconds=time.monotonic() - started, error=str(exc)
        )

    considered = list(gamma.normalize_events(raw_events, settings=settings, stats=stats))
    normalized = _within_budget(
        considered,
        settings.price_sync_max_markets,
        priority=settings.discovery_priority_category,
    )

    async with db.transaction() as conn:
        result = await markets_repo.upsert_events(conn, normalized)

        retired = await markets_repo.retire_surplus_markets(
            conn,
            keep=settings.price_sync_max_markets,
            priority_category=settings.discovery_priority_category,
        )

    report = DiscoveryReport(
        ran=True,
        duration_seconds=round(time.monotonic() - started, 3),
        markets_considered=sum(len(e.markets) for e in considered),
        events_upserted=result.events,
        markets_created=result.markets_created,
        markets_updated=result.markets_updated,
        markets_retired=retired,
        stats=stats.as_dict(),
    )

    logger.info("discovery complete: %s", asdict(report))
    if len(normalized) < len(considered):
        logger.info(
            "discovery took the top %d of %d markets by volume, which is the price "
            "sync's budget. The rest would have been parked immediately after being "
            "written.",
            report.markets_created + report.markets_updated,
            report.markets_considered,
        )
    if retired:
        logger.info(
            "retired %d market(s) past the %d the price sync is budgeted for; "
            "they keep their history and return if their volume does",
            retired,
            settings.price_sync_max_markets,
        )
    if stats.events_seen and not stats.events_kept:
        logger.warning(
            "discovery kept none of %s events; skips=%s tags_seen=%s",
            stats.events_seen,
            dict(stats.skips),
            stats.top_unmatched_tags(),
        )
    return report
