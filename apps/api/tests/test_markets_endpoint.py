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
    assert "boosts" not in first, "there are no promotional prices to list"


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


async def test_a_boost_left_in_the_table_changes_nothing(app_client):
    """Boost rows from before the site went free-to-play may still exist.
    Nothing reads them: the feed does not list them and a quote ignores them."""
    markets = await seed(1)
    auth = await authorise(app_client)
    await price_cache.write_many(
        [(markets[0]["id"], Decimal("0.50"), "CLOB_MIDPOINT", datetime.now(UTC))],
        ttl_seconds=300,
    )

    async with db.transaction() as conn:
        await conn.execute(
            """
            INSERT INTO odds_boosts (market_id, side, boost_multiplier, ends_at,
                                     max_total_stake, max_stake_per_user)
            VALUES ($1, 'YES', 1.400, NOW() + INTERVAL '2 hours', 1000000, 50000)
            """,
            markets[0]["id"],
        )

    listed = (await app_client.get("/v1/markets", headers=auth)).json()["markets"][0]
    assert "boosts" not in listed

    quote = (
        await app_client.post(
            "/v1/predictions/quote",
            json={"legs": [{"market_id": str(markets[0]["id"]), "side": "YES"}], "stake": 10000},
            headers=auth,
        )
    ).json()
    assert quote["combined_odds"] == "2.000000"


async def test_the_feed_carries_the_rules_a_slip_must_satisfy(app_client):
    """So the page can say "this one is all but settled" before a round trip.
    Advisory only: the server re-checks every one at quote and placement."""
    await seed(1)
    auth = await authorise(app_client)
    settings = get_settings()

    body = (await app_client.get("/v1/markets", headers=auth)).json()

    assert body["max_legs"] == settings.max_legs
    assert body["min_prob"] == "0.01"
    assert body["max_prob"] == "0.99"
    assert body["max_combined_odds"] == "1000.0"
    assert body["min_stake"]["minor"] == settings.min_stake_minor
    assert body["max_stake"]["minor"] == settings.max_stake_minor
    assert body["payout_cap"]["minor"] == settings.payout_cap_minor
    for gone in ("vig_rate", "min_legs", "parlay_bonus_by_legs", "example_stake", "referral_bonus"):
        assert gone not in body


async def test_market_text_is_served_in_english_whatever_the_row_holds(app_client):
    """`question` and `title` may still hold a translation from when the feed
    was localised. The source columns are what the API reads."""
    markets = await seed(1)
    auth = await authorise(app_client)
    async with db.acquire() as conn:
        await conn.execute("UPDATE markets SET question = 'ein übersetzter Text'")
        await conn.execute("UPDATE market_events SET title = 'ein übersetzter Titel'")

    listed = (await app_client.get("/v1/markets", headers=auth)).json()["markets"][0]

    assert listed["question"] == markets[0]["question_source"]
    assert listed["question"].isascii()
    assert listed["event"]["title"].isascii()


async def test_probabilities_are_strings_not_json_numbers(app_client):
    """These feed payout arithmetic; a JSON number is a double in most clients."""
    await seed(1)
    auth = await authorise(app_client)

    raw = (await app_client.get("/v1/markets", headers=auth)).text
    assert '"yes":"0.6200"' in raw.replace(" ", "")
