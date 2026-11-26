"""Settings-level guards against configuration that would open the API up.

Each of these is safe as a *default* and only dangerous as a production
misconfiguration, which is exactly what `require_secrets()` exists to refuse
at boot rather than let through to the first request.
"""

from __future__ import annotations

import pytest

from backend.config import Settings


def _settings(**overrides) -> Settings:
    values = {
        "jwt_secret": "y" * 32,
        "internal_api_key": "k" * 32,
        "environment": "production",
        **overrides,
    }
    return Settings(**values)


def test_a_wildcard_cors_origin_is_refused_in_production():
    """CORSMiddleware is mounted with allow_credentials=True. Starlette's
    answer to a wildcard origin under credentials is not the literal string
    "*" — it reflects whatever Origin the request sent, which lets any site
    make authenticated requests against a player's session cookie."""
    settings = _settings(cors_origins="*")
    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        settings.require_secrets()


def test_a_wildcard_among_several_origins_is_also_refused():
    settings = _settings(cors_origins="https://app.example.com,*")
    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        settings.require_secrets()


def test_an_explicit_origin_list_boots_fine_in_production():
    _settings(cors_origins="https://app.example.com").require_secrets()


def test_the_wildcard_guard_does_not_apply_outside_production():
    """Local dev defaults are never touched by this — only is_production
    triggers the refusal."""
    Settings(jwt_secret="y", cors_origins="*").require_secrets()


def test_a_short_signing_secret_is_refused_in_production():
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        _settings(jwt_secret="too-short").require_secrets()


def test_a_missing_signing_secret_is_refused_everywhere():
    """Not only in production: a session signed with the empty string is not
    a session, and there is no environment in which serving one is right."""
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        Settings(jwt_secret="").require_secrets()


def test_inconsistent_stake_limits_are_refused():
    """A minimum above the maximum is a game nobody can play, and it is
    better to hear that at boot than from the first player."""
    with pytest.raises(RuntimeError, match="Stake limits"):
        _settings(min_stake_minor=5_000, max_stake_minor=1_000).require_secrets()


def test_a_blank_timezone_means_utc():
    """A deployment form that prompts for the zone and is left empty sets the
    variable to the empty string, which is not a zone and must not become a
    500 on the first request that needs to know what day it is."""
    assert Settings(jwt_secret="y", economy_timezone="").economy_timezone == "UTC"
    assert Settings(jwt_secret="y", economy_timezone="   ").economy_timezone == "UTC"


def test_a_real_timezone_is_kept_as_typed():
    assert (
        Settings(jwt_secret="y", economy_timezone=" Europe/London ").economy_timezone
        == "Europe/London"
    )


@pytest.mark.parametrize("zone", ["Europe/Londn", "Mars/Olympus_Mons", "../etc/passwd"])
def test_an_unknown_timezone_fails_at_startup_and_names_itself(zone):
    """At startup rather than at first use, and with the offending value in
    the message, because the alternative is a stack trace from zoneinfo in a
    request handler that never mentions configuration."""
    with pytest.raises(ValueError, match="not a known IANA time zone"):
        Settings(jwt_secret="y", economy_timezone=zone)
