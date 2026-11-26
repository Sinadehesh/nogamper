"""The operator answers a player without becoming a person they can contact.

The inbox was built one-way: a player wrote, and the operator answered from
their own Telegram account or not at all. That is a bad trade — answering a
question about a prize should not hand a stranger the operator's name,
username and photo, permanently.

So the reply goes out as the bot. What is under test is that promise (the
operator's identity never travels), and the case that would otherwise lose an
answer: a bot may not open a conversation the player has not opened first, so
some players simply cannot be delivered to. Their answer has to survive that
rather than disappear while the operator believes they replied.
"""

from __future__ import annotations

import httpx
import pytest
from conftest import TEST_ADMIN_TELEGRAM_ID, authorise

REPLY = "/v1/admin/messages/{id}/reply"


class FakeBot:
    """A Bot API that records what was sent, and can refuse like Telegram does."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.refuse: tuple[int, str] | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        method = request.url.path.rsplit("/", 1)[-1]
        body = {} if not request.content else __import__("json").loads(request.content)
        self.calls.append((method, body))
        if method == "sendMessage" and self.refuse:
            code, description = self.refuse
            return httpx.Response(
                200, json={"ok": False, "error_code": code, "description": description}
            )
        return httpx.Response(200, json={"ok": True, "result": True})

    def sent(self) -> list[dict]:
        return [body for name, body in self.calls if name == "sendMessage"]


@pytest.fixture
def bot(app_client) -> FakeBot:
    fake = FakeBot()
    app = app_client._transport.app  # type: ignore[attr-defined]
    app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(fake.handler))
    return fake


async def write_message(app_client, headers, body="I won, where is my prize?") -> str:
    response = await app_client.post("/v1/messages", json={"body": body}, headers=headers)
    response.raise_for_status()
    return response.json()["id"]


async def test_the_reply_goes_out_as_the_bot_and_carries_nothing_about_the_operator(
    app_client, bot
):
    """The whole reason this exists. The player is sent the answer and nothing
    else — no operator id, no username, no "from" of any kind."""
    player = await authorise(app_client, telegram_id=717171)
    admin = await authorise(app_client, telegram_id=TEST_ADMIN_TELEGRAM_ID)
    message_id = await write_message(app_client, player)

    response = await app_client.post(
        REPLY.format(id=message_id), json={"body": "Send me your address."}, headers=admin
    )

    assert response.status_code == 200
    assert response.json()["delivered"] is True

    sent = bot.sent()
    assert len(sent) == 1
    assert sent[0]["chat_id"] == 717171
    assert sent[0]["text"] == "Send me your address."
    assert str(TEST_ADMIN_TELEGRAM_ID) not in str(sent[0])


async def test_the_player_reads_the_reply_in_the_app(app_client, bot):
    """Not only in Telegram. The player wrote from the app, so the answer has
    to be findable where they asked."""
    player = await authorise(app_client, telegram_id=717172)
    admin = await authorise(app_client, telegram_id=TEST_ADMIN_TELEGRAM_ID)
    message_id = await write_message(app_client, player)

    await app_client.post(
        REPLY.format(id=message_id), json={"body": "Your prize is on its way."}, headers=admin
    )

    mine = (await app_client.get("/v1/messages", headers=player)).json()["messages"][0]
    assert mine["reply_body"] == "Your prize is on its way."
    assert mine["replied_at"] is not None
    assert mine["status"] == "ANSWERED"


async def test_the_private_note_is_still_never_sent_to_the_player(app_client, bot):
    """`admin_note` is a notebook — "this one is lying about winning" — and
    adding a reply channel must not turn it into a message."""
    player = await authorise(app_client, telegram_id=717173)
    admin = await authorise(app_client, telegram_id=TEST_ADMIN_TELEGRAM_ID)
    message_id = await write_message(app_client, player)

    await app_client.post(
        f"/v1/admin/messages/{message_id}",
        json={"status": "SEEN", "note": "probably lying"},
        headers=admin,
    )
    await app_client.post(REPLY.format(id=message_id), json={"body": "Thanks!"}, headers=admin)

    mine = (await app_client.get("/v1/messages", headers=player)).json()["messages"][0]
    assert "probably lying" not in str(mine)
    assert mine["reply_body"] == "Thanks!"
    assert "probably lying" not in str(bot.sent())


async def test_a_player_who_never_started_the_bot_still_gets_their_answer(app_client, bot):
    """Telegram forbids a bot opening a conversation first, so a player who
    launched the Mini App from a link is unreachable — 403, permanently.

    Losing the answer there would be worse than not sending it: the operator
    would believe they had replied and the player would be left waiting.
    """
    bot.refuse = (403, "Forbidden: bot can't initiate conversation with a user")
    player = await authorise(app_client, telegram_id=717174)
    admin = await authorise(app_client, telegram_id=TEST_ADMIN_TELEGRAM_ID)
    message_id = await write_message(app_client, player)

    response = await app_client.post(
        REPLY.format(id=message_id), json={"body": "Open the bot and message me."}, headers=admin
    )

    assert response.status_code == 200
    body = response.json()
    assert body["delivered"] is False
    assert "never started the bot" in body["delivery_detail"]

    mine = (await app_client.get("/v1/messages", headers=player)).json()["messages"][0]
    assert mine["reply_body"] == "Open the bot and message me."


async def test_the_inbox_shows_which_replies_telegram_would_not_carry(app_client, bot):
    """The operator has to be able to tell "answered" from "answered and they
    have seen it", or they will wait for a response that cannot come."""
    bot.refuse = (403, "Forbidden: bot was blocked by the user")
    player = await authorise(app_client, telegram_id=717175)
    admin = await authorise(app_client, telegram_id=TEST_ADMIN_TELEGRAM_ID)
    message_id = await write_message(app_client, player)

    await app_client.post(REPLY.format(id=message_id), json={"body": "Hello"}, headers=admin)

    inbox = (await app_client.get("/v1/admin/messages", headers=admin)).json()["messages"][0]
    assert inbox["reply_body"] == "Hello"
    assert inbox["reply_delivered"] is False


async def test_a_telegram_outage_does_not_lose_the_reply(app_client, bot):
    """Distinct from an unreachable player and worth its own case: the answer
    is still saved, and the operator is told it did not go out."""
    bot.refuse = (500, "Internal Server Error")
    player = await authorise(app_client, telegram_id=717176)
    admin = await authorise(app_client, telegram_id=TEST_ADMIN_TELEGRAM_ID)
    message_id = await write_message(app_client, player)

    body = (
        await app_client.post(
            REPLY.format(id=message_id), json={"body": "Still saved"}, headers=admin
        )
    ).json()

    assert body["delivered"] is False
    assert body["reply_body"] == "Still saved"


async def test_a_player_cannot_reply_to_their_own_message(app_client, bot):
    """Otherwise anyone could send app messages as the bot, to anyone."""
    player = await authorise(app_client, telegram_id=717177)
    message_id = await write_message(app_client, player)

    response = await app_client.post(
        REPLY.format(id=message_id), json={"body": "credit me 1m"}, headers=player
    )

    assert response.status_code == 404
    assert bot.sent() == []


async def test_replying_to_a_message_that_does_not_exist_is_a_404(app_client, bot):
    import uuid

    admin = await authorise(app_client, telegram_id=TEST_ADMIN_TELEGRAM_ID)
    response = await app_client.post(
        REPLY.format(id=uuid.uuid4()), json={"body": "hello"}, headers=admin
    )

    assert response.status_code == 404
    assert bot.sent() == []


async def test_an_empty_reply_is_refused_before_anything_is_sent(app_client, bot):
    player = await authorise(app_client, telegram_id=717178)
    admin = await authorise(app_client, telegram_id=TEST_ADMIN_TELEGRAM_ID)
    message_id = await write_message(app_client, player)

    response = await app_client.post(
        REPLY.format(id=message_id), json={"body": "   "}, headers=admin
    )

    assert response.status_code == 422
    assert bot.sent() == []
