"""The engagement economy: daily drip, inactivity decay, boosts, leaderboard.

Every coin that moves here goes through `ledger_entries` with a date-scoped
idempotency key, so a job that runs twice — a retry, an overlapping replica, a
manual re-run during an incident — credits or debits exactly once. The unique
index on `(user_id, idempotency_key)` is what enforces that, not the code.

**Dates come from a timezone, not from the server clock.** `CURRENT_DATE` in a
UTC database rolls the daily claim over mid-evening for an audience east of
it, which reads as arbitrary and silently shortens somebody's streak. Every
date here is computed in `economy_timezone`.

**Ledger metadata carries both a code and Farsi prose.** `reason` is stable and
machine-readable; `note` is what a human reads. Storing only the prose would
lock the ledger to one language, and storing only the code would make the
history unreadable to the people whose money it is.
"""

from __future__ import annotations

import logging
import random
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

import asyncpg

from ..config import Settings

logger = logging.getLogger(__name__)

__all__ = [
    "ClaimResult",
    "EconomyError",
    "claim_daily_drip",
    "economy_date",
    "ensure_current_season",
    "generate_boosts",
    "next_claim_at",
    "roll_up_leaderboard",
    "run_inactivity_decay",
    "streak_bonus_for",
]

NOTE_DAILY_DRIP = "هدیهٔ روزانه"
NOTE_STREAK_BONUS = "پاداش روزهای پیاپی"
NOTE_INACTIVITY_DECAY = "کسر به دلیل بی‌فعالیتی"


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


def next_claim_at(settings: Settings, claimed_on: date) -> datetime:
    """Midnight after `claimed_on`, in the economy timezone."""
    tz = ZoneInfo(settings.economy_timezone)
    return datetime.combine(claimed_on + timedelta(days=1), datetime.min.time(), tzinfo=tz)


def streak_bonus_for(streak: int, settings: Settings) -> int:
    """Bonus for the nth consecutive day. Day one earns the base drip only."""
    step = max(0, streak - 1) * settings.streak_bonus_step_minor
    return min(step, settings.streak_bonus_max_minor)


@dataclass(frozen=True, slots=True)
class ClaimResult:
    claim_id: uuid.UUID
    claim_date: date
    base_minor: int
    streak_bonus_minor: int
    streak: int
    balance_after_minor: int
    next_claim_at: datetime

    @property
    def total_minor(self) -> int:
        return self.base_minor + self.streak_bonus_minor


_LOCK_USER = "SELECT last_claim_date, streak_count, status FROM users WHERE id = $1 FOR UPDATE"

_INSERT_CLAIM = """
INSERT INTO daily_claims (user_id, claim_date, base_amount, streak_bonus, streak_after)
VALUES ($1, $2, $3, $4, $5)
ON CONFLICT (user_id, claim_date) DO NOTHING
RETURNING id
"""

_CREDIT = """
INSERT INTO ledger_entries (user_id, entry_type, amount, ref_type, ref_id,
                            idempotency_key, metadata)
VALUES ($1, $2::ledger_entry_type, $3, 'DAILY_CLAIM', $4, $5, $6::jsonb)
RETURNING balance_after
"""


async def claim_daily_drip(
    conn: asyncpg.Connection,
    *,
    user_id: uuid.UUID,
    settings: Settings,
    today: date | None = None,
) -> ClaimResult:
    """Credit today's drip, once.

    The row lock serialises a double-tapped button; the unique constraint on
    `(user_id, claim_date)` is the guarantee behind it. A second call on the
    same day raises rather than crediting again.
    """
    today = today or economy_date(settings)

    user = await conn.fetchrow(_LOCK_USER, user_id)
    if user is None:
        raise EconomyError("user_not_found", "No such player.", status=404)
    if user["status"] != "ACTIVE":
        raise EconomyError("account_restricted", "This account cannot claim right now.", status=403)

    last_claim: date | None = user["last_claim_date"]
    streak = (user["streak_count"] or 0) + 1 if last_claim == today - timedelta(days=1) else 1

    base = settings.daily_drip_minor
    bonus = streak_bonus_for(streak, settings)

    claim_id = await conn.fetchval(_INSERT_CLAIM, user_id, today, base, bonus, streak)
    if claim_id is None:
        raise EconomyError("already_claimed", "Today's gift has already been claimed.", status=409)

    balance = await conn.fetchval(
        _CREDIT,
        user_id,
        "DAILY_DRIP_CREDIT",
        base,
        claim_id,
        f"drip:{user_id}:{today.isoformat()}",
        f'{{"reason":"daily_drip","note":"{NOTE_DAILY_DRIP}","streak":{streak}}}',
    )

    if bonus > 0:
        balance = await conn.fetchval(
            _CREDIT,
            user_id,
            "STREAK_BONUS_CREDIT",
            bonus,
            claim_id,
            f"streak:{user_id}:{today.isoformat()}",
            f'{{"reason":"streak_bonus","note":"{NOTE_STREAK_BONUS}","streak":{streak}}}',
        )

    await conn.execute(
        "UPDATE users SET last_claim_date = $2, streak_count = $3 WHERE id = $1",
        user_id,
        today,
        streak,
    )

    return ClaimResult(
        claim_id=claim_id,
        claim_date=today,
        base_minor=base,
        streak_bonus_minor=bonus,
        streak=streak,
        balance_after_minor=balance,
        next_claim_at=next_claim_at(settings, today),
    )


@dataclass
class DecayReport:
    users_considered: int = 0
    users_charged: int = 0
    total_decayed_minor: int = 0
    skipped_at_floor: int = 0


_DECAY_CANDIDATES = """
SELECT u.id, u.coin_balance
  FROM users u
 WHERE u.status = 'ACTIVE'
   AND u.coin_balance > $1
   -- A player who has never predicted gets the same grace period from signup
   -- rather than being charged for not having started yet.
   AND COALESCE(u.last_prediction_at, u.created_at) < NOW() - make_interval(days => $2)
   AND NOT EXISTS (
         SELECT 1 FROM decay_events d WHERE d.user_id = u.id AND d.run_date = $3
       )
   AND ($4::bool IS FALSE OR NOT EXISTS (
         SELECT 1 FROM predictions p WHERE p.user_id = u.id AND p.status = 'PENDING'
       ))
 ORDER BY u.id
 LIMIT $5
"""

_INSERT_DECAY = """
INSERT INTO decay_events (user_id, run_date, days_inactive, decay_rate, amount,
                          balance_before, balance_after)
VALUES ($1, $2, $3, $4, $5, $6, $7)
ON CONFLICT (user_id, run_date) DO NOTHING
RETURNING id
"""


def decay_amount(balance: int, settings: Settings) -> int:
    """5% of balance, never taking it below the floor.

    The floor is what keeps decay from reading as confiscation: a dormant
    account still has something to come back to, which is the difference
    between a nudge and a reason to uninstall.
    """
    if balance <= settings.decay_floor_minor:
        return 0
    proportional = int(
        (Decimal(balance) * Decimal(str(settings.decay_rate))).quantize(
            Decimal(1), rounding=ROUND_HALF_UP
        )
    )
    return max(0, min(proportional, balance - settings.decay_floor_minor))


async def run_inactivity_decay(
    conn: asyncpg.Connection, settings: Settings, *, run_date: date | None = None
) -> DecayReport:
    run_date = run_date or economy_date(settings)
    report = DecayReport()

    candidates = await conn.fetch(
        _DECAY_CANDIDATES,
        settings.decay_floor_minor,
        settings.decay_inactive_days,
        run_date,
        settings.decay_skips_open_slips,
        settings.decay_batch_size,
    )
    report.users_considered = len(candidates)

    for row in candidates:
        amount = decay_amount(row["coin_balance"], settings)
        if amount <= 0:
            report.skipped_at_floor += 1
            continue

        balance_before = row["coin_balance"]
        event_id = await conn.fetchval(
            _INSERT_DECAY,
            row["id"],
            run_date,
            settings.decay_inactive_days,
            Decimal(str(settings.decay_rate)),
            amount,
            balance_before,
            balance_before - amount,
        )
        if event_id is None:
            continue

        await conn.execute(
            """
            INSERT INTO ledger_entries (user_id, entry_type, amount, ref_type, ref_id,
                                        idempotency_key, metadata)
            VALUES ($1, 'INACTIVITY_DECAY_DEBIT', $2, 'DECAY_EVENT', $3, $4, $5::jsonb)
            """,
            row["id"],
            -amount,
            event_id,
            f"decay:{row['id']}:{run_date.isoformat()}",
            f'{{"reason":"inactivity_decay","note":"{NOTE_INACTIVITY_DECAY}",'
            f'"rate":"{settings.decay_rate}"}}',
        )

        report.users_charged += 1
        report.total_decayed_minor += amount

    return report


@dataclass
class BoostReport:
    candidates: int = 0
    created: int = 0
    no_longshot_side: int = 0
    collisions: int = 0


_BOOST_CANDIDATES = """
SELECT m.id, m.raw_yes_prob, m.volume_usd, m.question
  FROM markets m
 WHERE m.status = 'ACTIVE'
   AND m.lock_at > NOW() + make_interval(hours => $1)
   AND m.volume_usd >= $2
   AND NOT EXISTS (
         SELECT 1 FROM odds_boosts b
          WHERE b.market_id = m.id AND b.is_active AND b.ends_at > NOW()
       )
 ORDER BY m.volume_usd DESC
 LIMIT $3
"""

_INSERT_BOOST = """
INSERT INTO odds_boosts (market_id, side, boost_multiplier, max_raw_prob, starts_at,
                         ends_at, max_total_stake, max_stake_per_user)
VALUES ($1, $2::outcome_side, $3, $4, NOW(), NOW() + make_interval(hours => $5), $6, $7)
RETURNING id
"""


def longshot_side(raw_yes_prob: Decimal, max_raw_prob: Decimal) -> str | None:
    """Which side, if either, is unlikely enough to be worth boosting.

    Not a coin toss between YES and NO: the quoting layer refuses to apply a
    boost whose side is likelier than `max_raw_prob`, so a randomly chosen
    side would be inert roughly half the time. Boosting a favourite also has
    no engagement value — the payout is already small, and inflating it is
    money handed away for nothing.
    """
    if raw_yes_prob <= max_raw_prob:
        return "YES"
    if (Decimal(1) - raw_yes_prob) <= max_raw_prob:
        return "NO"
    return None


async def generate_boosts(
    conn: asyncpg.Connection, settings: Settings, *, rng: random.Random | None = None
) -> BoostReport:
    rng = rng or random.SystemRandom()
    report = BoostReport()
    max_raw_prob = Decimal(str(settings.boost_max_raw_prob))

    candidates = await conn.fetch(
        _BOOST_CANDIDATES,
        settings.boost_duration_hours,
        Decimal(str(settings.boost_min_volume_usd)),
        settings.boosts_per_run * 4,
    )
    report.candidates = len(candidates)

    for row in candidates:
        if report.created >= settings.boosts_per_run:
            break

        side = longshot_side(row["raw_yes_prob"], max_raw_prob)
        if side is None:
            report.no_longshot_side += 1
            continue

        multiplier = Decimal(
            str(round(rng.uniform(settings.boost_min_multiplier, settings.boost_max_multiplier), 3))
        )

        try:
            await conn.fetchval(
                _INSERT_BOOST,
                row["id"],
                side,
                multiplier,
                max_raw_prob,
                settings.boost_duration_hours,
                settings.boost_max_total_stake_minor,
                settings.boost_max_stake_per_user_minor,
            )
        except asyncpg.ExclusionViolationError:
            report.collisions += 1
            continue

        report.created += 1
        logger.info(
            "boost created: market=%s side=%s multiplier=%s budget=%s",
            row["id"],
            side,
            multiplier,
            settings.boost_max_total_stake_minor,
        )

    return report


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


async def roll_up_leaderboard(
    conn: asyncpg.Connection, settings: Settings, *, today: date | None = None
) -> LeaderboardReport:
    today = today or economy_date(settings)
    report = LeaderboardReport()

    finalized = await conn.execute(
        """
        UPDATE leaderboard_seasons
           SET is_finalized = TRUE, finalized_at = NOW()
         WHERE ends_at <= NOW() AND NOT is_finalized
        """
    )
    report.seasons_finalized = int(finalized.rsplit(" ", 1)[-1])

    season = await ensure_current_season(conn, settings, today=today)
    if season["is_finalized"]:
        return report
    report.season_code = season["code"]

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

    report.entries = await conn.fetchval(
        "SELECT count(*) FROM leaderboard_entries WHERE season_id = $1", season["id"]
    )
    report.ranked = await conn.fetchval(
        "SELECT count(*) FROM leaderboard_entries WHERE season_id = $1 AND rank IS NOT NULL",
        season["id"],
    )
    return report
