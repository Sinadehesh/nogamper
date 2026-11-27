"""Questions, read for pages anybody can open.

Read-only, all of it. Discovery writes what is read here
(repositories/markets.py) and the price sync keeps the price; this file only
answers "what is this question, and how has its chance changed".
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

import asyncpg

Window = Literal["day", "week"]

_COLUMNS = """
       m.id, m.slug, m.question, m.description, m.category, m.status, m.resolution,
       m.resolved_at, m.raw_yes_prob, m.price_updated_at, m.lock_at, m.end_date,
       m.volume_usd, m.yes_token_id, m.change_1h, m.change_24h, m.change_7d,
       m.change_ref_prob, m.changes_at, m.updated_at, e.title AS event_title
  FROM markets AS m
  JOIN market_events AS e ON e.id = m.event_id
"""

_BY_SLUG = f"""
SELECT {_COLUMNS}
 WHERE m.slug = $1
 -- An address is the source's and need not be unique. If two questions ever
 -- share one, the page shows the one still open, then the newest.
 ORDER BY (m.status = 'ACTIVE') DESC, m.created_at DESC
 LIMIT 1
"""  # noqa: S608 - built from constants in this file, never from a request


async def find_by_slug(conn: asyncpg.Connection, slug: str) -> asyncpg.Record | None:
    return await conn.fetchrow(_BY_SLUG, slug)


def _candidates(column: str) -> str:
    return f"""
SELECT {_COLUMNS}
 WHERE m.status = 'ACTIVE'
   AND m.slug IS NOT NULL
   AND m.{column} IS NOT NULL
   AND abs(m.{column}) >= $1
   AND m.lock_at > $2
   AND m.changes_at >= $3
 ORDER BY abs(m.{column}) DESC, m.volume_usd DESC, m.id
 LIMIT $4
"""  # noqa: S608 - `column` is one of the two names below, never a request's


_CANDIDATES: dict[Window, str] = {
    "day": _candidates("change_24h"),
    "week": _candidates("change_7d"),
}


async def move_candidates(
    conn: asyncpg.Connection,
    *,
    window: Window,
    min_change: Decimal,
    closes_after: datetime,
    measured_after: datetime,
    limit: int,
) -> list[asyncpg.Record]:
    """Open questions whose reported change over `window` is at least
    `min_change`, largest first.

    Candidates, not the answer. The source's figure was measured when the
    question list was last read; the caller compares where the question stood
    then with where it stands now, and drops the ones that have since come
    back.
    """
    return await conn.fetch(_CANDIDATES[window], min_change, closes_after, measured_after, limit)


async def newest_readings(conn: asyncpg.Connection) -> tuple[datetime | None, datetime | None]:
    """When change figures, and when a price, were last read for any open
    question. Either is None when nothing has been read at all."""
    row = await conn.fetchrow(
        "SELECT max(changes_at) AS changes_at, max(price_updated_at) AS price_at"
        "  FROM markets WHERE status = 'ACTIVE'"
    )
    return row["changes_at"], row["price_at"]


_INDEXED = (
    "m.slug IS NOT NULL"
    " AND m.status IN ('ACTIVE', 'LOCKED', 'SETTLING', 'RESOLVED')"
    " AND (m.resolution IS NULL OR m.resolution <> 'VOID')"
)

_INDEX = f"""
SELECT m.slug, m.question, m.category, m.status, m.resolution, m.updated_at
  FROM markets AS m
 WHERE {_INDEXED}
 -- Open first, then the most recently finished. Ordered by dates that are set
 -- once: `updated_at` moves every time a price is read, and a list read a page
 -- at a time in an order that shifts under it repeats some rows and drops others.
 ORDER BY (m.status = 'ACTIVE') DESC, COALESCE(m.resolved_at, m.created_at) DESC, m.id
 LIMIT $1 OFFSET $2
"""  # noqa: S608 - built from constants in this file, never from a request

_INDEX_TOTAL = f"SELECT count(*) FROM markets AS m WHERE {_INDEXED}"  # noqa: S608


async def index(
    conn: asyncpg.Connection, *, limit: int, offset: int
) -> tuple[list[asyncpg.Record], int]:
    """Every question with a page worth listing: open ones first.

    Left out are the questions the site stopped following and the ones their
    source cancelled. Their pages still answer, for anyone holding the
    address, but there is nothing on them to send a stranger to.
    """
    rows = await conn.fetch(_INDEX, limit, offset)
    total = await conn.fetchval(_INDEX_TOTAL)
    return rows, int(total)


_OWN_HISTORY = """
SELECT date_trunc('hour', captured_at) AS at,
       (array_agg(yes_prob ORDER BY captured_at DESC))[1] AS yes
  FROM market_price_snapshots
 WHERE market_id = $1 AND captured_at >= $2
 GROUP BY 1
 ORDER BY 1
"""


async def own_history(
    conn: asyncpg.Connection, market_id: uuid.UUID, *, since: datetime
) -> list[tuple[datetime, Decimal]]:
    """This site's own record of a question's price: the last price it saw in
    each hour. Thinner than the source's — nothing is recorded while the
    server is not running — and used only when the source's cannot be had."""
    rows = await conn.fetch(_OWN_HISTORY, market_id, since)
    return [(row["at"], row["yes"]) for row in rows]
