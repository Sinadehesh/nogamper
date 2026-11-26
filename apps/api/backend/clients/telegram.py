"""Telegram Bot API client.

Only the methods this system needs: issuing Stars invoices, answering the
pre-checkout handshake, refunding a Stars payment, and sending a player the
operator's reply.

Two things this module is careful about:

**The bot token is in the URL.** It is the root of all authentication here —
`initData` HMACs derive from it — so every error path scrubs it. An exception
that quotes the request URL puts the token in logs, in Sentry, and in whatever
reads them.

**`answerPreCheckoutQuery` has a ten-second deadline.** Miss it and Telegram
cancels the payment on the player's behalf. Its timeout is deliberately short
and separate from the general one.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from .http import UpstreamUnavailable, post_json

logger = logging.getLogger(__name__)

__all__ = [
    "STARS_CURRENCY",
    "StarTransaction",
    "TelegramApiError",
    "answer_pre_checkout_query",
    "create_invoice_link",
    "get_star_transactions",
    "refund_star_payment",
    "send_message",
]

MAX_TRANSACTIONS_PER_PAGE = 100

STARS_CURRENCY = "XTR"
DEFAULT_API_URL = "https://api.telegram.org"

PRE_CHECKOUT_TIMEOUT_SECONDS = 5.0


class TelegramApiError(Exception):
    """Telegram answered, and said no."""

    def __init__(self, method: str, error_code: int | None, description: str) -> None:
        super().__init__(f"{method} failed: {description}")
        self.method = method
        self.error_code = error_code
        self.description = description


@dataclass(frozen=True, slots=True)
class LabeledPrice:
    label: str
    amount: int
    """For XTR this is a whole number of Stars.

    Note the difference from fiat, where `amount` is in the currency's minor
    units — 1000 there means 10.00, but 1000 here means a thousand Stars.
    """


async def _call(
    client: httpx.AsyncClient,
    bot_token: str,
    method: str,
    payload: dict[str, object],
    *,
    api_url: str = DEFAULT_API_URL,
    timeout: float | None = None,
    max_retries: int = 3,
) -> object:
    url = f"{api_url.rstrip('/')}/bot{bot_token}/{method}"

    try:
        body = await post_json(
            client,
            url,
            payload,
            max_retries=max_retries,
            timeout=timeout,
            scrub=bot_token,
        )
    except UpstreamUnavailable as exc:
        raise TelegramApiError(method, None, str(exc)) from exc

    if not isinstance(body, dict):
        raise TelegramApiError(method, None, "response was not a JSON object")

    if not body.get("ok"):
        raise TelegramApiError(
            method,
            body.get("error_code") if isinstance(body.get("error_code"), int) else None,
            str(body.get("description", "no description")),
        )

    return body.get("result")


class TelegramCannotReach(TelegramApiError):
    """Telegram will not deliver to this chat, and retrying will not help.

    A bot may not open a conversation a person has not opened first. A player
    who launched the Mini App from a link without ever pressing Start, or who
    later blocked the bot, is unreachable — 403, permanently, until they act.

    Separated from TelegramApiError because the two need different handling:
    this is a fact about the recipient to report to the operator, not a
    failure to retry or an outage to alarm about.
    """


async def send_message(
    client: httpx.AsyncClient,
    bot_token: str,
    *,
    chat_id: int,
    text: str,
    api_url: str = DEFAULT_API_URL,
    timeout: float | None = None,
) -> None:
    """Send a player a message as the bot.

    The point of routing this through the bot is that the operator answering a
    support message must not have to do it from their own account. Telegram
    shows the player the bot; the operator's id, username and photo never
    travel with the reply.

    `parse_mode` is deliberately not set. The text is typed by the operator
    into a web form and forwarded to a player: sending it as Markdown or HTML
    would make an unbalanced asterisk a 400 and an accidental tag a rendering
    surprise. Plain text says exactly what was typed.
    """
    try:
        await _call(
            client,
            bot_token,
            "sendMessage",
            {"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            api_url=api_url,
            timeout=timeout,
        )
    except TelegramApiError as exc:
        if exc.error_code in (400, 403):
            raise TelegramCannotReach(exc.method, exc.error_code, exc.description) from exc
        raise


async def create_invoice_link(
    client: httpx.AsyncClient,
    bot_token: str,
    *,
    title: str,
    description: str,
    payload: str,
    prices: list[LabeledPrice],
    api_url: str = DEFAULT_API_URL,
) -> str:
    """Create a Stars invoice link.

    `provider_token` is deliberately empty: that is what marks an invoice as
    payable in Telegram Stars rather than through a fiat payment provider.
    """
    result = await _call(
        client,
        bot_token,
        "createInvoiceLink",
        {
            "title": title,
            "description": description,
            "payload": payload,
            "provider_token": "",
            "currency": STARS_CURRENCY,
            "prices": [{"label": p.label, "amount": p.amount} for p in prices],
        },
        api_url=api_url,
    )

    if not isinstance(result, str) or not result:
        raise TelegramApiError("createInvoiceLink", None, "no invoice link returned")
    return result


async def answer_pre_checkout_query(
    client: httpx.AsyncClient,
    bot_token: str,
    *,
    query_id: str,
    ok: bool,
    error_message: str | None = None,
    api_url: str = DEFAULT_API_URL,
) -> None:
    """Answer the pre-checkout handshake. `error_message` is shown to the player."""
    payload: dict[str, object] = {"pre_checkout_query_id": query_id, "ok": ok}
    if not ok:
        payload["error_message"] = error_message or "This purchase is no longer available."

    await _call(
        client,
        bot_token,
        "answerPreCheckoutQuery",
        payload,
        api_url=api_url,
        timeout=PRE_CHECKOUT_TIMEOUT_SECONDS,
        max_retries=1,
    )


async def refund_star_payment(
    client: httpx.AsyncClient,
    bot_token: str,
    *,
    telegram_user_id: int,
    telegram_payment_charge_id: str,
    api_url: str = DEFAULT_API_URL,
) -> None:
    await _call(
        client,
        bot_token,
        "refundStarPayment",
        {
            "user_id": telegram_user_id,
            "telegram_payment_charge_id": telegram_payment_charge_id,
        },
        api_url=api_url,
    )


@dataclass(frozen=True, slots=True)
class StarTransaction:
    """One row of `getStarTransactions`, reduced to what reconciliation needs.

    `id` is the important field: the Bot API documents it as coinciding with
    `SuccessfulPayment.telegram_payment_charge_id` for an incoming payment.
    That is what lets a reconciled settlement use exactly the same ledger
    idempotency key the webhook would have used, so the two paths cannot
    double-credit each other.
    """

    charge_id: str
    stars: int
    at: datetime
    invoice_payload: str | None
    is_incoming: bool


def _transaction_payload(source: dict) -> str | None:
    """Pull our nonce out of a transaction partner.

    The documented location is `source.invoice_payload` on a
    `TransactionPartnerUser`. The fallbacks exist because this code cannot be
    exercised against the live API from here, and the cost of missing a
    payload is a player who paid and was never credited. They are checked
    after the documented path, never instead of it.
    """
    for key in ("invoice_payload", "payload"):
        value = source.get(key)
        if isinstance(value, str) and value:
            return value

    receipt = source.get("receipt")
    if isinstance(receipt, dict):
        for key in ("invoice_payload", "payload"):
            value = receipt.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def parse_star_transaction(raw: object) -> StarTransaction | None:
    if not isinstance(raw, dict):
        return None

    charge_id = raw.get("id")
    stars = raw.get("amount")
    if not isinstance(charge_id, str) or not charge_id or not isinstance(stars, int):
        return None

    try:
        at = datetime.fromtimestamp(int(raw.get("date", 0)), tz=UTC)
    except (ValueError, OverflowError, OSError):
        return None

    source = raw.get("source")
    is_incoming = isinstance(source, dict) and "receiver" not in raw
    payload = _transaction_payload(source) if isinstance(source, dict) else None

    return StarTransaction(
        charge_id=charge_id,
        stars=stars,
        at=at,
        invoice_payload=payload,
        is_incoming=is_incoming,
    )


async def get_star_transactions(
    client: httpx.AsyncClient,
    bot_token: str,
    *,
    offset: int = 0,
    limit: int = MAX_TRANSACTIONS_PER_PAGE,
    api_url: str = DEFAULT_API_URL,
) -> list[StarTransaction]:
    """One page of the bot's Stars ledger, newest first."""
    result = await _call(
        client,
        bot_token,
        "getStarTransactions",
        {"offset": offset, "limit": min(limit, MAX_TRANSACTIONS_PER_PAGE)},
        api_url=api_url,
    )

    if not isinstance(result, dict):
        raise TelegramApiError("getStarTransactions", None, "result was not an object")

    raw_transactions = result.get("transactions")
    if not isinstance(raw_transactions, list):
        raise TelegramApiError("getStarTransactions", None, "no transactions array")

    parsed = [parse_star_transaction(row) for row in raw_transactions]
    return [t for t in parsed if t is not None]
