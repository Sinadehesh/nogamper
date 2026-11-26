"""The brakes a player sets for themselves, and the mirror they can look in.

Two tools and one report:

  * a **daily limit** on how much may be staked in a day,
  * a **break**, during which no forecast can be placed at all,
  * the **reality check** — the player's own record, and what a bookmaker's
    margin would have taken from it.

These are play points. Nobody loses rent here. The tools exist anyway, and are
enforced as seriously as if it were money, for two reasons: somebody who came
to this site to get away from betting should be able to practise stopping in a
place where stopping is cheap; and a control that can be switched off the
moment it bites was never a control.

That second reason is the whole design. Both tools are **easy to tighten and
slow to loosen**:

  * a limit can be lowered at once, and raised or removed only after it has
    stood for a day;
  * a break can be extended at once, and never shortened.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

import asyncpg

from ..config import Settings

__all__ = [
    "CalibrationRow",
    "RealityCheckRow",
    "SaferPlayError",
    "loosen_available_at",
    "reality_check",
    "set_daily_limit",
    "start_break",
]


class SaferPlayError(Exception):
    def __init__(
        self, code: str, detail: str, *, status: int = 400, until: datetime | None = None
    ) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status = status
        self.until = until


_LOCK_LIMITS = """
SELECT daily_stake_limit, daily_limit_set_at, cooloff_until
  FROM users
 WHERE id = $1
   FOR UPDATE
"""


def loosen_available_at(
    limit: int | None, set_at: datetime | None, settings: Settings
) -> datetime | None:
    """When the current limit may next be raised or removed.

    None means "now": there is no limit to loosen, or nothing records when it
    was set — which is true of limits that predate this rule, and they are
    given the benefit of the doubt rather than locked from an invented date.
    """
    if limit is None or set_at is None:
        return None
    available = set_at + timedelta(seconds=settings.limit_loosen_delay_seconds)
    return available if available > datetime.now(UTC) else None


async def set_daily_limit(
    conn: asyncpg.Connection,
    *,
    user_id: uuid.UUID,
    new_limit: int | None,
    settings: Settings,
) -> None:
    """Change the daily limit, refusing to loosen one that is still fresh.

    Must run inside a transaction: the row is locked so that "is this a
    loosening" is decided against the limit that is actually in force, not one
    another tab replaced a moment ago.
    """
    row = await conn.fetchrow(_LOCK_LIMITS, user_id)
    if row is None:
        raise SaferPlayError("user_not_found", "No such player.", status=404)

    current: int | None = row["daily_stake_limit"]
    if new_limit == current:
        # Saving the same value again is not a change, and must not restart
        # the clock — otherwise opening the settings page and pressing save
        # would quietly extend the wait.
        return

    loosening = current is not None and (new_limit is None or new_limit > current)
    if loosening:
        available = loosen_available_at(current, row["daily_limit_set_at"], settings)
        if available is not None:
            raise SaferPlayError(
                "limit_locked",
                "A limit can be lowered at any time, but raised or removed only "
                "after it has been in place for a day.",
                status=409,
                until=available,
            )

    await conn.execute(
        """
        UPDATE users
           SET daily_stake_limit  = $2,
               daily_limit_set_at = CASE WHEN $2::bigint IS NULL THEN NULL ELSE NOW() END
         WHERE id = $1
        """,
        user_id,
        new_limit,
    )


async def start_break(
    conn: asyncpg.Connection,
    *,
    user_id: uuid.UUID,
    hours: int,
    settings: Settings,
) -> datetime:
    """Begin a break, or lengthen one already running. Returns when it ends.

    A request that would end *sooner* than the break in force changes nothing
    and returns the existing end. That is deliberate: there is no call a
    player can make that brings the end of a break closer.
    """
    if hours not in settings.break_options_hours:
        raise SaferPlayError(
            "bad_break_length",
            f"Choose one of: {', '.join(str(h) for h in settings.break_options_hours)} hours.",
        )

    row = await conn.fetchrow(_LOCK_LIMITS, user_id)
    if row is None:
        raise SaferPlayError("user_not_found", "No such player.", status=404)

    requested = datetime.now(UTC) + timedelta(hours=hours)
    current: datetime | None = row["cooloff_until"]
    if current is not None and current >= requested:
        return current

    await conn.execute("UPDATE users SET cooloff_until = $2 WHERE id = $1", user_id, requested)
    return requested


# ---------------------------------------------------------------------------
# Reality check
# ---------------------------------------------------------------------------

_RECORD = """
SELECT count(*)                                              AS placed,
       count(*) FILTER (WHERE status = 'PENDING')            AS open,
       count(*) FILTER (WHERE status <> 'PENDING')           AS settled,
       count(*) FILTER (WHERE status = 'WON')                AS won,
       count(*) FILTER (WHERE status = 'LOST')               AS lost,
       COALESCE(SUM(total_cost)     FILTER (WHERE status <> 'PENDING'), 0) AS staked,
       COALESCE(SUM(settled_payout) FILTER (WHERE status <> 'PENDING'), 0) AS returned,
       count(*) FILTER (WHERE placed_at >= NOW() - INTERVAL '30 days')     AS slips_30d,
       count(DISTINCT (placed_at AT TIME ZONE $2)::date)
           FILTER (WHERE placed_at >= NOW() - INTERVAL '30 days')           AS active_days_30d
  FROM predictions
 WHERE user_id = $1
"""

# What the same winning slips would have paid at a margin of $2 per pick.
# A bookmaker prices each pick at (1 - m) / p, so an n-pick slip pays
# (1 - m)^n of the fair amount. Voided picks are counted out: a void settles
# at 1.0 everywhere, margin or not.
_MARGIN_COST = """
SELECT COALESCE(SUM(
           p.settled_payout::numeric * (1 - power(1 - $2::numeric, won.legs))
       ), 0) AS cost
  FROM predictions p
  JOIN LATERAL (
        SELECT count(*) AS legs
          FROM prediction_legs pl
         WHERE pl.prediction_id = p.id AND pl.status = 'WON'
       ) won ON TRUE
 WHERE p.user_id = $1
   AND p.status = 'WON'
"""

_CALIBRATION = """
WITH picks AS (
    SELECT CASE WHEN pl.side = 'YES' THEN pl.raw_prob ELSE 1 - pl.raw_prob END AS prob,
           pl.status
      FROM prediction_legs pl
      JOIN predictions p ON p.id = pl.prediction_id
     WHERE p.user_id = $1
       AND pl.status IN ('WON', 'LOST')
)
SELECT LEAST(width_bucket(prob, 0, 1, 5), 5)       AS bucket,
       count(*)                                    AS picks,
       count(*) FILTER (WHERE status = 'WON')      AS correct,
       avg(prob)                                   AS expected
  FROM picks
 GROUP BY 1
 ORDER BY 1
"""

_PICKS = """
SELECT count(*)                                    AS settled,
       count(*) FILTER (WHERE pl.status = 'WON')   AS correct
  FROM prediction_legs pl
  JOIN predictions p ON p.id = pl.prediction_id
 WHERE p.user_id = $1
   AND pl.status IN ('WON', 'LOST')
"""

_BUCKETS = 5


@dataclass(frozen=True, slots=True)
class CalibrationRow:
    low: Decimal
    high: Decimal
    picks: int
    correct: int
    expected: Decimal | None


@dataclass(frozen=True, slots=True)
class RealityCheckRow:
    slips_placed: int
    slips_open: int
    slips_settled: int
    slips_won: int
    slips_lost: int
    picks_settled: int
    picks_correct: int
    staked: int
    returned: int
    margin_cost: int
    active_days_30d: int
    slips_30d: int
    calibration: list[CalibrationRow] = field(default_factory=list)

    @property
    def net(self) -> int:
        return self.returned - self.staked


async def reality_check(
    conn: asyncpg.Connection, *, user_id: uuid.UUID, settings: Settings
) -> RealityCheckRow:
    record = await conn.fetchrow(_RECORD, user_id, settings.economy_timezone)
    picks = await conn.fetchrow(_PICKS, user_id)
    cost = await conn.fetchval(_MARGIN_COST, user_id, Decimal(str(settings.reference_margin)))
    found = {row["bucket"]: row for row in await conn.fetch(_CALIBRATION, user_id)}

    step = Decimal(1) / _BUCKETS
    calibration = []
    for index in range(1, _BUCKETS + 1):
        row = found.get(index)
        calibration.append(
            CalibrationRow(
                low=step * (index - 1),
                high=step * index,
                picks=int(row["picks"]) if row else 0,
                correct=int(row["correct"]) if row else 0,
                expected=row["expected"] if row else None,
            )
        )

    return RealityCheckRow(
        slips_placed=int(record["placed"]),
        slips_open=int(record["open"]),
        slips_settled=int(record["settled"]),
        slips_won=int(record["won"]),
        slips_lost=int(record["lost"]),
        picks_settled=int(picks["settled"]),
        picks_correct=int(picks["correct"]),
        staked=int(record["staked"]),
        returned=int(record["returned"]),
        margin_cost=int(Decimal(cost).quantize(Decimal(1), rounding=ROUND_HALF_UP)),
        active_days_30d=int(record["active_days_30d"]),
        slips_30d=int(record["slips_30d"]),
        calibration=calibration,
    )
