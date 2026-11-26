"""The signed-in player: who they are, the limits they have set, their record."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, status

from .. import db
from ..config import Settings, get_settings
from ..repositories import auth as auth_repo
from ..repositories import predictions as predictions_repo
from ..repositories import safer_play
from ..schemas import (
    BreakRequest,
    CalibrationBucket,
    EraseRequest,
    ErrorResponse,
    LimitRequest,
    Limits,
    Money,
    ProfileUpdate,
    RealityCheck,
    UserProfile,
)
from ..security import passwords
from ..security.dependencies import CurrentUser, is_admin
from ..services import economy

router = APIRouter(prefix="/v1", tags=["me"])


def to_limits(row: asyncpg.Record, settings: Settings, *, daily_spent_minor: int = 0) -> Limits:
    limit = row["daily_stake_limit"]
    break_until = row["cooloff_until"]
    if break_until is not None and break_until <= datetime.now(UTC):
        break_until = None  # a break that has ended is not a break

    return Limits(
        daily_limit=Money.of(limit) if limit is not None else None,
        daily_spent=Money.of(daily_spent_minor),
        daily_limit_loosen_at=safer_play.loosen_available_at(
            limit, row["daily_limit_set_at"], settings
        ),
        break_until=break_until,
        break_options_hours=settings.break_options_hours,
    )


def to_profile(
    row: asyncpg.Record,
    settings: Settings,
    *,
    is_admin: bool = False,
    daily_spent_minor: int = 0,
) -> UserProfile:
    today = economy.economy_date(settings)
    last_claim = row["last_claim_date"]
    can_claim = settings.daily_topup_minor > 0 and (last_claim is None or last_claim < today)

    return UserProfile(
        id=str(row["id"]),
        player_code=row["player_code"],
        display_name=row["first_name"] or auth_repo.GUEST_DISPLAY_NAME,
        email=row["email"],
        is_guest=row["is_guest"],
        balance=Money.of(row["coin_balance"]),
        lifetime_staked=Money.of(row["lifetime_staked"]),
        lifetime_returned=Money.of(row["lifetime_returned"]),
        can_claim_daily=can_claim,
        daily_topup=Money.of(settings.daily_topup_minor),
        next_claim_at=None if can_claim else economy.next_claim_at(settings, today),
        member_since=row["created_at"],
        is_admin=is_admin,
        limits=to_limits(row, settings, daily_spent_minor=daily_spent_minor),
        session_expires_at=row["session_expires_at"],
    )


async def _spent_today(conn: asyncpg.Connection, user: asyncpg.Record, settings: Settings) -> int:
    return await predictions_repo.staked_since(conn, user["id"], economy.day_start(settings))


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
        spent = await _spent_today(conn, user, settings)
    return to_profile(user, settings, is_admin=is_admin(user, settings), daily_spent_minor=spent)


@router.patch(
    "/me",
    response_model=UserProfile,
    responses={400: {"model": ErrorResponse}},
    summary="Change the display name",
)
async def update_me(
    payload: ProfileUpdate,
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> UserProfile:
    display_name = auth_repo.normalise_display_name(payload.display_name)

    async with db.transaction() as conn:
        await auth_repo.update_display_name(conn, user["id"], display_name)
        spent = await _spent_today(conn, user, settings)

    merged = {**dict(user), "first_name": display_name}
    return to_profile(merged, settings, is_admin=is_admin(user, settings), daily_spent_minor=spent)


async def _fresh_limits(conn: asyncpg.Connection, user: asyncpg.Record, settings: Settings):
    row = await conn.fetchrow(
        "SELECT daily_stake_limit, daily_limit_set_at, cooloff_until FROM users WHERE id = $1",
        user["id"],
    )
    return to_limits(row, settings, daily_spent_minor=await _spent_today(conn, user, settings))


@router.get("/me/limits", response_model=Limits, summary="The limits this player has set")
async def read_limits(
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> Limits:
    async with db.acquire() as conn:
        return await _fresh_limits(conn, user, settings)


@router.put(
    "/me/limits",
    response_model=Limits,
    responses={409: {"model": ErrorResponse}},
    summary="Set, lower, raise or remove the daily limit",
)
async def set_limit(
    payload: LimitRequest,
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> Limits:
    """Lowering applies at once. Raising or removing waits a day — see
    repositories/safer_play.py for why the asymmetry is the feature."""
    async with db.transaction() as conn:
        await safer_play.set_daily_limit(
            conn, user_id=user["id"], new_limit=payload.daily_limit_minor, settings=settings
        )
        return await _fresh_limits(conn, user, settings)


@router.post(
    "/me/break",
    response_model=Limits,
    responses={400: {"model": ErrorResponse}},
    summary="Take a break from forecasting",
)
async def take_break(
    payload: BreakRequest,
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> Limits:
    """There is deliberately no route that ends a break early."""
    async with db.transaction() as conn:
        await safer_play.start_break(
            conn, user_id=user["id"], hours=payload.hours, settings=settings
        )
        return await _fresh_limits(conn, user, settings)


@router.get(
    "/me/reality-check",
    response_model=RealityCheck,
    summary="This player's record, and what a bookmaker's margin would have cost",
)
async def read_reality_check(
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> RealityCheck:
    async with db.acquire() as conn:
        record = await safer_play.reality_check(conn, user_id=user["id"], settings=settings)

    return RealityCheck(
        member_since=user["created_at"],
        slips_placed=record.slips_placed,
        slips_open=record.slips_open,
        slips_settled=record.slips_settled,
        slips_won=record.slips_won,
        slips_lost=record.slips_lost,
        picks_settled=record.picks_settled,
        picks_correct=record.picks_correct,
        staked=Money.of(record.staked),
        returned=Money.of(record.returned),
        net=Money.of(record.net),
        reference_margin=str(settings.reference_margin),
        margin_cost=Money.of(record.margin_cost),
        net_with_margin=Money.of(record.net - record.margin_cost),
        active_days_30d=record.active_days_30d,
        slips_30d=record.slips_30d,
        calibration=[
            CalibrationBucket(
                low=f"{bucket.low:.2f}",
                high=f"{bucket.high:.2f}",
                picks=bucket.picks,
                correct=bucket.correct,
                expected=f"{bucket.expected:.4f}" if bucket.expected is not None else None,
            )
            for bucket in record.calibration
        ],
    )


@router.post(
    "/me/erase",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={401: {"model": ErrorResponse}},
    summary="Erase this account",
)
async def erase_me(
    payload: EraseRequest,
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """Remove what identifies this player and sign them out everywhere.

    A POST rather than a DELETE, because it carries a body — the password —
    and a body on DELETE is something intermediaries are allowed to drop.

    A registered account confirms with its password: this cannot be undone,
    and an unlocked laptop should not be enough to do it. A guest has no
    password to give — the session is all there ever was.
    """
    if user["email"] is not None:
        supplied = payload.password or ""
        if not await passwords.verify_async(user["password_hash"], supplied, settings):
            raise auth_repo.AccountError(
                "invalid_credentials", "Your password is not correct.", status=401
            )

    async with db.transaction() as conn:
        await auth_repo.erase_account(conn, user["id"])
