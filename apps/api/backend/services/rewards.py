"""Redeeming a balance for something outside the game.

The mechanic is a burn. A player who has ground to thirty million coins spends
them on a reward, and the coins are gone — a reward that left the balance
intact would be claimable again the same second, and the number would stop
meaning anything. The burn is the whole design; the item on the other end is
fulfilment detail.

**Two phases, because fulfilment leaves the database.** Minting an NFT or
sending a gift is slow and can fail. Doing it inside the redeeming transaction
would mean the first failure leaves a player who has paid and has no record of
what they are owed. So `redeem` only reserves — it debits the coins, takes a
unit of supply, and writes a RESERVED claim. Delivery happens afterwards, and
`fulfil` or `fail` records how it went. A FAILED claim is refunded, which
returns both the coins and the unit of supply.

**Nothing here computes a balance.** The ledger trigger does that, under a row
lock, and raises PT001 when the balance would go negative. Checking the
balance in Python first and then debiting would be a race with every other
tab the player has open; the check below exists only to produce a decent error
message, and the trigger remains the authority.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass

import asyncpg

logger = logging.getLogger(__name__)

__all__ = [
    "ClaimRecord",
    "RewardError",
    "fail_claim",
    "fulfil_claim",
    "list_claims",
    "list_rewards",
    "redeem",
    "refund_claim",
]

INSUFFICIENT_FUNDS_SQLSTATE = "PT001"

NOTE_REDEEM = "خرید جایزه"
NOTE_REFUND = "بازگشت سکه‌های جایزه"


class RewardError(Exception):
    def __init__(self, code: str, detail: str, *, status: int = 400) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status = status


@dataclass(frozen=True, slots=True)
class ClaimRecord:
    id: uuid.UUID
    reward_code: str
    cost_minor: int
    status: str
    balance_after_minor: int


_LIST_REWARDS = """
SELECT r.code, r.title, r.description, r.kind, r.image_url, r.cost,
       r.min_lifetime_staked, r.total_supply, r.claimed_count, r.per_user_limit,
       COALESCE(held.count, 0) AS held_by_user
  FROM rewards r
  LEFT JOIN LATERAL (
      SELECT count(*) AS count
        FROM reward_claims c
       WHERE c.reward_code = r.code
         AND c.user_id = $1
         AND c.status <> 'REFUNDED'
  ) held ON TRUE
 WHERE r.is_active
 ORDER BY r.sort_order, r.code
"""

_LIST_CLAIMS = """
SELECT c.id, c.reward_code, c.cost, c.status, c.fulfilment, c.failure_reason,
       c.created_at, c.fulfilled_at, r.title, r.kind, r.image_url
  FROM reward_claims c
  JOIN rewards r ON r.code = c.reward_code
 WHERE c.user_id = $1
 ORDER BY c.created_at DESC
 LIMIT $2
"""


async def list_rewards(conn: asyncpg.Connection, *, user_id: uuid.UUID) -> list[asyncpg.Record]:
    """The active catalogue, with this player's holdings joined in.

    Holdings come back with the catalogue rather than from a second call
    because every row needs them to decide whether it is claimable, and a
    per-row round trip for that is the classic way to make a five-item list
    cost eleven queries.
    """
    return await conn.fetch(_LIST_REWARDS, user_id)


async def list_claims(
    conn: asyncpg.Connection, *, user_id: uuid.UUID, limit: int = 50
) -> list[asyncpg.Record]:
    return await conn.fetch(_LIST_CLAIMS, user_id, limit)


_LOCK_REWARD = """
SELECT code, title, cost, kind, min_lifetime_staked, total_supply,
       claimed_count, per_user_limit, is_active
  FROM rewards WHERE code = $1 FOR UPDATE
"""

_LOCK_USER = """
SELECT coin_balance, lifetime_staked, status
  FROM users WHERE id = $1 FOR UPDATE
"""

_COUNT_HELD = """
SELECT count(*) FROM reward_claims
 WHERE user_id = $1 AND reward_code = $2 AND status <> 'REFUNDED'
"""

_TAKE_SUPPLY = """
UPDATE rewards SET claimed_count = claimed_count + 1
 WHERE code = $1 AND (total_supply IS NULL OR claimed_count < total_supply)
RETURNING claimed_count
"""

_INSERT_CLAIM = """
INSERT INTO reward_claims (user_id, reward_code, cost)
VALUES ($1, $2, $3)
RETURNING id
"""

_DEBIT = """
INSERT INTO ledger_entries (user_id, entry_type, amount, ref_type, ref_id,
                            idempotency_key, metadata)
VALUES ($1, 'REWARD_REDEEM_DEBIT', $2, 'REWARD_CLAIM', $3, $4, $5::jsonb)
RETURNING balance_after
"""


async def redeem(conn: asyncpg.Connection, *, user_id: uuid.UUID, reward_code: str) -> ClaimRecord:
    """Burn the coins, reserve a unit, and record what is owed.

    Must be called inside a transaction: the debit, the supply increment and
    the claim row are one atomic fact. Committing the debit without the claim
    would take a player's coins and owe them nothing.
    """
    reward = await conn.fetchrow(_LOCK_REWARD, reward_code)
    if reward is None or not reward["is_active"]:
        raise RewardError("reward_unavailable", "This reward is not available.", status=404)

    user = await conn.fetchrow(_LOCK_USER, user_id)
    if user is None:
        raise RewardError("user_not_found", "No such player.", status=404)
    if user["status"] != "ACTIVE":
        raise RewardError("account_restricted", "This account cannot redeem right now.", status=403)

    cost: int = reward["cost"]

    if user["lifetime_staked"] < reward["min_lifetime_staked"]:
        raise RewardError(
            "not_enough_play",
            "This reward unlocks after you have staked more coins in play.",
            status=403,
        )

    if reward["per_user_limit"] is not None:
        held = await conn.fetchval(_COUNT_HELD, user_id, reward_code)
        if held >= reward["per_user_limit"]:
            raise RewardError(
                "already_claimed", "You have already claimed this reward.", status=409
            )

    if user["coin_balance"] < cost:
        raise RewardError("insufficient_funds", "Not enough coins for this reward.", status=400)

    if await conn.fetchval(_TAKE_SUPPLY, reward_code) is None:
        raise RewardError("reward_exhausted", "This reward is fully claimed.", status=409)

    claim_id = await conn.fetchval(_INSERT_CLAIM, user_id, reward_code, cost)

    metadata = json.dumps(
        {
            "reason": "reward_redeem",
            "note": NOTE_REDEEM,
            "reward_code": reward_code,
            "reward_kind": reward["kind"],
        },
        ensure_ascii=False,
    )

    try:
        balance = await conn.fetchval(
            _DEBIT, user_id, -cost, claim_id, f"reward:{claim_id}", metadata
        )
    except asyncpg.PostgresError as exc:
        if getattr(exc, "sqlstate", None) == INSUFFICIENT_FUNDS_SQLSTATE:
            raise RewardError(
                "insufficient_funds", "Not enough coins for this reward.", status=400
            ) from exc
        raise

    logger.info(
        "reward reserved: user=%s reward=%s claim=%s cost=%s",
        user_id,
        reward_code,
        claim_id,
        cost,
    )
    return ClaimRecord(
        id=claim_id,
        reward_code=reward_code,
        cost_minor=cost,
        status="RESERVED",
        balance_after_minor=balance,
    )


_FULFIL = """
UPDATE reward_claims
   SET status = 'FULFILLED', fulfilment = $2::jsonb, fulfilled_at = NOW(),
       failure_reason = NULL
 WHERE id = $1 AND status IN ('RESERVED','FAILED')
RETURNING id
"""

_FAIL = """
UPDATE reward_claims
   SET status = 'FAILED', failure_reason = $2
 WHERE id = $1 AND status = 'RESERVED'
RETURNING id
"""


async def fulfil_claim(conn: asyncpg.Connection, *, claim_id: uuid.UUID, fulfilment: dict) -> None:
    """Record delivery. `fulfilment` is the proof — a tx hash, a gift code.

    FAILED is an accepted starting state as well as RESERVED: a mint that
    timed out and then landed is delivered, and refusing to record that would
    leave the claim queued for a refund it no longer deserves.
    """
    updated = await conn.fetchval(_FULFIL, claim_id, json.dumps(fulfilment, ensure_ascii=False))
    if updated is None:
        raise RewardError(
            "claim_not_fulfillable",
            "This claim is not awaiting fulfilment.",
            status=409,
        )


async def fail_claim(conn: asyncpg.Connection, *, claim_id: uuid.UUID, reason: str) -> None:
    """Mark a claim undeliverable. Does not refund — `refund_claim` does that,
    so a transient failure can be retried without the coins bouncing back and
    forth across the ledger."""
    if await conn.fetchval(_FAIL, claim_id, reason) is None:
        raise RewardError("claim_not_failable", "This claim is not reserved.", status=409)


_LOCK_CLAIM = """
SELECT id, user_id, reward_code, cost, status
  FROM reward_claims WHERE id = $1 FOR UPDATE
"""

_RELEASE_SUPPLY = """
UPDATE rewards SET claimed_count = GREATEST(claimed_count - 1, 0) WHERE code = $1
"""

_MARK_REFUNDED = """
UPDATE reward_claims SET status = 'REFUNDED', refunded_at = NOW() WHERE id = $1
"""

_REFUND = """
INSERT INTO ledger_entries (user_id, entry_type, amount, ref_type, ref_id,
                            idempotency_key, metadata)
VALUES ($1, 'REWARD_REFUND_CREDIT', $2, 'REWARD_CLAIM', $3, $4, $5::jsonb)
RETURNING balance_after
"""


async def refund_claim(conn: asyncpg.Connection, *, claim_id: uuid.UUID) -> int:
    """Give back the coins and the unit of supply. Returns the new balance.

    Idempotent by construction: `uq_ledger_ref_once` permits one
    REWARD_REFUND_CREDIT per claim, and the status guard below rejects a
    second attempt before it gets that far.
    """
    claim = await conn.fetchrow(_LOCK_CLAIM, claim_id)
    if claim is None:
        raise RewardError("claim_not_found", "No such claim.", status=404)
    if claim["status"] == "REFUNDED":
        raise RewardError("already_refunded", "This claim was already refunded.", status=409)
    if claim["status"] == "FULFILLED":
        raise RewardError(
            "claim_fulfilled", "A delivered reward cannot be refunded here.", status=409
        )

    metadata = json.dumps(
        {"reason": "reward_refund", "note": NOTE_REFUND, "reward_code": claim["reward_code"]},
        ensure_ascii=False,
    )
    balance = await conn.fetchval(
        _REFUND,
        claim["user_id"],
        claim["cost"],
        claim_id,
        f"reward-refund:{claim_id}",
        metadata,
    )

    await conn.execute(_RELEASE_SUPPLY, claim["reward_code"])
    await conn.execute(_MARK_REFUNDED, claim_id)

    logger.info("reward refunded: claim=%s amount=%s", claim_id, claim["cost"])
    return balance
