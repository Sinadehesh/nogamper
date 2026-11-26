# Prediction Mini App

A Telegram Mini App. FastAPI service, Next.js client, PostgreSQL, Redis.

## Layout

```
apps/api/    FastAPI service — auth, ingestion, odds, settlement
apps/web/    Next.js Mini App; app/api/ is the BFF holding the session cookie
db/          Migrations, applied in order, and schema invariants
scripts/     Migration runner and webhook setup
```

## Running

    make db-up          # local Postgres and Redis
    make migrate        # apply migrations
    make test           # schema invariants, API suite, web build

Configuration: `apps/api/.env.example` and `apps/web/.env.example`.
Deployment: `render.yaml`.
