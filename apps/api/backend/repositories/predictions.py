"""Slip placement and retrieval.

Placement is one transaction that must hold four things at once:

  1. **Exactly one slip per idempotency key.** A double-tapped button on flaky
     mobile data is the normal case, not the edge case.
  2. **The stake actually leaves the balance.** Via the ledger, so the debit
     and the slip commit together or not at all.
  3. **Boost budgets are consumed, not just read.** A boost checked and then
     used by someone else in the gap is a boost with no ceiling.
  4. **Market liability stays inside its cap.** Checked against what is
     already open, under the same transaction that adds to it.

The idempotency guard is a transaction-scoped advisory lock on
(user, key) rather than `ON CONFLICT DO NOTHING`. Two concurrent identical
requests then serialise cleanly: the second waits, sees the committed slip,
and returns it. Postgres releases the lock at commit or rollback, so a crashed
request cannot hold it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

import asyncpg

from ..config import Settings
from ..engine.quoting import SlipQuote

__all__ = [
    "PlacementError",
    "PlacementResult",
    "get_slip",
    "list_slips",
    "place_slip",
]


INSUFFICIENT_FUNDS_SQLSTATE = "PT001"


class PlacementError(Exception):
    def __init__(self, code: str, detail: str, *, market_id: str | None = None) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.market_id = market_id


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

_INSERT_SLIP = """
INSERT INTO predictions (
    user_id, idempotency_key, request_fingerprint, type, leg_count, stake,
    combined_odds, gross_potential_payout, payout_cap, potential_payout,
    has_insurance, insurance_premium, insurance_rate, insurance_min_legs,
    insurance_max_failed, house_edge_bps, parlay_bonus
)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)
RETURNING id
"""

_REFERRAL_BONUS = """
INSERT INTO ledger_entries (user_id, entry_type, amount, ref_type, ref_id,
                            idempotency_key, metadata)
VALUES ($1, 'REFERRAL_BONUS_CREDIT', $2, 'REFERRAL', $3, $4, $5)
ON CONFLICT (user_id, idempotency_key) DO NOTHING
"""

_RECENT_REFERRAL_BONUSES = """
SELECT count(*) FROM ledger_entries
 WHERE user_id = $1 AND entry_type = 'REFERRAL_BONUS_CREDIT'
   AND created_at > NOW() - make_interval(secs => $2)
"""

_INSERT_LEG = """
INSERT INTO prediction_legs (
    prediction_id, leg_index, market_id, event_id, side, raw_prob, vig_rate,
    boost_id, boost_multiplier, locked_odds
)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
"""

_CONSUME_BOOST = """
UPDATE odds_boosts
   SET consumed_stake = consumed_stake + $2
 WHERE id = $1
   AND is_active
   AND ends_at > NOW()
   AND consumed_stake + $2 <= max_total_stake
RETURNING max_total_stake - consumed_stake AS remaining
"""

_USER_BOOST_STAKE = """
SELECT COALESCE(SUM(p.stake), 0)
  FROM prediction_legs pl
  JOIN predictions p ON p.id = pl.prediction_id
 WHERE pl.boost_id = $1 AND p.user_id = $2
"""

_MARKET_BOOK = """
SELECT pl.market_id,
       pl.side,
       COALESCE(SUM(p.potential_payout), 0) AS owed,
       COALESCE(SUM(p.stake), 0)            AS staked
  FROM prediction_legs pl
  JOIN predictions p ON p.id = pl.prediction_id
 WHERE pl.market_id = ANY($1::uuid[])
   AND p.status = 'PENDING'
   AND pl.status = 'PENDING'
 GROUP BY pl.market_id, pl.side
"""

_TODAYS_STAKE = """
SELECT COALESCE(SUM(total_cost), 0)
  FROM predictions
 WHERE user_id = $1 AND placed_at >= date_trunc('day', NOW())
"""


async def _guard_account(conn: asyncpg.Connection, user: asyncpg.Record, cost: int) -> None:
    if user["status"] != "ACTIVE":
        raise PlacementError(
            "account_restricted",
            f"This account is {user['status'].lower()} and cannot place predictions.",
        )

    if user["coin_balance"] < cost:
        raise PlacementError("insufficient_funds", "Not enough coins for this stake.")

    limit = await conn.fetchval("SELECT daily_stake_limit FROM users WHERE id = $1", user["id"])
    if limit is not None:
        spent = await conn.fetchval(_TODAYS_STAKE, user["id"])
        if spent + cost > limit:
            raise PlacementError(
                "daily_limit_reached",
                "This would pass the daily limit set on this account.",
            )


def _other(side: str) -> str:
    return "NO" if side == "YES" else "YES"


async def _guard_liability(conn: asyncpg.Connection, quote: SlipQuote, settings: Settings) -> None:
    """Cap what the house can actually *lose* on one market and side.

    The house is the counterparty on every bet here — nobody is matched
    against another player — so with no cap a single market can accumulate
    unbounded exposure, and a boosted longshot is exactly where a group would
    point it.

    What is capped is **net** exposure, not gross liability:

        exposure = owed to this side  -  staked against it

    because when a side wins we pay its backers out of the money staked
    against them. A market with 100,000 on each side is close to a matched
    book and costs the house almost nothing however it resolves; the old
    gross check refused it anyway once the payouts alone crossed the cap.

    Netting is what lets `house_seed_minor` mean what it says: *the most the
    house will ever be down on one market*. Below that, the house is
    effectively taking the other side itself, so a player can bet even when
    nobody has taken the other side yet — which with no users is every bet.
    """
    if quote.priced.uncapped:
        return

    market_ids = [uuid.UUID(leg.market_id) for leg in quote.priced.legs]
    rows = await conn.fetch(_MARKET_BOOK, market_ids)
    owed = {(row["market_id"], row["side"]): row["owed"] for row in rows}
    staked = {(row["market_id"], row["side"]): row["staked"] for row in rows}

    for leg in quote.priced.legs:
        market = uuid.UUID(leg.market_id)
        projected_owed = owed.get((market, leg.side), 0) + quote.priced.potential_payout_minor
        against = staked.get((market, _other(leg.side)), 0)

        if projected_owed - against > settings.house_seed_minor:
            raise PlacementError(
                "market_at_capacity",
                "This market is not taking more action right now.",
                market_id=leg.market_id,
            )


async def _consume_boosts(conn: asyncpg.Connection, quote: SlipQuote, user_id: uuid.UUID) -> None:
    stake = quote.priced.stake_minor

    for leg in quote.priced.legs:
        if leg.boost_id is None:
            continue
        boost_id = uuid.UUID(leg.boost_id)

        per_user_cap = await conn.fetchval(
            "SELECT max_stake_per_user FROM odds_boosts WHERE id = $1", boost_id
        )
        already = await conn.fetchval(_USER_BOOST_STAKE, boost_id, user_id)
        if already + stake > per_user_cap:
            raise PlacementError(
                "boost_limit_reached",
                "The boost on this market is limited per player.",
                market_id=leg.market_id,
            )

        remaining = await conn.fetchval(_CONSUME_BOOST, boost_id, stake)
        if remaining is None:
            raise PlacementError(
                "boost_exhausted",
                "The boost on this market has just run out.",
                market_id=leg.market_id,
            )


async def place_slip(
    conn: asyncpg.Connection,
    *,
    user: asyncpg.Record,
    quote: SlipQuote,
    idempotency_key: str,
    request_fingerprint: str,
    settings: Settings,
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

    await _guard_account(conn, user, priced.total_cost_minor)
    await _guard_liability(conn, quote, settings)
    await _consume_boosts(conn, quote, user_id)

    insurance = priced.insurance
    insured = insurance.premium_minor > 0

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
        insured,
        insurance.premium_minor,
        insurance.rate if insured else None,
        insurance.min_legs if insured else None,
        insurance.covers_failed_legs if insured else None,
        priced.house_edge_bps,
        priced.parlay_bonus,
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
            leg.vig_rate,
            uuid.UUID(leg.boost_id) if leg.boost_id else None,
            leg.boost_multiplier,
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
            _leg_metadata(priced),
        )

        if insured:
            await conn.execute(
                """
                INSERT INTO ledger_entries (user_id, entry_type, amount, ref_type, ref_id,
                                            idempotency_key, metadata)
                VALUES ($1, 'INSURANCE_PREMIUM_DEBIT', $2, 'PREDICTION', $3, $4, $5)
                """,
                user_id,
                -insurance.premium_minor,
                prediction_id,
                f"premium:{prediction_id}",
                f'{{"rate":"{insurance.rate}","fair_rate":"{insurance.fair_rate}"}}',
            )
    except asyncpg.PostgresError as exc:
        if getattr(exc, "sqlstate", None) == INSUFFICIENT_FUNDS_SQLSTATE:
            raise PlacementError("insufficient_funds", "Not enough coins for this stake.") from exc
        raise

    await conn.execute("UPDATE users SET last_prediction_at = NOW() WHERE id = $1", user_id)

    if user["referred_by"] is not None:
        await _credit_referrer(
            conn, referrer_id=user["referred_by"], referred_id=user_id, settings=settings
        )

    return PlacementResult(prediction_id=prediction_id, replayed=False)


async def _credit_referrer(
    conn: asyncpg.Connection,
    *,
    referrer_id: uuid.UUID,
    referred_id: uuid.UUID,
    settings: Settings,
) -> None:
    """Pay the referrer, once, for the player they brought in actually
    playing — not for the account existing.

    Called unconditionally on every bet a referred player places. The first
    call wins the idempotency key and every later one collides and does
    nothing, so this never needs to work out whether *this* bet happens to be
    the player's first — the ledger already enforces "at most once" more
    reliably than a `COUNT(*) FROM predictions` check taken outside a lock
    ever could.

    The rate cap is the only thing standing between this and a Telegram
    account farm minting coins for itself: see Settings.
    referral_bonus_max_per_window. It is a plain COUNT
    with no row lock, matching the same trade-off messages.py already makes
    for its own rate limit — an approximate guard against an abuse pattern,
    not a security boundary, and not worth serialising every referred
    player's first bet over.
    """
    if settings.referral_bonus_minor <= 0:
        return

    recent = await conn.fetchval(
        _RECENT_REFERRAL_BONUSES, referrer_id, settings.referral_bonus_window_seconds
    )
    if recent >= settings.referral_bonus_max_per_window:
        return

    await conn.execute(
        _REFERRAL_BONUS,
        referrer_id,
        settings.referral_bonus_minor,
        referred_id,
        f"referral:{referred_id}",
        f'{{"reason":"referral","referred_user_id":"{referred_id}"}}',
    )


def _leg_metadata(priced) -> str:
    boosted = sum(1 for leg in priced.legs if leg.boost_id)
    return (
        f'{{"legs":{len(priced.legs)},"combined_odds":"{priced.combined_odds}",'
        f'"boosted_legs":{boosted},"house_edge_bps":{priced.house_edge_bps}}}'
    )


_SLIP_LEGS = """
SELECT pl.prediction_id, pl.leg_index, pl.market_id, pl.side, pl.raw_prob,
       pl.boost_multiplier, pl.locked_odds, pl.status, pl.settled_at,
       m.question, m.category, m.lock_at, m.resolution
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


async def market_liability(
    conn: asyncpg.Connection, market_ids: list[uuid.UUID]
) -> dict[tuple[uuid.UUID, str], Decimal]:
    rows = await conn.fetch(_MARKET_BOOK, market_ids)
    return {(row["market_id"], row["side"]): row["owed"] for row in rows}


async def market_book(
    conn: asyncpg.Connection, market_ids: list[uuid.UUID]
) -> dict[tuple[uuid.UUID, str], dict[str, int]]:
    """Owed and staked per market and side — what the UI shows as the pool."""
    rows = await conn.fetch(_MARKET_BOOK, market_ids)
    return {
        (row["market_id"], row["side"]): {"owed": int(row["owed"]), "staked": int(row["staked"])}
        for row in rows
    }
