"""The container's start script: bring the database up to date, then serve.

`scripts/start.sh` is the one command the image runs, on every host and on
every start. It replaced a separate pre-deploy migration step, because not
every host has one, and that makes its order of operations load-bearing: a
server that starts before its migrations have run answers 500 to everything,
and a server that starts after a migration has *failed* is running new code
against an old schema.

The real `python` and `uvicorn` are swapped for stand-ins that only write down
how they were called, so this tests the script and nothing else.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "start.sh"

MIGRATE = "python scripts/migrate.py"


@pytest.fixture
def stand_ins(tmp_path: Path) -> tuple[Path, Path]:
    """A directory to put first on PATH, and the file its programs write to."""
    calls = tmp_path / "calls.log"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("python", "uvicorn"):
        program = bin_dir / name
        program.write_text(
            "#!/bin/sh\n"
            f'echo "{name} $* (in $(pwd))" >> "{calls}"\n'
            f'exit "${{EXIT_{name.upper()}:-0}}"\n'
        )
        program.chmod(0o755)
    return bin_dir, calls


def start(stand_ins: tuple[Path, Path], *, cwd: Path = REPO, **env: str):
    bin_dir, calls = stand_ins
    result = subprocess.run(  # noqa: S603 - the repository's own script, with no outside input
        ["/bin/sh", str(SCRIPT)],
        cwd=cwd,
        env={"PATH": f"{bin_dir}:/usr/bin:/bin", **env},
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    called = calls.read_text().splitlines() if calls.exists() else []
    return result, called


def test_the_database_is_migrated_before_the_server_starts(stand_ins):
    result, called = start(stand_ins)

    assert result.returncode == 0, result.stderr
    assert len(called) == 2
    assert called[0].startswith(MIGRATE)
    assert called[1].startswith(
        "uvicorn backend.main:app --host 0.0.0.0 --port 8000 --no-server-header"
    )


def test_a_failed_migration_stops_the_server_from_starting(stand_ins):
    """New code against a half-migrated schema is worse than no new code: the
    host sees a container that did not come up and keeps the last release."""
    result, called = start(stand_ins, EXIT_PYTHON="3")

    assert result.returncode == 3
    assert len(called) == 1
    assert called[0].startswith(MIGRATE)


def test_the_host_chooses_the_port(stand_ins):
    _, called = start(stand_ins, PORT="10000")

    assert "--port 10000 " in called[-1]


def test_migrating_at_start_can_be_switched_off(stand_ins):
    """For a deployment that runs the migrations some other way."""
    result, called = start(stand_ins, MIGRATE_ON_START="false")

    assert result.returncode == 0, result.stderr
    assert len(called) == 1
    assert called[0].startswith("uvicorn ")


def test_it_runs_from_the_directory_that_holds_the_migrations(stand_ins, tmp_path):
    """migrate.py is named by a relative path, so wherever the script is
    called from, it has to move to the root that path is relative to."""
    _, called = start(stand_ins, cwd=tmp_path)

    assert called[0] == f"{MIGRATE} (in {REPO})"


def test_the_image_runs_this_script_and_nothing_else():
    """The Dockerfile's last word. If it went back to starting uvicorn
    directly, a host with no pre-deploy step would never migrate at all."""
    dockerfile = (REPO / "Dockerfile").read_text(encoding="utf-8")
    commands = [line for line in dockerfile.splitlines() if line.startswith("CMD ")]

    assert commands == ['CMD ["sh", "scripts/start.sh"]']


def test_the_server_replaces_the_shell_so_it_receives_the_stop_signal():
    """Without `exec` the shell stays in front as process 1 and swallows
    SIGTERM, and a deploy kills a settlement halfway through its transaction."""
    lines = [
        line.strip()
        for line in SCRIPT.read_text(encoding="utf-8").splitlines()
        if "uvicorn" in line and not line.lstrip().startswith("#")
    ]

    assert len(lines) == 1
    assert lines[0].startswith("exec uvicorn ")
