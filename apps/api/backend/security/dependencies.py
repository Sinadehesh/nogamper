"""Request-scoped authentication.

`current_user` is the only door into an authenticated route. It re-reads the
session row on every request, so revoking a session takes effect at once
rather than whenever the token happens to expire.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

import asyncpg
from fastapi import Depends, Header, HTTPException

from .. import db
from ..config import Settings, get_settings
from ..repositories import auth as auth_repo
from .tokens import SessionClaims, TokenError, decode_session_token


def _bearer(authorization: str | None) -> str:
    if not authorization:
        raise TokenError("token_missing", "Authorization header is required.")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise TokenError("token_missing", "Expected an Authorization: Bearer header.")
    return token.strip()


async def current_session(
    authorization: Annotated[str | None, Header()] = None,
    settings: Annotated[Settings, Depends(get_settings)] = None,  # noqa: B008
) -> SessionClaims:
    return decode_session_token(
        _bearer(authorization),
        secret=settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


async def _load_live_user(claims: SessionClaims) -> asyncpg.Record:
    async with db.acquire() as conn:
        row = await auth_repo.load_session_user(conn, claims.session_id)

    if row is None:
        raise TokenError("session_unknown", "Session is no longer valid.")
    if row["revoked_at"] is not None:
        raise TokenError("session_revoked", "Session has been revoked.")
    if row["session_expires_at"] <= datetime.now(UTC):
        raise TokenError("session_expired", "Session has expired.")
    if row["id"] != claims.user_id:
        raise TokenError("token_invalid", "Session does not belong to this subject.")
    if row["deleted_at"] is not None:
        # Erasing an account revokes its sessions in the same transaction, so
        # this is unreachable in the ordinary course. It is checked anyway:
        # "this person asked to be forgotten" should not depend on a second
        # statement having run.
        raise TokenError("session_unknown", "Session is no longer valid.")
    if row["status"] == "BANNED":
        raise auth_repo.AccountSuspended(row["status"])

    return row


async def current_user(
    claims: Annotated[SessionClaims, Depends(current_session)],
) -> asyncpg.Record:
    return await _load_live_user(claims)


CurrentUser = Annotated[asyncpg.Record, Depends(current_user)]


async def optional_user(
    authorization: Annotated[str | None, Header()] = None,
    settings: Annotated[Settings, Depends(get_settings)] = None,  # noqa: B008
) -> asyncpg.Record | None:
    """The signed-in player if there is one, and None rather than a 401 if not.

    For the one route that means two different things depending on the answer:
    registering while playing as a guest keeps that guest's history, and
    registering cold starts a new account. A stale or broken token is treated
    as "nobody" — the caller is about to be issued a fresh session either way,
    and failing the sign-up over a dead cookie would strand them on a form
    that can never succeed.
    """
    if not authorization:
        return None
    try:
        claims = decode_session_token(
            _bearer(authorization),
            secret=settings.jwt_secret,
            algorithm=settings.jwt_algorithm,
        )
        return await _load_live_user(claims)
    except (TokenError, auth_repo.AccountSuspended):
        return None


OptionalUser = Annotated[asyncpg.Record | None, Depends(optional_user)]


def is_admin(user: asyncpg.Record, settings: Settings) -> bool:
    return user["player_code"] in settings.admin_player_codes


async def current_admin(
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)] = None,  # noqa: B008
) -> asyncpg.Record:
    """An authenticated player who is also on the admin allowlist.

    Two deliberate choices here.

    **Empty allowlist denies everyone.** The obvious alternative — unset means
    unrestricted — turns a forgotten environment variable into a public roster
    of everybody's email address, silently, on the deploy that forgets it.
    There is no reading of ADMIN_PLAYER_CODES="" that should show anyone that.

    **A non-admin gets 404, not 403.** 403 confirms the route exists and that
    an allowlist is what stands between the caller and it, which is an
    invitation to go looking for a way onto it. 404 is what any other unknown
    path returns, so the admin surface does not announce itself to the players
    it is hidden from.
    """
    if not is_admin(user, settings):
        raise HTTPException(status_code=404, detail={"code": "not_found", "detail": "Not found."})
    return user


CurrentAdmin = Annotated[asyncpg.Record, Depends(current_admin)]
