"""Knowing that a request came from the web tier, and who it is acting for.

The browser never calls this API. The Next.js server does, and forwards the
visitor's session token. So from here every request appears to come from one
address — the web tier's — which is useless for throttling visitors and is the
reason this module exists.

The web tier proves itself with `X-Internal-Key`. A request that carries the
right key may then state the visitor's address in `X-Client-IP`; a request
that does not is taken at its socket address and nothing it says about itself
is believed.
"""

from __future__ import annotations

import hmac
import ipaddress
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request

from ..config import Settings, get_settings

__all__ = ["ClientAddress", "client_address", "from_web_tier", "require_web_tier"]


def from_web_tier(provided: str | None, settings: Settings) -> bool:
    """Constant-time comparison; an unset key matches nothing."""
    expected = settings.internal_api_key
    if not expected or not provided:
        return False
    return hmac.compare_digest(provided.encode(), expected.encode())


def _socket_address(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _valid_ip(candidate: str | None) -> str | None:
    if not candidate:
        return None
    try:
        return str(ipaddress.ip_address(candidate.strip()))
    except ValueError:
        return None


async def client_address(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    internal_key: Annotated[str | None, Header(alias="X-Internal-Key")] = None,
    forwarded_ip: Annotated[str | None, Header(alias="X-Client-IP")] = None,
) -> str:
    """The address to throttle on.

    The forwarded value is parsed as an IP rather than passed through: it ends
    up in a Redis key, and "whatever string the caller sent" is not a thing to
    build a key from even when the caller is trusted.
    """
    if from_web_tier(internal_key, settings):
        return _valid_ip(forwarded_ip) or _socket_address(request)
    return _socket_address(request)


ClientAddress = Annotated[str, Depends(client_address)]


async def require_web_tier(
    settings: Annotated[Settings, Depends(get_settings)],
    internal_key: Annotated[str | None, Header(alias="X-Internal-Key")] = None,
) -> None:
    """Gate for the routes that open a session without already having one.

    When no key is configured — development, tests — the gate is open: there
    is one machine and nothing to tell apart. Production refuses to start
    without a key, so "unset" never means "open to the internet".

    404 rather than 403, for the reason the admin routes use it: a 403 says
    there is something here and a key would open it.
    """
    if not settings.internal_api_key:
        return
    if not from_web_tier(internal_key, settings):
        raise HTTPException(status_code=404, detail={"code": "not_found", "detail": "Not found."})
