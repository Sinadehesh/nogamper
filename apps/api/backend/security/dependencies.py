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


async def current_user(
    claims: Annotated[SessionClaims, Depends(current_session)],
) -> asyncpg.Record:
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
    if row["status"] == "BANNED":
        raise auth_repo.AccountSuspended(row["status"])

    return row


CurrentUser = Annotated[asyncpg.Record, Depends(current_user)]


async def current_admin(
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)] = None,  # noqa: B008
) -> asyncpg.Record:
    """An authenticated player who is also on the admin allowlist.

    Two deliberate choices here.

    **Empty allowlist denies everyone.** The obvious alternative — unset means
    unrestricted — turns a forgotten environment variable into a public
    revenue feed, silently, on the deploy that forgets it. There is no reading
    of ADMIN_TELEGRAM_IDS="" that should show anyone lifetime takings.

    **A non-admin gets 404, not 403.** 403 confirms the route exists and that
    an allowlist is what stands between the caller and it, which is an
    invitation to go looking for the ids on it. 404 is what any other unknown
    path returns, so the admin surface does not announce itself to the players
    it is hidden from.
    """
    if user["telegram_id"] not in settings.admin_telegram_ids:
        raise HTTPException(status_code=404, detail={"code": "not_found", "detail": "Not found."})
    return user


CurrentAdmin = Annotated[asyncpg.Record, Depends(current_admin)]
