# NoGamper

**Prediction markets without the gambling.** A free forecasting game: real
questions about the news, live odds taken from real markets, and points that
cannot be bought, sold or cashed out.

![The landing page](docs/screenshots/landing.png)

Calling an outcome, putting something behind it and finding out whether you
were right is genuinely fun. Most places that let you do it are built to keep
you there after you have lost money. This is the same game with the money
taken out and those mechanisms left out — an alternative for people who enjoy
the forecasting and do not want the rest.

It is also a portfolio project: a small system with the parts a larger one
has, built end to end with AI coding agents under human direction, with the
behaviour pinned by tests.

- [What makes it not gambling](#what-makes-it-not-gambling)
- [What you can do](#what-you-can-do)
- [How it is built](#how-it-is-built)
- [Run it locally](#run-it-locally)
- [Tests](#tests)
- [Deploying](#deploying)
- [Limits and non-goals](#limits-and-non-goals)

## What makes it not gambling

Gambling needs three things: something of value staked, an outcome you do not
control, and something of value to win. The first and the last are removed
here, structurally rather than by policy.

| On a betting site | Here |
| --- | --- |
| You deposit money | There is no way to pay. Everyone starts with 1,000 points and can claim 200 more each day |
| You can win money or prizes | Points buy nothing and redeem for nothing. The leaderboard has no prizes |
| The price includes a margin, and it compounds on multi-pick bets | Odds are exactly `1 ÷ probability`. Nothing is taken out at any length |
| Streaks, boosts and limited-time offers bring you back | The daily top-up is flat, so a missed day costs nothing. Nothing is boosted and nothing is on offer for a limited time |
| Limits are a setting you can undo in a click | A limit lowers at once and takes 24 hours to raise. A break cannot be cut short |
| Your losses are your business | A reality check shows your record, and what it would have cost at a bookmaker |

The codebase began as a conventional betting-style product. These were
**removed, not switched off** — the settings no longer exist, so nothing is one
environment variable away from coming back:

- buying points with real money, and every payment path
- prizes and anything redeemable
- a house margin on each pick
- a bonus for adding picks to a slip, and paid "insurance" on losing ones
- limited-time boosted odds
- a balance that decays if you stay away
- streak bonuses that punish a missed day
- rewards for recruiting friends
- a live ticker of other people's wins

This is a description of how the game works, not legal advice, and it is not
a treatment for a gambling problem. For some people in recovery, odds and
stakes of any kind are a trigger; the site says so plainly and links to
[real help](apps/web/app/help/page.tsx) from every page.

## What you can do

![The questions feed](docs/screenshots/play.png)

- **Play at once, as a guest**, or create an account with an email and a
  password. A guest who signs up keeps their points and their record.
- **Forecast real questions** — politics, the economy, crypto — priced from
  Polymarket's public market data. Pick yes or no, stake some points, and
  combine up to five questions on one slip.
- **See the honest number.** Every slip shows the chance it comes in, not
  just what it pays.
- **Follow your record**: open and settled forecasts, and a monthly
  leaderboard for bragging rights.
- **Use the brakes**: a daily limit, a break of a day to a month, a reminder
  after a set time on the site, and account deletion that works immediately.
- **Run it**: an operator view with player support, an inbox, an overview of
  where points went, and diagnostics that name which layer is unhealthy.

![Safer-play tools](docs/screenshots/safer-play.png)

## How it is built

```mermaid
flowchart LR
    B["Browser"] -- "HttpOnly cookie" --> W["Next.js server<br/>apps/web"]
    W -- "Bearer token<br/>+ web-tier key" --> A["FastAPI<br/>apps/api"]
    A --> P[("PostgreSQL")]
    A --> R[("Redis")]
    K["Worker<br/>same image"] --> P
    K --> R
    K -- "read only" --> M["Polymarket<br/>public data"]
```

```
apps/web/     Next.js 16 (App Router), React 19, Tailwind 4 — the site and its server
apps/api/     FastAPI on asyncpg — accounts, pricing, placement, settlement, workers
db/           SQL migrations, applied in order, and the schema's invariants
scripts/      The migration runner
render.yaml   The API and worker, as a Render Blueprint
```

Some of it is worth reading:

**The browser holds no credential.** It has an HttpOnly, `SameSite=Lax` cookie
it cannot read. The Next.js server turns that into a bearer token and forwards
an [explicit allowlist](apps/web/app/api/%5B...path%5D/route.ts) of requests;
[`proxy.ts`](apps/web/proxy.ts) refuses any state-changing request that did not
come from the site's own pages. The API's address never reaches a browser.

**Sessions are rows, not just signatures.** The token is a pointer to a
session record, so signing out, changing a password and deleting an account
revoke access immediately instead of waiting for an expiry.

**Sign-in is built to be attacked.** Passwords are hashed with Argon2id off the
event loop, behind a semaphore sized to the container. An unknown email costs
the same time as a wrong password. Attempts are throttled per account and per
visitor in Redis with an atomic script, and the routes that open a session
only answer the web tier, which proves itself with a
[shared key](apps/api/backend/security/webtier.py).

**Every point is a ledger row.** Balances are never written directly: an
append-only ledger drives them through a trigger that refuses an overdraft,
idempotency keys make a retried request safe, and a reconciliation view
([`0001_init.sql`](db/migrations/0001_init.sql)) lists any account whose
balance and ledger disagree — which the tests assert is none.

**The pricing is small enough to audit.**
[`engine/odds.py`](apps/api/backend/engine/odds.py) is `1 ÷ p`, rounded down.
An outcome the market prices outside 1%–99% is refused rather than clamped —
clamping would overpay near-certain outcomes — and two picks from the same
event are refused because their outcomes are tied together.

**The brakes are enforced where the forecast is placed.** Limits and breaks
are checked under a row lock in the same transaction that debits the stake, so
two requests arriving together cannot both get through
([`safer_play.py`](apps/api/backend/repositories/safer_play.py),
[`predictions.py`](apps/api/backend/repositories/predictions.py)).

**Workers survive each other.** Discovery, price sync, resolution and the
leaderboard roll-up run on a schedule in one process. A lease that expires by
itself keeps replicas from doing the same work twice, every run records how it
went, and the diagnostics endpoint says whether the database, the worker, the
source or the cache is at fault.

**Migrations are checksummed.** [`scripts/migrate.py`](scripts/migrate.py)
applies each file once, in a transaction with its own bookkeeping, and refuses
to run if an applied file has been edited since. Every table has row security
enabled, the runner's own included, so a database host that puts a REST API in
front of Postgres exposes nothing.

**The words are in one place.** Everything a visitor reads lives in
[`lib/copy.ts`](apps/web/lib/copy.ts) and
[`lib/content.ts`](apps/web/lib/content.ts), and any sentence that states a
number reads it from the API's live rules. CI fails if text is typed straight
into a component. The site loads nothing from third parties — no web fonts, no
analytics.

## Run it locally

You need Docker, Python 3.11+ with [uv](https://docs.astral.sh/uv/), and
Node 20.9 or newer.

```bash
make db-up                    # Postgres and Redis; creates appdb and appdb_test
make api-install web-install  # the API's virtualenv and the site's node_modules

cp apps/api/.env.example apps/api/.env
cp apps/web/.env.example apps/web/.env.local
```

Set `JWT_SECRET` in `apps/api/.env` — the API will not start without one:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Then:

```bash
make migrate       # apply the schema
make api-workers   # the API on :8000, pulling live questions
make web-dev       # in a second terminal: the site on http://localhost:3000
```

The first questions appear within half a minute of the API starting. To open the
operator pages, create an account, copy its six-character player code from the
Account tab into `ADMIN_PLAYER_CODES` in `apps/api/.env`, and restart the API.

`make help` lists everything else. Each setting is explained in
[`apps/api/.env.example`](apps/api/.env.example) and
[`apps/web/.env.example`](apps/web/.env.example).

## Tests

```bash
make api-test api-lint        # needs the services from `make db-up`
make web-typecheck web-build
make schema-test              # needs PostgreSQL's own binaries (initdb) on PATH
```

`make test` runs all of it.

| What | How |
| --- | --- |
| Schema invariants | Every migration replayed into a throwaway cluster, then [`invariants.sql`](db/tests/invariants.sql): the ledger cannot overdraw, a balance always equals its ledger, nothing is on sale |
| API | More than 550 tests against a real Postgres and Redis: pricing, placement, settlement, sign-in, throttling, limits and breaks, the workers, and the migration runner itself |
| Configuration | The example environment file is [checked against the code](apps/api/tests/test_env_example.py), so it cannot advertise a setting that is gone |
| Site | Typecheck, production build, and a check that no UI text is hard-coded |

CI runs all of it on every push ([`ci.yml`](.github/workflows/ci.yml)).

## Deploying

The API and the worker are one image run twice, described in
[`render.yaml`](render.yaml); the file's own comments walk through a first
deploy. Postgres and Redis are external. The site is a Next.js app deployed
from `apps/web`.

| Where | Variable | Value |
| --- | --- | --- |
| API and worker | `DATABASE_URL` | A direct or session-mode connection string, not a transaction pooler |
| API and worker | `REDIS_URL` | |
| API and worker | `JWT_SECRET`, `INTERNAL_API_KEY` | Generated by the Blueprint |
| API and worker | `ADMIN_PLAYER_CODES` | Your own player code, once your account exists |
| Site | `API_BASE_URL` | The API's public URL |
| Site | `INTERNAL_API_KEY` | The same value the API has |

In production the API refuses to start without a signing secret and a web-tier
key of at least 32 characters each.

The site trusts its hosting platform to report the visitor's address, which
the sign-up throttle depends on. That is correct on a platform that overwrites
`X-Real-IP` and `X-Forwarded-For` itself; behind any other proxy, set
`CLIENT_IP_HEADER` as described in the site's example file.

### Moving the original deployment over

Migration `0016` is additive and drops nothing.

- Accounts created through the old Telegram client stay in the database but
  have no email or password, so they cannot sign in to the site.
- `ADMIN_PLAYER_CODES` replaces `ADMIN_TELEGRAM_IDS`, and `INTERNAL_API_KEY`
  is new and required on the API, the worker and the site. Every other old
  variable is ignored and can be deleted.
- The retired tables — purchases, rewards, boosts and the rest — are kept with
  the rows they already hold. Nothing writes to them, and the migration marks
  everything in them as no longer on sale.
- Earlier migrations still contain the old product's text. They are
  checksummed, so they are superseded rather than edited.

## Limits and non-goals

- **Nothing sends email.** Addresses are not verified and there is no password
  reset: a forgotten password cannot be recovered.
- **A guest account lives in one browser.** Clear the cookie and it is gone.
  The site tells guests so, and offers to make the account permanent.
- **Age is self-declared.** The site is for adults and says so; it does not
  check.
- **Prices are borrowed.** Questions and odds come from Polymarket's public
  data. This project is not affiliated with Polymarket and places no trades.
  When the source is unreachable, questions show as updating and cannot be
  picked.
- **Rate limits fail open.** If Redis is down, sign-in keeps working without a
  throttle rather than locking everybody out.
- **It is a game, not a service for problem gambling.** The help page links to
  people who are.

## If gambling is costing you more than you want it to

Free, confidential help exists, and none of it is this website:
[Gambling Therapy](https://www.gamblingtherapy.org/) (worldwide, many
languages), [GamCare](https://www.gamcare.org.uk/) (UK),
the [National Problem Gambling Helpline](https://www.ncpgambling.org/help-treatment/)
(US) and [Gamblers Anonymous](https://www.gamblersanonymous.org/).
