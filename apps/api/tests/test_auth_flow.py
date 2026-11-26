"""End-to-end auth: initData in, session out, protected route reachable."""

from __future__ import annotations

import time

import pytest
from conftest import make_init_data

from backend import db


async def exchange(client, raw: str):
    return await client.post("/v1/auth/session", json={"initData": raw})


async def test_first_launch_creates_an_account_with_a_ledger_backed_balance(app_client):
    response = await exchange(app_client, make_init_data(telegram_id=1001, first_name="Ada"))
    assert response.status_code == 200

    body = response.json()
    assert body["is_new_user"] is True
    assert body["token_type"] == "Bearer"
    assert body["user"]["telegram_id"] == 1001
    assert body["user"]["balance"] == {"minor": 100_000, "display": "1,000"}
    assert body["user"]["streak_count"] == 0
    assert body["user"]["can_claim_daily"] is True

    async with db.acquire() as conn:
        entries = await conn.fetch("SELECT entry_type, amount, balance_after FROM ledger_entries")
        drift = await conn.fetch("SELECT * FROM v_balance_reconciliation")

    assert [(e["entry_type"], e["amount"], e["balance_after"]) for e in entries] == [
        ("SIGNUP_BONUS_CREDIT", 100_000, 100_000)
    ]
    assert drift == []


async def test_returning_player_is_not_paid_the_signup_bonus_twice(app_client):
    first = await exchange(app_client, make_init_data(telegram_id=1002))
    assert first.json()["is_new_user"] is True

    second = await exchange(
        app_client, make_init_data(telegram_id=1002, auth_date=int(time.time()) - 5)
    )
    assert second.status_code == 200
    assert second.json()["is_new_user"] is False
    assert second.json()["user"]["balance"]["minor"] == 100_000

    async with db.acquire() as conn:
        bonuses = await conn.fetchval(
            "SELECT count(*) FROM ledger_entries WHERE entry_type = 'SIGNUP_BONUS_CREDIT'"
        )
    assert bonuses == 1


async def test_profile_updates_follow_the_telegram_account(app_client):
    await exchange(app_client, make_init_data(telegram_id=1003, first_name="Ada"))
    again = await exchange(
        app_client,
        make_init_data(telegram_id=1003, first_name="Ada L", auth_date=int(time.time()) - 1),
    )
    assert again.json()["user"]["first_name"] == "Ada L"


async def test_session_token_unlocks_the_protected_route(app_client):
    token = (await exchange(app_client, make_init_data(telegram_id=1004))).json()["access_token"]

    me = await app_client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["telegram_id"] == 1004


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": ""},
        {"Authorization": "Bearer "},
        {"Authorization": "Basic abc"},
        {"Authorization": "Bearer not-a-jwt"},
        {"Authorization": "Bearer eyJhbGciOiJub25lIn0.eyJzdWIiOiJ4In0."},
    ],
)
async def test_protected_route_refuses_everything_unsigned(app_client, headers):
    assert (await app_client.get("/v1/me", headers=headers)).status_code == 401


async def test_token_signed_with_another_key_is_refused(app_client):
    import uuid
    from datetime import UTC, datetime, timedelta

    from backend.security.tokens import mint_session_token

    forged = mint_session_token(
        user_id=uuid.uuid4(),
        telegram_id=1005,
        session_id=uuid.uuid4(),
        secret="an-attackers-own-signing-key-32-chars",
        algorithm="HS256",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    response = await app_client.get("/v1/me", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401
    assert response.json()["code"] == "token_invalid"


async def test_replaying_init_data_rotates_the_session_and_kills_the_old_token(app_client):
    """A captured initData string cannot run a session alongside its owner."""
    raw = make_init_data(telegram_id=1006)

    first_token = (await exchange(app_client, raw)).json()["access_token"]
    assert (
        await app_client.get("/v1/me", headers={"Authorization": f"Bearer {first_token}"})
    ).status_code == 200

    second_token = (await exchange(app_client, raw)).json()["access_token"]
    assert second_token != first_token

    stale = await app_client.get("/v1/me", headers={"Authorization": f"Bearer {first_token}"})
    assert stale.status_code == 401
    assert stale.json()["code"] == "session_unknown"

    assert (
        await app_client.get("/v1/me", headers={"Authorization": f"Bearer {second_token}"})
    ).status_code == 200

    async with db.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM auth_sessions") == 1


async def test_revoking_a_session_takes_effect_immediately(app_client):
    token = (await exchange(app_client, make_init_data(telegram_id=1007))).json()["access_token"]
    auth = {"Authorization": f"Bearer {token}"}

    assert (await app_client.delete("/v1/auth/session", headers=auth)).status_code == 204

    after = await app_client.get("/v1/me", headers=auth)
    assert after.status_code == 401
    assert after.json()["code"] == "session_revoked"


async def test_stale_init_data_cannot_open_a_session(app_client):
    response = await exchange(
        app_client, make_init_data(telegram_id=1008, auth_date=int(time.time()) - 7200)
    )
    assert response.status_code == 401
    assert response.json()["code"] == "init_data_expired"


async def test_tampered_init_data_cannot_open_a_session(app_client):
    raw = make_init_data(telegram_id=1009)
    response = await exchange(app_client, raw.replace("1009", "1010"))
    assert response.status_code == 401
    assert response.json()["code"] == "init_data_bad_signature"


async def test_banned_accounts_are_refused(app_client):
    raw = make_init_data(telegram_id=1011)
    token = (await exchange(app_client, raw)).json()["access_token"]

    async with db.acquire() as conn:
        await conn.execute("UPDATE users SET status = 'BANNED' WHERE telegram_id = 1011")

    denied = await app_client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert denied.status_code == 403
    assert denied.json()["code"] == "account_suspended"

    assert (await exchange(app_client, make_init_data(telegram_id=1011))).status_code == 403


async def test_health_and_readiness(app_client):
    assert (await app_client.get("/health")).json() == {"status": "ok"}

    ready = (await app_client.get("/health/ready")).json()
    assert ready["status"] == "ready"
    assert ready["database"] == "ok"
    assert ready["cache"] in {"ok", "degraded"}
