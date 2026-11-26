"""Unit tests for the initData verifier.

These do not touch the database. They exist to pin down the exact behaviour
of the one function that decides who a caller is.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime, timedelta

import pytest
from conftest import TEST_BOT_TOKEN, make_init_data, sign_init_data

from backend.security.telegram import InitDataError, verify_init_data

TTL = timedelta(seconds=3600)


def verify(raw: str, token: str = TEST_BOT_TOKEN, **kwargs):
    return verify_init_data(raw, token, ttl=TTL, **kwargs)


def test_accepts_correctly_signed_init_data():
    raw = make_init_data(telegram_id=777, first_name="Ada")
    result = verify(raw)

    assert result.user.id == 777
    assert result.user.first_name == "Ada"
    assert result.user.username == "user777"
    assert result.query_id == "AAH777"
    assert result.fingerprint == hashlib.sha256(raw.encode()).hexdigest()


def test_rejects_a_tampered_field():
    raw = make_init_data(telegram_id=777)
    tampered = raw.replace("%22id%22%3A777", "%22id%22%3A999")
    assert tampered != raw

    with pytest.raises(InitDataError) as exc:
        verify(tampered)
    assert exc.value.code == "init_data_bad_signature"


def test_rejects_a_signature_from_another_bot():
    raw = make_init_data(token="999999:SOME-OTHER-BOTS-TOKEN")

    with pytest.raises(InitDataError) as exc:
        verify(raw)
    assert exc.value.code == "init_data_bad_signature"


def test_rejects_unsigned_init_data():
    with pytest.raises(InitDataError) as exc:
        verify("user=%7B%22id%22%3A1%7D&auth_date=1")
    assert exc.value.code == "init_data_unsigned"


def test_rejects_duplicate_fields():
    """A repeated key lets two parsers disagree about what was signed."""
    raw = make_init_data(telegram_id=777)
    with pytest.raises(InitDataError) as exc:
        verify(raw + "&auth_date=1")
    assert exc.value.code == "init_data_duplicate_field"


def test_rejects_stale_init_data():
    raw = make_init_data(auth_date=int(time.time()) - 7200)
    with pytest.raises(InitDataError) as exc:
        verify(raw)
    assert exc.value.code == "init_data_expired"


def test_rejects_init_data_from_the_future():
    raw = make_init_data(auth_date=int(time.time()) + 600)
    with pytest.raises(InitDataError) as exc:
        verify(raw)
    assert exc.value.code == "init_data_future"


def test_accepts_init_data_within_clock_skew():
    raw = make_init_data(auth_date=int(time.time()) + 10)
    assert verify(raw).user.id == 4242


def test_rejects_init_data_without_a_user():
    raw = sign_init_data({"auth_date": str(int(time.time())), "query_id": "AAH1"})
    with pytest.raises(InitDataError) as exc:
        verify(raw)
    assert exc.value.code == "init_data_no_user"


def test_rejects_malformed_user_json():
    raw = sign_init_data({"auth_date": str(int(time.time())), "user": "not-json"})
    with pytest.raises(InitDataError) as exc:
        verify(raw)
    assert exc.value.code == "init_data_malformed"


@pytest.mark.parametrize(
    "user_payload",
    [
        {"first_name": "Ada"},
        {"id": "777", "first_name": "Ada"},
        {"id": 0, "first_name": "Ada"},
        {"id": True, "first_name": "Ada"},
        {"id": 777},
        {"id": 777, "first_name": ""},
    ],
)
def test_rejects_unusable_user_objects(user_payload):
    raw = sign_init_data(
        {
            "auth_date": str(int(time.time())),
            "user": json.dumps(user_payload, separators=(",", ":")),
        }
    )
    with pytest.raises(InitDataError) as exc:
        verify(raw)
    assert exc.value.code == "init_data_malformed"


def test_signature_field_stays_inside_the_signed_payload():
    """Telegram's Ed25519 `signature` is part of what the HMAC covers.

    Stripping it — a common mistake, borrowed from the separate third-party
    validation flow — would reject every launch from a client that sends it.
    """
    raw = make_init_data(telegram_id=777, signature="abc123_ed25519")
    assert verify(raw).user.id == 777


def test_handles_names_with_spaces_and_unicode():
    raw = make_init_data(telegram_id=777, first_name="Ada Lovelace ✨")
    assert verify(raw).user.first_name == "Ada Lovelace ✨"


def test_rejects_an_empty_string():
    with pytest.raises(InitDataError) as exc:
        verify("")
    assert exc.value.code == "init_data_malformed"


def test_rejects_when_no_bot_token_is_configured():
    with pytest.raises(InitDataError) as exc:
        verify_init_data(make_init_data(), "", ttl=TTL)
    assert exc.value.code == "server_misconfigured"


def test_ttl_is_measured_against_the_supplied_clock():
    issued = int(time.time())
    raw = make_init_data(auth_date=issued)
    later = datetime.fromtimestamp(issued, tz=UTC) + timedelta(seconds=3599)
    assert verify(raw, now=later).user.id == 4242

    with pytest.raises(InitDataError):
        verify(raw, now=later + timedelta(seconds=2))
