"""Localising normalised events before they are persisted.

Sits between the Gamma normaliser and the upsert. Everything a player reads —
event titles, market questions, descriptions — is translated here; everything
that links data together is not.

**What is never translated, and why:** `polymarket_market_id`,
`polymarket_event_id`, `condition_id`, `yes_token_id` and `no_token_id` are
join keys against Polymarket. Translating one would silently detach a market
from the price feed and from resolution. `category` is likewise a key, not
prose — the markets endpoint filters on `category = 'Macro'`, and the UI
translates the label at render time.
"""

from __future__ import annotations

import logging
from dataclasses import replace

import asyncpg

from ..clients.gamma import NormalizedEvent, NormalizedMarket
from ..services.translation import TranslationService

logger = logging.getLogger(__name__)

__all__ = ["localize_events"]


def _translatable(events: list[NormalizedEvent]) -> list[str]:
    texts: list[str] = []
    for event in events:
        texts.append(event.title_source)
        for market in event.markets:
            texts.append(market.question_source)
    return texts


def _localized_market(market: NormalizedMarket, table: dict[str, str]) -> NormalizedMarket:
    return replace(
        market,
        question=table.get(market.question_source, market.question_source),
        description=(
            table.get(market.description_source, market.description_source)
            if market.description_source
            else None
        ),
    )


async def localize_events(
    conn: asyncpg.Connection,
    events: list[NormalizedEvent],
    service: TranslationService,
) -> list[NormalizedEvent]:
    """Return the events with player-facing text translated.

    Never raises. The service maps anything it cannot translate back to its
    own source, so a provider outage degrades to English text rather than to
    an empty market list.
    """
    if not events:
        return events

    table = await service.translate_many(conn, _translatable(events))

    return [
        replace(
            event,
            title=table.get(event.title_source, event.title_source),
            markets=tuple(_localized_market(market, table) for market in event.markets),
        )
        for event in events
    ]
