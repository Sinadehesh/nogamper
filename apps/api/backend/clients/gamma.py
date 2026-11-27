"""Polymarket Gamma API — market discovery and normalisation.

Gamma describes the world loosely: JSON arrays arrive as strings, numbers as
strings, categories sometimes as a field and sometimes only as tags. This
module's job is to turn that into rows our schema will accept, and to refuse
anything it cannot describe honestly.

Every rejection is counted rather than silently dropped. A discovery run that
suddenly skips 90% of its input is a signal, and it is only visible if the
skips are named.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import TypeVar

import httpx

from ..config import Settings
from .http import get_json

logger = logging.getLogger(__name__)

_T = TypeVar("_T")

_CATEGORY_ALIASES: dict[str, str] = {
    "iran": "Iran",
    "iran-israel": "Iran",
    "israel-iran": "Iran",
    "iran-nuclear": "Iran",
    "iran-nuclear-deal": "Iran",
    "iran-deal": "Iran",
    "iran-strike": "Iran",
    "us-iran": "Iran",
    "tehran": "Iran",
    "khamenei": "Iran",
    "irgc": "Iran",
    "strait-of-hormuz": "Iran",
    "hormuz": "Iran",
    "macro": "Macro",
    "macroeconomics": "Macro",
    "economics": "Macro",
    "economy": "Macro",
    "us-economy": "Macro",
    "fed": "Macro",
    "fed-rates": "Macro",
    "federal-reserve": "Macro",
    "fomc": "Macro",
    "inflation": "Macro",
    "cpi": "Macro",
    "interest-rates": "Macro",
    "rates": "Macro",
    "recession": "Macro",
    "gdp": "Macro",
    "unemployment": "Macro",
    "jobs": "Macro",
    "tariffs": "Macro",
    "trade": "Macro",
    "treasury": "Macro",
    "crypto": "Crypto",
    "cryptocurrency": "Crypto",
    "crypto-prices": "Crypto",
    "bitcoin": "Crypto",
    "btc": "Crypto",
    "ethereum": "Crypto",
    "eth": "Crypto",
    "solana": "Crypto",
    "xrp": "Crypto",
    "dogecoin": "Crypto",
    "altcoins": "Crypto",
    "memecoins": "Crypto",
    "stablecoins": "Crypto",
    "crypto-etfs": "Crypto",
    "defi": "Crypto",
    "nft": "Crypto",
    "politics": "Politics",
    "us-politics": "Politics",
    "world-politics": "Politics",
    "geopolitics": "Politics",
    "elections": "Politics",
    "election": "Politics",
    "world-elections": "Politics",
    "us-election": "Politics",
    "presidential-election": "Politics",
    "congress": "Politics",
    "senate": "Politics",
    "house": "Politics",
    "white-house": "Politics",
    "government": "Politics",
    "government-shutdown": "Politics",
    "supreme-court": "Politics",
    "foreign-policy": "Politics",
    "trade-war": "Politics",
    "sanctions": "Politics",
}

_YES_LABELS = frozenset({"yes"})
_NO_LABELS = frozenset({"no"})


@dataclass(frozen=True, slots=True)
class NormalizedMarket:
    polymarket_market_id: str
    condition_id: str
    question: str
    """What the player reads: Polymarket's own English, same as `question_source`."""
    description: str | None
    category: str
    image_url: str | None
    yes_token_id: str
    no_token_id: str
    raw_yes_prob: Decimal
    liquidity_usd: Decimal
    volume_usd: Decimal
    lock_at: datetime
    end_date: datetime
    question_source: str = ""
    """Polymarket's original text. Identical to `question`; the column predates
    the site being English-only and is still what the API reads, so a row
    written while questions were being translated renders in English too."""
    description_source: str | None = None
    slug: str | None = None
    """Gamma's own name for the market, and the address of its public page.
    None when it is missing or is not shaped like an address."""
    change_1h: Decimal | None = None
    change_24h: Decimal | None = None
    change_7d: Decimal | None = None
    """How far the YES price has moved over the last hour, day and week, as
    Gamma reports it: signed, in probability. None where Gamma gave no figure
    — never zero, which would be a claim that nothing happened."""
    reference_prob: Decimal | None = None
    """The YES price those changes were measured to: Gamma's own, unclamped.
    None when no usable change came with it."""


@dataclass(frozen=True, slots=True)
class NormalizedEvent:
    polymarket_event_id: str
    slug: str | None
    title: str
    category: str
    image_url: str | None
    end_date: datetime | None
    markets: tuple[NormalizedMarket, ...]
    title_source: str = ""


@dataclass
class DiscoveryStats:
    events_seen: int = 0
    events_kept: int = 0
    markets_seen: int = 0
    markets_kept: int = 0
    skips: Counter[str] = field(default_factory=Counter)
    unmatched_tags: Counter[str] = field(default_factory=Counter)
    """Tags on events we rejected. Not part of the run report — it would
    swamp it — but the one thing worth having when the category mapping has
    fallen behind Gamma's taxonomy and every event is being dropped."""

    def skip(self, reason: str) -> None:
        self.skips[reason] += 1

    def as_dict(self) -> dict[str, object]:
        return {
            "events_seen": self.events_seen,
            "events_kept": self.events_kept,
            "markets_seen": self.markets_seen,
            "markets_kept": self.markets_kept,
            "skips": dict(self.skips),
        }

    def top_unmatched_tags(self, limit: int = 20) -> dict[str, int]:
        return dict(self.unmatched_tags.most_common(limit))


def _as_list(value: object) -> list[object] | None:
    """Gamma sends JSON arrays as strings on some endpoints and as arrays on others."""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, list) else None
    return None


def _as_decimal(value: object, default: Decimal = Decimal(0)) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool) or value is None:
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return default


_ADDRESS = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_MAX_ADDRESS = 200
_SIX_PLACES = Decimal("0.000001")


def _as_address(value: object) -> str | None:
    """A slug, if it can be used as a page's address exactly as given.

    Not repaired. A slug that needed lowercasing or trimming is a slug that
    might collide with another once it had been, and the page for one question
    would then be showing a different one.
    """
    text = _as_text(value)
    if text is None or len(text) > _MAX_ADDRESS or not _ADDRESS.match(text):
        return None
    return text


def _as_change(value: object, *, sign: int) -> Decimal | None:
    """A price change in probability, for the YES side, or None.

    Gamma reports every price figure for the market's *first* outcome. On the
    markets where that is "No", a rise is YES falling, so the sign is turned.
    Anything that is not a finite number between -1 and 1 is no figure at all.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        change = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not change.is_finite() or not Decimal(-1) <= change <= Decimal(1):
        return None
    return (change * sign).quantize(_SIX_PLACES)


def _as_reference(value: object) -> Decimal | None:
    """Gamma's own YES price, unclamped: a probability from 0 to 1, or None."""
    if value is None or isinstance(value, bool):
        return None
    try:
        price = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not price.is_finite() or not Decimal(0) <= price <= Decimal(1):
        return None
    return price.quantize(_SIX_PLACES)


def _as_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _as_text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _is_truthy(value: object, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return default


def _slugify(value: str) -> str:
    """Fold a tag's label form onto its slug form.

    Gamma gives the same tag two ways — `{"label": "Interest Rates",
    "slug": "interest-rates"}` — and which one is populated varies by
    endpoint. Normalising here means _CATEGORY_ALIASES holds one key per
    concept instead of two that can drift apart.
    """
    return value.strip().casefold().replace("_", "-").replace(" ", "-")


def resolve_category(
    event: dict,
    allowed: Iterable[str],
    stats: DiscoveryStats | None = None,
    *,
    priority: str | None = None,
) -> str | None:
    """Map a Gamma event onto one of our categories, or None to skip it.

    Older Gamma responses carry a `category` string; current ones carry
    `tags`. We read both, because a discovery pipeline that silently stops
    matching after an upstream schema change is the worst kind of broken.

    **`priority` wins over tag order.** An event is usually tagged several
    ways at once — a strike on Tehran carries `iran`, `geopolitics` and
    `world-politics` — and Gamma's tag order is not stable between endpoints
    or between days. Taking the first match would file the same event under
    Iran today and Politics tomorrow, which shows up in the app as markets
    disappearing from the tab a player was watching. Scanning every candidate
    and preferring the priority category makes the answer depend on the tags
    an event has rather than on the order they arrived in.
    """
    allowed_set = {c.casefold() for c in allowed}
    candidates: list[str] = []

    direct = _as_text(event.get("category"))
    if direct:
        candidates.append(direct)

    for tag in event.get("tags") or []:
        if isinstance(tag, dict):
            candidates.extend(text for key in ("label", "slug") if (text := _as_text(tag.get(key))))
        elif isinstance(tag, str):
            candidates.append(tag)

    matched: list[str] = []
    for candidate in candidates:
        mapped = _CATEGORY_ALIASES.get(_slugify(candidate))
        if mapped and mapped.casefold() in allowed_set and mapped not in matched:
            matched.append(mapped)

    if not matched:
        if stats is not None:
            stats.unmatched_tags.update({_slugify(c) for c in candidates})
        return None

    if priority:
        for category in matched:
            if category.casefold() == priority.casefold():
                return category
    return matched[0]


def _resolve_yes_index(outcomes: list[object]) -> int | None:
    """Find which slot is YES.

    `clobTokenIds[i]` pairs with `outcomes[i]`, and the order is not
    guaranteed. Assuming index 0 is YES would, on a reversed market, sell
    every player the opposite side of the bet they thought they placed.
    Markets whose outcomes are not a Yes/No pair are not binary in the sense
    we can label, so they are skipped rather than guessed at.
    """
    if len(outcomes) != 2:
        return None

    labels = [o.strip().casefold() if isinstance(o, str) else "" for o in outcomes]
    if labels[0] in _YES_LABELS and labels[1] in _NO_LABELS:
        return 0
    if labels[0] in _NO_LABELS and labels[1] in _YES_LABELS:
        return 1
    return None


def normalize_market(
    raw: dict,
    *,
    category: str,
    settings: Settings,
    stats: DiscoveryStats,
    now: datetime,
) -> NormalizedMarket | None:
    market_id = _as_text(raw.get("id"))
    if not market_id:
        stats.skip("market_no_id")
        return None

    if _is_truthy(raw.get("closed")) or _is_truthy(raw.get("archived")):
        stats.skip("market_closed")
        return None
    if not _is_truthy(raw.get("active"), default=True):
        stats.skip("market_inactive")
        return None

    token_ids = _as_list(raw.get("clobTokenIds"))
    if token_ids is None:
        stats.skip("market_token_ids_unparseable")
        return None
    if len(token_ids) != 2:
        stats.skip("market_not_binary")
        return None

    tokens = [_as_text(t) for t in token_ids]
    if not all(tokens) or tokens[0] == tokens[1]:
        stats.skip("market_token_ids_invalid")
        return None

    outcomes = _as_list(raw.get("outcomes")) or []
    yes_index = _resolve_yes_index(outcomes)
    if yes_index is None:
        stats.skip("market_outcomes_not_yes_no")
        return None
    no_index = 1 - yes_index

    condition_id = _as_text(raw.get("conditionId"))
    question = _as_text(raw.get("question"))
    if not condition_id or not question:
        stats.skip("market_missing_fields")
        return None

    end_date = _as_datetime(raw.get("endDate")) or _as_datetime(raw.get("end_date"))
    if end_date is None:
        stats.skip("market_no_end_date")
        return None

    lock_at = end_date - timedelta(seconds=settings.market_lock_buffer_seconds)
    if lock_at <= now:
        stats.skip("market_past_cutoff")
        return None

    prices = _as_list(raw.get("outcomePrices")) or []
    raw_prob = (
        _as_decimal(prices[yes_index], Decimal("0.5")) if len(prices) == 2 else Decimal("0.5")
    )
    raw_prob = _clamp(raw_prob, settings)

    liquidity = _as_decimal(raw.get("liquidityNum", raw.get("liquidity")))
    volume = _as_decimal(raw.get("volumeNum", raw.get("volume")))

    # The source's own account of how the price has moved. All of it is for
    # the first outcome, so it is turned to face YES; and none of it is kept
    # without the price it was measured to, because "up 25 points" means
    # nothing to a reader until it can be said as "from 30% to 55%".
    sign = 1 if yes_index == 0 else -1
    reference = _as_reference(prices[yes_index]) if len(prices) == 2 else None
    changes = {
        "change_1h": _as_change(raw.get("oneHourPriceChange"), sign=sign),
        "change_24h": _as_change(raw.get("oneDayPriceChange"), sign=sign),
        "change_7d": _as_change(raw.get("oneWeekPriceChange"), sign=sign),
    }
    if reference is None:
        changes = dict.fromkeys(changes)
    elif all(value is None for value in changes.values()):
        reference = None

    return NormalizedMarket(
        polymarket_market_id=market_id,
        condition_id=condition_id,
        question=question,
        description=_as_text(raw.get("description")),
        question_source=question,
        description_source=_as_text(raw.get("description")),
        category=category,
        image_url=_as_text(raw.get("image")) or _as_text(raw.get("icon")),
        yes_token_id=tokens[yes_index],  # type: ignore[arg-type]
        no_token_id=tokens[no_index],  # type: ignore[arg-type]
        raw_yes_prob=raw_prob,
        liquidity_usd=liquidity,
        volume_usd=volume,
        lock_at=lock_at,
        end_date=end_date,
        slug=_as_address(raw.get("slug")),
        reference_prob=reference,
        **changes,
    )


def _clamp(value: Decimal, settings: Settings) -> Decimal:
    low = Decimal(str(settings.min_prob))
    high = Decimal(str(settings.max_prob))
    return min(max(value, low), high)


def normalize_event(
    raw: dict,
    *,
    settings: Settings,
    stats: DiscoveryStats,
    now: datetime | None = None,
) -> NormalizedEvent | None:
    now = now or datetime.now(UTC)
    stats.events_seen += 1

    event_id = _as_text(raw.get("id"))
    title = _as_text(raw.get("title"))
    if not event_id or not title:
        stats.skip("event_missing_fields")
        return None

    if _is_truthy(raw.get("closed")) or _is_truthy(raw.get("archived")):
        stats.skip("event_closed")
        return None

    category = resolve_category(
        raw,
        settings.discovery_categories,
        stats,
        priority=settings.discovery_priority_category,
    )
    if category is None:
        stats.skip("event_category_not_wanted")
        return None

    markets: list[NormalizedMarket] = []
    for raw_market in raw.get("markets") or []:
        if not isinstance(raw_market, dict):
            continue
        stats.markets_seen += 1
        normalized = normalize_market(
            raw_market, category=category, settings=settings, stats=stats, now=now
        )
        if normalized is not None:
            markets.append(normalized)
            stats.markets_kept += 1

    if not markets:
        stats.skip("event_no_usable_markets")
        return None

    stats.events_kept += 1
    return NormalizedEvent(
        polymarket_event_id=event_id,
        slug=_as_text(raw.get("slug")),
        title=title,
        title_source=title,
        category=category,
        image_url=_as_text(raw.get("image")) or _as_text(raw.get("icon")),
        end_date=_as_datetime(raw.get("endDate")),
        markets=tuple(markets),
    )


def normalize_events(
    payload: Iterable[object], *, settings: Settings, stats: DiscoveryStats
) -> Iterator[NormalizedEvent]:
    now = datetime.now(UTC)
    for raw in payload:
        if not isinstance(raw, dict):
            continue
        event = normalize_event(raw, settings=settings, stats=stats, now=now)
        if event is not None:
            yield event


_PRIORITY_MAX_PAGES = 3
"""Pages to read per priority tag.

The priority pass exists to guarantee presence, not coverage. A Gamma tag as
narrow as `iran` holds tens of open events, not thousands, so three pages
reaches the end of it; spending discovery's twenty-page budget per slug would
cost twenty round trips to read the same short list.
"""


async def _page_through(
    client: httpx.AsyncClient,
    settings: Settings,
    *,
    params: dict[str, object],
    max_pages: int,
    warn_on_ceiling: bool,
    convert: Callable[[list[dict]], list[_T]],
) -> list[_T]:
    """Read one ordered query until it runs out, its ceiling, or a short page.

    Each page is handed to `convert` as it arrives, and only what that returns
    is kept. That is what bounds the memory this takes. Gamma's own JSON for
    an event is enormous beside what we keep of it — every market carries
    scores of fields nothing here reads — and the events at the top of a
    volume ordering are the largest of all. Holding twenty pages of it at once
    measured over half a gigabyte, which is more than a small server has; held
    a page at a time, the same pass needs a fraction of that.
    """
    collected: list[_T] = []
    url = f"{settings.gamma_api_url}/events"
    base_params = dict(params)

    async def fetch_page(page: int) -> object:
        page_params = {
            **base_params,
            "limit": settings.discovery_page_size,
            "offset": page * settings.discovery_page_size,
        }
        try:
            return await get_json(
                client, url, params=page_params, max_retries=settings.http_max_retries
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code >= 500 or "order" not in base_params:
                raise
            logger.warning(
                "Gamma rejected order=%r (HTTP %s); retrying unordered — "
                "set DISCOVERY_ORDER to a field it accepts",
                settings.discovery_order,
                exc.response.status_code,
            )
            base_params.pop("order")
            base_params.pop("ascending", None)
            return await get_json(
                client,
                url,
                params={**base_params, **{k: page_params[k] for k in ("limit", "offset")}},
                max_retries=settings.http_max_retries,
            )

    for page in range(max_pages):
        payload = await fetch_page(page)

        batch = payload if isinstance(payload, list) else (payload or {}).get("data")
        if not isinstance(batch, list) or not batch:
            break

        collected.extend(convert([item for item in batch if isinstance(item, dict)]))
        if len(batch) < settings.discovery_page_size:
            break
    else:
        if warn_on_ceiling:
            logger.warning(
                "discovery hit its page ceiling (%s); some events may be unread",
                max_pages,
            )

    return collected


def _as_it_came(batch: list[dict]) -> list[dict]:
    return batch


async def _fetch_priority_events(
    client: httpx.AsyncClient,
    settings: Settings,
    base_params: dict[str, object],
    convert: Callable[[list[dict]], list[_T]],
) -> list[_T]:
    """Read the priority tags directly, before anything is ranked by volume.

    Everything downstream of this function sorts by trading volume — Gamma's
    `order`, discovery's budget cut, the surplus trim — and a regional tag
    loses that comparison to Bitcoin and the Fed every time. Enabling the
    category alone therefore produces a tab that is empty in production and
    full in a test with ten events in it. Asking Gamma for the tag by name is
    the only step that does not depend on how much money is on the market.

    A failure here is not fatal. The priority tag is a preference, and a run
    that ingests the ordinary feed without it beats a run that ingests
    nothing, so the error is logged and the pass returns empty.
    """
    slugs = [slug for slug in settings.discovery_priority_tag_slugs if slug.strip()]
    if not slugs:
        return []

    collected: list[_T] = []
    for slug in slugs:
        try:
            # Read whole before anything is converted. A tag is a few pages at
            # most, so this is small — and `convert` remembers which events it
            # has been shown, so a tag that failed on its second page must not
            # have had its first page shown to it: those events would then be
            # dropped as repeats when the ordinary feed returned them, and be
            # in neither list.
            batch = await _page_through(
                client,
                settings,
                params={**base_params, "tag_slug": slug},
                max_pages=_PRIORITY_MAX_PAGES,
                warn_on_ceiling=False,
                convert=_as_it_came,
            )
        except Exception:
            logger.warning(
                "priority tag %r could not be read; continuing with the ordinary feed. "
                "If this persists the slug has probably moved — check the discovery "
                "log's unmatched tags and update DISCOVERY_PRIORITY_TAG_SLUGS.",
                slug,
                exc_info=True,
            )
            continue
        logger.info("priority tag %r returned %d event(s)", slug, len(batch))
        collected.extend(convert(batch))

    return collected


async def _read_feed(
    client: httpx.AsyncClient,
    settings: Settings,
    convert: Callable[[list[dict]], list[_T]],
) -> list[_T]:
    """Page through active, open events — priority tags first, then most-traded.

    The sort key is the whole game. Gamma holds tens of thousands of open
    events and this reads at most page_size * max_pages of them, so `order`
    decides *which* slice we ever see.

    Sorting by soonest end date is the obvious choice and the wrong one: the
    events ending in the next few hours are almost entirely the hourly crypto
    candles ("Bitcoin Up or Down — 3PM ET"). They are tagged crypto, so they
    pass the category filter, and their outcomes are Up/Down rather than
    Yes/No, so normalize_market then rejects every one. That combination is
    not hypothetical — it read 2000 events and kept zero, while the headline
    markets a player actually wants sat outside the window.

    Ordering by trading activity instead puts those headline markets on page
    one. `end_date_min` spends nothing on events already past the point where
    a bet could be placed.

    The priority tags are read first and placed at the front, because the rest
    of the pipeline consumes this list in order and cuts it at a budget. An
    event returned by both passes is kept once, at its priority position.
    """
    horizon = datetime.now(UTC) + timedelta(seconds=settings.market_lock_buffer_seconds)

    base_params: dict[str, object] = {
        "active": "true",
        "closed": "false",
        "archived": "false",
        "end_date_min": horizon.isoformat().replace("+00:00", "Z"),
        "order": settings.discovery_order,
        "ascending": "true" if settings.discovery_order_ascending else "false",
    }

    priority = await _fetch_priority_events(client, settings, base_params, convert)
    ordinary = await _page_through(
        client,
        settings,
        params=base_params,
        max_pages=settings.discovery_max_pages,
        warn_on_ceiling=True,
        convert=convert,
    )
    return [*priority, *ordinary]


def _first_sighting(seen: set[str]) -> Callable[[list[dict]], list[dict]]:
    """A page filter that drops events an earlier page or pass already returned.

    The priority pass and the ordinary pass overlap by design, and an event is
    kept once, where it was first seen — which is its priority position.
    """

    def unique(batch: list[dict]) -> list[dict]:
        fresh: list[dict] = []
        for item in batch:
            event_id = _as_text(item.get("id"))
            if event_id is not None:
                if event_id in seen:
                    continue
                seen.add(event_id)
            fresh.append(item)
        return fresh

    return unique


async def fetch_events(client: httpx.AsyncClient, settings: Settings) -> list[dict]:
    """The feed as Gamma sent it: every event, whole, each one once.

    This holds all of it in memory at the same time, which for a full pass is
    several hundred megabytes. It is for tests and for looking at the feed by
    hand. Discovery itself uses `fetch_normalized_events`.
    """
    return await _read_feed(client, settings, _first_sighting(set()))


async def fetch_normalized_events(
    client: httpx.AsyncClient, settings: Settings, stats: DiscoveryStats
) -> list[NormalizedEvent]:
    """The same feed, in the same order, reduced to our own records as it arrives.

    Equivalent to `normalize_events(await fetch_events(...))`, and tested to
    be. The difference is what is in memory while it runs: one page of
    Gamma's JSON and the compact records kept so far, instead of all of
    Gamma's JSON at once.
    """
    unique = _first_sighting(set())
    now = datetime.now(UTC)

    def compact(batch: list[dict]) -> list[NormalizedEvent]:
        kept: list[NormalizedEvent] = []
        for raw in unique(batch):
            event = normalize_event(raw, settings=settings, stats=stats, now=now)
            if event is not None:
                kept.append(event)
        return kept

    return await _read_feed(client, settings, compact)
