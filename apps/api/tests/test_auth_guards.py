"""The throttle and the web-tier gate on the routes that open a session.

Three routes answer a caller who has not signed in. These tests are about what
stops them being used as a password-guessing service or a way to fill the
users table.
"""

from __future__ import annotations

import pytest
from conftest import TEST_PASSWORD

from backend.cache import prices as redis_owner
from backend.config import Settings, get_settings
from backend.security import passwords, ratelimit
from backend.security.ratelimit import RateLimited, RateWindow

ACCOUNT = {"email": "ada@example.test", "password": TEST_PASSWORD, "display_name": "Ada"}
KEY = "k" * 40


async def login(client, password=TEST_PASSWORD, email=ACCOUNT["email"], **kwargs):
    return await client.post(
        "/v1/auth/login", json={"email": email, "password": password}, **kwargs
    )


# ----- the limiter itself ---------------------------------------------------


async def test_the_window_allows_its_limit_and_refuses_the_next(resources):
    window = RateWindow("unit", limit=3, window_seconds=60)

    for _ in range(3):
        await ratelimit.hit(window, "somebody")

    with pytest.raises(RateLimited) as refused:
        await ratelimit.hit(window, "somebody")
    assert 1 <= refused.value.retry_after <= 60


async def test_subjects_and_scopes_are_counted_apart(resources):
    window = RateWindow("unit", limit=1, window_seconds=60)
    await ratelimit.hit(window, "alice")

    await ratelimit.hit(window, "bob")
    await ratelimit.hit(RateWindow("other", limit=1, window_seconds=60), "alice")


async def test_every_counter_has_a_lifetime(resources):
    """A counter with no expiry counts upward forever, which for a sign-in
    limit is a permanent lockout. The script sets one on the first hit."""
    window = RateWindow("unit", limit=5, window_seconds=120)
    await ratelimit.hit(window, "somebody")

    ttl = await redis_owner.get_client().ttl(ratelimit.key_for("unit", "somebody"))
    assert 0 < ttl <= 120


async def test_a_counter_that_lost_its_expiry_is_repaired(resources):
    """The gap a two-step INCR-then-EXPIRE leaves behind, simulated."""
    key = ratelimit.key_for("unit", "somebody")
    await redis_owner.get_client().set(key, 2)
    assert await redis_owner.get_client().ttl(key) == -1

    await ratelimit.hit(RateWindow("unit", limit=10, window_seconds=90), "somebody")

    assert 0 < await redis_owner.get_client().ttl(key) <= 90


async def test_the_key_does_not_carry_the_subject_in_the_clear(resources):
    """It is an email address or an IP; a cache is no place to leave either
    legible."""
    key = ratelimit.key_for("login-email", "ada@example.test")
    assert "ada" not in key
    assert "example" not in key


async def test_a_redis_outage_allows_the_request_rather_than_locking_everyone_out(
    resources, monkeypatch
):
    class Down:
        async def eval(self, *args, **kwargs):
            raise ConnectionError("redis is down")

        async def delete(self, *args, **kwargs):
            raise ConnectionError("redis is down")

    monkeypatch.setattr(redis_owner, "get_client", lambda: Down())

    window = RateWindow("unit", limit=1, window_seconds=60)
    await ratelimit.hit(window, "somebody")
    await ratelimit.hit(window, "somebody")
    await ratelimit.clear(window, "somebody")


async def test_a_limit_of_zero_switches_a_window_off(resources):
    window = RateWindow("unit", limit=0, window_seconds=60)
    for _ in range(5):
        await ratelimit.hit(window, "somebody")


# ----- on the routes --------------------------------------------------------


async def test_repeated_wrong_passwords_lock_the_address_for_a_while(app_client):
    await app_client.post("/v1/auth/register", json=ACCOUNT)
    get_settings().login_rate_max = 3

    for _ in range(3):
        assert (await login(app_client, password="a wrong guess")).status_code == 401

    locked = await login(app_client, password="a wrong guess")
    assert locked.status_code == 429
    assert locked.json()["code"] == "rate_limited"
    assert locked.json()["retry_after"] >= 1
    assert int(locked.headers["Retry-After"]) == locked.json()["retry_after"]

    # The right password does not get through either: otherwise the lock would
    # only slow an attacker down by one extra request per guess.
    assert (await login(app_client)).status_code == 429


async def test_a_successful_sign_in_clears_the_count(app_client):
    await app_client.post("/v1/auth/register", json=ACCOUNT)
    get_settings().login_rate_max = 3

    for _ in range(2):
        await login(app_client, password="a wrong guess")
    assert (await login(app_client)).status_code == 200

    # A fresh allowance, not the one remaining attempt.
    for _ in range(3):
        assert (await login(app_client, password="a wrong guess")).status_code == 401


async def test_guessing_at_one_address_does_not_lock_another(app_client):
    await app_client.post("/v1/auth/register", json=ACCOUNT)
    await app_client.post(
        "/v1/auth/register",
        json={**ACCOUNT, "email": "grace@example.test", "display_name": "Grace"},
    )
    get_settings().login_rate_max = 2

    for _ in range(3):
        await login(app_client, password="a wrong guess")

    assert (await login(app_client, email="grace@example.test")).status_code == 200


async def test_one_visitor_cannot_open_accounts_without_limit(app_client):
    get_settings().signup_ip_rate_max = 3

    for _ in range(3):
        assert (await app_client.post("/v1/auth/guest")).status_code == 201

    assert (await app_client.post("/v1/auth/guest")).status_code == 429
    # Guests and registrations draw on the same allowance: they are the same
    # act, opening an account, and separate buckets would double it.
    assert (await app_client.post("/v1/auth/register", json=ACCOUNT)).status_code == 429


async def test_a_form_that_fails_validation_does_not_spend_an_attempt(app_client):
    get_settings().signup_ip_rate_max = 1

    for _ in range(4):
        refused = await app_client.post("/v1/auth/register", json={**ACCOUNT, "password": "short"})
        assert refused.status_code == 400

    assert (await app_client.post("/v1/auth/register", json=ACCOUNT)).status_code == 201


# ----- the web tier ---------------------------------------------------------


async def test_with_a_key_configured_the_session_routes_answer_only_the_web_tier(app_client):
    get_settings().internal_api_key = KEY

    for path, body in (
        ("/v1/auth/guest", None),
        ("/v1/auth/register", ACCOUNT),
        ("/v1/auth/login", {"email": ACCOUNT["email"], "password": TEST_PASSWORD}),
    ):
        bare = await app_client.post(path, json=body)
        assert bare.status_code == 404, path

        wrong = await app_client.post(path, json=body, headers={"X-Internal-Key": "x" * 40})
        assert wrong.status_code == 404, path

    assert (
        await app_client.post("/v1/auth/guest", headers={"X-Internal-Key": KEY})
    ).status_code == 201


async def test_a_signed_in_player_does_not_need_the_key(app_client):
    """Only the routes that open a session without one are gated. Everything
    else is already behind the session itself."""
    get_settings().internal_api_key = KEY
    guest = await app_client.post("/v1/auth/guest", headers={"X-Internal-Key": KEY})
    headers = {"Authorization": f"Bearer {guest.json()['access_token']}"}

    assert (await app_client.get("/v1/me", headers=headers)).status_code == 200
    assert (await app_client.get("/health")).status_code == 200


async def test_the_web_tier_can_say_which_visitor_it_is_acting_for(app_client):
    """Otherwise every visitor shares one bucket — the web tier's address."""
    settings = get_settings()
    settings.internal_api_key = KEY
    settings.signup_ip_rate_max = 1

    def as_visitor(ip):
        return {"X-Internal-Key": KEY, "X-Client-IP": ip}

    assert (
        await app_client.post("/v1/auth/guest", headers=as_visitor("203.0.113.5"))
    ).status_code == 201
    assert (
        await app_client.post("/v1/auth/guest", headers=as_visitor("203.0.113.5"))
    ).status_code == 429
    assert (
        await app_client.post("/v1/auth/guest", headers=as_visitor("203.0.113.9"))
    ).status_code == 201


async def test_a_caller_without_the_key_cannot_choose_its_own_address(app_client):
    """`X-Client-IP` from anyone else is a field they filled in themselves."""
    get_settings().signup_ip_rate_max = 1

    assert (
        await app_client.post("/v1/auth/guest", headers={"X-Client-IP": "198.51.100.1"})
    ).status_code == 201
    # A different claimed address, same real caller: still the same bucket.
    assert (
        await app_client.post("/v1/auth/guest", headers={"X-Client-IP": "198.51.100.2"})
    ).status_code == 429


async def test_a_forwarded_address_that_is_not_an_address_is_ignored(app_client):
    settings = get_settings()
    settings.internal_api_key = KEY
    settings.signup_ip_rate_max = 1

    junk = {"X-Internal-Key": KEY, "X-Client-IP": "rl:*; DROP"}
    assert (await app_client.post("/v1/auth/guest", headers=junk)).status_code == 201
    # Fell back to the socket address, so a second junk value shares its bucket.
    junk["X-Client-IP"] = "something else entirely"
    assert (await app_client.post("/v1/auth/guest", headers=junk)).status_code == 429


# ----- password rules and hashing -------------------------------------------


def _settings(**overrides) -> Settings:
    return Settings(jwt_secret="x" * 40, **overrides)


def test_length_is_the_rule_and_composition_is_not():
    settings = _settings()
    passwords.check_policy("all lower case and no digits", email=None, settings=settings)

    with pytest.raises(passwords.PasswordPolicyError) as short:
        passwords.check_policy("Sh0rt!", email=None, settings=settings)
    assert short.value.code == "password_too_short"


async def test_verifying_against_no_account_does_the_work_and_says_no(resources):
    """An unknown address must cost a hash, like a wrong password does."""
    assert await passwords.verify_async(None, "anything at all", resources) is False


async def test_a_corrupt_stored_hash_is_a_failed_sign_in_not_a_crash(resources):
    assert await passwords.verify_async("not-a-hash", "anything", resources) is False
    assert passwords.needs_rehash("not-a-hash", resources) is True


async def test_each_hash_of_the_same_password_is_different(resources):
    first = await passwords.hash_async(TEST_PASSWORD, resources)
    second = await passwords.hash_async(TEST_PASSWORD, resources)

    assert first != second
    assert await passwords.verify_async(first, TEST_PASSWORD, resources)
    assert await passwords.verify_async(second, TEST_PASSWORD, resources)
    assert not await passwords.verify_async(first, TEST_PASSWORD + "x", resources)


def test_production_refuses_to_start_without_the_web_tier_key():
    settings = _settings(environment="production", cors_origins=["https://example.test"])
    with pytest.raises(RuntimeError, match="INTERNAL_API_KEY"):
        settings.require_secrets()

    _settings(
        environment="production",
        cors_origins=["https://example.test"],
        internal_api_key=KEY,
    ).require_secrets()
