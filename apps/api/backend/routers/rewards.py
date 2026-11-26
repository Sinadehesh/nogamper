"""Spending a balance on something outside the game.

Read the catalogue, redeem one item, review what you have claimed. Fulfilment
is not here: delivering an NFT or a gift is an operator job, and exposing it
on the player-facing API would be an endpoint whose only correct caller is
never the player.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from .. import db
from ..schemas import (
    ErrorResponse,
    Money,
    RedeemRequest,
    RedeemResponse,
    RewardCatalogue,
    RewardClaimItem,
    RewardClaimList,
    RewardItem,
)
from ..security.dependencies import CurrentUser
from ..services import rewards

router = APIRouter(prefix="/v1/rewards", tags=["rewards"])


def _blocked_reason(row, *, balance: int, lifetime_staked: int) -> str | None:
    """Why this player cannot take this reward, in the order they should hear it.

    Supply first: "sold out" is about the reward and settles the question, and
    telling somebody to go and earn six million coins for an item that no
    longer exists is the worse of the two messages. Then the personal gates,
    cheapest to fix last.
    """
    if row["total_supply"] is not None and row["claimed_count"] >= row["total_supply"]:
        return "reward_exhausted"
    if row["per_user_limit"] is not None and row["held_by_user"] >= row["per_user_limit"]:
        return "already_claimed"
    if lifetime_staked < row["min_lifetime_staked"]:
        return "not_enough_play"
    if balance < row["cost"]:
        return "insufficient_funds"
    return None


@router.get("", response_model=RewardCatalogue, summary="Rewards you can redeem")
async def catalogue(user: CurrentUser) -> RewardCatalogue:
    async with db.acquire() as conn:
        rows = await rewards.list_rewards(conn, user_id=user["id"])

    balance: int = user["coin_balance"]
    staked: int = user["lifetime_staked"]

    items = []
    for row in rows:
        reason = _blocked_reason(row, balance=balance, lifetime_staked=staked)
        items.append(
            RewardItem(
                code=row["code"],
                title=row["title"],
                description=row["description"],
                kind=row["kind"],
                image_url=row["image_url"],
                cost=Money.of(row["cost"]),
                min_lifetime_staked=Money.of(row["min_lifetime_staked"]),
                remaining=(
                    None
                    if row["total_supply"] is None
                    else max(0, row["total_supply"] - row["claimed_count"])
                ),
                held_by_user=row["held_by_user"],
                claimable=reason is None,
                blocked_reason=reason,
            )
        )

    return RewardCatalogue(rewards=items, balance=Money.of(balance))


@router.post(
    "/redeem",
    response_model=RedeemResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
    summary="Spend coins on a reward",
)
async def redeem(user: CurrentUser, body: RedeemRequest) -> RedeemResponse:
    """Burns the coins and reserves the item. Delivery follows separately.

    One transaction: the debit, the unit of supply and the claim row are a
    single fact. A commit that took the coins without recording what they
    bought would owe the player something with no record of it.
    """
    async with db.transaction() as conn:
        claim = await rewards.redeem(conn, user_id=user["id"], reward_code=body.reward_code)
        title = await conn.fetchval("SELECT title FROM rewards WHERE code = $1", body.reward_code)

    return RedeemResponse(
        claim_id=str(claim.id),
        reward_code=claim.reward_code,
        title=title,
        cost=Money.of(claim.cost_minor),
        balance=Money.of(claim.balance_after_minor),
        status="RESERVED",
    )


@router.get("/claims", response_model=RewardClaimList, summary="Rewards you have claimed")
async def claims(
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> RewardClaimList:
    async with db.acquire() as conn:
        rows = await rewards.list_claims(conn, user_id=user["id"], limit=limit)

    return RewardClaimList(
        claims=[
            RewardClaimItem(
                id=str(row["id"]),
                reward_code=row["reward_code"],
                title=row["title"],
                kind=row["kind"],
                image_url=row["image_url"],
                cost=Money.of(row["cost"]),
                status=row["status"],
                created_at=row["created_at"],
                fulfilled_at=row["fulfilled_at"],
                fulfilment=_as_dict(row["fulfilment"]),
            )
            for row in rows
        ]
    )


def _as_dict(value: object) -> dict:
    """asyncpg hands back JSONB as a string unless a codec is registered."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        import json

        try:
            parsed = json.loads(value)
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}
