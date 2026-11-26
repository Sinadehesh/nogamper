"""Which slice of Gamma we read — the paging and, above all, the sort key.

fetch_events reads at most page_size * max_pages of an event list tens of
thousands long, so `order` is not a nicety: it decides what the app ends up
showing. Ordering by soonest end date returned the hourly crypto candles
("Bitcoin Up or Down — 3PM ET"), which are tagged crypto and so pass the
category filter, then fail the Yes/No check inside normalize_market. A run
read 2000 events and kept none of them. These tests pin the sort key, and the
behaviour when Gamma refuses it.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from conftest import mock_http_client
from fixtures import gamma_events as fx

from backend.clients import gamma
from backend.config import Settings


def settings(**overrides) -> Settings:
    return Settings(jwt_secret="y", **overrides)


def pager(pages: list[list[dict]], *, status_for_ordered: int | None = None):
    """Serve `pages` by offset, optionally refusing any ordered request first."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if status_for_ordered is not None and "order" in request.url.params:
            return httpx.Response(status_for_ordered, json={"error": "unknown sort field"})

        offset = int(request.url.params.get("offset", 0))
        limit = int(request.url.params.get("limit", 100))
        index = offset // limit
        return httpx.Response(200, json=pages[index] if index < len(pages) else [])

    handler.seen = seen  # type: ignore[attr-defined]
    return handler


def full_page(size: int, first_id: int = 0) -> list[dict]:
    return [fx.event(str(first_id + i)) for i in range(size)]


def feed(handler) -> list[httpx.Request]:
    """The volume-ordered pass only.

    fetch_events makes two passes now — the priority tags by name, then the
    ordinary feed — and the paging rules below are about the second one. Asked
    of every request, these assertions would be counting both.
    """
    return [r for r in handler.seen if "tag_slug" not in r.url.params]


def tagged(handler) -> list[httpx.Request]:
    return [r for r in handler.seen if "tag_slug" in r.url.params]


async def test_events_are_requested_most_traded_first():
    """The sort key that decides everything. Not endDate."""
    handler = pager([[]])
    async with mock_http_client(handler) as client:
        await gamma.fetch_events(client, settings(discovery_page_size=5))

    params = handler.seen[0].url.params
    assert params["order"] == "volume24hr"
    assert params["ascending"] == "false"


async def test_the_sort_key_is_tunable_without_a_deploy():
    handler = pager([[]])
    async with mock_http_client(handler) as client:
        await gamma.fetch_events(
            client,
            settings(discovery_page_size=5, discovery_order="liquidity"),
        )

    assert handler.seen[0].url.params["order"] == "liquidity"


async def test_events_already_past_their_betting_window_are_never_requested():
    handler = pager([[]])
    config = settings(discovery_page_size=5)
    async with mock_http_client(handler) as client:
        await gamma.fetch_events(client, config)

    horizon = datetime.fromisoformat(
        handler.seen[0].url.params["end_date_min"].replace("Z", "+00:00")
    )
    assert horizon > datetime.now(UTC)


async def test_paging_stops_on_the_first_short_page():
    handler = pager([full_page(5), full_page(5, 100), [fx.event("200")]])
    async with mock_http_client(handler) as client:
        events = await gamma.fetch_events(client, settings(discovery_page_size=5))

    assert len(events) == 11
    assert len(feed(handler)) == 3
    assert [int(r.url.params["offset"]) for r in feed(handler)] == [0, 5, 10]


async def test_paging_stops_at_the_ceiling(caplog):
    handler = pager([full_page(5, page * 100) for page in range(10)])
    async with mock_http_client(handler) as client:
        events = await gamma.fetch_events(
            client, settings(discovery_page_size=5, discovery_max_pages=3)
        )

    assert len(events) == 15
    assert len(feed(handler)) == 3
    assert "page ceiling" in caplog.text


async def test_a_rejected_sort_key_degrades_instead_of_ingesting_nothing():
    """Gamma renaming a sort field must not empty the app.

    An unordered slice is a poor one. A run that raises is a worse one: the
    market list goes stale and the only evidence is a traceback in the worker
    log.
    """
    handler = pager([full_page(5), [fx.event("200")]], status_for_ordered=400)
    async with mock_http_client(handler) as client:
        events = await gamma.fetch_events(client, settings(discovery_page_size=5))

    assert len(events) == 6
    assert [int(r.url.params["offset"]) for r in feed(handler)] == [0, 0, 5]
    assert "order" not in feed(handler)[1].url.params
    assert "order" not in feed(handler)[2].url.params


async def test_a_server_error_is_not_mistaken_for_a_bad_sort_key():
    """A 500 is Gamma being unwell; retrying without the sort proves nothing."""
    handler = pager([full_page(5)], status_for_ordered=503)
    with pytest.raises(Exception) as exc:
        async with mock_http_client(handler) as client:
            await gamma.fetch_events(client, settings(discovery_page_size=5))

    assert "order" in handler.seen[-1].url.params
    assert "unordered" not in str(exc.value)


async def test_a_wrapped_payload_is_read_like_a_bare_array():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [fx.event("1")]})

    async with mock_http_client(handler) as client:
        events = await gamma.fetch_events(client, settings(discovery_page_size=5))

    assert len(events) == 1


async def test_the_priority_tags_are_asked_for_by_name_before_the_feed():
    """The one request whose result does not depend on trading volume.

    Every later stage ranks by it, so a tag as small as `iran` is only ever in
    the app because this request went out first and its events were placed at
    the front of the list.
    """
    handler = pager([[]])
    async with mock_http_client(handler) as client:
        await gamma.fetch_events(client, settings(discovery_page_size=5))

    assert [r.url.params["tag_slug"] for r in tagged(handler)] == ["iran"]
    assert handler.seen[0] is tagged(handler)[0]
    assert tagged(handler)[0].url.params["order"] == "volume24hr"


async def test_an_event_in_both_passes_is_returned_once_at_its_priority_place():
    """The passes overlap by design: a busy Iran event is in both."""
    handler = pager([[fx.event("1", tags=fx.IRAN_TAGS), fx.event("2")]])
    async with mock_http_client(handler) as client:
        events = await gamma.fetch_events(client, settings(discovery_page_size=5))

    assert [e["id"] for e in events] == ["1", "2"]


async def test_a_priority_tag_gamma_no_longer_knows_costs_only_itself():
    """Our slugs are a guess at a taxonomy that moves upstream.

    When the guess goes stale the category empties, which is bad. The run
    failing would empty the whole app, which is worse.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if "tag_slug" in request.url.params:
            return httpx.Response(404, json={"error": "unknown tag"})
        offset = int(request.url.params.get("offset", 0))
        return httpx.Response(200, json=[fx.event("1")] if offset == 0 else [])

    async with mock_http_client(handler) as client:
        events = await gamma.fetch_events(client, settings(discovery_page_size=5))

    assert [e["id"] for e in events] == ["1"]


async def test_the_priority_pass_can_be_turned_off():
    handler = pager([[]])
    async with mock_http_client(handler) as client:
        await gamma.fetch_events(
            client, settings(discovery_page_size=5, discovery_priority_tag_slugs="")
        )

    assert tagged(handler) == []


# ----- the same feed, a page at a time ---------------------------------------
#
# Discovery does not call fetch_events. Twenty pages of Gamma's own JSON held
# at once measured over half a gigabyte, which is more than the server this
# runs on has. fetch_normalized_events reduces each page to our own records
# before it asks for the next — and it has to give exactly the answer the
# simple way gives.


def mixed_pages() -> list[list[dict]]:
    """Three pages: wanted and unwanted events, one with no usable market, and
    one that the priority pass will have returned already."""
    return [
        [
            fx.event("1", tags=fx.IRAN_TAGS),
            fx.event("2"),
            fx.event("3", tags=[{"id": "9", "label": "Sports", "slug": "sports"}]),
            fx.event("4"),
            fx.event("5", markets=[]),
        ],
        [fx.event(str(n)) for n in range(6, 11)],
        [fx.event("11"), fx.event("2")],
    ]


async def test_a_page_at_a_time_gives_the_same_events_in_the_same_order():
    config = settings(discovery_page_size=5)
    # Built once: the fixture dates its events from the moment it is called.
    pages = mixed_pages()

    simple_stats = gamma.DiscoveryStats()
    async with mock_http_client(pager(pages)) as client:
        raw = await gamma.fetch_events(client, config)
    simple = list(gamma.normalize_events(raw, settings=config, stats=simple_stats))

    paged_stats = gamma.DiscoveryStats()
    async with mock_http_client(pager(pages)) as client:
        paged = await gamma.fetch_normalized_events(client, config, paged_stats)

    assert len(simple) > 5, "the fixture kept almost nothing; it would prove nothing"
    assert simple_stats.skips, "nothing was skipped; the unwanted events are not unwanted"
    # Records are compared whole: every field of every market of every event.
    assert paged == simple
    assert paged_stats.as_dict() == simple_stats.as_dict()
    # The overlapping event is counted once, where the priority pass put it.
    assert [e.polymarket_event_id for e in paged][0] == "1"
    assert [e.polymarket_event_id for e in paged].count("2") == 1


async def test_a_priority_tag_that_fails_halfway_does_not_take_its_events_with_it():
    """The first page of the tag arrives, the second does not. Those five
    events are also in the ordinary feed, and that is where they must come
    from — a reader that had already ticked them off as seen would return
    them from neither pass."""
    events = full_page(5)

    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("offset", 0))
        if "tag_slug" in request.url.params:
            if offset == 0:
                return httpx.Response(200, json=events)
            return httpx.Response(404, json={"error": "gone"})
        return httpx.Response(200, json=events if offset == 0 else [])

    config = settings(discovery_page_size=5)
    stats = gamma.DiscoveryStats()
    async with mock_http_client(handler) as client:
        kept = await gamma.fetch_normalized_events(client, config, stats)
        raw = await gamma.fetch_events(client, config)

    assert [e.polymarket_event_id for e in kept] == ["0", "1", "2", "3", "4"]
    assert [e["id"] for e in raw] == ["0", "1", "2", "3", "4"]
    # Each was read once, not once per pass.
    assert stats.events_seen == 5


async def test_each_page_is_reduced_before_the_next_is_asked_for(monkeypatch):
    """The point of the exercise. If every page were fetched first and reduced
    afterwards, the order below would be all the requests, then all the events."""
    order: list[str] = []
    pages = [full_page(5), full_page(5, 100), [fx.event("200")]]
    serve = pager(pages)

    def handler(request: httpx.Request) -> httpx.Response:
        order.append(f"page at {request.url.params['offset']}")
        return serve(request)

    normalize = gamma.normalize_event

    def watching(raw, **kwargs):
        order.append("event")
        return normalize(raw, **kwargs)

    monkeypatch.setattr(gamma, "normalize_event", watching)

    async with mock_http_client(handler) as client:
        events = await gamma.fetch_normalized_events(
            client,
            # The ordinary feed alone: the priority pass pages too, and would
            # put its own events ahead of the first request counted here.
            settings(discovery_page_size=5, discovery_priority_tag_slugs=""),
            gamma.DiscoveryStats(),
        )

    assert len(events) == 11
    assert order == (
        ["page at 0"] + ["event"] * 5 + ["page at 5"] + ["event"] * 5 + ["page at 10", "event"]
    )


async def test_nothing_of_a_page_is_kept_but_the_records_made_from_it(monkeypatch):
    """What comes back holds no reference into Gamma's JSON — not to an event
    and not to a market inside one — so a page can be let go as soon as it has
    been read. A record that kept its source "for debugging" would quietly
    bring the half-gigabyte back."""
    import gc
    import weakref

    class Tracked(dict):
        """A dict that can be watched: a plain one cannot be weakly referenced."""

    watched: list[weakref.ref] = []

    def track(item: dict) -> Tracked:
        tracked = Tracked(item)
        watched.append(weakref.ref(tracked))
        return tracked

    real = gamma.get_json

    async def tracking(*args, **kwargs):
        payload = await real(*args, **kwargs)
        return [
            track({**event, "markets": [track(market) for market in event["markets"]]})
            for event in payload
        ]

    monkeypatch.setattr(gamma, "get_json", tracking)

    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("offset", 0))
        return httpx.Response(200, json=full_page(5) if offset == 0 else [])

    async with mock_http_client(handler) as client:
        events = await gamma.fetch_normalized_events(
            client,
            settings(discovery_page_size=5, discovery_priority_tag_slugs=""),
            gamma.DiscoveryStats(),
        )

    gc.collect()
    assert len(events) == 5
    assert len(watched) == 10, "five events and the one market in each"
    assert [ref() for ref in watched] == [None] * 10
