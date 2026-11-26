"""GET /v1/markets — Postgres for metadata, Redis for price."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
from conftest import authorise, mock_http_client
from fixtures import gamma_events as fx

from backend import db
from backend.cache import prices as price_cache
from backend.config import get_settings
from backend.workers import polymarket_discovery as discovery


async def seed(count: int = 3, *, categories: list[str] | None = None) -> list[dict]:
    events = []
    for i in range(count):
        tags = fx.CRYPTO_TAGS if (categories and categories[i] == "Crypto") else None
        events.append(
            fx.event(
                str(i),
                tags=tags,
                markets=[fx.binary_market(f"8{i:04d}", end_in_days=i + 1)],
            )
        )

    def gamma(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("offset", 0))
        return httpx.Response(200, json=events if offset == 0 else [])

    async with mock_http_client(gamma) as client:
        await discovery.run_discovery(client, get_settings())

    async with db.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM markets ORDER BY lock_at")
    return [dict(r) for r in rows]


async def test_requires_authentication(app_client):
    assert (await app_client.get("/v1/markets")).status_code == 401


async def test_lists_active_markets_soonest_first(app_client):
    await seed(3)
    auth = await authorise(app_client)

    body = (await app_client.get("/v1/markets", headers=auth)).json()

    assert len(body["markets"]) == 3
    lock_times = [m["lock_at"] for m in body["markets"]]
    assert lock_times == sorted(lock_times)
    assert body["next_cursor"] is None

    first = body["markets"][0]
    assert first["event"]["title"]
    assert first["category"] in {"Macro", "Crypto"}
    assert first["boosts"] == []


async def test_price_is_served_from_redis_when_present(app_client):
    markets = await seed(1)
    auth = await authorise(app_client)
    now = datetime.now(UTC)

    await price_cache.write_many(
        [(markets[0]["id"], Decimal("0.7350"), "CLOB_MIDPOINT", now)], ttl_seconds=300
    )

    probability = (await app_client.get("/v1/markets", headers=auth)).json()["markets"][0][
        "probability"
    ]

    assert probability["yes"] == "0.7350"
    assert probability["no"] == "0.2650"
    assert probability["source"] == "CLOB_MIDPOINT"
    assert probability["stale"] is False


async def test_falls_back_to_the_database_on_a_cache_miss(app_client):
    await seed(1)
    auth = await authorise(app_client)

    probability = (await app_client.get("/v1/markets", headers=auth)).json()["markets"][0][
        "probability"
    ]

    assert probability["source"] == "DATABASE"
    assert probability["yes"] == "0.6200"


async def test_an_old_price_is_flagged_rather_than_hidden(app_client):
    """The market still appears — the UI needs to say the number is old, and
    Phase 3's odds engine needs to refuse to price on it."""
    markets = await seed(1)
    auth = await authorise(app_client)
    settings = get_settings()

    stale_at = datetime.now(UTC) - timedelta(seconds=settings.price_staleness_seconds + 60)
    await price_cache.write_many(
        [(markets[0]["id"], Decimal("0.5"), "CLOB_MIDPOINT", stale_at)], ttl_seconds=600
    )

    probability = (await app_client.get("/v1/markets", headers=auth)).json()["markets"][0][
        "probability"
    ]

    assert probability["stale"] is True
    assert probability["age_seconds"] > settings.price_staleness_seconds


async def test_yes_and_no_always_sum_to_one(app_client):
    markets = await seed(1)
    auth = await authorise(app_client)
    await price_cache.write_many(
        [(markets[0]["id"], Decimal("0.123456789"), "CLOB_MIDPOINT", datetime.now(UTC))],
        ttl_seconds=300,
    )

    probability = (await app_client.get("/v1/markets", headers=auth)).json()["markets"][0][
        "probability"
    ]

    assert Decimal(probability["yes"]) + Decimal(probability["no"]) == Decimal(1)


async def test_filters_by_category(app_client):
    await seed(2, categories=["Macro", "Crypto"])
    auth = await authorise(app_client)

    crypto = (await app_client.get("/v1/markets?category=Crypto", headers=auth)).json()
    assert len(crypto["markets"]) == 1
    assert crypto["markets"][0]["category"] == "Crypto"


async def test_pagination_walks_every_market_exactly_once(app_client):
    await seed(5)
    auth = await authorise(app_client)

    seen: list[str] = []
    cursor = None
    for _ in range(10):
        url = f"/v1/markets?limit=2{f'&cursor={cursor}' if cursor else ''}"
        page = (await app_client.get(url, headers=auth)).json()
        seen.extend(m["id"] for m in page["markets"])
        cursor = page["next_cursor"]
        if cursor is None:
            break

    assert len(seen) == 5
    assert len(set(seen)) == 5


async def test_a_bad_cursor_is_rejected(app_client):
    auth = await authorise(app_client)
    response = await app_client.get("/v1/markets?cursor=not-a-cursor", headers=auth)
    assert response.status_code == 400


async def test_locked_and_resolved_markets_are_not_listed(app_client):
    markets = await seed(3)
    auth = await authorise(app_client)

    async with db.transaction() as conn:
        await conn.execute("UPDATE markets SET status='LOCKED' WHERE id=$1", markets[0]["id"])
        await conn.execute(
            "UPDATE markets SET status='RESOLVED', resolution='YES', resolved_at=NOW() WHERE id=$1",
            markets[1]["id"],
        )

    body = (await app_client.get("/v1/markets", headers=auth)).json()
    assert [m["id"] for m in body["markets"]] == [str(markets[2]["id"])]


async def test_active_boosts_are_nested_on_their_market(app_client):
    markets = await seed(1)
    auth = await authorise(app_client)

    async with db.transaction() as conn:
        await conn.execute(
            """
            INSERT INTO odds_boosts (market_id, side, boost_multiplier, ends_at,
                                     max_total_stake, max_stake_per_user)
            VALUES ($1, 'YES', 1.400, NOW() + INTERVAL '2 hours', 1000000, 50000),
                   ($1, 'NO',  1.250, NOW() + INTERVAL '2 hours', 1000000, 50000)
            """,
            markets[0]["id"],
        )

    boosts = (await app_client.get("/v1/markets", headers=auth)).json()["markets"][0]["boosts"]

    assert [b["side"] for b in boosts] == ["YES", "NO"]
    assert boosts[0]["multiplier"] == "1.400"
    assert boosts[0]["remaining_stake"] == {"minor": 1000000, "display": "10,000"}


async def test_exhausted_and_expired_boosts_are_not_offered(app_client):
    markets = await seed(1)
    auth = await authorise(app_client)

    async with db.transaction() as conn:
        await conn.execute(
            """
            INSERT INTO odds_boosts (market_id, side, boost_multiplier, starts_at, ends_at,
                                     max_total_stake, consumed_stake, max_stake_per_user)
            VALUES ($1, 'YES', 1.4, NOW() - INTERVAL '3 hours', NOW() - INTERVAL '1 hour',
                    1000000, 0, 50000),
                   ($1, 'NO', 1.3, NOW(), NOW() + INTERVAL '2 hours',
                    1000000, 1000000, 50000)
            """,
            markets[0]["id"],
        )

    assert (await app_client.get("/v1/markets", headers=auth)).json()["markets"][0]["boosts"] == []


async def test_probabilities_are_strings_not_json_numbers(app_client):
    """These feed payout arithmetic; a JSON number is a double in most clients."""
    await seed(1)
    auth = await authorise(app_client)

    raw = (await app_client.get("/v1/markets", headers=auth)).text
    assert '"yes":"0.6200"' in raw.replace(" ", "")
