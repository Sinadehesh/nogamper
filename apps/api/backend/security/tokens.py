"""Session tokens.

The JWT is a pointer, not a capability: `jti` names a row in `auth_sessions`,
and every authenticated request re-reads that row. A signed-but-revoked token
is therefore dead immediately, which a stateless JWT could not offer.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import jwt

__all__ = ["SessionClaims", "TokenError", "decode_session_token", "mint_session_token"]


class TokenError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass(frozen=True, slots=True)
class SessionClaims:
    user_id: uuid.UUID
    telegram_id: int
    session_id: uuid.UUID
    expires_at: datetime


def mint_session_token(
    *,
    user_id: uuid.UUID,
    telegram_id: int,
    session_id: uuid.UUID,
    secret: str,
    algorithm: str,
    expires_at: datetime,
    now: datetime | None = None,
) -> str:
    """Mint a token that expires exactly when its `auth_sessions` row does."""
    now = now or datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "tg": telegram_id,
        "jti": str(session_id),
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


def decode_session_token(token: str, *, secret: str, algorithm: str) -> SessionClaims:
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[algorithm],
            options={"require": ["sub", "exp", "iat", "jti"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("token_expired", "Session token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("token_invalid", "Session token is not valid.") from exc

    try:
        return SessionClaims(
            user_id=uuid.UUID(payload["sub"]),
            telegram_id=int(payload["tg"]),
            session_id=uuid.UUID(payload["jti"]),
            expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise TokenError("token_invalid", "Session token claims are malformed.") from exc
