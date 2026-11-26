"""Discovery worker against a real database and a mocked Gamma."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
from conftest import mock_http_client
from fixtures import gamma_events as fx

from backend import db
from backend.clients import gamma
from backend.config import get_settings
from backend.workers import polymarket_discovery as discovery


def gamma_serving(*pages: list[dict]):
    """Serve `pages` in order, then an empty page, mimicking Gamma's paging."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        offset = int(request.url.params.get("offset", 0))
        limit = int(request.url.params.get("limit", 100))
        index = offset // limit if limit else 0
        body = pages[index] if index < len(pages) else []
        return httpx.Response(200, json=body)

    handler.calls = calls  # type: ignore[attr-defined]
    return handler


async def market_rows() -> list[dict]:
    async with db.acquire() as conn:
        rows = await conn.fetch(
            "SELECT m.*, e.polymarket_event_id, e.category AS event_category "
            "FROM markets m JOIN market_events e ON e.id = m.event_id "
            "ORDER BY m.polymarket_market_id"
        )
    return [dict(r) for r in rows]


async def test_ingests_macro_and_crypto_and_leaves_the_rest(resources):
    page = [
        fx.event("1"),
        fx.event("2", tags=fx.CRYPTO_TAGS, markets=[fx.binary_market("52000")]),
        fx.event("3", tags=fx.SPORTS_TAGS, markets=[fx.binary_market("53000")]),
    ]
    async with mock_http_client(gamma_serving(page)) as client:
        report = await discovery.run_discovery(client, resources)

    assert report.ran is True
    assert report.events_upserted == 2
    assert report.markets_created == 2
    assert report.stats["skips"]["event_category_not_wanted"] == 1

    rows = await market_rows()
    assert {r["polymarket_market_id"] for r in rows} == {"51234", "52000"}
    assert {r["category"] for r in rows} == {"Macro", "Crypto"}
    assert all(r["status"] == "ACTIVE" for r in rows)


async def test_lock_at_is_set_before_end_date(resources):
    async with mock_http_client(gamma_serving([fx.event()])) as client:
        await discovery.run_discovery(client, resources)

    row = (await market_rows())[0]
    assert row["end_date"] - row["lock_at"] == timedelta(
        seconds=resources.market_lock_buffer_seconds
    )


async def test_rediscovery_updates_metadata_but_not_price_or_tokens(resources):
    """Ownership boundary: discovery owns metadata, the sync worker owns price."""
    async with mock_http_client(gamma_serving([fx.event()])) as client:
        await discovery.run_discovery(client, resources)

    async with db.transaction() as conn:
        await conn.execute("UPDATE markets SET raw_yes_prob = 0.81")

    revised = fx.binary_market(
        "51234",
        prices=["0.10", "0.90"],
        token_ids=["swapped-yes", "swapped-no"],
        liquidityNum=99999.0,
    )
    revised["question"] = "Will the Fed cut by 25 bps? (revised)"

    async with mock_http_client(gamma_serving([fx.event(markets=[revised])])) as client:
        report = await discovery.run_discovery(client, resources)

    assert report.markets_created == 0
    assert report.markets_updated == 1

    row = (await market_rows())[0]
    assert row["question"].endswith("(revised)")
    assert row["liquidity_usd"] == Decimal("99999.00")
    assert row["raw_yes_prob"] == Decimal("0.810000")
    assert row["yes_token_id"] == "tok-yes-51234"


async def test_discovery_never_resurrects_a_settled_market(resources):
    async with mock_http_client(gamma_serving([fx.event()])) as client:
        await discovery.run_discovery(client, resources)

    async with db.transaction() as conn:
        await conn.execute(
            "UPDATE markets SET status = 'RESOLVED', resolution = 'YES', resolved_at = NOW()"
        )

    async with mock_http_client(gamma_serving([fx.event()])) as client:
        await discovery.run_discovery(client, resources)

    assert (await market_rows())[0]["status"] == "RESOLVED"


async def test_pages_until_the_feed_runs_out(resources):
    page_one = [fx.event(str(i), markets=[fx.binary_market(f"6{i:04d}")]) for i in range(100)]
    page_two = [fx.event("900", markets=[fx.binary_market("69999")])]

    handler = gamma_serving(page_one, page_two)
    async with mock_http_client(handler) as client:
        report = await discovery.run_discovery(client, resources)

    assert report.markets_created == 101
    feed_calls = [c for c in handler.calls if "tag_slug" not in c.url.params]
    assert len(feed_calls) == 2
    assert feed_calls[1].url.params["offset"] == "100"


async def test_the_priority_tag_is_read_before_the_volume_ordered_feed(resources):
    """The one fetch that does not depend on how much money is on the market.

    Everything after this point ranks by volume — Gamma's `order`, discovery's
    budget cut, the surplus trim — and a regional tag loses that comparison to
    crypto and macro every time. Asking Gamma for the tag by name is what makes
    the category present at all rather than merely enabled.
    """
    handler = gamma_serving([fx.event("1")])
    async with mock_http_client(handler) as client:
        await discovery.run_discovery(client, resources)

    tagged = [c for c in handler.calls if "tag_slug" in c.url.params]
    assert tagged, "the priority tag was never requested"
    assert tagged[0].url.params["tag_slug"] == "iran"
    assert handler.calls[0] is tagged[0], "the priority pass must run first"


async def test_an_event_in_both_passes_is_ingested_once(resources):
    """The priority tag overlaps the ordinary feed by design.

    A high-volume Iran event is returned by both passes. Upserting is
    idempotent, but the duplicate would still be translated and written twice
    and would consume the ingest budget twice over.
    """
    page = [fx.event("1", tags=fx.IRAN_TAGS, markets=[fx.binary_market("57000")])]

    handler = gamma_serving(page)
    async with mock_http_client(handler) as client:
        report = await discovery.run_discovery(client, resources)

    assert len([c for c in handler.calls if "tag_slug" in c.url.params]) >= 1
    assert report.events_upserted == 1
    assert report.markets_created == 1
    assert [r["polymarket_market_id"] for r in await market_rows()] == ["57000"]


async def test_a_dead_priority_tag_does_not_take_the_run_down(resources):
    """Gamma's taxonomy moves and ours is a guess at it.

    A slug that has been renamed upstream must cost the priority category, not
    the whole feed — the ordinary pass still holds the markets the app is
    otherwise made of.
    """
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if "tag_slug" in request.url.params:
            return httpx.Response(404, json={"error": "unknown tag"})
        offset = int(request.url.params.get("offset", 0))
        return httpx.Response(200, json=[fx.event("1")] if offset == 0 else [])

    async with mock_http_client(handler) as client:
        report = await discovery.run_discovery(client, resources)

    assert report.error is None
    assert report.markets_created == 1


async def test_the_priority_category_outranks_the_tag_order_gamma_sent(resources):
    """Gamma tags a regional event `geopolitics` and `iran`, in that order.

    Taking the first match would file it under Politics, and the order is not
    stable between endpoints — so the same event would move between tabs from
    one run to the next, which a player watching it sees as markets vanishing.
    """
    page = [
        fx.event("1", tags=fx.IRAN_AND_POLITICS_TAGS, markets=[fx.binary_market("57100")]),
    ]
    async with mock_http_client(gamma_serving(page)) as client:
        await discovery.run_discovery(client, resources)

    rows = await market_rows()
    assert [r["category"] for r in rows] == ["Iran"]
    assert [r["event_category"] for r in rows] == ["Iran"]


async def test_an_unreachable_gamma_leaves_existing_markets_alone(resources):
    async with mock_http_client(gamma_serving([fx.event()])) as client:
        await discovery.run_discovery(client, resources)

    def failing(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={})

    async with mock_http_client(failing) as client:
        report = await discovery.run_discovery(client, resources)

    assert report.error is not None
    assert len(await market_rows()) == 1


async def test_a_malformed_feed_does_not_wipe_the_market_list(resources):
    async with mock_http_client(gamma_serving([fx.event()])) as client:
        await discovery.run_discovery(client, resources)

    garbage = [{"id": "x"}, "not-an-object", {"id": "y", "title": "t", "markets": []}]
    async with mock_http_client(gamma_serving(garbage)) as client:
        report = await discovery.run_discovery(client, resources)

    assert report.ran is True
    assert report.markets_created == 0
    assert len(await market_rows()) == 1


async def test_only_one_replica_runs_a_tick(resources):
    """The advisory lock is what makes lifespan-attached workers safe at N replicas."""
    import asyncio

    async with mock_http_client(gamma_serving([fx.event()])) as client:
        reports = await asyncio.gather(
            discovery.run_discovery(client, resources),
            discovery.run_discovery(client, resources),
            discovery.run_discovery(client, resources),
        )

    assert sum(1 for r in reports if r.ran) == 1
    assert len(await market_rows()) == 1


async def test_the_json_shapes_gamma_actually_sends_round_trip(resources):
    """Arrays-as-strings, numbers-as-strings, tags instead of category."""
    raw = fx.event()
    assert isinstance(raw["markets"][0]["clobTokenIds"], str)
    assert isinstance(raw["liquidity"], str)
    assert "category" not in raw
    assert json.loads(raw["markets"][0]["outcomes"]) == ["Yes", "No"]

    async with mock_http_client(gamma_serving([raw])) as client:
        report = await discovery.run_discovery(client, resources)

    assert report.markets_created == 1
    row = (await market_rows())[0]
    assert row["raw_yes_prob"] == Decimal("0.620000")
    assert row["end_date"] > datetime.now(UTC)


async def test_discovery_parks_markets_it_no_longer_offers(resources, monkeypatch):
    """The trim now has a narrower job than when it was written, and it is
    still needed.

    Capping the ingest stops discovery *paying* for markets the price sync
    cannot keep fresh. It does nothing about markets already ACTIVE in the
    database from an earlier run — including the 7,268 that put the app in this
    state — because this pass never sees them. Those are what the trim parks.
    """
    monkeypatch.setattr(resources, "price_sync_max_markets", 1)

    async with db.transaction() as conn:
        event_id = await conn.fetchval(
            """
            INSERT INTO market_events (polymarket_event_id, slug, title, title_source,
                                       category, end_date)
            VALUES ('old', 'old', 'e', 'e', 'Crypto', NOW() + INTERVAL '10 days')
            RETURNING id
            """
        )
        await conn.execute(
            """
            INSERT INTO markets (event_id, polymarket_market_id, condition_id, question,
                                 category, yes_token_id, no_token_id, raw_yes_prob,
                                 volume_usd, lock_at, end_date, question_source, status)
            VALUES ($1, 'stale-one', 'stale-one', 'q?', 'Crypto', 'y', 'n', 0.5, 1,
                    NOW() + INTERVAL '9 days', NOW() + INTERVAL '10 days', 'q?', 'ACTIVE')
            """,
            event_id,
        )

    page = [fx.event("1", markets=[fx.binary_market("51234", volumeNum=90000.0)])]
    async with mock_http_client(gamma_serving(page)) as client:
        report = await discovery.run_discovery(client, resources)

    assert report.markets_created == 1
    assert report.markets_retired == 1

    rows = {r["polymarket_market_id"]: r["status"] for r in await market_rows()}
    assert rows == {"51234": "ACTIVE", "stale-one": "DRAFT"}


def test_the_budget_cut_lands_on_an_event_boundary():
    """Whole events, never a partial one.

    The markets under an event are outcomes of the same question, so taking
    three of a five-way race would show players a board with legs missing. The
    last event is taken in full even if it goes slightly over budget.
    """
    from backend.workers.polymarket_discovery import _within_budget

    events = [
        fx.event("1", markets=[fx.binary_market("a"), fx.binary_market("b")]),
        fx.event("2", markets=[fx.binary_market("c"), fx.binary_market("d")]),
        fx.event("3", markets=[fx.binary_market("e")]),
    ]
    normalized = list(
        gamma.normalize_events(events, settings=get_settings(), stats=gamma.DiscoveryStats())
    )

    kept = _within_budget(normalized, 3)
    assert [e.polymarket_event_id for e in kept] == ["1", "2"]
    assert sum(len(e.markets) for e in kept) == 4

    assert _within_budget(normalized, 100) == normalized
    assert _within_budget(normalized, 1) == normalized[:1]


def test_the_priority_category_is_taken_before_the_budget_is_spent():
    """A regional event sits below the volume cut and must survive it anyway.

    Gamma's order is volume descending, so the priority event arrives last.
    Under a plain top-of-feed cut it is the first thing dropped — which is the
    same outcome as never enabling the category.
    """
    from backend.workers.polymarket_discovery import _within_budget

    events = [
        fx.event("1", markets=[fx.binary_market("a"), fx.binary_market("b")]),
        fx.event("2", markets=[fx.binary_market("c"), fx.binary_market("d")]),
        fx.event("3", tags=fx.IRAN_TAGS, markets=[fx.binary_market("e")]),
    ]
    normalized = list(
        gamma.normalize_events(events, settings=get_settings(), stats=gamma.DiscoveryStats())
    )

    assert _within_budget(normalized, 2) == normalized[:1]

    kept = _within_budget(normalized, 2, priority="Iran")
    assert [e.polymarket_event_id for e in kept] == ["3", "1"]


async def test_discovery_ingests_only_what_the_price_sync_can_keep_fresh(resources, monkeypatch):
    """The run that took eighty-six minutes.

    Discovery read its whole page budget and upserted 7,268 markets — two
    sequential database round trips and a translation call each — so that
    `retire_surplus_markets` could park 6,868 of them seconds later. The work
    was not slow; it was unnecessary.
    """
    monkeypatch.setattr(resources, "price_sync_max_markets", 1)

    page = [
        fx.event("1", markets=[fx.binary_market("51234", volumeNum=90000.0)]),
        fx.event("2", tags=fx.CRYPTO_TAGS, markets=[fx.binary_market("52000", volumeNum=500.0)]),
    ]
    async with mock_http_client(gamma_serving(page)) as client:
        report = await discovery.run_discovery(client, resources)

    assert report.markets_considered == 2
    assert report.markets_created == 1
    assert report.markets_retired == 0

    rows = await market_rows()
    assert [r["polymarket_market_id"] for r in rows] == ["51234"]


async def test_a_pass_that_overruns_is_abandoned_rather_than_left_running(resources, monkeypatch):
    """The lease heartbeat extends while a run continues, so an unbounded pass
    holds discovery shut against every later tick — which is how one run held
    it for eighty-six minutes while the operator watched "the worker is the
    problem" and had nothing to act on.

    Nothing is half-written: the ingest is a transaction and an abandoned one
    rolls back.
    """
    import asyncio

    monkeypatch.setattr(resources, "discovery_deadline_seconds", 0.05)

    async def crawl(request):
        await asyncio.sleep(5)
        raise AssertionError("the deadline should have fired first")

    async with mock_http_client(crawl) as client:
        report = await discovery.run_discovery(client, resources)

    assert report.ran is True
    assert report.error == "deadline_exceeded"
    assert await market_rows() == []


async def test_the_deadline_is_inside_the_runaway_threshold(resources):
    """So that a discovery run tripping "this job is hung" really is hung.

    If the deadline were the looser of the two, a healthy long pass would raise
    the alarm the endpoint uses for a genuinely stuck job, and the operator
    would learn to ignore it.
    """
    from backend.workers import locks

    assert resources.discovery_deadline_seconds < locks.RUNAWAY_AFTER_SECONDS


def test_the_deadline_allows_a_pass_that_actually_translates():
    """240 seconds was measured against a pass that translated nothing.

    With a reasoning provider that takes one request at a time, every
    production run spent about a minute on Gamma and was then cut off at 241
    seconds with the batches still in flight — outcome=deadline every hour,
    and an empty translations table, from a budget that was never wrong so
    much as written for different work.
    """
    from backend.config import Settings

    assert Settings().discovery_deadline_seconds >= 900.0


async def test_an_abandoned_run_still_reports_what_it_translated(resources, monkeypatch):
    """A run that overruns used to report only that it overran.

    That is the same report whether it translated four hundred strings or
    could not translate one, and those need opposite fixes — raise the
    deadline, or go look at the provider.
    """
    monkeypatch.setattr(resources, "discovery_deadline_seconds", 0.05)

    async def crawl(*args, **kwargs):
        await asyncio.sleep(1)
        return []

    monkeypatch.setattr(gamma, "fetch_events", crawl)

    async with mock_http_client(gamma_serving([fx.event()])) as client:
        report = await discovery.run_discovery(client, resources)

    assert report.error == "deadline_exceeded"
    assert report.translation is not None, "the counters must survive the deadline"
    assert report.translation["translated"] == 0
