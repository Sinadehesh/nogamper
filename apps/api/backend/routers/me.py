from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends

from .. import db
from ..config import Settings, get_settings
from ..repositories import auth as auth_repo
from ..schemas import Money, UserProfile
from ..security.dependencies import CurrentUser

router = APIRouter(prefix="/v1", tags=["me"])


def build_invite_link(settings: Settings, player_code: str) -> str | None:
    """A Mini App deep link that carries the player's own code as
    `start_param`, so opening it hands the new player straight to
    open_session with a referral already attached.

    None when the operator has not set both TELEGRAM_BOT_USERNAME and
    TELEGRAM_MINI_APP_SHORT_NAME — nothing on the server can discover either
    one, so the app has to omit the invite feature rather than construct a
    link that opens the wrong thing or nothing at all.
    """
    if not settings.telegram_bot_username or not settings.telegram_mini_app_short_name:
        return None
    return (
        f"https://t.me/{settings.telegram_bot_username}/"
        f"{settings.telegram_mini_app_short_name}?startapp={player_code}"
    )


def to_profile(
    row: asyncpg.Record,
    *,
    is_admin: bool = False,
    invite_link: str | None = None,
    referred_count: int = 0,
    referral_earned_minor: int = 0,
) -> UserProfile:
    last_claim = row["last_claim_date"]
    return UserProfile(
        id=str(row["id"]),
        telegram_id=row["telegram_id"],
        player_code=row["player_code"],
        first_name=row["first_name"],
        last_name=row["last_name"],
        username=row["username"],
        photo_url=row["photo_url"],
        balance=Money.of(row["coin_balance"]),
        streak_count=row["streak_count"],
        lifetime_staked=Money.of(row["lifetime_staked"]),
        lifetime_returned=Money.of(row["lifetime_returned"]),
        can_claim_daily=last_claim is None or last_claim < datetime.now(UTC).date(),
        member_since=row["created_at"],
        is_admin=is_admin,
        invite_link=invite_link,
        referred_count=referred_count,
        referral_earned=Money.of(referral_earned_minor),
    )


@router.get("/me", response_model=UserProfile, summary="The authenticated player")
async def read_me(
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> UserProfile:
    """`is_admin` rides along so the app knows whether to offer the admin link.

    It is a display hint and nothing more. Every admin route checks the
    allowlist again on its own, so a client that set this flag by hand would
    reach a page whose first request 404s — the flag opens a door, the server
    decides whether anything is behind it.
    """
    async with db.acquire() as conn:
        stats = await auth_repo.referral_stats(conn, user["id"])
    return to_profile(
        user,
        is_admin=user["telegram_id"] in settings.admin_telegram_ids,
        invite_link=build_invite_link(settings, user["player_code"]),
        referred_count=stats["referred_count"],
        referral_earned_minor=stats["referral_earned_minor"],
    )
