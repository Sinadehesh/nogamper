"""Password storage and the rules for choosing one.

Argon2id, through argon2-cffi. The encoded hash carries its own salt and cost
parameters, so raising the cost later needs no migration: an old hash still
verifies, `needs_rehash` notices, and the account is upgraded at its next
successful sign-in — the only moment the plaintext is available.

## Hashing is CPU, and this is an asyncio service

A hash is tens of milliseconds of pure computation. Run inline it would stall
every other request on the event loop for exactly that long, so both
operations run on a worker thread (the C core releases the GIL), behind a
semaphore: each hash in flight holds its memory cost for the duration, and an
unbounded burst of sign-ins is a memory spike with a login form attached.

## Unknown addresses cost the same as wrong passwords

`verify_async(None, ...)` hashes against a throwaway digest instead of
returning early. Otherwise "no such account" answers measurably faster than
"wrong password", and the sign-in form becomes a way to ask whether an
address is registered.
"""

from __future__ import annotations

import asyncio
import secrets
from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from ..config import Settings

__all__ = [
    "PasswordPolicyError",
    "check_policy",
    "hash_async",
    "needs_rehash",
    "verify_async",
]


class PasswordPolicyError(Exception):
    """The chosen password is not acceptable. `code` is stable and client-safe."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


_OBVIOUS = frozenset(
    {
        "1234567890",
        "12345678910",
        "0123456789",
        "0987654321",
        "1q2w3e4r5t",
        "qwertyuiop",
        "qwerty12345",
        "password12",
        "password123",
        "password1234",
        "passwordpassword",
        "iloveyou123",
        "letmein123",
        "welcome123",
        "abcdefghij",
        "abc1234567",
        "1111111111",
        "0000000000",
    }
)
"""A short list, not a breach corpus.

Length does most of the work; this only catches the handful of ten-character
strings that are common *because* they satisfy a length rule. A real
compromised-password check is a network call to somebody else's service, and
that is a decision for the operator rather than a default.
"""


def check_policy(password: str, *, email: str | None, settings: Settings) -> None:
    """Raise `PasswordPolicyError` unless this password is acceptable.

    Length over composition, following NIST SP 800-63B: required symbols and
    capitals produce `Password1!`, and a long phrase is both stronger and
    easier to remember. The upper bound is not about strength — it stops a
    megabyte "password" from being hashed at somebody else's expense.
    """
    if len(password) < settings.password_min_length:
        raise PasswordPolicyError(
            "password_too_short",
            f"Use at least {settings.password_min_length} characters.",
        )
    if len(password) > settings.password_max_length:
        raise PasswordPolicyError(
            "password_too_long",
            f"Use at most {settings.password_max_length} characters.",
        )

    lowered = password.lower()
    if len(set(lowered)) < 4 or lowered in _OBVIOUS:
        raise PasswordPolicyError(
            "password_too_common", "That password is too easy to guess. Try a longer phrase."
        )
    if email:
        local = email.split("@", 1)[0].lower()
        if lowered == email.lower() or (len(local) >= 4 and lowered == local):
            raise PasswordPolicyError(
                "password_too_common", "Your password cannot be your email address."
            )


@lru_cache(maxsize=4)
def _hasher(time_cost: int, memory_kib: int, parallelism: int) -> PasswordHasher:
    return PasswordHasher(time_cost=time_cost, memory_cost=memory_kib, parallelism=parallelism)


def _hasher_for(settings: Settings) -> PasswordHasher:
    return _hasher(
        settings.password_hash_time_cost,
        settings.password_hash_memory_kib,
        settings.password_hash_parallelism,
    )


@lru_cache(maxsize=4)
def _decoy(time_cost: int, memory_kib: int, parallelism: int) -> str:
    """A real hash of a value nobody knows, at the current cost."""
    return _hasher(time_cost, memory_kib, parallelism).hash(secrets.token_urlsafe(32))


_gate: asyncio.Semaphore | None = None
_gate_size = 0


def _semaphore(settings: Settings) -> asyncio.Semaphore:
    """One gate per process, rebuilt if the configured width changes.

    Created lazily because a Semaphore binds to the running loop, and at
    import time there is none.
    """
    global _gate, _gate_size
    width = max(1, settings.password_hash_concurrency)
    if _gate is None or _gate_size != width:
        _gate = asyncio.Semaphore(width)
        _gate_size = width
    return _gate


async def hash_async(password: str, settings: Settings) -> str:
    hasher = _hasher_for(settings)
    async with _semaphore(settings):
        return await asyncio.to_thread(hasher.hash, password)


def _verify(hasher: PasswordHasher, encoded: str, password: str) -> bool:
    try:
        return hasher.verify(encoded, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


async def verify_async(encoded: str | None, password: str, settings: Settings) -> bool:
    """True only when `password` matches `encoded`.

    With `encoded=None` — no such account — the work is done anyway against a
    decoy and the answer is always False.
    """
    hasher = _hasher_for(settings)
    target = encoded or _decoy(
        settings.password_hash_time_cost,
        settings.password_hash_memory_kib,
        settings.password_hash_parallelism,
    )
    async with _semaphore(settings):
        matched = await asyncio.to_thread(_verify, hasher, target, password)
    return matched and encoded is not None


def needs_rehash(encoded: str, settings: Settings) -> bool:
    try:
        return _hasher_for(settings).check_needs_rehash(encoded)
    except InvalidHashError:
        return True
