"""ADMIN_TELEGRAM_IDS must never be able to stop the API from booting.

Written after it did. The operator was told to put their Telegram id in this
variable, pasted their six-character player code instead, and every player
lost the app: `int("GRDZGN")` raised inside Settings(), uvicorn could not
import the module, and the container crash-looped.

The rule this file pins is about *which* direction a configuration mistake is
allowed to fail in. A missing JWT_SECRET should stop the process, because
serving without one is worse than not serving at all. This list is the
opposite: it decides who may read the admin pages, so the dangerous mistake is
letting somebody in, not keeping the operator out. A value that cannot be a
Telegram id is dropped, which grants nothing — exactly what an unset variable
already does.
"""

from __future__ import annotations

import logging

import pytest

from backend.config import Settings


def settings_with(ids: str) -> Settings:
    return Settings(admin_telegram_ids=ids)


def test_a_player_code_does_not_take_the_api_down():
    """The outage, as a test. A player code is letters; an id is digits."""
    assert settings_with("GRDZGN").admin_telegram_ids == []


def test_a_good_id_alongside_a_bad_one_still_works():
    """Dropping the whole list on one bad entry would lock the operator out of
    their own admin pages for a stray character — the same unhelpful outcome
    as crashing, minus the crash."""
    assert settings_with("909090,GRDZGN,4242").admin_telegram_ids == [909090, 4242]


def test_the_rejected_value_is_named_in_the_log(caplog):
    """Named, not counted. "1 invalid entry" in a comma-separated list leaves
    the operator to work out which one, which is the whole difficulty."""
    with caplog.at_level(logging.WARNING, logger="backend.config"):
        settings_with("GRDZGN,909090")

    assert "GRDZGN" in caplog.text
    assert "ADMIN_TELEGRAM_IDS" in caplog.text


def test_a_clean_list_logs_nothing(caplog):
    """A warning that fires on a correct configuration is a warning that gets
    ignored on a broken one."""
    with caplog.at_level(logging.WARNING, logger="backend.config"):
        assert settings_with("909090, 4242").admin_telegram_ids == [909090, 4242]

    assert caplog.text == ""


@pytest.mark.parametrize("value", ["", "   ", ",,"])
def test_an_empty_list_means_nobody(value):
    """Unset still has to mean "no admins" rather than "all admins" — the
    original reason this validator exists."""
    assert settings_with(value).admin_telegram_ids == []


def test_negative_and_padded_ids_survive_normalisation():
    """Telegram ids are negative for channels and people paste with spaces.
    Neither is a mistake, so neither should be dropped."""
    assert settings_with(" 909090 ,-1001234567890").admin_telegram_ids == [909090, -1001234567890]
