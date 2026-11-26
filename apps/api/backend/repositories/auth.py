"""Account provisioning and session issuance.

One transaction covers the whole exchange: upsert the profile, post the
signup bonus for genuinely new accounts, and open the session. A crash
anywhere rolls all three back, so there is no state in which a user exists
without their opening balance.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import asyncpg

from ..security.telegram import TelegramUser, VerifiedInitData

_UPSERT_USER = """
INSERT INTO users (telegram_id, username, first_name, last_name,
                   language_code, is_telegram_premium, photo_url, last_seen_at)
VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
ON CONFLICT (telegram_id) DO UPDATE SET
    username            = EXCLUDED.username,
    first_name          = EXCLUDED.first_name,
    last_name           = EXCLUDED.last_name,
    language_code       = EXCLUDED.language_code,
    is_telegram_premium = EXCLUDED.is_telegram_premium,
    photo_url           = EXCLUDED.photo_url,
    last_seen_at        = NOW()
RETURNING id, status, (xmax = 0) AS was_created
"""

_SIGNUP_BONUS = """
INSERT INTO ledger_entries (user_id, entry_type, amount, idempotency_key, metadata)
VALUES ($1, 'SIGNUP_BONUS_CREDIT', $2, $3, '{"reason":"signup"}'::jsonb)
ON CONFLICT (user_id, idempotency_key) DO NOTHING
"""

_SET_REFERRER = """
UPDATE users AS u
   SET referred_by = r.id
  FROM users AS r
 WHERE u.id = $1
   AND u.referred_by IS NULL
   AND r.player_code = upper($2)
"""

_OPEN_SESSION = """
INSERT INTO auth_sessions (user_id, init_data_hash, telegram_auth_date, expires_at)
VALUES ($1, $2, $3, $4)
ON CONFLICT (init_data_hash) DO UPDATE SET
    id         = gen_random_uuid(),
    user_id    = EXCLUDED.user_id,
    issued_at  = NOW(),
    expires_at = EXCLUDED.expires_at,
    revoked_at = NULL
RETURNING id, expires_at
"""


@dataclass(frozen=True, slots=True)
class OpenedSession:
    user_id: uuid.UUID
    session_id: uuid.UUID
    expires_at: datetime
    is_new_user: bool


class AccountSuspended(Exception):
    def __init__(self, status: str) -> None:
        super().__init__(f"Account status is {status}.")
        self.status = status


async def open_session(
    conn: asyncpg.Connection,
    verified: VerifiedInitData,
    *,
    session_ttl: timedelta,
    signup_bonus_minor: int,
) -> OpenedSession:
    """
    ``verified.start_param`` carries a referral code when the Mini App was
    opened via ``https://t.me/<bot>/<app>?startapp=<code>`` — Telegram hands
    it straight through as initData's own `start_param` field, unverified by
    Telegram itself, which is why `_SET_REFERRER` treats it as untrusted
    input: a join that finds nothing rather than a lookup that can fail.
    """
    tg: TelegramUser = verified.user

    row = await conn.fetchrow(
        _UPSERT_USER,
        tg.id,
        tg.username,
        tg.first_name,
        tg.last_name,
        tg.language_code,
        tg.is_premium,
        tg.photo_url,
    )
    user_id: uuid.UUID = row["id"]
    was_created: bool = row["was_created"]

    if row["status"] == "BANNED":
        raise AccountSuspended(row["status"])

    if was_created and signup_bonus_minor > 0:
        await conn.execute(_SIGNUP_BONUS, user_id, signup_bonus_minor, f"signup:{tg.id}")

    if was_created and verified.start_param:
        await conn.execute(_SET_REFERRER, user_id, verified.start_param.strip())

    expires_at = datetime.now(UTC) + session_ttl

    session = await conn.fetchrow(
        _OPEN_SESSION, user_id, verified.fingerprint, verified.auth_date, expires_at
    )

    return OpenedSession(
        user_id=user_id,
        session_id=session["id"],
        expires_at=session["expires_at"],
        is_new_user=was_created,
    )


_LOAD_SESSION_USER = """
SELECT u.id, u.telegram_id, u.username, u.first_name, u.last_name, u.photo_url,
       u.player_code, u.referred_by,
       u.coin_balance, u.streak_count, u.last_claim_date, u.status,
       u.lifetime_staked, u.lifetime_returned, u.created_at,
       s.expires_at AS session_expires_at, s.revoked_at
  FROM auth_sessions s
  JOIN users u ON u.id = s.user_id
 WHERE s.id = $1
"""

_REFERRAL_STATS = """
SELECT (SELECT count(*) FROM users WHERE referred_by = $1) AS referred_count,
       COALESCE(
           (SELECT sum(amount) FROM ledger_entries
             WHERE user_id = $1 AND entry_type = 'REFERRAL_BONUS_CREDIT'),
           0
       ) AS referral_earned_minor
"""


async def load_session_user(
    conn: asyncpg.Connection, session_id: uuid.UUID
) -> asyncpg.Record | None:
    return await conn.fetchrow(_LOAD_SESSION_USER, session_id)


async def referral_stats(conn: asyncpg.Connection, user_id: uuid.UUID) -> asyncpg.Record:
    return await conn.fetchrow(_REFERRAL_STATS, user_id)


async def revoke_session(conn: asyncpg.Connection, session_id: uuid.UUID) -> None:
    await conn.execute(
        "UPDATE auth_sessions SET revoked_at = NOW() WHERE id = $1 AND revoked_at IS NULL",
        session_id,
    )
