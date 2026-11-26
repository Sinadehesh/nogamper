"""Quote and place forecasts.

Two endpoints do the work:

  POST /v1/predictions/quote  prices a slip without committing anything
  POST /v1/predictions        places it, once, under an Idempotency-Key

Quoting and placing run the *same* pricing path. The quote is not a promise —
prices move — so placement re-prices from live state and compares against the
odds the client says it displayed. If the market has moved against the player
beyond the tolerance, the placement is refused and a fresh quote returned
rather than a worse price being taken on their behalf. Movement in their
favour is simply given to them.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status

from .. import db
from ..config import Settings, get_settings
from ..engine import quoting
from ..engine.quoting import LegRequest, QuoteError, SlipQuote
from ..repositories import predictions as repo
from ..schemas import (
    ErrorResponse,
    Money,
    QuotedLeg,
    SettledLeg,
    Slip,
    SlipPage,
    SlipQuoteResponse,
    SlipRequest,
)
from ..security.dependencies import CurrentUser
from ..services import economy

router = APIRouter(prefix="/v1/predictions", tags=["predictions"])


def _fingerprint(body: SlipRequest) -> str:
    """Identify the *forecast*, not the request.

    `accepted_odds` is deliberately excluded: a client that retries with a
    refreshed quote is placing the same slip, and should get it back rather
    than a 409.
    """
    payload = {
        "legs": sorted((leg.market_id, leg.side) for leg in body.legs),
        "stake": body.stake,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _parse_legs(body: SlipRequest) -> list[LegRequest]:
    try:
        return [LegRequest(market_id=uuid.UUID(leg.market_id), side=leg.side) for leg in body.legs]
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "bad_market_id", "detail": "A market id is not a valid UUID."},
        ) from exc


def _quote_response(quote: SlipQuote) -> SlipQuoteResponse:
    priced = quote.priced

    def context(leg):
        return quote.markets[uuid.UUID(leg.market_id)]

    return SlipQuoteResponse(
        legs=[
            QuotedLeg(
                market_id=leg.market_id,
                question=context(leg).question,
                category=context(leg).category,
                side=leg.side,
                probability=str(leg.true_prob),
                locked_odds=str(leg.locked_odds),
                lock_at=context(leg).lock_at,
            )
            for leg in priced.legs
        ],
        stake=Money.of(priced.stake_minor),
        combined_odds=str(priced.combined_odds),
        win_probability=f"{priced.true_probability:.6f}",
        potential_payout=Money.of(priced.potential_payout_minor),
        gross_potential_payout=Money.of(priced.gross_payout_minor),
        payout_cap=Money.of(priced.payout_cap_minor),
        capped=priced.capped,
    )


async def _build_quote(body: SlipRequest, settings: Settings, *, conn=None) -> SlipQuote:
    legs = _parse_legs(body)

    async def build(connection) -> SlipQuote:
        contexts = await quoting.load_market_contexts(connection, legs, settings)
        return quoting.quote_slip(legs, contexts, stake_minor=body.stake, settings=settings)

    if conn is not None:
        return await build(conn)
    async with db.acquire() as connection:
        return await build(connection)


def _check_stake(body: SlipRequest, settings: Settings) -> None:
    if body.stake < settings.min_stake_minor:
        raise QuoteError(
            "stake_too_small",
            f"The minimum stake is {Money.of(settings.min_stake_minor).display} points.",
        )
    if body.stake > settings.max_stake_minor:
        raise QuoteError(
            "stake_too_large",
            f"The maximum stake is {Money.of(settings.max_stake_minor).display} points.",
        )


@router.post(
    "/quote",
    response_model=SlipQuoteResponse,
    responses={400: {"model": ErrorResponse}},
    summary="Price a slip without placing it",
)
async def quote(
    _: CurrentUser,
    body: SlipRequest,
    settings: Annotated[Settings, Depends(get_settings)],
) -> SlipQuoteResponse:
    _check_stake(body, settings)
    return _quote_response(await _build_quote(body, settings))


@router.post(
    "",
    response_model=Slip,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse},
        402: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
    summary="Place a slip",
)
async def place(
    user: CurrentUser,
    body: SlipRequest,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> Slip:
    if not idempotency_key or not idempotency_key.strip():
        raise HTTPException(
            status_code=400,
            detail={
                "code": "idempotency_key_required",
                "detail": "Send an Idempotency-Key header with every placement.",
            },
        )
    if len(idempotency_key) > 255:
        raise HTTPException(
            status_code=400,
            detail={"code": "idempotency_key_too_long", "detail": "Key is too long."},
        )

    _check_stake(body, settings)
    fingerprint = _fingerprint(body)

    async with db.transaction() as conn:
        fresh = await _build_quote(body, settings, conn=conn)
        _check_odds_drift(body, fresh, settings)

        result = await repo.place_slip(
            conn,
            user=user,
            quote=fresh,
            idempotency_key=idempotency_key.strip(),
            request_fingerprint=fingerprint,
            day_start=economy.day_start(settings),
        )
        slip, legs = await repo.get_slip(conn, user["id"], result.prediction_id)

    if result.replayed:
        response.status_code = status.HTTP_200_OK
    return _slip_response(slip, legs)


def _check_odds_drift(body: SlipRequest, fresh: SlipQuote, settings: Settings) -> None:
    if body.accepted_odds is None:
        return
    try:
        accepted = Decimal(body.accepted_odds)
    except ArithmeticError as exc:
        raise QuoteError("bad_accepted_odds", "accepted_odds is not a number.") from exc

    if accepted <= 0:
        raise QuoteError("bad_accepted_odds", "accepted_odds must be positive.")

    current = fresh.priced.combined_odds
    if current >= accepted:
        return

    tolerance = Decimal(str(settings.odds_drift_tolerance))
    if (accepted - current) / accepted > tolerance:
        raise QuoteError(
            "odds_moved",
            f"The price moved from {accepted} to {current} while this slip was open. "
            "Re-confirm to place it at the current price.",
        )


@router.get("", response_model=SlipPage, summary="This player's slips, newest first")
async def list_predictions(
    user: CurrentUser,
    slip_status: Annotated[str | None, Query(alias="status", max_length=16)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    cursor: Annotated[str | None, Query(max_length=64)] = None,
) -> SlipPage:
    if slip_status is not None and slip_status not in {
        "PENDING",
        "WON",
        "LOST",
        "INSURED",
        "VOID",
    }:
        raise HTTPException(
            status_code=400,
            detail={"code": "bad_status", "detail": "Unknown slip status."},
        )

    before = None
    if cursor:
        try:
            before = uuid.UUID(cursor)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail={"code": "bad_cursor", "detail": "Cursor is not valid."},
            ) from exc

    async with db.acquire() as conn:
        slips, legs = await repo.list_slips(
            conn, user["id"], status=slip_status, limit=limit + 1, before=before
        )

    has_more = len(slips) > limit
    slips = slips[:limit]

    return SlipPage(
        slips=[_slip_response(slip, legs.get(slip["id"], [])) for slip in slips],
        next_cursor=str(slips[-1]["id"]) if has_more and slips else None,
    )


@router.get("/{prediction_id}", response_model=Slip, summary="One slip")
async def get_prediction(user: CurrentUser, prediction_id: uuid.UUID) -> Slip:
    async with db.acquire() as conn:
        slip, legs = await repo.get_slip(conn, user["id"], prediction_id)
    if slip is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "detail": "No such slip."}
        )
    return _slip_response(slip, legs)


def _slip_response(slip, legs) -> Slip:
    return Slip(
        id=str(slip["id"]),
        type=slip["type"],
        status=slip["status"],
        legs=[
            SettledLeg(
                leg_index=leg["leg_index"],
                market_id=str(leg["market_id"]),
                question=leg["question"],
                side=leg["side"],
                locked_odds=str(leg["locked_odds"]),
                status=leg["status"],
                resolution=leg["resolution"],
                lock_at=leg["lock_at"],
            )
            for leg in legs
        ],
        stake=Money.of(slip["stake"]),
        combined_odds=str(slip["combined_odds"]),
        potential_payout=Money.of(slip["potential_payout"]),
        capped=slip["potential_payout"] < slip["gross_potential_payout"],
        total_cost=Money.of(slip["total_cost"]),
        settled_payout=Money.of(slip["settled_payout"]),
        placed_at=slip["placed_at"],
        settled_at=slip["settled_at"],
    )
