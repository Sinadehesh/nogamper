"""Invoice issuance and the Telegram payments webhook.

The webhook is the only unauthenticated write path in the system. Everything
about it is shaped by that:

* **Fail closed.** No configured secret means every request is refused, not
  every request accepted.
* **Constant-time secret comparison.** A byte-at-a-time check on a shared
  secret is a byte-at-a-time oracle.
* **Answer 200 for anything already handled, 500 for anything worth
  retrying.** Telegram redelivers on non-2xx, which is exactly what we want
  after a transient failure and exactly what we do not want after an update we
  can never process.
"""

from __future__ import annotations

import hmac
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Request, Response, status

from .. import db
from ..config import Settings, get_settings
from ..schemas import (
    CoinPackage,
    ErrorResponse,
    InvoiceRequest,
    InvoiceResponse,
    Money,
    PackageList,
)
from ..security.dependencies import CurrentUser
from ..services import payment_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/payments", tags=["payments"])


@router.post(
    "/invoices",
    response_model=InvoiceResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
    summary="Create a Telegram Stars invoice",
)
async def create_invoice(
    user: CurrentUser,
    body: InvoiceRequest,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> InvoiceResponse:
    async with db.transaction() as conn:
        issued = await payment_service.issue_invoice(
            conn,
            request.app.state.http,
            settings,
            user_id=user["id"],
            package_code=body.package_code,
        )

    return InvoiceResponse(
        purchase_id=str(issued.purchase_id),
        invoice_link=issued.invoice_link,
        stars=issued.stars,
        coins=Money.of(issued.coins_minor),
    )


@router.get("/packages", response_model=PackageList, summary="Coin packages on sale")
async def list_packages(_: CurrentUser) -> PackageList:
    async with db.acquire() as conn:
        rows = await conn.fetch(
            "SELECT code, title, description, stars_price, coins, bonus_coins "
            "  FROM coin_packages WHERE is_active ORDER BY sort_order"
        )

    return PackageList(
        packages=[
            CoinPackage(
                code=row["code"],
                title=row["title"],
                description=row["description"],
                stars=row["stars_price"],
                coins=Money.of(row["coins"] + row["bonus_coins"]),
                bonus_coins=Money.of(row["bonus_coins"]),
            )
            for row in rows
        ]
    )


def _secret_ok(provided: str | None, expected: str) -> bool:
    if not expected or not provided:
        return False
    return hmac.compare_digest(provided, expected)


@router.post(
    "/webhook",
    include_in_schema=False,
    summary="Telegram payments webhook",
)
async def webhook(
    request: Request,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
    secret_token: Annotated[str | None, Header(alias="X-Telegram-Bot-Api-Secret-Token")] = None,
) -> dict[str, Any]:
    if not settings.telegram_webhook_secret:
        logger.error("payments webhook called but TELEGRAM_WEBHOOK_SECRET is not set")
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"ok": False, "code": "webhook_not_configured"}

    if not _secret_ok(secret_token, settings.telegram_webhook_secret):
        logger.warning("payments webhook rejected: bad or missing secret token")
        response.status_code = status.HTTP_403_FORBIDDEN
        return {"ok": False, "code": "bad_secret"}

    try:
        update = await request.json()
    except Exception:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return {"ok": False, "code": "bad_json"}

    if not isinstance(update, dict) or not isinstance(update.get("update_id"), int):
        response.status_code = status.HTTP_400_BAD_REQUEST
        return {"ok": False, "code": "not_an_update"}

    update_id: int = update["update_id"]
    kind = _classify(update)

    async with db.transaction() as conn:
        already = await conn.fetchval(
            """
            INSERT INTO telegram_updates (update_id, update_type, payload)
            VALUES ($1, $2, $3::jsonb)
            ON CONFLICT (update_id) DO UPDATE SET update_id = EXCLUDED.update_id
            RETURNING processed_at
            """,
            update_id,
            kind,
            _json(update),
        )

    if already is not None:
        return {"ok": True, "deduplicated": True}

    try:
        outcome = await _dispatch(request, settings, update, kind)
    except Exception:
        logger.exception("payments webhook failed on update %s (%s)", update_id, kind)
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return {"ok": False, "code": "processing_failed"}

    async with db.transaction() as conn:
        await conn.execute(
            "UPDATE telegram_updates SET processed_at = NOW(), error = $2 WHERE update_id = $1",
            update_id,
            outcome,
        )

    return {"ok": True}


def _classify(update: dict) -> str:
    if "pre_checkout_query" in update:
        return "pre_checkout_query"
    message = update.get("message")
    if isinstance(message, dict):
        if "successful_payment" in message:
            return "successful_payment"
        if "refunded_payment" in message:
            return "refunded_payment"
    return "ignored"


def _json(value: dict) -> str:
    import json

    return json.dumps(value, separators=(",", ":"))


async def _dispatch(request: Request, settings: Settings, update: dict, kind: str) -> str | None:
    if kind == "pre_checkout_query":
        return await _handle_pre_checkout(request, settings, update["pre_checkout_query"])
    if kind == "successful_payment":
        return await _handle_successful_payment(update["message"])
    if kind == "refunded_payment":
        return await _handle_refund(update["message"])

    logger.debug("ignoring update type on the payments webhook: %s", sorted(update))
    return "ignored"


async def _handle_pre_checkout(request: Request, settings: Settings, query: dict) -> str | None:
    from ..clients import telegram

    query_id = str(query.get("id", ""))
    payload = str(query.get("invoice_payload", ""))
    currency = str(query.get("currency", ""))
    total = query.get("total_amount")

    if not query_id:
        return "pre_checkout_without_id"

    async with db.acquire() as conn:
        ok, message = await payment_service.resolve_pre_checkout(
            conn,
            invoice_payload=payload,
            total_amount=total if isinstance(total, int) else -1,
            currency=currency,
        )

    try:
        await telegram.answer_pre_checkout_query(
            request.app.state.http,
            settings.telegram_bot_token,
            query_id=query_id,
            ok=ok,
            error_message=message,
            api_url=settings.telegram_api_url,
        )
    except telegram.TelegramApiError as exc:
        logger.error("answerPreCheckoutQuery failed: %s", exc.description)
        return "pre_checkout_answer_failed"

    if not ok:
        logger.info("pre-checkout declined: %s", message)
    return "pre_checkout_accepted" if ok else "pre_checkout_declined"


async def _handle_successful_payment(message: dict) -> str | None:
    payment = message["successful_payment"]

    async with db.transaction() as conn:
        outcome = await payment_service.settle_payment(
            conn,
            invoice_payload=str(payment.get("invoice_payload", "")),
            telegram_payment_charge_id=str(payment.get("telegram_payment_charge_id", "")),
            provider_payment_charge_id=payment.get("provider_payment_charge_id"),
            total_amount=payment.get("total_amount")
            if isinstance(payment.get("total_amount"), int)
            else -1,
            currency=str(payment.get("currency", "")),
        )

    if outcome.already_settled:
        return "already_settled"
    return outcome.reason or "settled"


async def _handle_refund(message: dict) -> str | None:
    refund = message["refunded_payment"]
    charge_id = str(refund.get("telegram_payment_charge_id", ""))

    async with db.transaction() as conn:
        outcome = await payment_service.settle_refund(conn, telegram_payment_charge_id=charge_id)

    if outcome.already_settled:
        return "already_refunded"
    return outcome.reason or "refunded"
