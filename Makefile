DB_URL ?= postgresql://postgres:postgres@localhost:5432/appdb
TEST_DB_URL ?= postgresql://postgres:postgres@localhost:5432/appdb_test
TEST_REDIS_URL ?= redis://localhost:6379/15

VENV = . apps/api/.venv/bin/activate

.PHONY: help db-up db-down migrate migrate-test schema-apply schema-verify schema-test \
        api-install api-test api-lint api-dev api-workers \
        web-install web-dev web-typecheck web-build test

help:
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-15s %s\n", $$1, $$2}'

# ----- services ---------------------------------------------------------------

db-up: ## Start local Postgres and Redis, and create the test database
	docker compose up -d --wait db cache
	@docker compose exec -T db psql -U postgres -tAc \
		"SELECT 1 FROM pg_database WHERE datname = 'appdb_test'" | grep -q 1 \
		|| docker compose exec -T db createdb -U postgres appdb_test

db-down: ## Stop local services (the data is kept; `docker compose down -v` deletes it)
	docker compose down

# ----- schema -----------------------------------------------------------------

migrate: ## Apply pending migrations to $(DB_URL) — safe to re-run; this is what a deploy runs
	$(VENV) && DATABASE_URL="$(DB_URL)" python scripts/migrate.py

migrate-test: ## Apply pending migrations to the test database
	$(VENV) && DATABASE_URL="$(TEST_DB_URL)" python scripts/migrate.py

# psql only, no Python: what CI's schema job uses. It replays every file, so it
# works on an empty database and fails on one that already has the schema.
schema-apply: ## Apply every migration with psql to an EMPTY $(DB_URL)
	@for m in db/migrations/*.sql; do \
		echo "applying $$m"; \
		psql "$(DB_URL)" -v ON_ERROR_STOP=1 -f "$$m" >/dev/null || exit 1; \
	done

schema-verify: schema-apply ## Apply to an empty $(DB_URL), then prove the invariants
	psql "$(DB_URL)" -v ON_ERROR_STOP=1 -f db/tests/invariants.sql

schema-test: ## Prove the schema invariants in a throwaway cluster (needs initdb on PATH)
	bash db/run_tests.sh

# ----- API --------------------------------------------------------------------

api-install: ## Create the API venv and install dependencies (needs uv)
	cd apps/api && uv venv .venv && . .venv/bin/activate && uv pip install -e ".[dev]"

api-test: migrate-test ## Run the API test suite against the test database
	cd apps/api && . .venv/bin/activate && \
		TEST_DATABASE_URL="$(TEST_DB_URL)" TEST_REDIS_URL="$(TEST_REDIS_URL)" python -m pytest -q

api-lint: ## Lint and format-check every Python file (apps/api + scripts)
	$(VENV) && ruff check apps/api scripts && ruff format --check apps/api scripts

api-dev: ## Run the API with reload, workers off (reads apps/api/.env)
	cd apps/api && . .venv/bin/activate && uvicorn backend.main:app --reload --port 8000

api-workers: ## Run the API with the market-data workers on — what the site needs locally
	cd apps/api && . .venv/bin/activate && WORKERS_ENABLED=true \
		uvicorn backend.main:app --port 8000

# ----- web --------------------------------------------------------------------

web-install: ## Install frontend dependencies
	cd apps/web && npm install

web-dev: ## Run the site at http://localhost:3000 (reads apps/web/.env.local)
	cd apps/web && npm run dev

web-typecheck: ## Typecheck the site
	cd apps/web && npx tsc --noEmit

web-build: ## Production build of the site
	cd apps/web && npm run build

# ----- everything -------------------------------------------------------------

test: schema-test api-test api-lint web-typecheck web-build ## Everything CI runs
