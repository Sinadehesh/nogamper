from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, status

from .. import db
from ..config import Settings, get_settings
from ..repositories import auth as auth_repo
from ..schemas import ErrorResponse, SessionRequest, SessionResponse
from ..security.dependencies import CurrentUser, current_session
from ..security.telegram import verify_init_data
from ..security.tokens import SessionClaims, mint_session_token
from .me import build_invite_link, to_profile

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post(
    "/session",
    response_model=SessionResponse,
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
    summary="Exchange Telegram initData for a session token",
)
async def create_session(
    payload: SessionRequest,
    settings: Annotated[Settings, Depends(get_settings)],
) -> SessionResponse:
    verified = verify_init_data(
        payload.init_data,
        settings.telegram_bot_token,
        ttl=timedelta(seconds=settings.init_data_ttl_seconds),
    )

    async with db.transaction() as conn:
        opened = await auth_repo.open_session(
            conn,
            verified,
            session_ttl=timedelta(seconds=settings.jwt_ttl_seconds),
            signup_bonus_minor=settings.signup_bonus_minor,
        )
        row = await auth_repo.load_session_user(conn, opened.session_id)
        stats = await auth_repo.referral_stats(conn, opened.user_id)

    token = mint_session_token(
        user_id=opened.user_id,
        telegram_id=verified.user.id,
        session_id=opened.session_id,
        secret=settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
        expires_at=opened.expires_at,
    )

    return SessionResponse(
        access_token=token,
        expires_at=opened.expires_at,
        is_new_user=opened.is_new_user,
        user=to_profile(
            row,
            is_admin=verified.user.id in settings.admin_telegram_ids,
            invite_link=build_invite_link(settings, row["player_code"]),
            referred_count=stats["referred_count"],
            referral_earned_minor=stats["referral_earned_minor"],
        ),
    )


@router.delete(
    "/session",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke the current session",
)
async def revoke_session(
    _: CurrentUser,
    claims: Annotated[SessionClaims, Depends(current_session)],
) -> None:
    async with db.transaction() as conn:
        await auth_repo.revoke_session(conn, claims.session_id)
