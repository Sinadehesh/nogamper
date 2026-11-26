"""Opening, replacing and closing sessions.

Three routes here answer callers who have not signed in — register, sign in,
guest — and they are gated and throttled accordingly; see security/webtier.py
and security/ratelimit.py for why and how.

## What the responses do not say

A failed sign-in is `invalid_credentials` whether the address is unknown, the
password is wrong, or the account has been erased. Telling those apart would
let the sign-in form be used to check whether somebody has an account here —
and "has an account on a site about gambling less" is not a fact to hand out.

Registration cannot keep that secret: it has to say when an address is taken,
or the form is unusable. It is throttled per visitor instead.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, status

from .. import db
from ..config import Settings, get_settings
from ..repositories import auth as auth_repo
from ..schemas import (
    ErrorResponse,
    LoginRequest,
    PasswordChangeRequest,
    RegisterRequest,
    SessionResponse,
)
from ..security import passwords, ratelimit
from ..security.dependencies import CurrentUser, OptionalUser, current_session, is_admin
from ..security.passwords import PasswordPolicyError
from ..security.ratelimit import RateWindow
from ..security.tokens import SessionClaims, mint_session_token
from ..security.webtier import ClientAddress, require_web_tier
from .me import to_profile

router = APIRouter(prefix="/v1/auth", tags=["auth"])


def _per_visitor(settings: Settings) -> RateWindow:
    return RateWindow("auth-ip", settings.auth_ip_rate_max, settings.auth_ip_rate_window_seconds)


def _per_signup(settings: Settings) -> RateWindow:
    return RateWindow(
        "signup-ip", settings.signup_ip_rate_max, settings.signup_ip_rate_window_seconds
    )


def _per_email(settings: Settings) -> RateWindow:
    return RateWindow("login-email", settings.login_rate_max, settings.login_rate_window_seconds)


async def _respond(
    opened: auth_repo.OpenedSession, settings: Settings, *, status_code: int | None = None
) -> SessionResponse:
    async with db.acquire() as conn:
        row = await auth_repo.load_session_user(conn, opened.session_id)

    token = mint_session_token(
        user_id=opened.user_id,
        session_id=opened.session_id,
        secret=settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
        expires_at=opened.expires_at,
    )
    return SessionResponse(
        access_token=token,
        expires_at=opened.expires_at,
        is_new_user=opened.is_new_user,
        user=to_profile(row, settings, is_admin=is_admin(row, settings)),
    )


@router.post(
    "/register",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
    },
    dependencies=[Depends(require_web_tier)],
    summary="Create an account, or give a guest account credentials",
)
async def register(
    payload: RegisterRequest,
    guest: OptionalUser,
    address: ClientAddress,
    settings: Annotated[Settings, Depends(get_settings)],
) -> SessionResponse:
    """Sign up — or, when called by a guest, keep everything and add a login.

    Validation runs before the throttle is charged and the hash before the
    transaction opens: a rejected form should not cost the visitor an attempt,
    and a connection should not be held across the slowest step in the route.
    """
    email = auth_repo.normalise_email(payload.email)
    display_name = auth_repo.normalise_display_name(payload.display_name)
    try:
        passwords.check_policy(payload.password, email=email, settings=settings)
    except PasswordPolicyError as exc:
        raise auth_repo.AccountError(exc.code, exc.detail) from exc

    await ratelimit.hit(_per_signup(settings), address)

    password_hash = await passwords.hash_async(payload.password, settings)
    ttl = timedelta(seconds=settings.session_ttl_seconds)
    upgrading = guest is not None and guest["is_guest"]

    async with db.transaction() as conn:
        if upgrading:
            user_id = await auth_repo.upgrade_guest(
                conn,
                user_id=guest["id"],
                email=email,
                password_hash=password_hash,
                display_name=display_name,
            )
            # The guest session was a bearer of nothing but a cookie. Now that
            # the account has credentials, every session issued before them is
            # retired and a new one takes its place.
            await auth_repo.revoke_all_sessions(conn, user_id)
        else:
            user_id = await auth_repo.create_account(
                conn,
                email=email,
                password_hash=password_hash,
                display_name=display_name,
                signup_bonus_minor=settings.signup_bonus_minor,
            )

        opened = await auth_repo.open_session(
            conn,
            user_id=user_id,
            method="password",
            session_ttl=ttl,
            is_new_user=not upgrading,
        )

    return await _respond(opened, settings)


@router.post(
    "/login",
    response_model=SessionResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
    },
    dependencies=[Depends(require_web_tier)],
    summary="Sign in with an email and a password",
)
async def login(
    payload: LoginRequest,
    address: ClientAddress,
    settings: Annotated[Settings, Depends(get_settings)],
) -> SessionResponse:
    email = payload.email.strip().lower()

    await ratelimit.hit(_per_visitor(settings), address)
    await ratelimit.hit(_per_email(settings), email)

    async with db.acquire() as conn:
        account = await auth_repo.find_credentials(conn, email)

    stored = account["password_hash"] if account else None
    if not await passwords.verify_async(stored, payload.password, settings):
        raise auth_repo.AccountError(
            "invalid_credentials", "That email and password do not match.", status=401
        )

    # Only now, with the password proven, is it safe to say the account is
    # suspended — before this point that answer would confirm it exists.
    if account["status"] == "BANNED":
        raise auth_repo.AccountSuspended(account["status"])

    await ratelimit.clear(_per_email(settings), email)

    rehashed = (
        await passwords.hash_async(payload.password, settings)
        if passwords.needs_rehash(stored, settings)
        else None
    )

    async with db.transaction() as conn:
        if rehashed:
            await auth_repo.set_password_hash(conn, account["id"], rehashed)
        await auth_repo.touch_last_seen(conn, account["id"])
        opened = await auth_repo.open_session(
            conn,
            user_id=account["id"],
            method="password",
            session_ttl=timedelta(seconds=settings.session_ttl_seconds),
        )

    return await _respond(opened, settings)


@router.post(
    "/guest",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={429: {"model": ErrorResponse}},
    dependencies=[Depends(require_web_tier)],
    summary="Start playing without an account",
)
async def guest(
    address: ClientAddress,
    settings: Annotated[Settings, Depends(get_settings)],
) -> SessionResponse:
    """A full account with no credentials.

    The point is that somebody who wants something to do *instead of* placing
    a bet should not meet a form first. Registering later upgrades this same
    account, so nothing done as a guest is lost.
    """
    await ratelimit.hit(_per_signup(settings), address)

    async with db.transaction() as conn:
        user_id = await auth_repo.create_guest(conn, signup_bonus_minor=settings.signup_bonus_minor)
        opened = await auth_repo.open_session(
            conn,
            user_id=user_id,
            method="guest",
            session_ttl=timedelta(seconds=settings.session_ttl_seconds),
            is_new_user=True,
        )

    return await _respond(opened, settings)


@router.post(
    "/password",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}},
    summary="Change the password, and sign out every other device",
)
async def change_password(
    payload: PasswordChangeRequest,
    user: CurrentUser,
    claims: Annotated[SessionClaims, Depends(current_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    if user["email"] is None:
        raise auth_repo.AccountError(
            "not_registered", "A guest account has no password. Create an account first."
        )

    # Throttled on the account, like sign-in: this route also answers the
    # question "is this the password", and a stolen session should not be a
    # way to ask it as often as it likes.
    await ratelimit.hit(_per_email(settings), user["email"])

    if not await passwords.verify_async(user["password_hash"], payload.current_password, settings):
        raise auth_repo.AccountError(
            "invalid_credentials", "Your current password is not correct.", status=401
        )

    try:
        passwords.check_policy(payload.new_password, email=user["email"], settings=settings)
    except PasswordPolicyError as exc:
        raise auth_repo.AccountError(exc.code, exc.detail) from exc

    new_hash = await passwords.hash_async(payload.new_password, settings)

    async with db.transaction() as conn:
        await auth_repo.set_password_hash(conn, user["id"], new_hash)
        await auth_repo.revoke_all_sessions(conn, user["id"], keep=claims.session_id)

    await ratelimit.clear(_per_email(settings), user["email"])


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
