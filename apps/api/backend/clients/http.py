"""Shared HTTP client for the Polymarket APIs.

Retries are deliberately narrow: idempotent GETs, transient statuses only,
with jittered backoff. A worker that hammers a struggling upstream turns a
degraded API into an unreachable one.
"""

from __future__ import annotations

import asyncio
import logging
import random

import httpx

from ..config import Settings

logger = logging.getLogger(__name__)

_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


def _timeout(seconds: float | None) -> object:
    """Translate "no override" into httpx's sentinel rather than None.

    httpx reads `timeout=None` as *disable the timeout*, not as "fall back to
    the client default" — that is what USE_CLIENT_DEFAULT is for. Passing None
    through would have quietly removed the timeout from every call that did not
    set one, which is the opposite of what an optional override should mean.
    """
    return httpx.USE_CLIENT_DEFAULT if seconds is None else seconds


class UpstreamUnavailable(Exception):
    """The upstream did not produce a usable answer within the retry budget."""


def build_client(settings: Settings) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(settings.http_timeout_seconds, connect=5.0),
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=40),
        headers={"User-Agent": settings.http_user_agent},
        follow_redirects=True,
    )


async def get_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, object] | None = None,
    max_retries: int = 3,
    timeout: float | None = None,
) -> object:
    """GET and decode JSON, retrying transient failures.

    `timeout` overrides the client default for this one request. Callers on a
    clock want it: the shared 10s default is fine for hourly discovery and far
    too generous inside a job that runs every 60 seconds.

    Note what `max_retries=1` buys, because it is the point of the parameter:
    both sleep paths below are gated on there being a further attempt to make,
    so a single-attempt call cannot sleep at all — not on backoff, and not on a
    Retry-After the upstream asked for. It fails fast and lets the caller's
    next tick handle it.
    """
    last_error: Exception | None = None

    for attempt in range(max_retries):
        try:
            response = await client.get(url, params=params, timeout=_timeout(timeout))
        except httpx.HTTPError as exc:
            last_error = exc
        else:
            if response.status_code not in _RETRY_STATUSES:
                response.raise_for_status()
                return response.json()

            last_error = httpx.HTTPStatusError(
                f"{response.status_code} from {url}",
                request=response.request,
                response=response,
            )
            retry_after = _retry_after_seconds(response)
            if retry_after is not None and attempt < max_retries - 1:
                await asyncio.sleep(min(retry_after, 30.0))
                continue

        if attempt < max_retries - 1:
            backoff = (2**attempt) * 0.5
            await asyncio.sleep(backoff + random.uniform(0, 0.25))  # noqa: S311

    raise UpstreamUnavailable(f"GET {url} failed after {max_retries} attempts") from last_error


def _retry_after_seconds(response: httpx.Response) -> float | None:
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return None
