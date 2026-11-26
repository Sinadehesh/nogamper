"""The player's side of the message box.

Two routes: send one, read your own back. The operator's side lives in
routers/admin.py behind the allowlist.

Rate limiting is deliberately generous and deliberately present. It is not
protecting the database — a message is one small insert — it is protecting the
one person who reads the inbox. An operator who opens the admin page to two
hundred messages from the same player stops opening the admin page.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from .. import db
from ..config import Settings, get_settings
from ..repositories import messages as messages_repo
from ..schemas import MessageList, MessageOut, MessageRequest
from ..security.dependencies import CurrentUser

router = APIRouter(prefix="/v1/messages", tags=["messages"])


def _out(message: messages_repo.Message) -> MessageOut:
    return MessageOut(
        id=str(message.id),
        kind=message.kind,
        status=message.status,
        body=message.body,
        created_at=message.created_at,
        answered_at=message.answered_at,
        reply_body=message.reply_body,
        replied_at=message.replied_at,
    )


@router.post("", response_model=MessageOut, status_code=201, summary="Write to the operator")
async def send_message(
    payload: MessageRequest,
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> MessageOut:
    async with db.transaction() as conn:
        message = await messages_repo.send(
            conn,
            user_id=user["id"],
            body=payload.body,
            kind=payload.kind,
            window_seconds=settings.message_rate_window_seconds,
            max_in_window=settings.message_rate_max,
        )
    return _out(message)


@router.get("", response_model=MessageList, summary="Your own messages and their status")
async def my_messages(user: CurrentUser) -> MessageList:
    """Deliberately returns the player's own messages and not the operator's
    notes on them. A box that shows nothing back looks broken; a box that
    shows a private note looks like a reply the app never promised."""
    async with db.acquire() as conn:
        rows = await messages_repo.mine(conn, user["id"])
    return MessageList(messages=[_out(m) for m in rows])
