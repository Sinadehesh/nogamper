"""Player administration: the roster, balance adjustments, bans, and the inbox.

Everything here is reachable only through the admin allowlist. Three of these
operations change a player's money or their access, so each one leaves a
record that says who did it and why.

## Adjustments go through the ledger like everything else

`adjust_balance` posts an `ADMIN_ADJUSTMENT` entry rather than writing
`users.coin_balance`. That column is a cache maintained solely by
`fn_post_ledger_entry()`, and an UPDATE against it would put the cache and the
ledger permanently out of step — the one bug in this system that compounds
silently, which is why `v_balance_reconciliation` exists to catch it.

The consequence worth knowing: a debit that would take a balance below zero
raises PT001 exactly as a player's own bet would. The operator cannot take
coins that are not there, and that is correct — the alternative is a negative
balance nothing in the schema is prepared for.

## Bans are a status, not a deletion

`users.status` already gates every authenticated request through
`current_user`, and predictions check it again at placement. Setting BANNED
therefore takes effect on the player's next request rather than whenever their
token happens to expire. The rows stay: a banned player's ledger is still part
of the economy's history and deleting it would silently rewrite the books.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

import asyncpg

INSUFFICIENT_FUNDS_SQLSTATE = "PT001"

_ROSTER = """
WITH flow AS (
    SELECT user_id,
           COALESCE(SUM(-amount) FILTER (
               WHERE entry_type IN ('STAKE_DEBIT', 'INSURANCE_PREMIUM_DEBIT')), 0) AS staked,
           COALESCE(SUM(amount) FILTER (
               WHERE entry_type IN ('PAYOUT_CREDIT', 'INSURANCE_CREDIT',
                                    'VOID_REFUND_CREDIT')), 0) AS returned,
           COALESCE(SUM(amount) FILTER (WHERE entry_type = 'STAR_PURCHASE_CREDIT'), 0) AS bought,
           COALESCE(SUM(amount) FILTER (
               WHERE entry_type IN ('SIGNUP_BONUS_CREDIT', 'DAILY_DRIP_CREDIT',
                                    'STREAK_BONUS_CREDIT', 'SEASON_PRIZE_CREDIT',
                                    'PROMO_CREDIT')), 0) AS granted,
           COALESCE(SUM(amount) FILTER (WHERE entry_type = 'ADMIN_ADJUSTMENT'), 0) AS adjusted
      FROM ledger_entries
     GROUP BY user_id
),
slips AS (
    SELECT user_id,
           count(*)                                        AS slips,
           count(*) FILTER (WHERE status = 'WON')           AS won,
           count(*) FILTER (WHERE status = 'LOST')          AS lost,
           count(*) FILTER (WHERE status = 'PENDING')       AS open_slips
      FROM predictions
     GROUP BY user_id
)
SELECT u.id, u.player_code, u.telegram_id, u.username, u.first_name, u.last_name,
       u.status::text AS status, u.coin_balance, u.lifetime_stars, u.created_at,
       u.last_seen_at,
       COALESCE(f.staked, 0)   AS staked,
       COALESCE(f.returned, 0) AS returned,
       COALESCE(f.bought, 0)   AS bought,
       COALESCE(f.granted, 0)  AS granted,
       COALESCE(f.adjusted, 0) AS adjusted,
       COALESCE(s.slips, 0)      AS slips,
       COALESCE(s.won, 0)        AS won,
       COALESCE(s.lost, 0)       AS lost,
       COALESCE(s.open_slips, 0) AS open_slips
  FROM users u
  LEFT JOIN flow  f ON f.user_id = u.id
  LEFT JOIN slips s ON s.user_id = u.id
 WHERE ($1::text IS NULL
        OR u.player_code = upper($1)
        OR u.username ILIKE '%' || $1 || '%'
        OR u.first_name ILIKE '%' || $1 || '%')
 ORDER BY u.last_seen_at DESC
 LIMIT $2 OFFSET $3
"""

_COUNT_PLAYERS = """
SELECT count(*) FROM users u
 WHERE ($1::text IS NULL
        OR u.player_code = upper($1)
        OR u.username ILIKE '%' || $1 || '%'
        OR u.first_name ILIKE '%' || $1 || '%')
"""

_FIND_BY_CODE = """
SELECT id, player_code, coin_balance, status::text AS status
  FROM users WHERE player_code = upper($1)
"""

_FIND_BY_TELEGRAM_ID = """
SELECT id, player_code, coin_balance, status::text AS status
  FROM users WHERE telegram_id = $1
"""

_ADJUST = """
INSERT INTO ledger_entries (user_id, entry_type, amount, idempotency_key, metadata)
VALUES ($1, 'ADMIN_ADJUSTMENT', $2, $3, $4::jsonb)
RETURNING balance_after
"""

_SET_STATUS = """
UPDATE users SET status = $2::user_status, updated_at = NOW()
 WHERE id = $1
RETURNING status::text AS status
"""

_REVOKE_SESSIONS = """
UPDATE auth_sessions SET revoked_at = NOW()
 WHERE user_id = $1 AND revoked_at IS NULL
"""


@dataclass(frozen=True, slots=True)
class PlayerRow:
    id: uuid.UUID
    player_code: str
    telegram_id: int
    username: str | None
    first_name: str
    last_name: str | None
    status: str
    balance: int
    lifetime_stars: int
    created_at: datetime
    last_seen_at: datetime
    staked: int
    returned: int
    bought: int
    granted: int
    adjusted: int
    slips: int
    won: int
    lost: int
    open_slips: int

    @property
    def net(self) -> int:
        """Returned minus staked: what betting has cost or made this player.

        Positive means the house is down against them. Open slips are not in
        here — their stake is counted, their outcome is not — so a player
        mid-parlay reads slightly negative until it settles.
        """
        return self.returned - self.staked


async def list_players(
    conn: asyncpg.Connection, *, search: str | None, limit: int, offset: int
) -> tuple[list[PlayerRow], int]:
    rows = await conn.fetch(_ROSTER, search, limit, offset)
    total = await conn.fetchval(_COUNT_PLAYERS, search)
    return [
        PlayerRow(
            id=r["id"],
            player_code=r["player_code"],
            telegram_id=r["telegram_id"],
            username=r["username"],
            first_name=r["first_name"],
            last_name=r["last_name"],
            status=r["status"],
            balance=int(r["coin_balance"]),
            lifetime_stars=int(r["lifetime_stars"]),
            created_at=r["created_at"],
            last_seen_at=r["last_seen_at"],
            staked=int(r["staked"]),
            returned=int(r["returned"]),
            bought=int(r["bought"]),
            granted=int(r["granted"]),
            adjusted=int(r["adjusted"]),
            slips=int(r["slips"]),
            won=int(r["won"]),
            lost=int(r["lost"]),
            open_slips=int(r["open_slips"]),
        )
        for r in rows
    ], int(total)


class PlayerAdminError(Exception):
    def __init__(self, code: str, detail: str, *, status: int = 400) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status = status


async def find_by_code(conn: asyncpg.Connection, code: str) -> asyncpg.Record:
    row = await conn.fetchrow(_FIND_BY_CODE, code)
    if row is None:
        raise PlayerAdminError("player_not_found", "No player with that code.", status=404)
    return row


async def find_player(
    conn: asyncpg.Connection, *, player_code: str | None = None, telegram_id: int | None = None
) -> asyncpg.Record:
    """Find a player by either handle.

    Exactly one, checked here rather than left to the caller: passing both and
    having them disagree would silently credit whichever the query happened to
    prefer, and this function's callers move money.
    """
    if (player_code is None) == (telegram_id is None):
        raise PlayerAdminError(
            "ambiguous_player", "Give either a player code or a Telegram id, not both."
        )

    if player_code is not None:
        return await find_by_code(conn, player_code)

    row = await conn.fetchrow(_FIND_BY_TELEGRAM_ID, telegram_id)
    if row is None:
        raise PlayerAdminError(
            "player_not_found",
            "No player with that Telegram id. They have to open the app once before "
            "they have an account to credit.",
            status=404,
        )
    return row


async def adjust_balance(
    conn: asyncpg.Connection,
    *,
    player_code: str | None = None,
    telegram_id: int | None = None,
    amount_minor: int,
    reason: str,
    reference: str,
) -> tuple[str, int]:
    """Credit or debit a player, through the ledger.

    Identified by player code or Telegram id — whichever the operator has to
    hand. Must run inside a transaction. Returns the player's code and their
    balance afterwards, the code because the caller may have arrived with only
    an id and still has to report what it did.
    """
    if amount_minor == 0:
        raise PlayerAdminError("zero_adjustment", "An adjustment of zero changes nothing.")

    player = await find_player(conn, player_code=player_code, telegram_id=telegram_id)

    try:
        balance_after = await conn.fetchval(
            _ADJUST,
            player["id"],
            amount_minor,
            f"admin:{reference}",
            f'{{"reason": {_json_string(reason)}, "by": "admin"}}',
        )
    except asyncpg.UniqueViolationError as exc:
        raise PlayerAdminError(
            "duplicate_adjustment",
            "An adjustment with that reference has already been posted.",
            status=409,
        ) from exc
    except asyncpg.PostgresError as exc:
        if getattr(exc, "sqlstate", None) != INSUFFICIENT_FUNDS_SQLSTATE:
            raise
        raise PlayerAdminError(
            "insufficient_funds",
            f"That player holds {player['coin_balance']} and cannot go below zero.",
            status=409,
        ) from exc

    if balance_after is None:
        raise PlayerAdminError("player_not_found", "No player with that code.", status=404)
    return str(player["player_code"]), int(balance_after)


async def set_status(conn: asyncpg.Connection, *, player_code: str, status: str) -> str:
    allowed = {"ACTIVE", "RESTRICTED", "BANNED"}
    if status not in allowed:
        raise PlayerAdminError("bad_status", f"Status must be one of {sorted(allowed)}.")

    player = await find_by_code(conn, player_code)
    new_status = await conn.fetchval(_SET_STATUS, player["id"], status)

    if status in {"BANNED", "RESTRICTED"}:
        await conn.execute(_REVOKE_SESSIONS, player["id"])

    return new_status


def _json_string(value: str) -> str:
    """Minimal JSON string escaping for the metadata blob."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'
