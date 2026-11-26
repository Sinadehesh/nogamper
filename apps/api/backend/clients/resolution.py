"""Reading a settled outcome out of a Gamma market payload.

Pure functions, no I/O, because this is the code that decides who gets paid.

## The rule that matters

**Grade only what is unambiguous.** A Polymarket market can be `closed` and
still not be *resolved* — sitting in a UMA proposal window, or under dispute.
Grading on `closed` alone pays the wrong people, and the ledger is append-only,
so there is no clean undo. Anything this module cannot read with certainty
returns `None`, the market stays pending, and the next tick tries again. A
market stuck pending is a monitoring problem; a market graded wrongly is a
refund exercise across every slip that touched it.

## Finding the YES side

`outcomePrices[i]` pairs with `clobTokenIds[i]`, and that order is not
guaranteed to be YES-first. Rather than re-deriving it from outcome labels, we
look up the index of the `yes_token_id` we stored at discovery — the token we
have already been pricing and taking bets against. If it is not in the payload
we refuse to grade, because a market whose tokens no longer match ours is not
a market we understand.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)

__all__ = ["Resolution", "ResolutionReading", "read_resolution"]

Resolution = str

_SETTLED_HIGH = Decimal("0.99")
_SETTLED_LOW = Decimal("0.01")
_VOID_CENTRE = Decimal("0.5")
_VOID_TOLERANCE = Decimal("0.02")

_FINAL_UMA_STATES = frozenset({"resolved", "settled", ""})


@dataclass(frozen=True, slots=True)
class ResolutionReading:
    resolution: Resolution | None
    """None means: not gradeable yet. Not an error — just not final."""
    reason: str
    """Why, for the log. Always populated, including on success."""
    yes_price: Decimal | None = None
    no_price: Decimal | None = None


def _as_list(value: object) -> list[object] | None:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, list) else None
    return None


def _as_decimal(value: object) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _is_truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return False


def read_resolution(payload: object, *, yes_token_id: str) -> ResolutionReading:
    """Decide how a market settled, or that it has not settled yet."""
    if not isinstance(payload, dict):
        return ResolutionReading(None, "payload was not an object")

    if not _is_truthy(payload.get("closed")):
        return ResolutionReading(None, "not closed upstream")

    uma_state = payload.get("umaResolutionStatus")
    if uma_state is not None:
        state = str(uma_state).strip().lower()
        if state not in _FINAL_UMA_STATES:
            return ResolutionReading(None, f"upstream resolution is '{state}'")

    token_ids = _as_list(payload.get("clobTokenIds"))
    prices = _as_list(payload.get("outcomePrices"))
    if token_ids is None or prices is None:
        return ResolutionReading(None, "token ids or prices missing")
    if len(token_ids) != len(prices):
        return ResolutionReading(None, "token ids and prices are different lengths")
    if len(token_ids) != 2:
        return ResolutionReading(None, f"expected 2 outcomes, got {len(token_ids)}")

    tokens = [str(t).strip() if t is not None else "" for t in token_ids]
    if yes_token_id not in tokens:
        return ResolutionReading(None, "stored YES token is absent from the payload")

    yes_index = tokens.index(yes_token_id)
    yes_price = _as_decimal(prices[yes_index])
    no_price = _as_decimal(prices[1 - yes_index])
    if yes_price is None or no_price is None:
        return ResolutionReading(None, "outcome prices were not numbers")

    if yes_price >= _SETTLED_HIGH and no_price <= _SETTLED_LOW:
        return ResolutionReading("YES", "settled YES", yes_price, no_price)
    if yes_price <= _SETTLED_LOW and no_price >= _SETTLED_HIGH:
        return ResolutionReading("NO", "settled NO", yes_price, no_price)

    if (
        abs(yes_price - _VOID_CENTRE) <= _VOID_TOLERANCE
        and abs(no_price - _VOID_CENTRE) <= _VOID_TOLERANCE
    ):
        return ResolutionReading("VOID", "voided upstream", yes_price, no_price)

    return ResolutionReading(
        None, f"closed but prices are inconclusive ({yes_price}/{no_price})", yes_price, no_price
    )
