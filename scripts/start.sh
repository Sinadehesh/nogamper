#!/bin/sh
#
# What the container runs: bring the database up to date, then become the server.
#
# The migrations are applied here, at start, rather than in a separate step
# before a deploy, for one reason: not every host has such a step. Render's
# free plan does not, and a server that starts against a database it has not
# migrated is a server that answers 500 to everything.
#
# It is safe to do on every start and from several containers at once.
# scripts/migrate.py applies only what is pending, checks what is already
# applied against its checksum, and takes a lock while it works, so two
# containers starting together run the migrations once and the second finds
# nothing to do. A start with nothing pending costs one short connection.
#
# If a migration fails, this exits before the server starts. That is the
# point: the host sees a container that did not come up, keeps the previous
# release serving, and the failure is the last thing in the log.
#
# Set MIGRATE_ON_START=false to skip it, for a deployment that runs
# scripts/migrate.py some other way.

set -eu

# The paths below are relative to the directory that holds scripts/ and db/.
cd "$(dirname "$0")/.."

if [ "${MIGRATE_ON_START:-true}" = "true" ]; then
    python scripts/migrate.py
fi

# `exec` matters. Without it this shell stays PID 1 and does not forward
# SIGTERM, so a deploy would kill the process outright instead of letting it
# stop in order: requests in flight are answered, the scheduler is stopped,
# and the database pool is closed. With exec, uvicorn *is* PID 1 and receives
# the signal directly.
#
# Stopping the scheduler does not wait for a job that is mid-run. It cancels
# it, and the job's open transaction is rolled back. That is safe — every
# job's writes are transactional and the next start does the work again — but
# it means the replaced container can leave a job's lease behind for up to
# two minutes, which is why the new container's start-up jobs wait their turn
# and ask again (workers/scheduler.py, `when_free`).
#
# One process per container. Never --workers N: each fork would build its own
# scheduler, leaving the lease as the only thing between you and four
# concurrent price syncs. Scale containers instead.
exec uvicorn backend.main:app --host 0.0.0.0 --port "${PORT:-8000}" --no-server-header
