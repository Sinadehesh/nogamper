DB_URL ?= postgresql://postgres:postgres@localhost:5432/appdb
TEST_DB_URL ?= postgresql://postgres:postgres@localhost:5432/appdb_test
TEST_REDIS_URL ?= redis://localhost:6379/15

.PHONY: help db-up db-down migrate migrate-py schema-test schema-verify api-install api-test api-lint api-dev api-workers web-install web-dev web-build test

help:
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-14s %s\n", $$1, $$2}'

db-up: ## Start local Postgres and Redis
	docker compose up -d db cache

db-down: ## Stop local services
	docker compose down

migrate: ## Apply every migration in order to $(DB_URL)
	@for m in db/migrations/*.sql; do \
		echo "applying $$m"; \
		psql "$(DB_URL)" -v ON_ERROR_STOP=1 -f "$$m" >/dev/null || exit 1; \
	done

schema-test: ## Prove the schema invariants in a throwaway cluster
	./db/run_tests.sh

schema-verify: migrate ## Apply migrations and prove the invariants against $(DB_URL)
	psql "$(DB_URL)" -v ON_ERROR_STOP=1 -f db/tests/invariants.sql

api-install: ## Create the API venv and install dependencies
	cd apps/api && uv venv .venv && . .venv/bin/activate && uv pip install -e ".[dev]"

api-test: ## Run the API test suite
	cd apps/api && . .venv/bin/activate && \
		TEST_DATABASE_URL="$(TEST_DB_URL)" TEST_REDIS_URL="$(TEST_REDIS_URL)" python -m pytest -q

api-lint: ## Lint and format-check every Python file (apps/api + scripts)
	. apps/api/.venv/bin/activate && \
		ruff check apps/api scripts && ruff format --check apps/api scripts

migrate-py: ## Apply pending migrations with the runner CI and Render use
	. apps/api/.venv/bin/activate && DATABASE_URL="$(DB_URL)" python scripts/migrate.py

api-dev: ## Run the API with reload (workers off)
	cd apps/api && . .venv/bin/activate && uvicorn backend.main:app --reload --port 8000

api-workers: ## Run the API with the ingestion workers enabled
	cd apps/api && . .venv/bin/activate && WORKERS_ENABLED=true \
		uvicorn backend.main:app --port 8000

web-install: ## Install frontend dependencies
	cd apps/web && npm install

web-dev: ## Run the Next.js dev server
	cd apps/web && npm run dev

web-build: ## Production build and typecheck
	cd apps/web && npm run build

test: schema-test api-test web-build ## Everything
