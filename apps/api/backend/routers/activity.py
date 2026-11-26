"""Recent wins, from the ledger.

This backs the feed ticker. Every row is a slip that actually settled — the
amounts, the leg counts and the players are real. A ticker of invented wins
would be a fabricated record of other people's results, and it would work
precisely *because* readers assume it is real.

Displaying only wins is still a selective view, so `include_losses` is
available and the ticker can show both.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from .. import db
from ..schemas import ActivityEntry, ActivityFeed, Money
from ..security.dependencies import CurrentUser

router = APIRouter(prefix="/v1", tags=["activity"])

_RECENT = """
SELECT p.id, p.status, p.leg_count, p.settled_payout, p.stake, p.combined_odds,
       p.settled_at, u.first_name
  FROM predictions p
  JOIN users u ON u.id = p.user_id
 WHERE p.settled_at IS NOT NULL
   AND ($1::bool OR p.status IN ('WON', 'INSURED'))
   AND p.status <> 'VOID'
 ORDER BY p.settled_at DESC
 LIMIT $2
"""


def _display_name(first_name: str | None) -> str:
    """A label for the ticker that never carries the player's real handle.

    This used to return the Telegram `@username` verbatim whenever a player
    had one — a real, searchable handle, exposed to every other authenticated
    player through a feed nobody has to opt into appearing in. The initial is
    the same anonymisation already used for players with no username; it now
    applies to everyone, so it stops being a tell in itself (an initial-only
    label used to mean "this player has no username," which narrowed things
    for the players who used the ticker most: whoever was active enough to
    show up in it).
    """
    initial = (first_name or "?").strip()[:1].upper()
    return f"{initial}."


@router.get("/activity", response_model=ActivityFeed, summary="Recently settled slips")
async def recent_activity(
    _: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    include_losses: Annotated[bool, Query()] = False,
) -> ActivityFeed:
    async with db.acquire() as conn:
        rows = await conn.fetch(_RECENT, include_losses, limit)

    return ActivityFeed(
        entries=[
            ActivityEntry(
                id=str(row["id"]),
                player=_display_name(row["first_name"]),
                status=row["status"],
                leg_count=row["leg_count"],
                stake=Money.of(row["stake"]),
                payout=Money.of(row["settled_payout"]),
                combined_odds=str(row["combined_odds"]),
                settled_at=row["settled_at"],
            )
            for row in rows
        ]
    )
