"""Slip placement and retrieval.

Placement is one transaction that must hold three things at once:

  1. **Exactly one slip per idempotency key.** A double-tapped button on flaky
     mobile data is the normal case, not the edge case.
  2. **The stake actually leaves the balance.** Via the ledger, so the debit
     and the slip commit together or not at all.
  3. **The player's own limits hold.** A daily limit or a break they set is
     checked under a lock on their row, so two requests arriving together
     cannot both slip under it.

The idempotency guard is a transaction-scoped advisory lock on
(user, key) rather than `ON CONFLICT DO NOTHING`. Two concurrent identical
requests then serialise cleanly: the second waits, sees the committed slip,
and returns it. Postgres releases the lock at commit or rollback, so a crashed
request cannot hold it.

## What is no longer guarded

There used to be a cap on how much the house could lose on one market. There
is no house here: nobody is the counterparty, points are not scarce, and a
forecast is not refused because too many people agree with it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

import asyncpg

from ..engine.quoting import SlipQuote

__all__ = [
    "PlacementError",
    "PlacementResult",
    "get_slip",
    "list_slips",
    "place_slip",
    "staked_since",
]


INSUFFICIENT_FUNDS_SQLSTATE = "PT001"


class PlacementError(Exception):
    def __init__(
        self,
        code: str,
        detail: str,
        *,
        market_id: str | None = None,
        until: datetime | None = None,
    ) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.market_id = market_id
        self.until = until
        """When the refusal lifts, for the ones that do — a break ending."""


@dataclass(frozen=True, slots=True)
class PlacementResult:
    prediction_id: uuid.UUID
    replayed: bool
    """True when an earlier identical request already created this slip."""


_LOCK_IDEMPOTENCY = """
SELECT pg_advisory_xact_lock(hashtext($1::text), hashtext($2::text))
"""

_FIND_EXISTING = """
SELECT id, request_fingerprint FROM predictions
 WHERE user_id = $1 AND idempotency_key = $2
"""

# The insurance, margin and bonus columns are left to their defaults — off,
# zero and 1.0. They describe a product this one no longer is; the columns
# stay because slips placed before the change still read them at settlement.
_INSERT_SLIP = """
INSERT INTO predictions (
    user_id, idempotency_key, request_fingerprint, type, leg_count, stake,
    combined_odds, gross_potential_payout, payout_cap, potential_payout
)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
RETURNING id
"""

_INSERT_LEG = """
INSERT INTO prediction_legs (
    prediction_id, leg_index, market_id, event_id, side, raw_prob, vig_rate, locked_odds
)
VALUES ($1, $2, $3, $4, $5, $6, 0, $7)
"""

_STAKED_SINCE = """
SELECT COALESCE(SUM(total_cost), 0)
  FROM predictions
 WHERE user_id = $1 AND placed_at >= $2
"""

_LOCK_ACCOUNT = """
SELECT status::text AS status, coin_balance, daily_stake_limit, cooloff_until
  FROM users
 WHERE id = $1
   FOR UPDATE
"""


async def staked_since(conn: asyncpg.Connection, user_id: uuid.UUID, since: datetime) -> int:
    """Everything this player has staked from `since` on, settled or not."""
    return int(await conn.fetchval(_STAKED_SINCE, user_id, since))


async def _guard_account(
    conn: asyncpg.Connection, user_id: uuid.UUID, cost: int, *, day_start: datetime
) -> None:
    """Refuse a slip the account is not in a state to place.

    Reads the row afresh, under a lock, rather than trusting the copy the
    request was authenticated with. That copy was loaded before this
    transaction began: a break started in another tab a moment ago is not on
    it, and neither is a stake that committed in between. The lock is the same
    one the ledger trigger takes a few statements later, so it costs nothing
    extra — it only arrives early enough to make the limit check true.

    The order is the order the player should hear it in. A break comes before
    the balance: somebody who asked not to play should be told that, not
    invited to top up.
    """
    account = await conn.fetchrow(_LOCK_ACCOUNT, user_id)
    if account is None or account["status"] != "ACTIVE":
        status = account["status"].lower() if account else "missing"
        raise PlacementError(
            "account_restricted",
            f"This account is {status} and cannot place forecasts.",
        )

    until = account["cooloff_until"]
    if until is not None and until > datetime.now(until.tzinfo):
        raise PlacementError(
            "on_break",
            "You are taking a break. Forecasting opens again when it ends.",
            until=until,
        )

    limit = account["daily_stake_limit"]
    if limit is not None:
        spent = await staked_since(conn, user_id, day_start)
        if spent + cost > limit:
            raise PlacementError(
                "daily_limit_reached",
                "This would pass the daily limit you set for yourself.",
            )

    if account["coin_balance"] < cost:
        raise PlacementError("insufficient_funds", "Not enough points for this stake.")


async def place_slip(
    conn: asyncpg.Connection,
    *,
    user: asyncpg.Record,
    quote: SlipQuote,
    idempotency_key: str,
    request_fingerprint: str,
    day_start: datetime,
) -> PlacementResult:
    user_id: uuid.UUID = user["id"]
    priced = quote.priced

    await conn.execute(_LOCK_IDEMPOTENCY, str(user_id), idempotency_key)

    existing = await conn.fetchrow(_FIND_EXISTING, user_id, idempotency_key)
    if existing is not None:
        if existing["request_fingerprint"] != request_fingerprint:
            raise PlacementError(
                "idempotency_key_reused",
                "This Idempotency-Key was already used for a different slip.",
            )
        return PlacementResult(prediction_id=existing["id"], replayed=True)

    await _guard_account(conn, user_id, priced.stake_minor, day_start=day_start)

    prediction_id = await conn.fetchval(
        _INSERT_SLIP,
        user_id,
        idempotency_key,
        request_fingerprint,
        "SINGLE" if len(priced.legs) == 1 else "PARLAY",
        len(priced.legs),
        priced.stake_minor,
        priced.combined_odds,
        priced.gross_payout_minor,
        priced.payout_cap_minor,
        priced.potential_payout_minor,
    )

    for index, leg in enumerate(priced.legs, start=1):
        context = quote.markets[uuid.UUID(leg.market_id)]
        await conn.execute(
            _INSERT_LEG,
            prediction_id,
            index,
            context.id,
            context.event_id,
            leg.side,
            leg.raw_prob,
            leg.locked_odds,
        )

    try:
        await conn.execute(
            """
            INSERT INTO ledger_entries (user_id, entry_type, amount, ref_type, ref_id,
                                        idempotency_key, metadata)
            VALUES ($1, 'STAKE_DEBIT', $2, 'PREDICTION', $3, $4, $5)
            """,
            user_id,
            -priced.stake_minor,
            prediction_id,
            f"stake:{prediction_id}",
            f'{{"legs":{len(priced.legs)},"combined_odds":"{priced.combined_odds}"}}',
        )
    except asyncpg.PostgresError as exc:
        if getattr(exc, "sqlstate", None) == INSUFFICIENT_FUNDS_SQLSTATE:
            raise PlacementError("insufficient_funds", "Not enough points for this stake.") from exc
        raise

    await conn.execute("UPDATE users SET last_prediction_at = NOW() WHERE id = $1", user_id)

    return PlacementResult(prediction_id=prediction_id, replayed=False)


_SLIP_LEGS = """
SELECT pl.prediction_id, pl.leg_index, pl.market_id, pl.side, pl.raw_prob,
       pl.locked_odds, pl.status, pl.settled_at,
       COALESCE(m.question_source, m.question) AS question,
       m.category, m.lock_at, m.resolution
  FROM prediction_legs pl
  JOIN markets m ON m.id = pl.market_id
 WHERE pl.prediction_id = ANY($1::uuid[])
 ORDER BY pl.prediction_id, pl.leg_index
"""


async def list_slips(
    conn: asyncpg.Connection,
    user_id: uuid.UUID,
    *,
    status: str | None,
    limit: int,
    before: uuid.UUID | None,
) -> tuple[list[asyncpg.Record], dict[uuid.UUID, list[asyncpg.Record]]]:
    slips = await conn.fetch(
        """
        SELECT p.id, p.type, p.leg_count, p.stake, p.combined_odds, p.gross_potential_payout,
       p.payout_cap, p.potential_payout, p.has_insurance, p.insurance_premium,
       p.insurance_rate, p.insurance_max_failed, p.total_cost, p.status,
       p.settled_payout, p.settlement_note, p.placed_at, p.settled_at
          FROM predictions p
         WHERE p.user_id = $1
           AND ($2::text IS NULL OR p.status = $2::slip_status)
           AND ($3::uuid IS NULL OR p.placed_at < (
                   SELECT placed_at FROM predictions WHERE id = $3))
         ORDER BY p.placed_at DESC, p.id DESC
         LIMIT $4
        """,
        user_id,
        status,
        before,
        limit,
    )
    return slips, await _legs_for(conn, slips)


async def get_slip(
    conn: asyncpg.Connection, user_id: uuid.UUID, prediction_id: uuid.UUID
) -> tuple[asyncpg.Record | None, list[asyncpg.Record]]:
    slip = await conn.fetchrow(
        """
        SELECT p.id, p.type, p.leg_count, p.stake, p.combined_odds, p.gross_potential_payout,
       p.payout_cap, p.potential_payout, p.has_insurance, p.insurance_premium,
       p.insurance_rate, p.insurance_max_failed, p.total_cost, p.status,
       p.settled_payout, p.settlement_note, p.placed_at, p.settled_at
          FROM predictions p
         WHERE p.id = $1 AND p.user_id = $2
        """,
        prediction_id,
        user_id,
    )
    if slip is None:
        return None, []
    return slip, (await _legs_for(conn, [slip])).get(prediction_id, [])


async def _legs_for(
    conn: asyncpg.Connection, slips: list[asyncpg.Record]
) -> dict[uuid.UUID, list[asyncpg.Record]]:
    if not slips:
        return {}
    rows = await conn.fetch(_SLIP_LEGS, [slip["id"] for slip in slips])
    grouped: dict[uuid.UUID, list[asyncpg.Record]] = {}
    for row in rows:
        grouped.setdefault(row["prediction_id"], []).append(row)
    return grouped
