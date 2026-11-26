#
# One image, two services.
#
# The API and the worker run the *same* command from the *same* image and
# differ only in WORKERS_ENABLED. That is not a shortcut — the scheduler is
# attached to the FastAPI lifespan in main.py, so it starts after the database
# pool and stops before it, and a job can never run against a closing
# connection. A separate worker entrypoint would have to rebuild that ordering.
#
# Build context is the repository root, not apps/api, so scripts/ comes along.

# ---------------------------------------------------------------------------
# Stage 1 — build the virtualenv
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_ROOT_USER_ACTION=ignore

# Everything is installed into a venv rather than the system interpreter, so
# the runtime stage copies one self-contained directory and inherits none of
# the build stage's state.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /src

# Dependencies first, against a stub package. This layer is keyed on
# pyproject.toml alone, so editing application code — which is most commits —
# reuses the cached install instead of re-resolving nine packages.
COPY apps/api/pyproject.toml ./pyproject.toml
RUN mkdir -p backend \
 && touch backend/__init__.py \
 && pip install .

# Now the real source. --no-deps because the dependency set is already
# resolved and installed above; this layer only replaces our own package.
COPY apps/api/backend ./backend
RUN pip install --no-deps --force-reinstall .

# ---------------------------------------------------------------------------
# Stage 2 — runtime
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

# No compilers, headers or pip in the final image. asyncpg, uvloop and
# httptools all ship manylinux wheels, so nothing here needs to be built —
# if that ever changes, the build fails loudly in stage 1 rather than
# silently dragging a toolchain into production.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser

COPY --from=builder /opt/venv /opt/venv

# backend itself lives in the venv's site-packages — a non-editable
# install — so only the operational scripts and the migrations they read are
# copied in. scripts/migrate.py uses the asyncpg already in the venv, which is
# why this image needs no psql client and installs no database tooling.
COPY --chown=appuser:appuser scripts /app/scripts
# scripts/migrate.py resolves these relative to its own parent, so the layout
# under /app has to mirror the repository.
COPY --chown=appuser:appuser db/migrations /app/db/migrations

WORKDIR /app
USER appuser

EXPOSE 8000

# `exec` matters. Without it the shell stays PID 1 and does not forward
# SIGTERM, so a deploy would kill the process instead of letting the lifespan
# run scheduler.shutdown(wait=True) — which is what lets an in-flight
# settlement finish its transaction. With exec, uvicorn *is* PID 1 and
# receives the signal directly.
#
# One process per container. Never --workers N: each fork would build its own
# scheduler, leaving the advisory lock as the only thing between you and four
# concurrent price syncs. Scale containers instead.
CMD ["sh", "-c", "exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000} --no-server-header"]
