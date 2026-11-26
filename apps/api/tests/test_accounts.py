"""Accounts end to end: register, sign in, play as a guest, upgrade, leave."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from conftest import TEST_JWT_SECRET, TEST_PASSWORD, authorise, email_for

from backend import db
from backend.config import get_settings

GOOD = {
    "email": "ada@example.test",
    "password": TEST_PASSWORD,
    "display_name": "Ada",
}


async def register(client, **overrides):
    return await client.post("/v1/auth/register", json={**GOOD, **overrides})


async def login(client, email=GOOD["email"], password=TEST_PASSWORD):
    return await client.post("/v1/auth/login", json={"email": email, "password": password})


def bearer(response) -> dict[str, str]:
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


# ----- registering ----------------------------------------------------------


async def test_registering_creates_an_account_with_a_ledger_backed_balance(app_client):
    response = await register(app_client)
    assert response.status_code == 201

    body = response.json()
    assert body["is_new_user"] is True
    assert body["token_type"] == "Bearer"
    assert body["user"]["email"] == "ada@example.test"
    assert body["user"]["display_name"] == "Ada"
    assert body["user"]["is_guest"] is False
    assert body["user"]["balance"] == {"minor": 100_000, "display": "1,000"}
    assert body["user"]["can_claim_daily"] is True

    async with db.acquire() as conn:
        entries = await conn.fetch("SELECT entry_type, amount, balance_after FROM ledger_entries")
        drift = await conn.fetch("SELECT * FROM v_balance_reconciliation")

    assert [(e["entry_type"], e["amount"], e["balance_after"]) for e in entries] == [
        ("SIGNUP_BONUS_CREDIT", 100_000, 100_000)
    ]
    assert drift == []


async def test_the_password_is_stored_as_an_argon2id_hash_and_never_returned(app_client):
    response = await register(app_client)

    assert TEST_PASSWORD not in response.text
    assert "password" not in response.json()["user"]

    async with db.acquire() as conn:
        stored = await conn.fetchval(
            "SELECT password_hash FROM users WHERE email = $1", GOOD["email"]
        )
    assert stored.startswith("$argon2id$")
    assert TEST_PASSWORD not in stored


async def test_an_email_is_stored_lower_cased_and_matched_case_insensitively(app_client):
    await register(app_client, email="  Ada@Example.TEST ")

    assert (await register(app_client, email="ADA@example.test")).status_code == 409
    assert (await login(app_client, email="Ada@Example.Test")).status_code == 200


async def test_the_same_email_cannot_be_registered_twice(app_client):
    assert (await register(app_client)).status_code == 201

    again = await register(app_client, display_name="Someone else")
    assert again.status_code == 409
    assert again.json()["code"] == "email_taken"

    async with db.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM users") == 1
        # The refused sign-up must not have been paid an opening balance.
        assert await conn.fetchval("SELECT count(*) FROM ledger_entries") == 1


@pytest.mark.parametrize(
    "email",
    ["not-an-address", "two@@example.test", "no-domain@", "@no-local.test", "spa ce@example.test"],
)
async def test_a_malformed_email_is_refused(app_client, email):
    response = await register(app_client, email=email)
    assert response.status_code == 400
    assert response.json()["code"] == "invalid_email"


@pytest.mark.parametrize(
    ("password", "code"),
    [
        ("short", "password_too_short"),
        ("x" * 200, "password_too_long"),
        ("aaaaaaaaaaaa", "password_too_common"),
        ("1234567890", "password_too_common"),
        ("ada@example.test", "password_too_common"),
    ],
)
async def test_a_weak_password_is_refused_with_the_reason(app_client, password, code):
    response = await register(app_client, password=password)
    assert response.status_code == 400
    assert response.json()["code"] == code

    async with db.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM users") == 0


@pytest.mark.parametrize("name", ["A", "x" * 25, "Robert'); DROP", "bad‮name", "<b>bold</b>"])
async def test_a_display_name_that_could_mislead_is_refused(app_client, name):
    """Other players see this string. One character, an essay, markup, or a
    right-to-left override that makes one name read as another are all out."""
    response = await register(app_client, display_name=name)
    assert response.status_code == 400
    assert response.json()["code"] == "invalid_display_name"


@pytest.mark.parametrize("name", ["Ada", "Ada Lovelace", "José", "Zoë_92", "O'Neil", "李雷"])
async def test_ordinary_names_in_any_script_are_accepted(app_client, name):
    response = await register(app_client, display_name=name)
    assert response.status_code == 201
    assert response.json()["user"]["display_name"] == name


# ----- signing in -----------------------------------------------------------


async def test_signing_in_returns_a_session_and_pays_no_second_bonus(app_client):
    await register(app_client)

    response = await login(app_client)
    assert response.status_code == 200
    assert response.json()["is_new_user"] is False
    assert response.json()["user"]["balance"]["minor"] == 100_000

    async with db.acquire() as conn:
        bonuses = await conn.fetchval(
            "SELECT count(*) FROM ledger_entries WHERE entry_type = 'SIGNUP_BONUS_CREDIT'"
        )
    assert bonuses == 1


async def test_a_wrong_password_and_an_unknown_email_get_the_same_answer(app_client):
    """Telling them apart would let the sign-in form confirm who has an
    account here."""
    await register(app_client)

    wrong = await login(app_client, password="not the right password")
    unknown = await login(app_client, email="nobody@example.test")

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert wrong.json()["code"] == "invalid_credentials"


async def test_the_session_token_unlocks_the_protected_route(app_client):
    response = await register(app_client)

    me = await app_client.get("/v1/me", headers=bearer(response))
    assert me.status_code == 200
    assert me.json()["email"] == "ada@example.test"
    assert me.json()["player_code"] == response.json()["user"]["player_code"]


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer"},
        {"Authorization": "Basic abc"},
        {"Authorization": "Bearer x.y.z"},
    ],
)
async def test_the_protected_route_refuses_everything_unsigned(app_client, headers):
    assert (await app_client.get("/v1/me", headers=headers)).status_code == 401


async def test_a_token_signed_with_another_key_is_refused(app_client):
    response = await register(app_client)
    claims = jwt.decode(response.json()["access_token"], TEST_JWT_SECRET, algorithms=["HS256"])

    forged = jwt.encode(claims, "an-entirely-different-secret-value-000", algorithm="HS256")
    refused = await app_client.get("/v1/me", headers={"Authorization": f"Bearer {forged}"})
    assert refused.status_code == 401
    assert refused.json()["code"] == "token_invalid"


async def test_a_validly_signed_token_for_a_session_that_never_existed_is_refused(app_client):
    """The token is a pointer to a row, not a capability in itself."""
    response = await register(app_client)
    claims = jwt.decode(response.json()["access_token"], TEST_JWT_SECRET, algorithms=["HS256"])
    claims["jti"] = str(uuid.uuid4())

    orphan = jwt.encode(claims, TEST_JWT_SECRET, algorithm="HS256")
    refused = await app_client.get("/v1/me", headers={"Authorization": f"Bearer {orphan}"})
    assert refused.status_code == 401
    assert refused.json()["code"] == "session_unknown"


async def test_signing_out_takes_effect_immediately(app_client):
    headers = bearer(await register(app_client))

    assert (await app_client.delete("/v1/auth/session", headers=headers)).status_code == 204

    after = await app_client.get("/v1/me", headers=headers)
    assert after.status_code == 401
    assert after.json()["code"] == "session_revoked"


async def test_signing_in_twice_gives_two_independent_sessions(app_client):
    """A phone and a laptop. Signing out of one must not sign out the other."""
    await register(app_client)
    phone = bearer(await login(app_client))
    laptop = bearer(await login(app_client))

    await app_client.delete("/v1/auth/session", headers=phone)

    assert (await app_client.get("/v1/me", headers=phone)).status_code == 401
    assert (await app_client.get("/v1/me", headers=laptop)).status_code == 200


async def test_an_expired_session_is_refused_even_with_a_live_token(app_client):
    headers = bearer(await register(app_client))

    async with db.acquire() as conn:
        await conn.execute(
            "UPDATE auth_sessions SET issued_at = $1, expires_at = $2",
            datetime.now(UTC) - timedelta(days=2),
            datetime.now(UTC) - timedelta(days=1),
        )

    refused = await app_client.get("/v1/me", headers=headers)
    assert refused.status_code == 401
    assert refused.json()["code"] == "session_expired"


async def test_a_banned_account_cannot_sign_in_but_learns_it_only_with_the_password(app_client):
    await register(app_client)
    async with db.acquire() as conn:
        await conn.execute("UPDATE users SET status = 'BANNED'")

    with_password = await login(app_client)
    assert with_password.status_code == 403
    assert with_password.json()["code"] == "account_suspended"

    # Without the password, the answer is the one every other failure gets.
    without = await login(app_client, password="a guess at the password")
    assert without.status_code == 401
    assert without.json()["code"] == "invalid_credentials"


async def test_a_session_opened_before_a_ban_stops_working(app_client):
    headers = bearer(await register(app_client))
    async with db.acquire() as conn:
        await conn.execute("UPDATE users SET status = 'BANNED'")

    refused = await app_client.get("/v1/me", headers=headers)
    assert refused.status_code == 403
    assert refused.json()["code"] == "account_suspended"


async def test_an_old_hash_is_upgraded_at_the_next_sign_in(app_client):
    """Raising the cost needs no migration: the plaintext is only ever present
    at sign-in, so that is when a hash made under the old cost is replaced."""
    await register(app_client)
    async with db.acquire() as conn:
        before = await conn.fetchval("SELECT password_hash FROM users")

    get_settings().password_hash_time_cost = 2
    assert (await login(app_client)).status_code == 200

    async with db.acquire() as conn:
        after = await conn.fetchval("SELECT password_hash FROM users")
    assert after != before
    assert "t=2" in after

    # And the upgraded hash is the same password.
    assert (await login(app_client)).status_code == 200


# ----- guests ---------------------------------------------------------------


async def test_a_guest_gets_a_full_account_with_no_credentials(app_client):
    response = await app_client.post("/v1/auth/guest")
    assert response.status_code == 201

    user = response.json()["user"]
    assert user["is_guest"] is True
    assert user["email"] is None
    assert user["balance"]["minor"] == 100_000
    assert len(user["player_code"]) == 6

    me = await app_client.get("/v1/me", headers=bearer(response))
    assert me.status_code == 200
    assert me.json()["id"] == user["id"]


async def test_every_guest_is_a_separate_account(app_client):
    first = (await app_client.post("/v1/auth/guest")).json()["user"]
    second = (await app_client.post("/v1/auth/guest")).json()["user"]
    assert first["id"] != second["id"]
    assert first["player_code"] != second["player_code"]


async def test_a_guest_who_registers_keeps_their_account(app_client):
    """Same row, same balance, same history — only the credentials are new."""
    guest = await app_client.post("/v1/auth/guest")
    guest_headers = bearer(guest)
    guest_user = guest.json()["user"]

    async with db.acquire() as conn:
        await conn.execute(
            "INSERT INTO ledger_entries (user_id, entry_type, amount, idempotency_key) "
            "VALUES ($1, 'ADMIN_ADJUSTMENT', 4200, 'played-as-guest')",
            uuid.UUID(guest_user["id"]),
        )

    upgraded = await app_client.post("/v1/auth/register", json=GOOD, headers=guest_headers)
    assert upgraded.status_code == 201

    user = upgraded.json()["user"]
    assert user["id"] == guest_user["id"]
    assert user["player_code"] == guest_user["player_code"]
    assert user["is_guest"] is False
    assert user["email"] == GOOD["email"]
    assert user["balance"]["minor"] == 104_200
    assert upgraded.json()["is_new_user"] is False

    async with db.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM users") == 1
        bonuses = await conn.fetchval(
            "SELECT count(*) FROM ledger_entries WHERE entry_type = 'SIGNUP_BONUS_CREDIT'"
        )
    assert bonuses == 1, "upgrading must not pay a second opening balance"


async def test_upgrading_retires_the_guest_session(app_client):
    guest_headers = bearer(await app_client.post("/v1/auth/guest"))

    upgraded = await app_client.post("/v1/auth/register", json=GOOD, headers=guest_headers)

    assert (await app_client.get("/v1/me", headers=guest_headers)).status_code == 401
    assert (await app_client.get("/v1/me", headers=bearer(upgraded))).status_code == 200
    assert (await login(app_client)).status_code == 200


async def test_a_guest_cannot_take_an_email_that_is_already_registered(app_client):
    await register(app_client)
    guest_headers = bearer(await app_client.post("/v1/auth/guest"))

    refused = await app_client.post("/v1/auth/register", json=GOOD, headers=guest_headers)
    assert refused.status_code == 409
    assert refused.json()["code"] == "email_taken"

    # Still a guest, still signed in: the failed upgrade changed nothing.
    me = await app_client.get("/v1/me", headers=guest_headers)
    assert me.status_code == 200
    assert me.json()["is_guest"] is True


async def test_registering_with_a_dead_cookie_still_works(app_client):
    """A stale token is "nobody", not an error — the form must not be
    unusable for someone whose old session happens to have lapsed."""
    response = await app_client.post(
        "/v1/auth/register", json=GOOD, headers={"Authorization": "Bearer not.a.token"}
    )
    assert response.status_code == 201
    assert response.json()["is_new_user"] is True


async def test_a_registered_player_who_registers_again_gets_a_second_account(app_client):
    """Only a *guest* session is upgraded. A signed-in registered player
    filling in the form is opening another account, not renaming this one."""
    first = await register(app_client)

    second = await app_client.post(
        "/v1/auth/register",
        json={**GOOD, "email": "grace@example.test", "display_name": "Grace"},
        headers=bearer(first),
    )
    assert second.status_code == 201
    assert second.json()["user"]["id"] != first.json()["user"]["id"]
    assert (await app_client.get("/v1/me", headers=bearer(first))).status_code == 200


# ----- changing a password --------------------------------------------------


async def test_changing_the_password_signs_out_every_other_device(app_client):
    await register(app_client)
    here = bearer(await login(app_client))
    elsewhere = bearer(await login(app_client))

    changed = await app_client.post(
        "/v1/auth/password",
        json={"current_password": TEST_PASSWORD, "new_password": "a brand new long passphrase"},
        headers=here,
    )
    assert changed.status_code == 204

    assert (await app_client.get("/v1/me", headers=here)).status_code == 200
    assert (await app_client.get("/v1/me", headers=elsewhere)).status_code == 401

    assert (await login(app_client)).status_code == 401
    assert (await login(app_client, password="a brand new long passphrase")).status_code == 200


async def test_changing_the_password_needs_the_current_one(app_client):
    headers = bearer(await register(app_client))

    refused = await app_client.post(
        "/v1/auth/password",
        json={"current_password": "not it", "new_password": "a brand new long passphrase"},
        headers=headers,
    )
    assert refused.status_code == 401
    assert (await login(app_client)).status_code == 200


async def test_the_new_password_is_held_to_the_same_rules(app_client):
    headers = bearer(await register(app_client))

    refused = await app_client.post(
        "/v1/auth/password",
        json={"current_password": TEST_PASSWORD, "new_password": "short"},
        headers=headers,
    )
    assert refused.status_code == 400
    assert refused.json()["code"] == "password_too_short"


async def test_a_guest_has_no_password_to_change(app_client):
    headers = bearer(await app_client.post("/v1/auth/guest"))

    refused = await app_client.post(
        "/v1/auth/password",
        json={"current_password": "anything", "new_password": "a brand new long passphrase"},
        headers=headers,
    )
    assert refused.status_code == 400
    assert refused.json()["code"] == "not_registered"


# ----- the profile ----------------------------------------------------------


async def test_a_player_can_change_their_display_name(app_client):
    headers = bearer(await register(app_client))

    updated = await app_client.patch(
        "/v1/me", json={"display_name": "  Ada   L. "}, headers=headers
    )
    assert updated.status_code == 200
    assert updated.json()["display_name"] == "Ada L."

    assert (await app_client.get("/v1/me", headers=headers)).json()["display_name"] == "Ada L."


async def test_a_new_display_name_is_held_to_the_same_rules(app_client):
    headers = bearer(await register(app_client))

    refused = await app_client.patch("/v1/me", json={"display_name": "<script>"}, headers=headers)
    assert refused.status_code == 400
    assert refused.json()["code"] == "invalid_display_name"


# ----- leaving --------------------------------------------------------------


async def test_erasing_an_account_removes_what_identifies_the_person(app_client):
    response = await register(app_client)
    headers = bearer(response)
    await app_client.post(
        "/v1/messages", json={"body": "my address is 1 Example St"}, headers=headers
    )

    erased = await app_client.post(
        "/v1/me/erase", json={"password": TEST_PASSWORD}, headers=headers
    )
    assert erased.status_code == 204

    async with db.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users")
        messages = await conn.fetchval("SELECT count(*) FROM player_messages")
        ledger = await conn.fetchval("SELECT count(*) FROM ledger_entries")

    assert row["email"] is None
    assert row["password_hash"] is None
    assert row["first_name"] == "Deleted player"
    assert row["deleted_at"] is not None
    assert messages == 0
    assert ledger == 1, "the ledger is everybody's history and stays"

    assert (await app_client.get("/v1/me", headers=headers)).status_code == 401
    assert (await login(app_client)).status_code == 401


async def test_erasing_a_registered_account_needs_the_password(app_client):
    headers = bearer(await register(app_client))

    for body in ({}, {"password": "a wrong guess entirely"}):
        refused = await app_client.post("/v1/me/erase", json=body, headers=headers)
        assert refused.status_code == 401

    assert (await app_client.get("/v1/me", headers=headers)).status_code == 200


async def test_an_erased_email_can_be_registered_afresh(app_client):
    """The address was released, so the same person can come back — as a new
    account, with none of the old one attached."""
    first = await register(app_client)
    await app_client.post("/v1/me/erase", json={"password": TEST_PASSWORD}, headers=bearer(first))

    again = await register(app_client)
    assert again.status_code == 201
    assert again.json()["user"]["id"] != first.json()["user"]["id"]
    assert again.json()["user"]["balance"]["minor"] == 100_000


async def test_a_guest_can_erase_their_account_with_no_password(app_client):
    headers = bearer(await app_client.post("/v1/auth/guest"))

    assert (await app_client.post("/v1/me/erase", json={}, headers=headers)).status_code == 204
    assert (await app_client.get("/v1/me", headers=headers)).status_code == 401


# ----- plumbing -------------------------------------------------------------


async def test_health_and_readiness(app_client):
    assert (await app_client.get("/health")).json() == {"status": "ok"}

    ready = (await app_client.get("/health/ready")).json()
    assert ready["status"] == "ready"
    assert ready["database"] == "ok"


async def test_the_helper_signs_in_the_same_player_twice(app_client):
    """`authorise` is how every other test gets a player; it has to mean the
    same account the second time it is called with the same number."""
    await authorise(app_client, 7)
    await authorise(app_client, 7)

    async with db.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM users WHERE email = $1", email_for(7)) == 1
