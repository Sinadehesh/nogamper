"""The shop: what is for sale, a player's limits, checkout, and Stripe's word.

Four routes.

    GET  /v1/shop                      the price list, and where you stand
    PUT  /v1/shop/limit                set your own monthly spending limit
    POST /v1/shop/checkout             start buying one pack
    POST /v1/payments/stripe/webhook   Stripe telling us what happened

The last one is the only route in this service that is called by somebody
other than the web tier, and the only one that credits a purchase. The browser
coming back from Stripe's page credits nothing — it is shown a thank-you and
the points arrive when Stripe's signed message does, usually within seconds.

With no Stripe key configured the shop is closed: the price list says so, and
the routes that would sell something answer 404.
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from .. import db
from ..clients import stripe
from ..config import Settings, get_settings
from ..repositories import shop
from ..schemas import (
    CheckoutOut,
    CheckoutRequest,
    ErrorResponse,
    Money,
    ShopOut,
    ShopPack,
    ShopPurchase,
    ShopStanding,
    ShopTerms,
    SpendLimitRequest,
)
from ..security.dependencies import CurrentUser, OptionalUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["shop"])

MAX_WEBHOOK_BYTES = 512 * 1024


def terms(settings: Settings) -> ShopTerms:
    return ShopTerms(
        open=settings.shop_open,
        currency=settings.shop_currency,
        price_per_thousand_cents=settings.shop_price_per_thousand_cents,
        packs=[
            ShopPack(points=Money.of(pack.points_minor), price_cents=pack.price_cents)
            for pack in shop.packs(settings)
        ],
        monthly_cap_cents=settings.shop_monthly_cap_cents,
        min_age=settings.shop_min_age,
    )


async def _standing(conn, user_id: uuid.UUID, settings: Settings) -> ShopStanding:
    state = await shop.spending(conn, user_id=user_id, settings=settings)
    purchases = await shop.recent(conn, user_id=user_id)
    return ShopStanding(
        spent_month_cents=state.paid_month,
        pending_cents=state.pending,
        spent_all_cents=state.paid_all,
        limit_cents=state.personal_limit,
        limit_loosen_at=state.limit_loosen_at,
        remaining_cents=state.remaining,
        resets_at=state.resets_at,
        blocked=state.blocked,
        blocked_until=state.blocked_until,
        purchases=[
            ShopPurchase(
                id=str(row.id),
                points=Money.of(row.points_minor),
                amount_cents=row.amount_cents,
                currency=row.currency,
                status=row.status,
                at=row.created_at,
            )
            for row in purchases
        ],
    )


async def _shop_for(conn, user_id: uuid.UUID | None, settings: Settings) -> ShopOut:
    mine = await _standing(conn, user_id, settings) if user_id is not None else None
    return ShopOut(**terms(settings).model_dump(), mine=mine)


@router.get("/shop", response_model=ShopOut, summary="What is for sale, and your own limits")
async def read_shop(
    user: OptionalUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ShopOut:
    async with db.acquire() as conn:
        return await _shop_for(conn, user["id"] if user is not None else None, settings)


@router.put(
    "/shop/limit",
    response_model=ShopOut,
    responses={409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    summary="Set, lower, raise or remove your monthly spending limit",
)
async def set_limit(
    payload: SpendLimitRequest,
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ShopOut:
    """Zero closes the shop for this player. Lowering applies at once; raising
    or removing waits a day, like every other limit here.

    Available whether or not the shop is open: deciding in advance never to
    be sold anything is a decision somebody should be able to make early.
    """
    async with db.transaction() as conn:
        await shop.set_spend_limit(
            conn, user_id=user["id"], new_limit=payload.limit_cents, settings=settings
        )
        return await _shop_for(conn, user["id"], settings)


@router.post(
    "/shop/checkout",
    response_model=CheckoutOut,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
    summary="Start buying one pack of points",
)
async def checkout(
    payload: CheckoutRequest,
    request: Request,
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> CheckoutOut:
    """Record the purchase, then ask Stripe for a page to pay on.

    In that order, and in two transactions, so the cap is decided before
    anything outside this database is involved. If Stripe then cannot be
    reached, the row is closed again rather than left to count against the
    month for half an hour.
    """
    async with db.transaction() as conn:
        purchase = await shop.open_purchase(
            conn,
            user_id=user["id"],
            points=payload.points,
            adult=payload.adult,
            settings=settings,
        )

    try:
        session = await stripe.create_checkout_session(
            request.app.state.http,
            settings,
            purchase_id=purchase.id,
            points=payload.points,
            amount_cents=purchase.amount_cents,
            expires_at=purchase.expires_at,
        )
    except stripe.StripeUnavailable as exc:
        logger.warning("checkout for purchase %s failed: %s", purchase.id, exc)
        async with db.acquire() as conn:
            await shop.abandon(conn, purchase_id=purchase.id)
        raise shop.ShopError(
            "payment_unavailable",
            "Payment is unavailable right now. Nothing was charged.",
            status=502,
        ) from exc

    async with db.acquire() as conn:
        await shop.attach_session(conn, purchase_id=purchase.id, session_id=session.id)
    return CheckoutOut(url=session.url)


# ----- Stripe's side of the conversation -------------------------------------


def _purchase_id(session: dict) -> uuid.UUID | None:
    """Which purchase a checkout session is for, or None if it is not ours.

    "Not ours" is ordinary: the same Stripe account can take donations or
    sell something else entirely, and every one of those payments is reported
    to this endpoint too.
    """
    metadata = session.get("metadata") or {}
    candidate = metadata.get("purchase_id") or session.get("client_reference_id")
    try:
        return uuid.UUID(str(candidate))
    except (ValueError, TypeError):
        return None


async def _handle(event: dict) -> str:
    kind = event.get("type")
    obj = (event.get("data") or {}).get("object") or {}

    if kind in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        purchase_id = _purchase_id(obj)
        if purchase_id is None:
            return "ignored"
        if obj.get("payment_status") != "paid":
            # Completed but not yet paid: a method that settles later. Card is
            # the only one offered, so this should not happen; if it does, the
            # points wait for the message that says the money arrived.
            return "not_paid"
        async with db.transaction() as conn:
            return await shop.mark_paid(
                conn,
                purchase_id=purchase_id,
                session_id=obj.get("id"),
                payment_intent=obj.get("payment_intent"),
                amount_cents=obj.get("amount_total"),
                currency=obj.get("currency"),
            )

    if kind in ("checkout.session.expired", "checkout.session.async_payment_failed"):
        purchase_id = _purchase_id(obj)
        if purchase_id is None:
            return "ignored"
        async with db.acquire() as conn:
            return "expired" if await shop.expire(conn, purchase_id=purchase_id) else "ignored"

    if kind in ("charge.refunded", "charge.dispute.created"):
        payment_intent = obj.get("payment_intent")
        if not isinstance(payment_intent, str) or not payment_intent:
            return "ignored"
        async with db.transaction() as conn:
            outcome = await shop.mark_refunded(conn, payment_intent=payment_intent)
        return "ignored" if outcome == "unknown" else outcome

    return "ignored"


@router.post("/payments/stripe/webhook", include_in_schema=False)
async def stripe_webhook(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    signature: Annotated[str | None, Header(alias="Stripe-Signature")] = None,
) -> dict[str, object]:
    """Believe Stripe, and only Stripe.

    The body is read as bytes and verified before it is parsed: the signature
    is over those exact bytes. A request that fails gets a 400 and no detail —
    whoever sent it is either Stripe misconfigured, which the log explains to
    the operator, or not Stripe, who is owed no explanation.

    Everything understood answers 200, including "this was not about one of
    our purchases" and "we had already done that". Stripe retries anything
    else for days, and neither of those gets truer with repetition. A failure
    to reach the database is the one thing that should be retried, and it
    surfaces as a 500 on its own.
    """
    if not settings.shop_open:
        raise HTTPException(status_code=404, detail={"code": "not_found", "detail": "Not found."})

    payload = await request.body()
    if len(payload) > MAX_WEBHOOK_BYTES:
        raise HTTPException(
            status_code=413, detail={"code": "payload_too_large", "detail": "Too large."}
        )

    try:
        event = stripe.verify_webhook(payload, signature, settings.stripe_webhook_secret)
    except stripe.SignatureError as exc:
        logger.warning("rejected a Stripe webhook: %s", exc)
        raise HTTPException(
            status_code=400, detail={"code": "bad_signature", "detail": "Signature check failed."}
        ) from exc

    outcome = await _handle(event)
    if outcome != "ignored":
        logger.info(
            "stripe event %s (%s): %s", event.get("id"), event.get("type"), outcome
        )
    return {"received": True, "outcome": outcome}
