"""Messages from players to the operator.

A player writes; the operator may answer once. Not a chat: no threads, no
read receipts, no notifications. The shape is the question — "something looks
wrong with this market" needs an answer, not a conversation.

**The reply lives in the app.** The player reads it on the page they wrote
from. Nothing is emailed: addresses here are unverified, and sending an
operator's words to an address somebody merely typed is how a support box
becomes a way to message strangers.

`admin_note` stays private and is separate from the reply: somewhere to write
"this account looks automated" is worth keeping, and merging it into the reply
would publish it.

There was once a second kind of message, a prize claim. There are no prizes
now, so nothing creates one; rows of that kind from before are still listed.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

import asyncpg

_INSERT = """
INSERT INTO player_messages (user_id, kind, body)
VALUES ($1, 'MESSAGE', $2)
RETURNING id, kind::text AS kind, status::text AS status, body, created_at
"""

_RECENT_COUNT = """
SELECT count(*) FROM player_messages
 WHERE user_id = $1 AND created_at > NOW() - make_interval(secs => $2)
"""

_MINE = """
SELECT id, kind::text AS kind, status::text AS status, body, created_at, answered_at,
       reply_body, replied_at
  FROM player_messages
 WHERE user_id = $1
 ORDER BY created_at DESC
 LIMIT $2
"""

_INBOX = """
SELECT m.id, m.kind::text AS kind, m.status::text AS status, m.body,
       m.admin_note, m.created_at, m.answered_at,
       m.reply_body, m.replied_at,
       u.player_code, u.first_name, u.is_guest,
       u.coin_balance, u.status::text AS player_status
  FROM player_messages m
  JOIN users u ON u.id = m.user_id
 WHERE ($1::text IS NULL OR m.status = $1::player_message_status)
 ORDER BY (m.status = 'NEW') DESC, m.created_at DESC
 LIMIT $2 OFFSET $3
"""

_COUNT_INBOX = """
SELECT count(*) FILTER (WHERE status = 'NEW')      AS new_count,
       count(*)                                     AS total
  FROM player_messages
"""

_RESOLVE = """
UPDATE player_messages
   SET status      = $2::player_message_status,
       admin_note  = COALESCE($3, admin_note),
       answered_at = CASE WHEN $2 = 'ANSWERED' THEN NOW() ELSE NULL END
 WHERE id = $1
RETURNING id, status::text AS status
"""


class MessageError(Exception):
    def __init__(self, code: str, detail: str, *, status: int = 400) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status = status


@dataclass(frozen=True, slots=True)
class Message:
    id: uuid.UUID
    kind: str
    status: str
    body: str
    created_at: datetime
    answered_at: datetime | None = None
    reply_body: str | None = None
    replied_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class InboxItem(Message):
    admin_note: str | None = None
    player_code: str = ""
    first_name: str = ""
    is_guest: bool = False
    balance: int = 0
    player_status: str = "ACTIVE"


async def send(
    conn: asyncpg.Connection,
    *,
    user_id: uuid.UUID,
    body: str,
    window_seconds: int,
    max_in_window: int,
) -> Message:
    body = body.strip()
    if not body:
        raise MessageError("empty_message", "Write something first.")
    if len(body) > 2000:
        raise MessageError("message_too_long", "Keep it under 2000 characters.")

    recent = await conn.fetchval(_RECENT_COUNT, user_id, float(window_seconds))
    if recent >= max_in_window:
        raise MessageError(
            "too_many_messages",
            "You have sent several messages already. Give it a little while.",
            status=429,
        )

    row = await conn.fetchrow(_INSERT, user_id, body)
    return Message(
        id=row["id"],
        kind=row["kind"],
        status=row["status"],
        body=row["body"],
        created_at=row["created_at"],
    )


async def mine(conn: asyncpg.Connection, user_id: uuid.UUID, limit: int = 20) -> list[Message]:
    rows = await conn.fetch(_MINE, user_id, limit)
    return [
        Message(
            id=r["id"],
            kind=r["kind"],
            status=r["status"],
            body=r["body"],
            created_at=r["created_at"],
            answered_at=r["answered_at"],
            reply_body=r["reply_body"],
            replied_at=r["replied_at"],
        )
        for r in rows
    ]


async def inbox(
    conn: asyncpg.Connection, *, status: str | None, limit: int, offset: int
) -> tuple[list[InboxItem], int, int]:
    rows = await conn.fetch(_INBOX, status, limit, offset)
    counts = await conn.fetchrow(_COUNT_INBOX)
    items = [
        InboxItem(
            id=r["id"],
            kind=r["kind"],
            status=r["status"],
            body=r["body"],
            created_at=r["created_at"],
            answered_at=r["answered_at"],
            reply_body=r["reply_body"],
            replied_at=r["replied_at"],
            admin_note=r["admin_note"],
            player_code=r["player_code"],
            first_name=r["first_name"] or "",
            is_guest=r["is_guest"],
            balance=int(r["coin_balance"]),
            player_status=r["player_status"],
        )
        for r in rows
    ]
    return items, int(counts["new_count"]), int(counts["total"])


async def resolve(
    conn: asyncpg.Connection, *, message_id: uuid.UUID, status: str, note: str | None
) -> str:
    if status not in {"NEW", "SEEN", "ANSWERED"}:
        raise MessageError("bad_status", "Status must be NEW, SEEN or ANSWERED.")
    if note is not None and len(note) > 2000:
        raise MessageError("note_too_long", "Keep the note under 2000 characters.")

    row = await conn.fetchrow(_RESOLVE, message_id, status, note)
    if row is None:
        raise MessageError("message_not_found", "No such message.", status=404)
    return row["status"]


_RECORD_REPLY = """
UPDATE player_messages
   SET reply_body  = $2,
       replied_at  = NOW(),
       status      = 'ANSWERED',
       answered_at = COALESCE(answered_at, NOW())
 WHERE id = $1
RETURNING id, kind::text AS kind, status::text AS status, body, created_at, answered_at,
          reply_body, replied_at
"""


async def record_reply(conn: asyncpg.Connection, *, message_id: uuid.UUID, body: str) -> Message:
    """Write the operator's answer. The player reads it where they wrote."""
    body = body.strip()
    if not body:
        raise MessageError("empty_reply", "Write a reply first.")
    if len(body) > 2000:
        raise MessageError("reply_too_long", "Keep the reply under 2000 characters.")

    row = await conn.fetchrow(_RECORD_REPLY, message_id, body)
    if row is None:
        raise MessageError("message_not_found", "No such message.", status=404)
    return Message(
        id=row["id"],
        kind=row["kind"],
        status=row["status"],
        body=row["body"],
        created_at=row["created_at"],
        answered_at=row["answered_at"],
        reply_body=row["reply_body"],
        replied_at=row["replied_at"],
    )
