"""Market persistence.

Two ownership rules run through this file:

  * Discovery owns metadata (question, dates, liquidity). It does not touch
    `raw_yes_prob` on an existing row — Gamma's snapshot is a bootstrap for
    markets we have never seen, and the price sync worker owns it after that.
  * Discovery never resurrects a settled market. A row that has reached
    RESOLVED or VOID keeps its status no matter what the feed says.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

import asyncpg

from ..clients.gamma import NormalizedEvent

_UPSERT_EVENT = """
INSERT INTO market_events (polymarket_event_id, slug, title, title_source, category,
                          image_url, end_date)
VALUES ($1, $2, $3, $4, $5, $6, $7)
ON CONFLICT (polymarket_event_id) DO UPDATE SET
    slug         = EXCLUDED.slug,
    title        = EXCLUDED.title,
    title_source = EXCLUDED.title_source,
    category     = EXCLUDED.category,
    image_url    = EXCLUDED.image_url,
    end_date     = EXCLUDED.end_date
RETURNING id
"""

_UPSERT_MARKET = """
INSERT INTO markets (
    event_id, polymarket_market_id, condition_id, question, description, category,
    image_url, yes_token_id, no_token_id, raw_yes_prob, liquidity_usd, volume_usd,
    lock_at, end_date, question_source, description_source, status
)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, 'ACTIVE')
ON CONFLICT (polymarket_market_id) DO UPDATE SET
    question           = EXCLUDED.question,
    description        = EXCLUDED.description,
    question_source    = EXCLUDED.question_source,
    description_source = EXCLUDED.description_source,
    image_url     = EXCLUDED.image_url,
    liquidity_usd = EXCLUDED.liquidity_usd,
    volume_usd    = EXCLUDED.volume_usd,
    lock_at       = EXCLUDED.lock_at,
    end_date      = EXCLUDED.end_date,
    -- raw_yes_prob is deliberately absent: the price sync worker owns it.
    -- yes_token_id / no_token_id are absent too: a token swap on an existing
    -- market would silently flip the meaning of every open leg on it.
    status = CASE
        WHEN markets.status IN ('RESOLVED', 'VOID') THEN markets.status
        WHEN EXCLUDED.lock_at <= NOW()              THEN 'LOCKED'::market_status
        ELSE 'ACTIVE'::market_status
    END
RETURNING id, (xmax = 0) AS was_created
"""


@dataclass
class UpsertResult:
    events: int = 0
    markets_created: int = 0
    markets_updated: int = 0


async def upsert_events(conn: asyncpg.Connection, events: list[NormalizedEvent]) -> UpsertResult:
    result = UpsertResult()

    for event in events:
        event_id = await conn.fetchval(
            _UPSERT_EVENT,
            event.polymarket_event_id,
            event.slug,
            event.title,
            event.title_source or event.title,
            event.category,
            event.image_url,
            event.end_date,
        )
        result.events += 1

        for market in event.markets:
            row = await conn.fetchrow(
                _UPSERT_MARKET,
                event_id,
                market.polymarket_market_id,
                market.condition_id,
                market.question,
                market.description,
                market.category,
                market.image_url,
                market.yes_token_id,
                market.no_token_id,
                market.raw_yes_prob,
                market.liquidity_usd,
                market.volume_usd,
                market.lock_at,
                market.end_date,
                market.question_source or market.question,
                market.description_source,
            )
            if row["was_created"]:
                result.markets_created += 1
            else:
                result.markets_updated += 1

    return result


@dataclass(frozen=True, slots=True)
class SyncableMarket:
    id: uuid.UUID
    yes_token_id: str
    raw_yes_prob: Decimal
    price_updated_at: datetime


async def list_syncable_markets(
    conn: asyncpg.Connection, *, limit: int | None = None
) -> list[SyncableMarket]:
    """The ACTIVE markets to price this pass, stalest first.

    The order matters now that a price sync pass has a deadline and may not
    reach the end of the list. Under the old `ORDER BY lock_at` a truncated
    pass would price the same soonest-to-close markets every single tick and
    the tail would never be priced at all — permanently stale, which is the
    exact symptom the deadline exists to prevent, just moved to a subset.

    Stalest-first is starvation-free: falling behind delays every market a
    little instead of abandoning some of them completely, and a market that
    missed one pass is first in line for the next.

    `limit` caps the fan-out at what the pass is budgeted to fetch. It is a
    guard rail rather than the fix: a backlog larger than the budget still
    means most markets sit outside the staleness window, which is why
    discovery retires the surplus instead of leaving the sync to rotate
    through thousands. Without it a runaway catalogue turned into thousands of
    simultaneous tasks and connections, so the pass got slower exactly when it
    could least afford to.
    """
    rows = await conn.fetch(
        """
        SELECT id, yes_token_id, raw_yes_prob, price_updated_at
          FROM markets
         WHERE status = 'ACTIVE'
         ORDER BY price_updated_at ASC
         LIMIT $1
        """,
        limit,
    )
    return [SyncableMarket(**dict(row)) for row in rows]


_RETIRE_SURPLUS = """
WITH ranked AS (
    SELECT id,
           row_number() OVER (
               ORDER BY ($2::text IS NOT NULL AND category = $2) DESC,
                        volume_usd DESC,
                        id
           ) AS position
      FROM markets
     WHERE status = 'ACTIVE'
)
UPDATE markets AS m
   SET status = 'DRAFT'
  FROM ranked AS r
 WHERE m.id = r.id
   AND r.position > $1
   AND NOT EXISTS (
       SELECT 1 FROM prediction_legs AS l
        WHERE l.market_id = m.id AND l.status = 'PENDING'
   )
"""


async def count_active_markets(conn: asyncpg.Connection) -> int:
    """How many markets are ACTIVE, regardless of how many this pass will take.

    Separate from `list_syncable_markets` because that is now capped: once the
    list is bounded, its length can no longer tell the sync whether it is
    keeping up. This is the number that says whether the catalogue has outgrown
    the pricing budget.
    """
    return int(await conn.fetchval("SELECT count(*) FROM markets WHERE status = 'ACTIVE'"))


async def retire_surplus_markets(
    conn: asyncpg.Connection, *, keep: int, priority_category: str | None = None
) -> int:
    """Stop offering the markets the app cannot keep priced.

    A bookmaker offers the markets it can price. This one was offering 7,268
    because that is what discovery's page budget happened to return, while the
    price sync could refresh a few hundred per pass — so every card in the app
    sat outside the staleness window and read "this price is updating". No
    component had failed. The catalogue was simply larger than the pricing
    budget, and nothing in the system was responsible for noticing.

    Retiring to DRAFT rather than deleting or voiding is deliberate. DRAFT is
    already the pre-publication state: the market keeps its history and its
    upstream ids, it is invisible to the feed and unbettable in quoting, and
    the next discovery run promotes it straight back if its volume recovers.
    VOID would be a lie — it implies the market was cancelled and stakes
    returned — and deleting would take the event rows with it.

    **A market anyone still has money on is never retired.** The exclusion is
    on a PENDING leg rather than on the prediction, because that is the thing
    settlement walks, and pulling a market out from under an open leg would
    strand the slip it belongs to.

    Ranked by 24-hour volume because that is what discovery already orders by:
    the markets people are actually trading are the ones worth the budget.

    `priority_category` sorts ahead of that ranking. It is the same exemption
    discovery's budget cut makes, and it has to be made in both places or it
    is made in neither: ingesting a category the trim then parks by volume
    costs the writes and still leaves the tab empty. The
    priority markets are counted against `keep` rather than added to it, so
    the pricing budget this function exists to defend is unchanged — what
    moves is which markets get to sit inside it.
    """
    result = await conn.execute(_RETIRE_SURPLUS, keep, priority_category or None)
    return int(result.split()[-1])


async def apply_prices(conn: asyncpg.Connection, prices: list[tuple[uuid.UUID, Decimal]]) -> int:
    """Write every fetched price in one statement rather than one per market."""
    if not prices:
        return 0
    ids = [market_id for market_id, _ in prices]
    values = [probability for _, probability in prices]
    result = await conn.execute(
        """
        UPDATE markets AS m
           SET raw_yes_prob     = v.prob,
               price_updated_at = NOW()
          FROM (SELECT * FROM unnest($1::uuid[], $2::numeric[])) AS v(id, prob)
         WHERE m.id = v.id
        """,
        ids,
        values,
    )
    return int(result.rsplit(" ", 1)[-1])


async def record_snapshots(
    conn: asyncpg.Connection, snapshots: list[tuple[uuid.UUID, Decimal, str]]
) -> int:
    if not snapshots:
        return 0
    await conn.execute(
        """
        INSERT INTO market_price_snapshots (market_id, yes_prob, source)
        SELECT * FROM unnest($1::uuid[], $2::numeric[], $3::text[])
        """,
        [s[0] for s in snapshots],
        [s[1] for s in snapshots],
        [s[2] for s in snapshots],
    )
    return len(snapshots)


async def lock_expired_markets(conn: asyncpg.Connection) -> int:
    """Close forecasting on markets that have reached their cutoff.

    This runs on the sync tick rather than on discovery's hourly one: an hour
    of accepting forecasts on a market that has already stopped trading
    upstream is an hour in which the answer can be read off the news.
    """
    result = await conn.execute(
        "UPDATE markets SET status = 'LOCKED' WHERE status = 'ACTIVE' AND lock_at <= NOW()"
    )
    return int(result.rsplit(" ", 1)[-1])


_LIST_MARKETS = """
SELECT m.id,
       -- The *_source columns hold Polymarket's own English. They are read in
       -- preference to the plain ones so that a row written back when text
       -- was being translated still comes out in English.
       COALESCE(m.question_source, m.question)       AS question,
       COALESCE(m.description_source, m.description) AS description,
       m.category, m.image_url,
       m.raw_yes_prob, m.price_updated_at, m.liquidity_usd, m.volume_usd,
       m.lock_at, m.end_date,
       e.id AS event_id,
       COALESCE(e.title_source, e.title) AS event_title,
       e.slug AS event_slug
  FROM markets m
  JOIN market_events e ON e.id = m.event_id
 WHERE m.status = 'ACTIVE'
   AND m.lock_at > NOW()
   AND ($1::text IS NULL OR m.category = $1)
   AND ($2::timestamptz IS NULL OR (m.lock_at, m.id) > ($2::timestamptz, $3::uuid))
 ORDER BY m.lock_at, m.id
 LIMIT $4
"""


async def list_active_markets(
    conn: asyncpg.Connection,
    *,
    category: str | None,
    after_lock_at: datetime | None,
    after_id: uuid.UUID | None,
    limit: int,
) -> list[asyncpg.Record]:
    return await conn.fetch(_LIST_MARKETS, category, after_lock_at, after_id, limit)


@dataclass(frozen=True, slots=True)
class ResolvableMarket:
    id: uuid.UUID
    polymarket_market_id: str
    yes_token_id: str
    question: str
    end_date: datetime


async def list_markets_awaiting_resolution(
    conn: asyncpg.Connection, *, limit: int
) -> list[ResolvableMarket]:
    """Markets whose upstream event has passed but which we have not graded.

    LOCKED as well as ACTIVE: the sync worker locks a market at its cutoff, and
    an ACTIVE row past `end_date` only means no sync tick has run since.
    """
    rows = await conn.fetch(
        """
        SELECT id, polymarket_market_id, yes_token_id, question, end_date
          FROM markets
         WHERE status IN ('ACTIVE', 'LOCKED')
           AND end_date < NOW()
         ORDER BY end_date
         LIMIT $1
        """,
        limit,
    )
    return [ResolvableMarket(**dict(row)) for row in rows]


_RESOLVE_MARKET = """
UPDATE markets
   SET status            = 'RESOLVED',
       resolution        = $2::market_resolution,
       resolution_source = $3,
       resolved_at       = NOW()
 WHERE id = $1
   AND status IN ('ACTIVE', 'LOCKED')
RETURNING id
"""

_GRADE_LEGS = """
UPDATE prediction_legs
   SET status = CASE
                  WHEN $2::market_resolution = 'VOID' THEN 'VOID'::leg_status
                  WHEN side::text = $2::text          THEN 'WON'::leg_status
                  ELSE 'LOST'::leg_status
                END,
       settled_at = NOW()
 WHERE market_id = $1
   AND status = 'PENDING'
RETURNING prediction_id
"""


async def resolve_market(
    conn: asyncpg.Connection,
    market_id: uuid.UUID,
    resolution: str,
    *,
    source: str,
) -> list[uuid.UUID]:
    """Mark a market resolved and grade its open legs.

    Returns the slips touched. Returns empty if the market was already
    resolved — the guard on `status` makes a re-run a no-op rather than a
    second grading pass.
    """
    resolved = await conn.fetchval(_RESOLVE_MARKET, market_id, resolution, source)
    if resolved is None:
        return []

    rows = await conn.fetch(_GRADE_LEGS, market_id, resolution)
    return list({row["prediction_id"] for row in rows})


async def list_settleable_slips(conn: asyncpg.Connection, *, limit: int) -> list[uuid.UUID]:
    """Pending slips with no pending legs left.

    The safety net. Grading and settlement are separate transactions, so a
    worker that dies between them leaves a fully-graded slip that nobody has
    paid. Without this sweep that slip stays unpaid until someone notices.
    """
    rows = await conn.fetch(
        """
        SELECT p.id
          FROM predictions p
         WHERE p.status = 'PENDING'
           AND NOT EXISTS (
                 SELECT 1 FROM prediction_legs pl
                  WHERE pl.prediction_id = p.id AND pl.status = 'PENDING'
               )
         ORDER BY p.placed_at
         LIMIT $1
        """,
        limit,
    )
    return [row["id"] for row in rows]


async def settle_slip(conn: asyncpg.Connection, prediction_id: uuid.UUID) -> str:
    """Hand settlement to the database.

    All the multi-pick arithmetic, the void-leg collapse and the payout cap
    live in fn_settle_prediction. Re-implementing any of it
    here would mean two sources of truth for what a slip pays.
    """
    return await conn.fetchval("SELECT fn_settle_prediction($1)", prediction_id)


async def count_overdue_markets(conn: asyncpg.Connection, *, older_than_hours: int) -> int:
    return await conn.fetchval(
        """
        SELECT count(*) FROM markets
         WHERE status IN ('ACTIVE', 'LOCKED')
           AND end_date < NOW() - make_interval(hours => $1)
        """,
        older_than_hours,
    )
