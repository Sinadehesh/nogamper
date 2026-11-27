"""The free economy: the daily top-up and the leaderboard.

Every point that moves here goes through `ledger_entries` with a date-scoped
idempotency key, so a request that arrives twice — a double tap, a retry, two
tabs — credits exactly once. The unique index on `(user_id, idempotency_key)`
is what enforces that, not the code.

**Dates come from a timezone, not from the server clock.** `CURRENT_DATE` in a
UTC database rolls the day over mid-evening for an audience east of it, which
reads as arbitrary. Every date here — the top-up, a daily limit, a season — is
computed in `economy_timezone`.

## What is deliberately absent

This module used to charge accounts that had not played recently, pay a
growing bonus for consecutive days, and schedule short-lived better prices.
Each was a reason to open the app that had nothing to do with wanting to.
None of them survive: points do not expire, a missed day costs nothing, and no
price here is ever about to end.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import asyncpg

from ..config import Settings

logger = logging.getLogger(__name__)

__all__ = [
    "ClaimResult",
    "EconomyError",
    "claim_daily_topup",
    "day_start",
    "economy_date",
    "ensure_current_season",
    "next_claim_at",
    "roll_up_leaderboard",
]


class EconomyError(Exception):
    def __init__(self, code: str, detail: str, *, status: int = 400) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status = status


def economy_date(settings: Settings, now: datetime | None = None) -> date:
    """Today, in the timezone the economy runs on."""
    moment = now or datetime.now(UTC)
    return moment.astimezone(ZoneInfo(settings.economy_timezone)).date()


def day_start(settings: Settings, now: datetime | None = None) -> datetime:
    """The instant today began, in the economy timezone.

    What a daily limit is measured from. Using the same boundary as the
    top-up means a player sees one "day", not two that disagree by however far
    the server sits from them.
    """
    tz = ZoneInfo(settings.economy_timezone)
    return datetime.combine(economy_date(settings, now), datetime.min.time(), tzinfo=tz)


def next_claim_at(settings: Settings, claimed_on: date) -> datetime:
    """Midnight after `claimed_on`, in the economy timezone."""
    tz = ZoneInfo(settings.economy_timezone)
    return datetime.combine(claimed_on + timedelta(days=1), datetime.min.time(), tzinfo=tz)


@dataclass(frozen=True, slots=True)
class ClaimResult:
    claim_id: uuid.UUID
    claim_date: date
    amount_minor: int
    balance_after_minor: int
    next_claim_at: datetime


_LOCK_USER = "SELECT last_claim_date, status FROM users WHERE id = $1 FOR UPDATE"

# streak_bonus and streak_after are columns of a mechanic that no longer
# exists. They are written as "no bonus, day one" on every row rather than
# dropped, so the table reads the same for claims made before and after.
_INSERT_CLAIM = """
INSERT INTO daily_claims (user_id, claim_date, base_amount, streak_bonus, streak_after)
VALUES ($1, $2, $3, 0, 1)
ON CONFLICT (user_id, claim_date) DO NOTHING
RETURNING id
"""

_CREDIT = """
INSERT INTO ledger_entries (user_id, entry_type, amount, ref_type, ref_id,
                            idempotency_key, metadata)
VALUES ($1, 'DAILY_DRIP_CREDIT', $2, 'DAILY_CLAIM', $3, $4, '{"reason":"daily_topup"}'::jsonb)
RETURNING balance_after
"""


async def claim_daily_topup(
    conn: asyncpg.Connection,
    *,
    user_id: uuid.UUID,
    settings: Settings,
    today: date | None = None,
) -> ClaimResult:
    """Credit today's top-up, once.

    The row lock serialises a double-tapped button; the unique constraint on
    `(user_id, claim_date)` is the guarantee behind it. A second call on the
    same day raises rather than crediting again.

    A player on a break can still claim. A break is from forecasting, and the
    top-up is not a nudge to do that — withholding it would turn stepping away
    into something that costs points, which is the opposite of the intent.
    """
    today = today or economy_date(settings)

    user = await conn.fetchrow(_LOCK_USER, user_id)
    if user is None:
        raise EconomyError("user_not_found", "No such player.", status=404)
    if user["status"] != "ACTIVE":
        raise EconomyError("account_restricted", "This account cannot claim right now.", status=403)

    amount = settings.daily_topup_minor
    if amount <= 0:
        raise EconomyError("topup_disabled", "The daily top-up is switched off.", status=409)

    claim_id = await conn.fetchval(_INSERT_CLAIM, user_id, today, amount)
    if claim_id is None:
        raise EconomyError(
            "already_claimed", "Today's top-up has already been claimed.", status=409
        )

    balance = await conn.fetchval(
        _CREDIT, user_id, amount, claim_id, f"drip:{user_id}:{today.isoformat()}"
    )
    await conn.execute("UPDATE users SET last_claim_date = $2 WHERE id = $1", user_id, today)

    return ClaimResult(
        claim_id=claim_id,
        claim_date=today,
        amount_minor=amount,
        balance_after_minor=balance,
        next_claim_at=next_claim_at(settings, today),
    )


@dataclass
class LeaderboardReport:
    season_code: str | None = None
    entries: int = 0
    ranked: int = 0
    seasons_finalized: int = 0


def season_bounds(settings: Settings, today: date) -> tuple[str, datetime, datetime]:
    """The calendar month containing `today`, in the economy timezone."""
    tz = ZoneInfo(settings.economy_timezone)
    start = datetime(today.year, today.month, 1, tzinfo=tz)
    end = datetime(today.year + (today.month == 12), (today.month % 12) + 1, 1, tzinfo=tz)
    return f"{today.year:04d}-{today.month:02d}", start, end


async def ensure_current_season(
    conn: asyncpg.Connection, settings: Settings, *, today: date | None = None
) -> asyncpg.Record:
    today = today or economy_date(settings)
    code, start, end = season_bounds(settings, today)

    season = await conn.fetchrow("SELECT * FROM leaderboard_seasons WHERE code = $1", code)
    if season is not None:
        return season

    try:
        return await conn.fetchrow(
            """
            INSERT INTO leaderboard_seasons (code, starts_at, ends_at)
            VALUES ($1, $2, $3)
            RETURNING *
            """,
            code,
            start,
            end,
        )
    except (asyncpg.UniqueViolationError, asyncpg.ExclusionViolationError):
        return await conn.fetchrow("SELECT * FROM leaderboard_seasons WHERE code = $1", code)


_ROLLUP = """
WITH settled AS (
    SELECT p.user_id,
           count(*)                                          AS slips_settled,
           count(*) FILTER (WHERE p.status = 'WON')          AS slips_won,
           COALESCE(sum(p.total_cost), 0)                    AS total_staked,
           COALESCE(sum(p.settled_payout), 0)                AS total_returned,
           max(p.combined_odds) FILTER (WHERE p.status = 'WON') AS best_odds
      FROM predictions p
     WHERE p.status <> 'PENDING'
       AND p.settled_at >= $2 AND p.settled_at < $3
     GROUP BY p.user_id
),
scored AS (
    SELECT s.*,
           s.total_returned - s.total_staked AS net_profit,
           CASE WHEN s.total_staked > 0
                THEN (s.total_returned - s.total_staked)::numeric / s.total_staked
                ELSE 0 END AS roi,
           LEAST(1.0, s.total_staked::numeric / NULLIF($6::numeric, 0)) AS confidence
      FROM settled s
)
INSERT INTO leaderboard_entries (
    season_id, user_id, slips_settled, slips_won, total_staked, total_returned,
    net_profit, best_odds, score, updated_at
)
SELECT $1, user_id, slips_settled, slips_won, total_staked, total_returned, net_profit,
       best_odds,
       (net_profit / 100.0) * $4::numeric
         + (roi * 10000) * $5::numeric * COALESCE(confidence, 0),
       NOW()
  FROM scored
ON CONFLICT (season_id, user_id) DO UPDATE SET
    slips_settled  = EXCLUDED.slips_settled,
    slips_won      = EXCLUDED.slips_won,
    total_staked   = EXCLUDED.total_staked,
    total_returned = EXCLUDED.total_returned,
    net_profit     = EXCLUDED.net_profit,
    best_odds      = EXCLUDED.best_odds,
    score          = EXCLUDED.score,
    updated_at     = NOW()
"""

_RANK = """
WITH qualified AS (
    SELECT user_id, RANK() OVER (ORDER BY score DESC, total_staked DESC) AS position
      FROM leaderboard_entries
     WHERE season_id = $1 AND total_staked >= $2
)
UPDATE leaderboard_entries e
   SET rank = q.position
  FROM qualified q
 WHERE e.season_id = $1 AND e.user_id = q.user_id
"""


async def _count_season(
    conn: asyncpg.Connection, season: asyncpg.Record, settings: Settings
) -> None:
    """Rewrite one season's entries and ranks from the slips settled in it."""
    await conn.execute(
        _ROLLUP,
        season["id"],
        season["starts_at"],
        season["ends_at"],
        Decimal(str(settings.leaderboard_profit_weight)),
        Decimal(str(settings.leaderboard_roi_weight)),
        Decimal(settings.leaderboard_full_credit_volume_minor),
    )
    await conn.execute(
        "UPDATE leaderboard_entries SET rank = NULL WHERE season_id = $1", season["id"]
    )
    await conn.execute(_RANK, season["id"], settings.leaderboard_min_volume_minor)


async def roll_up_leaderboard(
    conn: asyncpg.Connection, settings: Settings, *, today: date | None = None
) -> LeaderboardReport:
    today = today or economy_date(settings)
    report = LeaderboardReport()

    # A season that has ended is counted one last time before it is closed.
    # Its standings were last written by whichever run came before the end —
    # up to an hour earlier on a server that never stops, and much longer on
    # one that was asleep — and anything settled in between belongs to that
    # season and would otherwise be in nobody's final standings. The rollup
    # reads by settlement time, so counting it late gives the same answer as
    # counting it at the stroke of midnight would have.
    ended = await conn.fetch(
        """
        SELECT id, starts_at, ends_at
          FROM leaderboard_seasons
         WHERE ends_at <= NOW() AND NOT is_finalized
         ORDER BY ends_at
           FOR UPDATE
        """
    )
    for closing in ended:
        await _count_season(conn, closing, settings)
    if ended:
        await conn.execute(
            """
            UPDATE leaderboard_seasons
               SET is_finalized = TRUE, finalized_at = NOW()
             WHERE id = ANY($1::uuid[])
            """,
            [closing["id"] for closing in ended],
        )
    report.seasons_finalized = len(ended)

    season = await ensure_current_season(conn, settings, today=today)
    if season["is_finalized"]:
        return report
    report.season_code = season["code"]

    await _count_season(conn, season, settings)

    report.entries = await conn.fetchval(
        "SELECT count(*) FROM leaderboard_entries WHERE season_id = $1", season["id"]
    )
    report.ranked = await conn.fetchval(
        "SELECT count(*) FROM leaderboard_entries WHERE season_id = $1 AND rank IS NOT NULL",
        season["id"],
    )
    return report
