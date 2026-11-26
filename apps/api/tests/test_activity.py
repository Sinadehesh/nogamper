"""The activity feed serves real settled slips, not invented ones."""

from __future__ import annotations

import uuid

import httpx
from conftest import authorise, mock_http_client
from fixtures import gamma_events as fx

from backend import db
from backend.config import get_settings
from backend.workers import polymarket_discovery as discovery


async def seed_market() -> dict:
    def gamma(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("offset", 0))
        return httpx.Response(200, json=[fx.event("1")] if offset == 0 else [])

    async with mock_http_client(gamma) as client:
        await discovery.run_discovery(client, get_settings())
    async with db.acquire() as conn:
        return dict(await conn.fetchrow("SELECT * FROM markets"))


async def settled_slip(telegram_id: int, *, status: str, payout: int, username: str | None):
    market = await seed_market()
    async with db.transaction() as conn:
        user_id = await conn.fetchval(
            "INSERT INTO users (telegram_id, username, first_name) VALUES ($1, $2, 'Ada') "
            "ON CONFLICT (telegram_id) DO UPDATE SET username = EXCLUDED.username RETURNING id",
            telegram_id,
            username,
        )
        slip_id = await conn.fetchval(
            """
            INSERT INTO predictions (user_id, idempotency_key, request_fingerprint, type,
                leg_count, stake, combined_odds, gross_potential_payout, payout_cap,
                potential_payout, status, settled_payout, settled_at)
            VALUES ($1, $2, 'fp', 'PARLAY', 4, 10000, 12.5, 125000, 500000000, 125000,
                    $3::slip_status, $4, NOW())
            RETURNING id
            """,
            user_id,
            f"key-{telegram_id}",
            status,
            payout,
        )
        await conn.execute(
            "INSERT INTO prediction_legs (prediction_id, leg_index, market_id, event_id, side,"
            " raw_prob, vig_rate, locked_odds, status, settled_at)"
            " VALUES ($1, 1, $2, $3, 'YES', 0.5, 0.05, 1.9, 'WON', NOW())",
            slip_id,
            market["id"],
            market["event_id"],
        )
    return slip_id


async def test_the_feed_reports_real_settled_slips(app_client):
    await settled_slip(8001, status="WON", payout=125000, username="crypto_king")
    auth = await authorise(app_client)

    body = (await app_client.get("/v1/activity", headers=auth)).json()

    assert len(body["entries"]) == 1
    entry = body["entries"][0]
    assert entry["player"] == "A."
    assert entry["status"] == "WON"
    assert entry["leg_count"] == 4
    assert entry["payout"] == {"minor": 125000, "display": "1,250"}

    async with db.acquire() as conn:
        stored = await conn.fetchrow(
            "SELECT settled_payout, leg_count FROM predictions WHERE id = $1",
            uuid.UUID(entry["id"]),
        )
    assert stored["settled_payout"] == entry["payout"]["minor"]
    assert stored["leg_count"] == entry["leg_count"]


async def test_an_empty_feed_is_empty_rather_than_filled_in(app_client):
    """With no settled slips there is nothing to show, and nothing invented."""
    auth = await authorise(app_client)
    assert (await app_client.get("/v1/activity", headers=auth)).json()["entries"] == []


async def test_losses_are_hidden_by_default_but_available(app_client):
    await settled_slip(8002, status="LOST", payout=0, username="unlucky")
    auth = await authorise(app_client)

    assert (await app_client.get("/v1/activity", headers=auth)).json()["entries"] == []

    with_losses = (await app_client.get("/v1/activity?include_losses=true", headers=auth)).json()
    assert [e["status"] for e in with_losses["entries"]] == ["LOST"]


async def test_a_player_without_a_username_is_shown_only_as_an_initial(app_client):
    await settled_slip(8003, status="WON", payout=50000, username=None)
    auth = await authorise(app_client)

    entry = (await app_client.get("/v1/activity", headers=auth)).json()["entries"][0]
    assert entry["player"] == "A."


async def test_a_players_telegram_username_never_reaches_the_feed(app_client):
    """The leak this ticker used to have: a real, searchable Telegram handle,
    shown to every other authenticated player with no opt-in. A player with a
    username must be indistinguishable in the response from one without."""
    await settled_slip(8004, status="WON", payout=75000, username="a_very_distinctive_handle")
    auth = await authorise(app_client)

    body = await app_client.get("/v1/activity", headers=auth)

    assert "a_very_distinctive_handle" not in body.text
    assert body.json()["entries"][0]["player"] == "A."


async def test_the_feed_requires_authentication(app_client):
    assert (await app_client.get("/v1/activity")).status_code == 401


async def test_packages_are_listed_for_the_top_up_modal(app_client):
    auth = await authorise(app_client)
    body = (await app_client.get("/v1/payments/packages", headers=auth)).json()

    codes = [p["code"] for p in body["packages"]]
    assert codes == ["TIER_1", "TIER_2", "TIER_3"]

    tier2 = body["packages"][1]
    assert tier2["stars"] == 125
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT coins, bonus_coins FROM coin_packages WHERE code = 'TIER_2'"
        )
    assert tier2["coins"]["minor"] == int(row["coins"]) + int(row["bonus_coins"])
    assert int(row["bonus_coins"]) > 0
    assert tier2["bonus_coins"]["minor"] == int(row["bonus_coins"])
