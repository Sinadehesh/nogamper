"""What a question's chance is right now, and how far to trust the number.

Shared by the game's feed and by the public question pages, so that the two
cannot disagree about a price or about whether it is stale.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from ..cache import prices as price_cache
from ..config import Settings
from ..schemas import Probability

PROB_PLACES = Decimal("0.0001")


def current_probability(
    market_id: uuid.UUID,
    stored_prob: Decimal,
    stored_at: datetime,
    cached: price_cache.CachedPrice | None,
    settings: Settings,
    now: datetime,
) -> Probability:
    """The cached price when there is one, the stored one otherwise.

    Prices are never invented. If the cache misses and the stored price is
    older than the staleness tolerance, the number is still given — with
    `stale: true` — rather than hidden or passed off as current.
    """
    if cached is not None:
        probability, source, age = (
            cached.probability,
            cached.source,
            cached.age_seconds(now),
        )
    else:
        probability, source, age = (
            stored_prob,
            "DATABASE",
            (now - stored_at).total_seconds(),
        )

    yes = probability.quantize(PROB_PLACES)
    return Probability(
        yes=str(yes),
        no=str((Decimal(1) - yes).quantize(PROB_PLACES)),
        source=source,
        age_seconds=round(age, 1),
        stale=age > settings.price_staleness_seconds,
    )
