"""The one thing this service asks of Stripe, and the one thing it checks.

It asks for a **Checkout Session**: Stripe's own hosted payment page. Card
details are typed into Stripe's page and never touch this service, which is
the whole reason to do it this way.

It checks a **webhook signature**. A payment is believed when Stripe says so
in a message signed with a secret only the two of us hold — not when a browser
arrives back at a "thank you" address, which anyone can type.

No SDK. Both jobs are a form post and an HMAC, and a dependency that can do
four hundred other things to a payments account is a poor trade for that.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime

import httpx

from ..config import Settings

logger = logging.getLogger(__name__)

__all__ = [
    "CheckoutSession",
    "SignatureError",
    "StripeUnavailable",
    "create_checkout_session",
    "sign_payload",
    "verify_webhook",
]

SIGNATURE_TOLERANCE_SECONDS = 300
"""How old a signed message may be. Stripe's own default: long enough for a
slow delivery, short enough that a captured message cannot be replayed later."""

NO_CASH_VALUE = (
    "Play points for forecasting. They have no cash value and can never be "
    "cashed out, traded or redeemed for anything."
)


class StripeUnavailable(Exception):
    """Stripe did not give a usable answer. Nothing was charged."""


class SignatureError(Exception):
    """The message is not provably from Stripe, or is too old to trust."""


@dataclass(frozen=True, slots=True)
class CheckoutSession:
    id: str
    url: str


def _form(
    purchase_id: uuid.UUID,
    *,
    points: int,
    amount_cents: int,
    expires_at: datetime,
    settings: Settings,
) -> dict[str, str]:
    """Stripe's form encoding of a one-line, one-off, card-only checkout.

    Card only, on purpose: a card is confirmed while the buyer is still on the
    page, so "paid" and "the session completed" are the same moment. Methods
    that settle days later would mean crediting points on a promise.

    The purchase id travels three ways — on the session, in its metadata and
    in the payment's metadata — so that whichever object a later message is
    about, it can be traced to one row here.
    """
    site = settings.public_site_url
    reference = str(purchase_id)
    return {
        "mode": "payment",
        "payment_method_types[0]": "card",
        "line_items[0][quantity]": "1",
        "line_items[0][price_data][currency]": settings.shop_currency,
        "line_items[0][price_data][unit_amount]": str(amount_cents),
        "line_items[0][price_data][product_data][name]": f"{points:,} play points",
        "line_items[0][price_data][product_data][description]": NO_CASH_VALUE,
        "custom_text[submit][message]": (
            "Points have no cash value and can never be cashed out. "
            "Thank you for helping to keep the site running."
        ),
        "success_url": f"{site}/play?purchase=done",
        "cancel_url": f"{site}/play?purchase=cancelled",
        "client_reference_id": reference,
        "metadata[purchase_id]": reference,
        "payment_intent_data[metadata][purchase_id]": reference,
        "expires_at": str(int(expires_at.timestamp())),
    }


async def create_checkout_session(
    client: httpx.AsyncClient,
    settings: Settings,
    *,
    purchase_id: uuid.UUID,
    points: int,
    amount_cents: int,
    expires_at: datetime,
) -> CheckoutSession:
    """Open Stripe's payment page for one purchase.

    Not retried here. The idempotency key makes a retry safe on Stripe's side,
    but the buyer is waiting on a button; a second attempt is theirs to make,
    and it will be a new purchase with a new key.

    Nothing about the player is sent — no name, no email, no account id. The
    only identifier Stripe receives is the purchase's own random id.
    """
    try:
        response = await client.post(
            f"{settings.stripe_api_base}/v1/checkout/sessions",
            data=_form(
                purchase_id,
                points=points,
                amount_cents=amount_cents,
                expires_at=expires_at,
                settings=settings,
            ),
            headers={
                "Authorization": f"Bearer {settings.stripe_secret_key}",
                "Idempotency-Key": f"checkout-{purchase_id}",
            },
            timeout=15.0,
        )
    except httpx.HTTPError as exc:
        raise StripeUnavailable(f"could not reach Stripe: {type(exc).__name__}") from exc

    if response.status_code != 200:
        # Stripe's error body names the parameter at fault and never contains
        # the key. Logged for the operator; the buyer is told only that
        # payment is unavailable.
        logger.error(
            "stripe refused a checkout session: status=%s body=%s",
            response.status_code,
            response.text[:500],
        )
        raise StripeUnavailable(f"Stripe answered {response.status_code}")

    try:
        body = response.json()
        return CheckoutSession(id=str(body["id"]), url=str(body["url"]))
    except (ValueError, KeyError, TypeError) as exc:
        raise StripeUnavailable("Stripe's answer was not a checkout session") from exc


def sign_payload(payload: bytes, secret: str, timestamp: int) -> str:
    """The signature Stripe would put on `payload` at `timestamp`."""
    signed = f"{timestamp}.".encode() + payload
    return hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()


def verify_webhook(
    payload: bytes,
    signature_header: str | None,
    secret: str,
    *,
    tolerance: int = SIGNATURE_TOLERANCE_SECONDS,
    now: float | None = None,
) -> dict:
    """Return the event, having proved Stripe sent it recently.

    The header reads `t=<unix time>,v1=<hex>[,v1=<hex>…]`. More than one `v1`
    appears while a secret is being rolled, and a match on any is a match.
    The signature covers the timestamp as well as the body, so an old message
    cannot be re-dated; the timestamp is then checked so it cannot be replayed.

    The payload must be the bytes exactly as received. Re-serialised JSON is a
    different string and will never verify.
    """
    if not secret:
        raise SignatureError("no webhook secret is configured")
    if not signature_header:
        raise SignatureError("the request carries no signature")

    timestamp: int | None = None
    candidates: list[str] = []
    for part in signature_header.split(","):
        key, _, value = part.strip().partition("=")
        if key == "t":
            try:
                timestamp = int(value)
            except ValueError as exc:
                raise SignatureError("the signature's timestamp is not a number") from exc
        elif key == "v1":
            candidates.append(value)

    if timestamp is None or not candidates:
        raise SignatureError("the signature is incomplete")

    expected = sign_payload(payload, secret, timestamp)
    if not any(hmac.compare_digest(expected, candidate) for candidate in candidates):
        raise SignatureError("the signature does not match")

    if abs((now if now is not None else time.time()) - timestamp) > tolerance:
        raise SignatureError("the signature is too old")

    try:
        event = json.loads(payload)
    except ValueError as exc:
        raise SignatureError("the signed body is not JSON") from exc
    if not isinstance(event, dict):
        raise SignatureError("the signed body is not an event")
    return event
