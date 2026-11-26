"""The example environment file, checked against the settings it documents.

An example file only ever drifts one way. A setting is removed from the code
and stays in the file, where it still looks like a switch; a default is retuned
in the code and the file goes on advertising the old one. Nothing fails, so
nobody notices — and here it matters more than usual, because the settings
that were removed are the house margin, the price list and the prize table. A
`VIG_RATE=0.05` left in the example would be a product that says it takes
nothing, shipping a file that says otherwise.

So the file is treated as code: every name in it must be a real setting, and
every value must be the one the code would have used anyway.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from backend.config import Settings

EXAMPLE = Path(__file__).resolve().parents[1] / ".env.example"

# `NAME=value`, live or commented out with a single `#`.
_ASSIGNMENT = re.compile(r"^(?P<off>#\s?)?(?P<name>[A-Z][A-Z0-9_]*)=(?P<value>.*)$")


class _FileOnly(Settings):
    """Settings read from a file and nothing else.

    conftest pins a few dozen environment variables, and the environment
    outranks a file. Read the ordinary way, the example would be compared with
    the test suite's pins rather than with the product's defaults.
    """

    @classmethod
    def settings_customise_sources(
        cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings
    ):
        return (init_settings, dotenv_settings)


def _assignments() -> list[tuple[str, str, bool]]:
    """(name, value, is_live) for every setting the file mentions."""
    found = []
    for line in EXAMPLE.read_text(encoding="utf-8").splitlines():
        match = _ASSIGNMENT.match(line)
        if match:
            found.append((match["name"], match["value"], match["off"] is None))
    return found


def test_the_example_file_is_where_the_makefile_says_it_is():
    assert EXAMPLE.is_file()
    assert len(_assignments()) > 30, "the parser found almost nothing; has the format changed?"


def test_every_name_in_the_example_is_a_real_setting():
    """Commented-out lines included: a suggestion to uncomment something that
    does not exist is worse than a live line, because it never even warns."""
    known = {name.upper() for name in Settings.model_fields}
    unknown = sorted({name for name, _, _ in _assignments() if name not in known})
    assert unknown == [], f"not settings: {unknown}"


def test_no_setting_is_listed_twice():
    names = [name for name, _, live in _assignments() if live]
    assert sorted(set(names)) == sorted(names)


def test_the_example_states_the_defaults_and_nothing_else():
    """Copying the file to .env must change nothing about how the game plays.

    One difference is expected and named: the database URL carries the
    password docker-compose.yml sets, where the code's default has none.
    """
    documented = _FileOnly(_env_file=EXAMPLE)
    shipped = _FileOnly(_env_file=None)

    differing = {
        name
        for name in Settings.model_fields
        if getattr(documented, name) != getattr(shipped, name)
    }
    assert differing == {"database_url"}, {
        name: (getattr(documented, name), getattr(shipped, name)) for name in differing
    }


def test_the_example_carries_no_secrets():
    values = {name: value for name, value, live in _assignments() if live}
    assert values["JWT_SECRET"] == ""
    assert values["INTERNAL_API_KEY"] == ""
    assert values["ADMIN_PLAYER_CODES"] == ""


def test_the_example_does_not_boot_until_a_secret_is_set():
    """Blank on purpose. A placeholder that worked would be a signing key
    published in a public repository and running in somebody's deployment."""
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        _FileOnly(_env_file=EXAMPLE).require_secrets()
