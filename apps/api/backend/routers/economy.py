"""Player-facing economy: the free daily top-up and the leaderboard."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from .. import db
from ..config import Settings, get_settings
from ..schemas import (
    ClaimResponse,
    ErrorResponse,
    LeaderboardPage,
    LeaderboardRow,
    Money,
)
from ..security.dependencies import CurrentUser
from ..services import economy

router = APIRouter(prefix="/v1/economy", tags=["economy"])


@router.post(
    "/claim",
    response_model=ClaimResponse,
    responses={409: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
    summary="Claim today's free top-up",
)
async def claim(
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ClaimResponse:
    async with db.transaction() as conn:
        result = await economy.claim_daily_topup(conn, user_id=user["id"], settings=settings)

    return ClaimResponse(
        claim_date=result.claim_date.isoformat(),
        amount=Money.of(result.amount_minor),
        balance=Money.of(result.balance_after_minor),
        next_claim_at=result.next_claim_at,
    )


_LEADERBOARD = """
SELECT e.rank, e.user_id, e.slips_settled, e.slips_won, e.total_staked,
       e.total_returned, e.net_profit, e.best_odds, e.score,
       u.first_name
  FROM leaderboard_entries e
  JOIN users u ON u.id = e.user_id
 WHERE e.season_id = $1 AND e.rank IS NOT NULL
 ORDER BY e.rank
 LIMIT $2
"""


def _display_name(first_name: str | None) -> str:
    """A label for the leaderboard that never carries the player's own name.

    An initial and nothing else. Whoever reaches rank 1 is the most-viewed
    row on this page, and a display name is free text a stranger typed — so
    printing it here would make the top of the table both the most exposed
    place to be named and the most rewarding place to put something that
    should not be on screen. A player finds themselves by `is_me`, not by
    reading their name.
    """
    return f"{(first_name or '?').strip()[:1].upper()}."


@router.get(
    "/leaderboard",
    response_model=LeaderboardPage,
    summary="This season's standings",
)
async def leaderboard(
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> LeaderboardPage:
    async with db.acquire() as conn:
        season = await economy.ensure_current_season(conn, settings)
        rows = await conn.fetch(_LEADERBOARD, season["id"], limit)
        mine = await conn.fetchrow(
            "SELECT rank, net_profit, total_staked, slips_settled, slips_won"
            "  FROM leaderboard_entries WHERE season_id = $1 AND user_id = $2",
            season["id"],
            user["id"],
        )

    def to_row(row) -> LeaderboardRow:
        return LeaderboardRow(
            rank=row["rank"],
            player=_display_name(row["first_name"]),
            slips_settled=row["slips_settled"],
            slips_won=row["slips_won"],
            total_staked=Money.of(row["total_staked"]),
            net_profit=Money.of(row["net_profit"]),
            best_odds=str(row["best_odds"]) if row["best_odds"] is not None else None,
            is_me=row["user_id"] == user["id"],
        )

    return LeaderboardPage(
        season=season["code"],
        ends_at=season["ends_at"],
        min_volume_to_rank=Money.of(settings.leaderboard_min_volume_minor),
        rows=[to_row(row) for row in rows],
        my_rank=mine["rank"] if mine else None,
        my_net_profit=Money.of(mine["net_profit"]) if mine else Money.of(0),
        my_total_staked=Money.of(mine["total_staked"]) if mine else Money.of(0),
    )
