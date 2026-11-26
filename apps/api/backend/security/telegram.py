"""Cryptographic verification of Telegram Mini App `initData`.

This module is the only place in the system that decides whether a caller is
who they claim to be. Everything downstream — balances, stakes, payouts —
trusts the `TelegramUser` this returns, so it fails closed on anything it
does not fully understand.

The algorithm is Telegram's, from "Validating data received via the Mini App":

    secret_key       = HMAC_SHA256(key="WebAppData", msg=<bot_token>)
    data_check_string = "\\n".join(f"{k}={v}" for k, v in sorted(fields))
    expected          = HMAC_SHA256(key=secret_key, msg=data_check_string)

Only the `hash` field is removed before building the check string. A
`signature` field, when present, stays in — it belongs to Telegram's separate
Ed25519 third-party validation flow and is part of the signed payload here.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qsl

__all__ = [
    "InitDataError",
    "TelegramUser",
    "VerifiedInitData",
    "verify_init_data",
]

_FUTURE_SKEW = timedelta(seconds=30)


class InitDataError(Exception):
    """initData failed verification. `code` is a stable, client-safe reason."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass(frozen=True, slots=True)
class TelegramUser:
    id: int
    first_name: str
    last_name: str | None = None
    username: str | None = None
    language_code: str | None = None
    is_premium: bool = False
    photo_url: str | None = None


@dataclass(frozen=True, slots=True)
class VerifiedInitData:
    user: TelegramUser
    auth_date: datetime
    fingerprint: str
    """SHA-256 of the raw initData string.

    Stored as `auth_sessions.init_data_hash`. We hash rather than store the
    raw string so a database leak does not hand out replayable credentials.
    """
    query_id: str | None = None
    start_param: str | None = None
    chat_type: str | None = None


def _parse_fields(raw: str) -> list[tuple[str, str]]:
    if not raw or len(raw) > 8192:
        raise InitDataError("init_data_malformed", "initData is empty or implausibly long.")

    fields = parse_qsl(raw, keep_blank_values=True, strict_parsing=False)
    if not fields:
        raise InitDataError("init_data_malformed", "initData contained no fields.")

    seen: set[str] = set()
    for key, _ in fields:
        if key in seen:
            raise InitDataError(
                "init_data_duplicate_field", f"Duplicate field {key!r} in initData."
            )
        seen.add(key)

    return fields


def _expected_hash(fields: list[tuple[str, str]], bot_token: str) -> str:
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields, key=lambda kv: kv[0]))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    return hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()


def _parse_auth_date(value: str, ttl: timedelta, now: datetime) -> datetime:
    try:
        auth_date = datetime.fromtimestamp(int(value), tz=UTC)
    except (ValueError, OverflowError, OSError) as exc:
        raise InitDataError("init_data_malformed", "auth_date is not a unix timestamp.") from exc

    if auth_date - now > _FUTURE_SKEW:
        raise InitDataError("init_data_future", "auth_date is in the future.")
    if now - auth_date > ttl:
        raise InitDataError("init_data_expired", "initData is older than the accepted window.")
    return auth_date


def _parse_user(value: str) -> TelegramUser:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise InitDataError("init_data_malformed", "user field is not valid JSON.") from exc

    if not isinstance(payload, dict):
        raise InitDataError("init_data_malformed", "user field is not an object.")

    user_id = payload.get("id")
    if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
        raise InitDataError("init_data_malformed", "user.id is missing or not a positive integer.")

    first_name = payload.get("first_name")
    if not isinstance(first_name, str) or not first_name:
        raise InitDataError("init_data_malformed", "user.first_name is missing.")

    def opt_str(key: str) -> str | None:
        raw = payload.get(key)
        return raw if isinstance(raw, str) and raw else None

    return TelegramUser(
        id=user_id,
        first_name=first_name[:128],
        last_name=(opt_str("last_name") or None),
        username=(opt_str("username") or None),
        language_code=(opt_str("language_code") or None),
        is_premium=payload.get("is_premium") is True,
        photo_url=opt_str("photo_url"),
    )


def verify_init_data(
    raw: str,
    bot_token: str,
    *,
    ttl: timedelta,
    now: datetime | None = None,
) -> VerifiedInitData:
    """Verify an initData string, or raise `InitDataError`.

    Order matters: the signature is checked before any field is interpreted,
    so unauthenticated input never reaches the JSON parser.
    """
    if not bot_token:
        raise InitDataError("server_misconfigured", "Bot token is not configured.")

    now = now or datetime.now(UTC)
    fields = _parse_fields(raw)

    received_hash = next((v for k, v in fields if k == "hash"), None)
    if not received_hash:
        raise InitDataError("init_data_unsigned", "initData carries no hash.")

    signed_fields = [(k, v) for k, v in fields if k != "hash"]
    if not hmac.compare_digest(_expected_hash(signed_fields, bot_token), received_hash):
        raise InitDataError("init_data_bad_signature", "initData signature does not match.")

    values = dict(signed_fields)

    if "auth_date" not in values:
        raise InitDataError("init_data_malformed", "auth_date is missing.")
    auth_date = _parse_auth_date(values["auth_date"], ttl, now)

    if "user" not in values:
        raise InitDataError("init_data_no_user", "initData carries no user object.")
    user = _parse_user(values["user"])

    return VerifiedInitData(
        user=user,
        auth_date=auth_date,
        fingerprint=hashlib.sha256(raw.encode()).hexdigest(),
        query_id=values.get("query_id"),
        start_param=values.get("start_param"),
        chat_type=values.get("chat_type"),
    )
