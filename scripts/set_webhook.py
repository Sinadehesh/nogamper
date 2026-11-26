#!/usr/bin/env python3
"""Register the Telegram payments webhook, and prove it registered.

Run it after every deploy that changes the API's public URL, and after any
rotation of TELEGRAM_BOT_TOKEN or TELEGRAM_WEBHOOK_SECRET — the token is part
of the Bot API URL, so rotating it silently unregisters the webhook.

    TELEGRAM_BOT_TOKEN=123456:ABC... \
    TELEGRAM_WEBHOOK_SECRET=... \
    PUBLIC_API_URL=https://api.example.com \
    python scripts/set_webhook.py

Standard library only, so it runs in the app image, in CI, or on a laptop
with nothing installed. Exit codes: 0 registered and verified, 1 bad
configuration, 2 Telegram refused, 3 registered but verification disagreed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from urllib.parse import urlparse, urlunparse

ALLOWED_UPDATES = ["pre_checkout_query", "message"]

WEBHOOK_PATH = "/v1/payments/webhook"

ALLOWED_PORTS = {443, 80, 88, 8443}

SECRET_CHARSET = re.compile(r"^[A-Za-z0-9_-]+$")

SECRET_MIN_LENGTH = 16

DEFAULT_API_URL = "https://api.telegram.org"
TIMEOUT_SECONDS = 20


class ConfigError(Exception):
    """Something in the environment is wrong. Nothing was sent."""


class UpstreamError(Exception):
    """Telegram could not be reached, or refused the call."""


def redact(value: str) -> str:
    """Enough to recognise a value in a log, never enough to use it."""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}…{value[-2:]} ({len(value)} chars)"


def env(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return None


def require(*names: str) -> str:
    value = env(*names)
    if value is None:
        joined = " or ".join(names)
        raise ConfigError(f"{joined} is not set")
    return value


def resolve_webhook_url(raw: str) -> str:
    """Accept either the API origin or the full webhook URL.

    Passing the origin is the common case and the easy thing to get subtly
    wrong, so appending the path is handled here rather than in six different
    deploy notes.
    """
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")

    if parsed.scheme != "https":
        raise ConfigError(f"webhook URL must be https, got {parsed.scheme or 'no scheme'}://")
    if not parsed.hostname:
        raise ConfigError(f"could not read a hostname from {raw!r}")

    port = parsed.port
    if port is not None and port not in ALLOWED_PORTS:
        allowed = ", ".join(str(p) for p in sorted(ALLOWED_PORTS))
        raise ConfigError(f"Telegram only delivers to ports {allowed}; got {port}")

    path = parsed.path.rstrip("/")
    if not path.endswith(WEBHOOK_PATH):
        path = f"{path}{WEBHOOK_PATH}"

    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def validate_secret(secret: str) -> None:
    if len(secret) < SECRET_MIN_LENGTH:
        raise ConfigError(
            f"webhook secret is {len(secret)} characters; the API refuses anything "
            f"under {SECRET_MIN_LENGTH} in production"
        )
    if len(secret) > 256:
        raise ConfigError(f"webhook secret is {len(secret)} characters; Telegram's limit is 256")
    if not SECRET_CHARSET.match(secret):
        raise ConfigError(
            "webhook secret may only contain A-Z a-z 0-9 _ - — Telegram rejects anything "
            'else. Generate one with: python -c "import secrets; '
            'print(secrets.token_urlsafe(32))"'
        )


def call(api_url: str, token: str, method: str, payload: dict | None = None) -> dict:
    """POST to the Bot API and return `result`, raising on anything else."""
    url = f"{api_url.rstrip('/')}/bot{token}/{method}"
    body = json.dumps(payload or {}).encode()
    request = urllib.request.Request(  # noqa: S310 - url is built from a validated https base
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
            document = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        try:
            parsed = json.loads(detail)
            detail = parsed.get("description", detail)
        except ValueError:
            pass
        raise UpstreamError(f"{method} failed: HTTP {exc.code} — {detail}") from exc
    except urllib.error.URLError as exc:
        raise UpstreamError(f"{method} could not reach {api_url}: {exc.reason}") from exc

    if not document.get("ok"):
        raise UpstreamError(f"{method} refused: {document.get('description', document)}")

    return document.get("result", {})


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Register the Telegram payments webhook and verify it took effect.",
    )
    parser.add_argument(
        "--url",
        help="API origin or full webhook URL. Overrides PUBLIC_API_URL / WEBHOOK_URL.",
    )
    parser.add_argument(
        "--drop-pending",
        action="store_true",
        help="Discard updates queued while the webhook was unset. Off by default — "
        "a queued successful_payment is a player who paid.",
    )
    parser.add_argument(
        "--max-connections",
        type=int,
        default=40,
        help="Concurrent deliveries Telegram may open (default: 40).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print the request without sending it.",
    )
    args = parser.parse_args()

    try:
        token = require("TELEGRAM_BOT_TOKEN")
        secret = require("TELEGRAM_WEBHOOK_SECRET", "WEBHOOK_SECRET")
        validate_secret(secret)
        target = args.url or require("PUBLIC_API_URL", "WEBHOOK_URL", "API_BASE_URL")
        webhook_url = resolve_webhook_url(target)
    except ConfigError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 1

    api_url = env("TELEGRAM_API_URL") or DEFAULT_API_URL

    payload = {
        "url": webhook_url,
        "secret_token": secret,
        "allowed_updates": ALLOWED_UPDATES,
        "drop_pending_updates": args.drop_pending,
        "max_connections": args.max_connections,
    }

    print(f"  bot token   {redact(token)}")
    print(f"  secret      {redact(secret)}")
    print(f"  webhook     {webhook_url}")
    print(f"  updates     {', '.join(ALLOWED_UPDATES)}")
    if api_url != DEFAULT_API_URL:
        print(f"  bot api     {api_url}")

    if args.dry_run:
        print("\n  dry run — nothing sent")
        return 0

    try:
        call(api_url, token, "setWebhook", payload)
        print("\n✓ setWebhook accepted")

        info = call(api_url, token, "getWebhookInfo")
    except UpstreamError as exc:
        print(f"\n✗ {exc}", file=sys.stderr)
        return 2
    registered = info.get("url", "")
    granted = info.get("allowed_updates") or []
    pending = info.get("pending_update_count", 0)
    last_error = info.get("last_error_message")

    print(f"  url                    {registered or '(none)'}")
    print(f"  allowed_updates        {', '.join(granted) or '(all)'}")
    print(f"  pending_update_count   {pending}")
    if last_error:
        print(f"  last_error_message     {last_error}")
    if info.get("has_custom_certificate"):
        print("  custom certificate     yes")

    problems = []
    if registered != webhook_url:
        problems.append(f"Telegram reports {registered!r}, not {webhook_url!r}")
    if set(granted) != set(ALLOWED_UPDATES):
        problems.append(
            f"allowed_updates is {granted!r}; payment confirmations need {ALLOWED_UPDATES!r}"
        )

    if problems:
        print("\n✗ registered, but verification disagreed:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 3

    if last_error:
        print("\n✓ webhook registered — but note the last_error_message above")
    else:
        print("\n✓ webhook registered and verified")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
