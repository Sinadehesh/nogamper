"""The roster, adjustments, bans, and the message box.

Two of these operations change a player's points and one removes their access,
so the gate tests come first: the worst bug here is not a wrong number, it is
a player who can adjust their own balance.

The adjustment tests are really ledger tests wearing an admin hat. An operator
credit is an ordinary `ADMIN_ADJUSTMENT` entry, which means every invariant the
ledger already enforces applies to it — no negative balances, no double-posting
the same reference, and `users.coin_balance` staying in step. Those are the
properties worth pinning, because the tempting implementation is an UPDATE
against the balance column and it would pass a naive test.
"""

from __future__ import annotations

from conftest import (
    TEST_ADMIN_PLAYER,
    TEST_PASSWORD,
    authorise,
    balance_of,
    email_for,
    make_admin,
    user_id_for,
)

from backend import db

PLAYERS = "/v1/admin/players"
ADJUST = "/v1/admin/players/adjust"
STATUS = "/v1/admin/players/status"
INBOX = "/v1/admin/messages"
MESSAGES = "/v1/messages"


async def code_for(player: int) -> str:
    async with db.acquire() as conn:
        return await conn.fetchval(
            "SELECT player_code FROM users WHERE email = $1", email_for(player)
        )


async def test_every_player_gets_a_code_at_signup(app_client):
    headers = await authorise(app_client, 4242)
    profile = (await app_client.get("/v1/me", headers=headers)).json()

    assert len(profile["player_code"]) == 6
    assert profile["player_code"].isupper()


async def test_codes_avoid_the_glyphs_people_mishear(app_client):
    """O/0 and I/1/L are the pairs that produce wrong-account support tickets.

    The code is read aloud and typed back in, so the alphabet simply does not
    contain them rather than relying on anyone to disambiguate.
    """
    for player in range(7000, 7020):
        await authorise(app_client, player)

    async with db.acquire() as conn:
        codes = [r["player_code"] for r in await conn.fetch("SELECT player_code FROM users")]

    assert codes, "no players were created"
    for code in codes:
        assert not set(code) & set("O0I1L"), f"{code} contains an ambiguous glyph"


async def test_two_players_never_share_a_code(app_client):
    for player in range(7100, 7130):
        await authorise(app_client, player)

    async with db.acquire() as conn:
        codes = [r["player_code"] for r in await conn.fetch("SELECT player_code FROM users")]

    assert len(codes) == len(set(codes))


async def test_a_player_cannot_read_the_roster(app_client):
    headers = await authorise(app_client, 4242)
    assert (await app_client.get(PLAYERS, headers=headers)).status_code == 404


async def test_a_player_cannot_adjust_a_balance(app_client):
    """The worst bug this file exists to prevent."""
    headers = await authorise(app_client, 4242)
    mine = await code_for(4242)
    before = await balance_of(4242)

    response = await app_client.post(
        ADJUST,
        headers=headers,
        json={
            "player_code": mine,
            "amount_minor": 999_999_999,
            "reason": "hello",
            "reference": "nope",
        },
    )

    assert response.status_code == 404
    assert await balance_of(4242) == before, "a non-admin moved money"


async def test_a_player_cannot_ban_anyone(app_client):
    headers = await authorise(app_client, 4242)
    await authorise(app_client, 4243)
    victim = await code_for(4243)

    response = await app_client.post(
        STATUS, headers=headers, json={"player_code": victim, "status": "BANNED"}
    )
    assert response.status_code == 404

    async with db.acquire() as conn:
        assert (
            await conn.fetchval("SELECT status FROM users WHERE email = 'player4243@example.test'")
            == "ACTIVE"
        )


async def test_the_roster_lists_players_with_their_flow(app_client):
    admin = await make_admin(app_client)
    await authorise(app_client, 4242)

    body = (await app_client.get(PLAYERS, headers=admin)).json()
    wanted = await code_for(4242)

    assert body["total"] == 2
    assert wanted in {p["player_code"] for p in body["players"]}
    fresh = next(p for p in body["players"] if p["player_code"] == wanted)
    assert fresh["staked"]["minor"] == 0
    assert fresh["slips"] == 0


async def test_net_is_returned_minus_staked(app_client):
    """From the ledger, not from slip statuses.

    A slip can be settled or voided, and each is a different ledger row.
    Counting statuses would miss the refunds.
    """
    admin = await make_admin(app_client)

    async with db.transaction() as conn:
        user_id = await user_id_for(TEST_ADMIN_PLAYER)
        for entry_type, amount, key in (
            ("ADMIN_ADJUSTMENT", 1_000_000, "funds"),
            ("STAKE_DEBIT", -300_000, "stake"),
            ("PAYOUT_CREDIT", 220_000, "won"),
        ):
            await conn.execute(
                "INSERT INTO ledger_entries (user_id, entry_type, amount, idempotency_key) "
                "VALUES ($1, $2::ledger_entry_type, $3, $4)",
                user_id,
                entry_type,
                amount,
                key,
            )

    body = (await app_client.get(PLAYERS, headers=admin)).json()
    me = body["players"][0]

    assert me["staked"]["minor"] == 300_000
    assert me["returned"]["minor"] == 220_000
    assert me["net"]["minor"] == -80_000


async def test_the_roster_can_be_searched_by_code(app_client):
    admin = await make_admin(app_client)
    await authorise(app_client, 4242)
    wanted = await code_for(4242)

    body = (await app_client.get(PLAYERS, headers=admin, params={"search": wanted})).json()

    assert [p["player_code"] for p in body["players"]] == [wanted]


async def test_a_credit_goes_through_the_ledger(app_client):
    """Not an UPDATE to coin_balance.

    That column is a cache the ledger trigger owns. Writing it directly is the
    one bug in this system that compounds silently, which is why
    v_balance_reconciliation exists — and why this test checks it.
    """
    admin = await make_admin(app_client)
    await authorise(app_client, 4242)
    code = await code_for(4242)
    before = await balance_of(4242)

    response = await app_client.post(
        ADJUST,
        headers=admin,
        json={
            "player_code": code,
            "amount_minor": 250_000,
            "reason": "prize for the launch quiz",
            "reference": "quiz-1",
        },
    )

    assert response.status_code == 200
    assert await balance_of(4242) == before + 250_000

    async with db.acquire() as conn:
        entry = await conn.fetchrow(
            "SELECT entry_type::text AS t, amount, ref_type, ref_id, metadata "
            "FROM ledger_entries WHERE entry_type = 'ADMIN_ADJUSTMENT'"
        )
        drift = await conn.fetch("SELECT * FROM v_balance_reconciliation")

    assert entry["t"] == "ADMIN_ADJUSTMENT"
    assert entry["amount"] == 250_000
    assert entry["ref_type"] is None
    assert entry["ref_id"] is None
    assert "prize for the launch quiz" in entry["metadata"]
    assert drift == [], "the cached balance and the ledger disagree"


async def test_a_debit_reduces_the_balance(app_client):
    admin = await make_admin(app_client)
    await authorise(app_client, 4242)
    code = await code_for(4242)
    before = await balance_of(4242)

    await app_client.post(
        ADJUST,
        headers=admin,
        json={
            "player_code": code,
            "amount_minor": -50_000,
            "reason": "reversing a mistake",
            "reference": "oops-1",
        },
    )

    assert await balance_of(4242) == before - 50_000


async def test_a_debit_past_zero_is_refused_not_clamped(app_client):
    """The operator cannot take coins that are not there.

    Clamping would look kinder and would silently make the ledger disagree
    with the amount the operator thought they removed. The trigger raises
    PT001 exactly as it would for a player's own bet.
    """
    admin = await make_admin(app_client)
    await authorise(app_client, 4242)
    code = await code_for(4242)
    before = await balance_of(4242)

    response = await app_client.post(
        ADJUST,
        headers=admin,
        json={
            "player_code": code,
            "amount_minor": -(before + 1),
            "reason": "too much",
            "reference": "over-1",
        },
    )

    assert response.status_code == 409
    assert response.json()["code"] == "insufficient_funds"
    assert await balance_of(4242) == before


async def test_the_same_reference_cannot_be_posted_twice(app_client):
    """A double-clicked button must not credit a player twice."""
    admin = await make_admin(app_client)
    await authorise(app_client, 4242)
    code = await code_for(4242)
    before = await balance_of(4242)

    payload = {
        "player_code": code,
        "amount_minor": 100_000,
        "reason": "gift",
        "reference": "gift-1",
    }
    first = await app_client.post(ADJUST, headers=admin, json=payload)
    second = await app_client.post(ADJUST, headers=admin, json=payload)

    assert first.status_code == 200
    assert second.status_code == 409
    assert await balance_of(4242) == before + 100_000


async def test_an_unknown_code_is_a_404(app_client):
    admin = await make_admin(app_client)
    response = await app_client.post(
        ADJUST,
        headers=admin,
        json={"player_code": "ZZZZZZ", "amount_minor": 1000, "reason": "x", "reference": "y"},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "player_not_found"


async def test_banning_locks_the_player_out_immediately(app_client):
    """Not "whenever their token expires".

    current_user re-reads the row on every request, so the status alone would
    take effect — revoking the live sessions is what makes it immediate and
    unambiguous.
    """
    admin = await make_admin(app_client)
    victim = await authorise(app_client, 4242)
    code = await code_for(4242)

    assert (await app_client.get("/v1/me", headers=victim)).status_code == 200

    response = await app_client.post(
        STATUS, headers=admin, json={"player_code": code, "status": "BANNED"}
    )
    assert response.status_code == 200

    assert (await app_client.get("/v1/me", headers=victim)).status_code == 401


async def test_a_banned_player_keeps_their_history(app_client):
    """The rows stay. A banned player's ledger is part of the economy's
    history and deleting it would silently rewrite the books."""
    admin = await make_admin(app_client)
    await authorise(app_client, 4242)
    code = await code_for(4242)

    await app_client.post(STATUS, headers=admin, json={"player_code": code, "status": "BANNED"})

    body = (await app_client.get(PLAYERS, headers=admin)).json()
    banned = next(p for p in body["players"] if p["player_code"] == code)
    assert banned["status"] == "BANNED"
    assert banned["balance"]["minor"] > 0


async def test_a_ban_can_be_lifted(app_client):
    admin = await make_admin(app_client)
    await authorise(app_client, 4242)
    code = await code_for(4242)

    await app_client.post(STATUS, headers=admin, json={"player_code": code, "status": "BANNED"})
    response = await app_client.post(
        STATUS, headers=admin, json={"player_code": code, "status": "ACTIVE"}
    )

    assert response.json()["status"] == "ACTIVE"
    fresh = await authorise(app_client, 4242)
    assert (await app_client.get("/v1/me", headers=fresh)).status_code == 200


async def test_a_player_can_write_to_the_operator(app_client):
    headers = await authorise(app_client, 4242)

    response = await app_client.post(
        MESSAGES, headers=headers, json={"body": "This market looks wrong."}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["kind"] == "MESSAGE"
    assert body["status"] == "NEW"


async def test_there_is_no_such_thing_as_a_prize_claim(app_client):
    """There are no prizes, so a message cannot be one. A client that still
    sends the old `kind` gets an ordinary message, not a claim."""
    headers = await authorise(app_client, 4242)

    response = await app_client.post(
        MESSAGES, headers=headers, json={"body": "I won, pay me", "kind": "PRIZE_CLAIM"}
    )

    assert response.status_code == 201
    assert response.json()["kind"] == "MESSAGE"


async def test_a_player_sees_their_own_messages_back(app_client):
    """A box that shows nothing back looks broken."""
    headers = await authorise(app_client, 4242)
    await app_client.post(MESSAGES, headers=headers, json={"body": "hello there"})

    body = (await app_client.get(MESSAGES, headers=headers)).json()
    assert [m["body"] for m in body["messages"]] == ["hello there"]


async def test_a_player_never_sees_the_operators_note(app_client):
    """The note is a notebook, not a reply.

    A reply is something the operator chose to publish to the player. The
    note beside it never leaves the admin page, and showing it here would
    publish something written for one reader to another.
    """
    player = await authorise(app_client, 4242)
    admin = await make_admin(app_client)
    sent = (await app_client.post(MESSAGES, headers=player, json={"body": "hi"})).json()

    await app_client.post(
        f"{INBOX}/{sent['id']}",
        headers=admin,
        json={"status": "ANSWERED", "note": "sent them a sticker"},
    )

    mine = (await app_client.get(MESSAGES, headers=player)).json()["messages"][0]
    assert mine["status"] == "ANSWERED"
    assert "admin_note" not in mine


async def test_one_player_cannot_flood_the_inbox(app_client):
    """Not protecting the database — protecting the person who reads it.

    An operator who opens the admin page to two hundred messages from one
    player stops opening the admin page.
    """
    from backend.config import get_settings

    headers = await authorise(app_client, 4242)
    limit = get_settings().message_rate_max

    for i in range(limit):
        assert (
            await app_client.post(MESSAGES, headers=headers, json={"body": f"message {i}"})
        ).status_code == 201

    refused = await app_client.post(MESSAGES, headers=headers, json={"body": "one more"})
    assert refused.status_code == 429
    assert refused.json()["code"] == "too_many_messages"


async def test_a_player_cannot_read_the_inbox(app_client):
    headers = await authorise(app_client, 4242)
    assert (await app_client.get(INBOX, headers=headers)).status_code == 404


async def test_the_inbox_carries_the_account_beside_the_message(app_client):
    """The question a message raises is almost always about the account rather
    than the text, so the numbers travel with it."""
    player = await authorise(app_client, 4242)
    admin = await make_admin(app_client)
    await app_client.post(MESSAGES, headers=player, json={"body": "is this market stuck?"})

    body = (await app_client.get(INBOX, headers=admin)).json()
    item = body["messages"][0]

    assert body["unread"] == 1
    assert item["player_code"] == await code_for(4242)
    assert item["balance"]["minor"] > 0
    assert item["player_status"] == "ACTIVE"


async def test_triage_moves_a_message_out_of_new(app_client):
    player = await authorise(app_client, 4242)
    admin = await make_admin(app_client)
    sent = (await app_client.post(MESSAGES, headers=player, json={"body": "hello"})).json()

    await app_client.post(f"{INBOX}/{sent['id']}", headers=admin, json={"status": "ANSWERED"})

    body = (await app_client.get(INBOX, headers=admin)).json()
    assert body["unread"] == 0
    assert body["messages"][0]["status"] == "ANSWERED"
    assert body["messages"][0]["answered_at"] is not None


async def test_a_message_of_only_whitespace_is_refused(app_client):
    """Three spaces satisfy pydantic's min_length=1 and are still nothing.

    Two layers catch it and both are wanted: the schema bounds the size, the
    repository strips and checks the content. A 400 with a code rather than a
    422 because it is the second one that fires — the request was well-formed,
    it just said nothing.
    """
    headers = await authorise(app_client, 4242)
    response = await app_client.post(MESSAGES, headers=headers, json={"body": "   "})

    assert response.status_code == 400
    assert response.json()["code"] == "empty_message"


async def test_a_message_past_the_length_limit_is_refused(app_client):
    headers = await authorise(app_client, 4242)
    response = await app_client.post(MESSAGES, headers=headers, json={"body": "x" * 2001})
    assert response.status_code == 422


async def test_the_profile_says_whether_this_player_is_an_admin(app_client):
    """So the site knows whether to show the link to the admin pages."""
    admin = await make_admin(app_client)
    player = await authorise(app_client, 4242)

    assert (await app_client.get("/v1/me", headers=admin)).json()["is_admin"] is True
    assert (await app_client.get("/v1/me", headers=player)).json()["is_admin"] is False


async def test_the_flag_is_present_on_the_session_response_too(app_client):
    """Otherwise the link appears only after the first profile refresh, which
    on a cold load is a page later."""
    await make_admin(app_client)

    response = await app_client.post(
        "/v1/auth/login", json={"email": email_for(TEST_ADMIN_PLAYER), "password": TEST_PASSWORD}
    )
    assert response.json()["user"]["is_admin"] is True


async def test_the_flag_is_a_hint_and_not_the_gate(app_client):
    """A client that forges is_admin reaches a page whose first request 404s.

    Stated as a test because the flag looks like an authorisation decision and
    is not one — the allowlist is re-checked on every admin route, and this is
    what keeps that true if somebody later reaches for the flag as a shortcut.
    """
    player = await authorise(app_client, 4242)

    assert (await app_client.get(PLAYERS, headers=player)).status_code == 404
    assert (await app_client.get("/v1/admin/diagnostics", headers=player)).status_code == 404


# ----- the operator's answer ------------------------------------------------


async def test_a_reply_is_stored_and_the_player_reads_it_in_the_app(app_client):
    player = await authorise(app_client, 4242)
    admin = await make_admin(app_client)
    sent = (await app_client.post(MESSAGES, headers=player, json={"body": "hello?"})).json()

    reply = await app_client.post(
        f"{INBOX}/{sent['id']}/reply", headers=admin, json={"body": "  Fixed — thanks.  "}
    )
    assert reply.status_code == 200
    assert reply.json()["status"] == "ANSWERED"
    assert reply.json()["reply_body"] == "Fixed — thanks."

    mine = (await app_client.get(MESSAGES, headers=player)).json()["messages"][0]
    assert mine["reply_body"] == "Fixed — thanks."
    assert mine["replied_at"] is not None
    assert mine["status"] == "ANSWERED"


async def test_a_player_cannot_answer_messages(app_client):
    player = await authorise(app_client, 4242)
    sent = (await app_client.post(MESSAGES, headers=player, json={"body": "hello?"})).json()

    refused = await app_client.post(
        f"{INBOX}/{sent['id']}/reply", headers=player, json={"body": "answering myself"}
    )
    assert refused.status_code == 404


async def test_replying_to_a_message_that_does_not_exist_is_a_404(app_client):
    admin = await make_admin(app_client)

    response = await app_client.post(
        f"{INBOX}/00000000-0000-0000-0000-000000000000/reply", headers=admin, json={"body": "hi"}
    )
    assert response.status_code == 404
    assert response.json()["code"] == "message_not_found"


async def test_an_empty_reply_is_refused(app_client):
    player = await authorise(app_client, 4242)
    admin = await make_admin(app_client)
    sent = (await app_client.post(MESSAGES, headers=player, json={"body": "hello?"})).json()

    refused = await app_client.post(
        f"{INBOX}/{sent['id']}/reply", headers=admin, json={"body": "   "}
    )
    assert refused.status_code == 422


# ----- what the roster shows ------------------------------------------------


async def test_the_roster_shows_who_is_a_guest_and_who_registered(app_client):
    admin = await make_admin(app_client)
    await app_client.post("/v1/auth/guest")

    players = (await app_client.get(PLAYERS, headers=admin)).json()["players"]
    by_guest = {p["is_guest"]: p for p in players}

    assert by_guest[True]["email"] is None
    assert by_guest[False]["email"] == email_for(TEST_ADMIN_PLAYER)


async def test_the_roster_can_be_searched_by_email(app_client):
    admin = await make_admin(app_client)
    await authorise(app_client, 4242)

    body = (await app_client.get(PLAYERS, headers=admin, params={"search": "player4242"})).json()
    assert [p["email"] for p in body["players"]] == [email_for(4242)]


async def test_a_percent_sign_in_the_search_is_a_percent_sign(app_client):
    """Unescaped, `%` is a wildcard and the search returns everybody."""
    admin = await make_admin(app_client)
    await authorise(app_client, 4242)

    body = (await app_client.get(PLAYERS, headers=admin, params={"search": "%"})).json()
    assert body["players"] == []
    assert body["total"] == 0


async def test_the_roster_shows_the_brakes_a_player_has_set(app_client):
    admin = await make_admin(app_client)
    player = await authorise(app_client, 4242)
    await app_client.put("/v1/me/limits", json={"daily_limit_minor": 20_000}, headers=player)
    await app_client.post("/v1/me/break", json={"hours": 24}, headers=player)

    body = (await app_client.get(PLAYERS, headers=admin, params={"search": "player4242"})).json()
    row = body["players"][0]

    assert row["daily_limit"]["minor"] == 20_000
    assert row["break_until"] is not None


async def test_an_erased_account_drops_off_the_roster(app_client):
    admin = await make_admin(app_client)
    player = await authorise(app_client, 4242)
    await app_client.post("/v1/me/erase", json={"password": TEST_PASSWORD}, headers=player)

    body = (await app_client.get(PLAYERS, headers=admin)).json()
    assert body["total"] == 1
    assert [p["email"] for p in body["players"]] == [email_for(TEST_ADMIN_PLAYER)]


async def test_an_adjustment_names_the_player_by_code_and_nothing_else(app_client):
    admin = await make_admin(app_client)
    await authorise(app_client, 4242)

    response = await app_client.post(
        ADJUST,
        headers=admin,
        json={"email": email_for(4242), "amount_minor": 5_000, "reason": "x", "reference": "r1"},
    )
    assert response.status_code == 422
    assert await balance_of(4242) == 100_000
