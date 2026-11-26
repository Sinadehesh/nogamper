"""Fixed-window rate limiting, in Redis.

Three routes can be called by somebody who has not signed in: register, sign
in, play as a guest. They are the ones a script would be pointed at — to guess
a password, or to fill the users table — so they are the ones counted.

## One atomic script, not INCR then EXPIRE

The obvious two-step version has a gap: a process that dies between the
increment and the expiry leaves a counter with no lifetime, and that key then
counts upward forever. For a sign-in limit that is a permanent lockout of one
email address, caused by a deploy. The script does both under Redis's own
atomicity and, belt and braces, repairs any key it finds without an expiry.

## Failing open

If Redis is unreachable the request is allowed and the failure is logged.
Redis here is a cache and a counter, never an authority — the readiness probe
already treats it as degradable — and a limiter that turns a cache outage into
"nobody can sign in" has made the site less available than having no limiter.
The password hash is still the thing standing in front of an account.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

from ..cache import prices as redis_owner

logger = logging.getLogger(__name__)

__all__ = ["RateLimited", "RateWindow", "clear", "hit", "key_for"]

_HIT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('TTL', KEYS[1])
if ttl < 0 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
    ttl = tonumber(ARGV[1])
end
return {count, ttl}
"""


class RateLimited(Exception):
    """Too many attempts. Carries how long until the window reopens."""

    def __init__(self, scope: str, retry_after: int) -> None:
        super().__init__(f"rate limited: {scope}")
        self.scope = scope
        self.retry_after = max(1, retry_after)


@dataclass(frozen=True, slots=True)
class RateWindow:
    scope: str
    limit: int
    window_seconds: int


def key_for(scope: str, subject: str) -> str:
    """The Redis key for one subject in one scope.

    The subject is hashed. It is an email address or a visitor's IP, and a
    cache is the last place either should be legible to whoever can run KEYS.
    """
    digest = hashlib.sha256(subject.encode()).hexdigest()[:32]
    return f"rl:{scope}:{digest}"


async def hit(window: RateWindow, subject: str) -> None:
    """Count one attempt, raising `RateLimited` if it is one too many."""
    if window.limit <= 0:
        return

    try:
        count, ttl = await redis_owner.get_client().eval(
            _HIT, 1, key_for(window.scope, subject), window.window_seconds
        )
    except Exception:  # noqa: BLE001 - any Redis failure means the same thing here
        logger.warning("rate limiter unavailable for %s; allowing the request", window.scope)
        return

    if int(count) > window.limit:
        raise RateLimited(window.scope, int(ttl))


async def clear(window: RateWindow, subject: str) -> None:
    """Forget a subject's attempts — called when a sign-in succeeds."""
    try:
        await redis_owner.get_client().delete(key_for(window.scope, subject))
    except Exception:  # noqa: BLE001
        logger.warning("rate limiter unavailable for %s; could not clear", window.scope)
