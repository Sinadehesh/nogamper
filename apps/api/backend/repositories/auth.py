"""Account provisioning and session issuance.

One transaction covers each exchange: create or find the account, post the
opening balance for a genuinely new one, and open the session. A crash
anywhere rolls all of it back, so there is no state in which a player exists
without their opening balance, or holds a session for an account that was
never written.

Three ways in, and they converge on the same row shape:

  * **Register** — an email and a password.
  * **Guest** — neither. The session is the only key to the account.
  * **Upgrade** — a guest registers. Same row, same balance, same history;
    only the credentials are new.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import asyncpg

__all__ = [
    "AccountError",
    "AccountSuspended",
    "OpenedSession",
    "create_account",
    "create_guest",
    "erase_account",
    "find_credentials",
    "load_session_user",
    "normalise_display_name",
    "normalise_email",
    "open_session",
    "revoke_all_sessions",
    "revoke_session",
    "set_password_hash",
    "touch_last_seen",
    "update_display_name",
    "upgrade_guest",
]

GUEST_DISPLAY_NAME = "Guest"
ERASED_DISPLAY_NAME = "Deleted player"

_EMAIL = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")


class AccountError(Exception):
    """A sign-up or profile request that cannot be honoured as sent."""

    def __init__(self, code: str, detail: str, *, status: int = 400) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status = status


class AccountSuspended(Exception):
    def __init__(self, status: str) -> None:
        super().__init__(f"Account status is {status}.")
        self.status = status


def normalise_email(raw: str) -> str:
    """Lower-case, trimmed, and shaped like an address.

    Deliberately permissive. Nothing here sends mail, so the only job of this
    check is to catch a typo'd field — and every stricter rule anyone has
    written for email addresses has rejected a real one.
    """
    email = raw.strip().lower()
    if len(email) > 254 or not _EMAIL.match(email):
        raise AccountError("invalid_email", "That does not look like an email address.")
    return email


def normalise_display_name(raw: str) -> str:
    """The name a player is shown by: 2 to 24 visible characters.

    Letters and digits from any script, plus spaces and a little punctuation.
    Control and formatting characters are refused outright — a name is shown
    on other people's screens, and a right-to-left override or a zero-width
    joiner in it is a way to make one account read as another.
    """
    name = " ".join(unicodedata.normalize("NFC", raw).split())
    if not 2 <= len(name) <= 24:
        raise AccountError("invalid_display_name", "Choose a name of 2 to 24 characters.")
    for char in name:
        category = unicodedata.category(char)
        allowed = category[0] in {"L", "M", "N"} or char in " _-.'"
        if not allowed:
            raise AccountError(
                "invalid_display_name",
                "Use letters, numbers, spaces and . _ - ' only.",
            )
    return name


@dataclass(frozen=True, slots=True)
class OpenedSession:
    user_id: uuid.UUID
    session_id: uuid.UUID
    expires_at: datetime
    is_new_user: bool


_SIGNUP_BONUS = """
INSERT INTO ledger_entries (user_id, entry_type, amount, idempotency_key, metadata)
VALUES ($1, 'SIGNUP_BONUS_CREDIT', $2, $3, '{"reason":"signup"}'::jsonb)
ON CONFLICT (user_id, idempotency_key) DO NOTHING
"""

_INSERT_ACCOUNT = """
INSERT INTO users (email, password_hash, first_name, is_guest, last_seen_at)
VALUES ($1, $2, $3, FALSE, NOW())
RETURNING id
"""

_INSERT_GUEST = """
INSERT INTO users (first_name, is_guest, last_seen_at)
VALUES ($1, TRUE, NOW())
RETURNING id
"""

_UPGRADE_GUEST = """
UPDATE users
   SET email         = $2,
       password_hash = $3,
       first_name    = $4,
       is_guest      = FALSE,
       last_seen_at  = NOW()
 WHERE id = $1
   AND is_guest
   AND deleted_at IS NULL
RETURNING id
"""

_OPEN_SESSION = """
INSERT INTO auth_sessions (user_id, method, expires_at)
VALUES ($1, $2, $3)
RETURNING id, expires_at
"""

_PRUNE_SESSIONS = """
DELETE FROM auth_sessions
 WHERE user_id = $1
   AND expires_at < NOW() - INTERVAL '7 days'
"""


async def _grant_opening_balance(
    conn: asyncpg.Connection, user_id: uuid.UUID, signup_bonus_minor: int
) -> None:
    if signup_bonus_minor > 0:
        await conn.execute(_SIGNUP_BONUS, user_id, signup_bonus_minor, f"signup:{user_id}")


async def create_account(
    conn: asyncpg.Connection,
    *,
    email: str,
    password_hash: str,
    display_name: str,
    signup_bonus_minor: int,
) -> uuid.UUID:
    """Insert a registered account and its opening balance.

    The unique index decides whether the address is free — not a SELECT
    beforehand, which two simultaneous sign-ups would both pass.
    """
    try:
        # A savepoint, so the unique violation rolls back this statement and
        # not the caller's transaction along with it.
        async with conn.transaction():
            user_id = await conn.fetchval(_INSERT_ACCOUNT, email, password_hash, display_name)
    except asyncpg.UniqueViolationError as exc:
        raise AccountError(
            "email_taken", "An account with that email already exists.", status=409
        ) from exc

    await _grant_opening_balance(conn, user_id, signup_bonus_minor)
    return user_id


async def create_guest(conn: asyncpg.Connection, *, signup_bonus_minor: int) -> uuid.UUID:
    user_id = await conn.fetchval(_INSERT_GUEST, GUEST_DISPLAY_NAME)
    await _grant_opening_balance(conn, user_id, signup_bonus_minor)
    return user_id


async def upgrade_guest(
    conn: asyncpg.Connection,
    *,
    user_id: uuid.UUID,
    email: str,
    password_hash: str,
    display_name: str,
) -> uuid.UUID:
    """Give a guest account credentials, in place.

    No second opening balance: the guest was paid one when they arrived, and
    the row — with everything they have done since — is the same row.
    """
    try:
        async with conn.transaction():
            upgraded = await conn.fetchval(
                _UPGRADE_GUEST, user_id, email, password_hash, display_name
            )
    except asyncpg.UniqueViolationError as exc:
        raise AccountError(
            "email_taken", "An account with that email already exists.", status=409
        ) from exc

    if upgraded is None:
        raise AccountError("not_a_guest", "This account is already registered.", status=409)
    return upgraded


async def open_session(
    conn: asyncpg.Connection,
    *,
    user_id: uuid.UUID,
    method: str,
    session_ttl: timedelta,
    is_new_user: bool = False,
) -> OpenedSession:
    await conn.execute(_PRUNE_SESSIONS, user_id)
    expires_at = datetime.now(UTC) + session_ttl
    session = await conn.fetchrow(_OPEN_SESSION, user_id, method, expires_at)
    return OpenedSession(
        user_id=user_id,
        session_id=session["id"],
        expires_at=session["expires_at"],
        is_new_user=is_new_user,
    )


_FIND_CREDENTIALS = """
SELECT id, password_hash, status::text AS status
  FROM users
 WHERE email = $1
   AND deleted_at IS NULL
"""


async def find_credentials(conn: asyncpg.Connection, email: str) -> asyncpg.Record | None:
    return await conn.fetchrow(_FIND_CREDENTIALS, email)


async def set_password_hash(
    conn: asyncpg.Connection, user_id: uuid.UUID, password_hash: str
) -> None:
    await conn.execute(
        "UPDATE users SET password_hash = $2 WHERE id = $1 AND email IS NOT NULL",
        user_id,
        password_hash,
    )


async def touch_last_seen(conn: asyncpg.Connection, user_id: uuid.UUID) -> None:
    await conn.execute("UPDATE users SET last_seen_at = NOW() WHERE id = $1", user_id)


_LOAD_SESSION_USER = """
SELECT u.id, u.email, u.is_guest, u.first_name, u.player_code,
       u.password_hash,
       u.coin_balance, u.last_claim_date, u.status,
       u.lifetime_staked, u.lifetime_returned, u.created_at,
       u.daily_stake_limit, u.daily_limit_set_at, u.cooloff_until, u.deleted_at,
       s.expires_at AS session_expires_at, s.revoked_at
  FROM auth_sessions s
  JOIN users u ON u.id = s.user_id
 WHERE s.id = $1
"""


async def load_session_user(
    conn: asyncpg.Connection, session_id: uuid.UUID
) -> asyncpg.Record | None:
    return await conn.fetchrow(_LOAD_SESSION_USER, session_id)


async def revoke_session(conn: asyncpg.Connection, session_id: uuid.UUID) -> None:
    await conn.execute(
        "UPDATE auth_sessions SET revoked_at = NOW() WHERE id = $1 AND revoked_at IS NULL",
        session_id,
    )


async def revoke_all_sessions(
    conn: asyncpg.Connection, user_id: uuid.UUID, *, keep: uuid.UUID | None = None
) -> int:
    """Sign a player out everywhere, optionally sparing the session in hand."""
    result = await conn.execute(
        """
        UPDATE auth_sessions SET revoked_at = NOW()
         WHERE user_id = $1 AND revoked_at IS NULL
           AND ($2::uuid IS NULL OR id <> $2)
        """,
        user_id,
        keep,
    )
    return int(result.rsplit(" ", 1)[-1])


async def update_display_name(
    conn: asyncpg.Connection, user_id: uuid.UUID, display_name: str
) -> None:
    await conn.execute("UPDATE users SET first_name = $2 WHERE id = $1", user_id, display_name)


_ERASE = """
UPDATE users
   SET email              = NULL,
       password_hash      = NULL,
       is_guest           = FALSE,
       first_name         = $2,
       last_name          = NULL,
       username           = NULL,
       photo_url          = NULL,
       language_code      = NULL,
       telegram_id        = NULL,
       referred_by        = NULL,
       daily_stake_limit  = NULL,
       daily_limit_set_at = NULL,
       deleted_at         = NOW(),
       status             = 'SELF_EXCLUDED'
 WHERE id = $1
   AND deleted_at IS NULL
RETURNING id
"""


async def erase_account(conn: asyncpg.Connection, user_id: uuid.UUID) -> bool:
    """Remove everything that says who this was, and sign them out everywhere.

    The row stays. Forecasts and ledger entries reference it, and those are
    not only this player's history — a settled market's totals and a season's
    standings were computed from them, and deleting the rows would quietly
    rewrite results other people were shown. What goes is every field that
    identifies a person: the address, the password, the name, the messages.

    `SELF_EXCLUDED` is the status the schema always had for "this account
    closed itself", which is exactly what happened.
    """
    erased = await conn.fetchval(_ERASE, user_id, ERASED_DISPLAY_NAME)
    if erased is None:
        return False

    # Messages are deleted rather than blanked: they are free text the player
    # wrote, nothing else is computed from them, and an empty shell of a
    # conversation is not worth keeping.
    await conn.execute("DELETE FROM player_messages WHERE user_id = $1", user_id)
    await conn.execute("DELETE FROM leaderboard_entries WHERE user_id = $1", user_id)
    await revoke_all_sessions(conn, user_id)
    return True
