
BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;    -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS btree_gist;  -- non-overlapping boost windows

CREATE TYPE user_status          AS ENUM ('ACTIVE','RESTRICTED','SELF_EXCLUDED','BANNED');
CREATE TYPE market_status        AS ENUM ('DRAFT','ACTIVE','LOCKED','SETTLING','RESOLVED','VOID');
CREATE TYPE outcome_side         AS ENUM ('YES','NO');
CREATE TYPE market_resolution    AS ENUM ('YES','NO','VOID');
CREATE TYPE slip_type            AS ENUM ('SINGLE','PARLAY');
CREATE TYPE slip_status          AS ENUM ('PENDING','WON','LOST','INSURED','VOID');
CREATE TYPE leg_status           AS ENUM ('PENDING','WON','LOST','VOID');
CREATE TYPE star_purchase_status AS ENUM ('PENDING','PAID','REFUNDED','EXPIRED','FAILED');

CREATE TYPE ledger_ref_type AS ENUM (
    'PREDICTION','STAR_PURCHASE','DAILY_CLAIM','DECAY_EVENT','SEASON_PRIZE','ADMIN'
);

CREATE TYPE ledger_entry_type AS ENUM (
    'SIGNUP_BONUS_CREDIT',
    'STAKE_DEBIT',
    'INSURANCE_PREMIUM_DEBIT',
    'PAYOUT_CREDIT',            -- parlay/single won
    'INSURANCE_CREDIT',         -- insured near-miss, stake returned
    'VOID_REFUND_CREDIT',       -- market voided / cancelled upstream
    'STAR_PURCHASE_CREDIT',
    'STAR_REFUND_DEBIT',        -- Telegram refundStarPayment clawback
    'DAILY_DRIP_CREDIT',
    'STREAK_BONUS_CREDIT',
    'INACTIVITY_DECAY_DEBIT',
    'SEASON_PRIZE_CREDIT',
    'PROMO_CREDIT',
    'ADMIN_ADJUSTMENT'
);

CREATE FUNCTION fn_touch_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TABLE app_config (
    key         TEXT PRIMARY KEY,
    value       JSONB       NOT NULL,
    description TEXT,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by  TEXT
);

CREATE TABLE users (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_id        BIGINT      NOT NULL UNIQUE,
    username           TEXT,
    first_name         TEXT,
    last_name          TEXT,
    language_code      TEXT,
    is_telegram_premium BOOLEAN    NOT NULL DEFAULT FALSE,
    photo_url          TEXT,

    coin_balance       BIGINT      NOT NULL DEFAULT 0 CHECK (coin_balance >= 0),

    lifetime_staked    BIGINT      NOT NULL DEFAULT 0 CHECK (lifetime_staked >= 0),
    lifetime_returned  BIGINT      NOT NULL DEFAULT 0 CHECK (lifetime_returned >= 0),
    lifetime_stars     BIGINT      NOT NULL DEFAULT 0 CHECK (lifetime_stars >= 0),

    streak_count       INTEGER     NOT NULL DEFAULT 0 CHECK (streak_count >= 0),
    last_claim_date    DATE,
    last_prediction_at TIMESTAMPTZ,
    last_decay_date    DATE,
    last_seen_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    daily_stake_limit  BIGINT      CHECK (daily_stake_limit IS NULL OR daily_stake_limit > 0),
    cooloff_until      TIMESTAMPTZ,

    status             user_status NOT NULL DEFAULT 'ACTIVE',
    referred_by        UUID        REFERENCES users(id) ON DELETE SET NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_users_last_prediction ON users (last_prediction_at NULLS FIRST);
CREATE TRIGGER trg_users_touch BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at();

COMMENT ON COLUMN users.coin_balance IS
    'Minor units (1 coin = 100). Derived cache of ledger_entries; never UPDATE directly.';

CREATE TABLE auth_sessions (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),  -- JWT jti
    user_id           UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    init_data_hash    TEXT        NOT NULL UNIQUE,
    telegram_auth_date TIMESTAMPTZ NOT NULL,
    issued_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at        TIMESTAMPTZ NOT NULL,
    revoked_at        TIMESTAMPTZ,
    CHECK (expires_at > issued_at)
);
CREATE INDEX idx_auth_sessions_user ON auth_sessions (user_id, expires_at DESC);

CREATE TABLE market_events (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    polymarket_event_id TEXT        NOT NULL UNIQUE,
    slug                TEXT,
    title               TEXT        NOT NULL,
    category            TEXT        NOT NULL,
    image_url           TEXT,
    end_date            TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TRIGGER trg_events_touch BEFORE UPDATE ON market_events
    FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at();

CREATE TABLE markets (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id             UUID          NOT NULL REFERENCES market_events(id) ON DELETE RESTRICT,
    polymarket_market_id TEXT          NOT NULL UNIQUE,
    condition_id         TEXT          NOT NULL,
    question             TEXT          NOT NULL,
    description          TEXT,
    category             TEXT          NOT NULL,
    image_url            TEXT,

    yes_token_id         TEXT          NOT NULL,
    no_token_id          TEXT          NOT NULL,
    CHECK (yes_token_id <> no_token_id),

    raw_yes_prob         NUMERIC(7,6)  NOT NULL DEFAULT 0.5
        CHECK (raw_yes_prob > 0 AND raw_yes_prob < 1),
    price_updated_at     TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

    liquidity_usd        NUMERIC(18,2) NOT NULL DEFAULT 0,
    volume_usd           NUMERIC(18,2) NOT NULL DEFAULT 0,

    lock_at              TIMESTAMPTZ   NOT NULL,
    end_date             TIMESTAMPTZ   NOT NULL,
    CHECK (lock_at <= end_date),

    status               market_status NOT NULL DEFAULT 'DRAFT',
    is_featured          BOOLEAN       NOT NULL DEFAULT FALSE,

    resolution           market_resolution,
    resolution_source    TEXT,
    resolved_at          TIMESTAMPTZ,
    CHECK ((status = 'RESOLVED') = (resolution IS NOT NULL)),
    CHECK ((resolution IS NULL) = (resolved_at IS NULL)),

    created_at           TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

    UNIQUE (id, event_id)
);
CREATE INDEX idx_markets_open      ON markets (lock_at) WHERE status = 'ACTIVE';
CREATE INDEX idx_markets_due       ON markets (end_date) WHERE status IN ('ACTIVE','LOCKED','SETTLING');
CREATE INDEX idx_markets_event     ON markets (event_id);
CREATE INDEX idx_markets_category  ON markets (category, lock_at) WHERE status = 'ACTIVE';
CREATE TRIGGER trg_markets_touch BEFORE UPDATE ON markets
    FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at();

CREATE TABLE market_price_snapshots (
    id          BIGSERIAL PRIMARY KEY,
    market_id   UUID         NOT NULL REFERENCES markets(id) ON DELETE CASCADE,
    yes_prob    NUMERIC(7,6) NOT NULL CHECK (yes_prob > 0 AND yes_prob < 1),
    source      TEXT         NOT NULL DEFAULT 'CLOB_MIDPOINT',
    captured_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_price_snap_market ON market_price_snapshots (market_id, captured_at DESC);

CREATE TABLE odds_boosts (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    market_id          UUID          NOT NULL REFERENCES markets(id) ON DELETE CASCADE,
    side               outcome_side  NOT NULL,
    boost_multiplier   NUMERIC(6,3)  NOT NULL CHECK (boost_multiplier > 1.0 AND boost_multiplier <= 5.0),
    max_raw_prob       NUMERIC(7,6)  NOT NULL DEFAULT 0.10
        CHECK (max_raw_prob > 0 AND max_raw_prob < 1),
    starts_at          TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    ends_at            TIMESTAMPTZ   NOT NULL,
    max_total_stake    BIGINT        NOT NULL CHECK (max_total_stake > 0),
    max_stake_per_user BIGINT        NOT NULL CHECK (max_stake_per_user > 0),
    consumed_stake     BIGINT        NOT NULL DEFAULT 0 CHECK (consumed_stake >= 0),
    is_active          BOOLEAN       NOT NULL DEFAULT TRUE,
    created_at         TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    CHECK (ends_at > starts_at),
    CHECK (consumed_stake <= max_total_stake),
    EXCLUDE USING gist (
        market_id WITH =,
        side WITH =,
        tstzrange(starts_at, ends_at, '[)') WITH &&
    ) WHERE (is_active)
);
CREATE INDEX idx_boosts_live ON odds_boosts (market_id, side) WHERE is_active;

CREATE TABLE predictions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID          NOT NULL REFERENCES users(id) ON DELETE RESTRICT,

    idempotency_key     TEXT          NOT NULL,
    request_fingerprint TEXT          NOT NULL,

    type                slip_type     NOT NULL,
    leg_count           SMALLINT      NOT NULL CHECK (leg_count BETWEEN 1 AND 5),
    CHECK ((type = 'SINGLE') = (leg_count = 1)),

    stake               BIGINT        NOT NULL CHECK (stake > 0),
    combined_odds       NUMERIC(14,6) NOT NULL CHECK (combined_odds >= 1.0),

    gross_potential_payout BIGINT     NOT NULL CHECK (gross_potential_payout > 0),
    payout_cap          BIGINT        NOT NULL CHECK (payout_cap > 0),
    potential_payout    BIGINT        NOT NULL CHECK (potential_payout > 0),
    CHECK (potential_payout = LEAST(gross_potential_payout, payout_cap)),

    has_insurance         BOOLEAN     NOT NULL DEFAULT FALSE,
    insurance_premium     BIGINT      NOT NULL DEFAULT 0 CHECK (insurance_premium >= 0),
    insurance_rate        NUMERIC(7,6),
    insurance_min_legs    SMALLINT,
    insurance_max_failed  SMALLINT,
    CHECK (
        (NOT has_insurance AND insurance_premium = 0 AND insurance_rate IS NULL
             AND insurance_min_legs IS NULL AND insurance_max_failed IS NULL)
        OR
        (has_insurance AND insurance_premium > 0 AND insurance_rate IS NOT NULL
             AND insurance_min_legs IS NOT NULL AND insurance_max_failed IS NOT NULL
             AND leg_count >= insurance_min_legs)
    ),

    total_cost          BIGINT GENERATED ALWAYS AS (stake + insurance_premium) STORED,

    house_edge_bps      INTEGER       NOT NULL DEFAULT 0,

    status              slip_status   NOT NULL DEFAULT 'PENDING',
    settled_payout      BIGINT        NOT NULL DEFAULT 0 CHECK (settled_payout >= 0),
    settlement_note     TEXT,
    placed_at           TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    settled_at          TIMESTAMPTZ,
    CHECK ((status = 'PENDING') = (settled_at IS NULL)),
    CHECK (status <> 'PENDING' OR settled_payout = 0),

    UNIQUE (user_id, idempotency_key)
);
CREATE INDEX idx_predictions_user      ON predictions (user_id, placed_at DESC);
CREATE INDEX idx_predictions_pending   ON predictions (placed_at) WHERE status = 'PENDING';
CREATE INDEX idx_predictions_settled   ON predictions (settled_at DESC) WHERE status <> 'PENDING';

CREATE TABLE prediction_legs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    prediction_id    UUID          NOT NULL REFERENCES predictions(id) ON DELETE CASCADE,
    leg_index        SMALLINT      NOT NULL CHECK (leg_index BETWEEN 1 AND 5),
    market_id        UUID          NOT NULL,
    event_id         UUID          NOT NULL,
    side             outcome_side  NOT NULL,

    raw_prob         NUMERIC(7,6)  NOT NULL CHECK (raw_prob > 0 AND raw_prob < 1),
    vig_rate         NUMERIC(7,6)  NOT NULL CHECK (vig_rate >= 0 AND vig_rate < 1),
    boost_id         UUID          REFERENCES odds_boosts(id) ON DELETE SET NULL,
    boost_multiplier NUMERIC(6,3)  NOT NULL DEFAULT 1.0 CHECK (boost_multiplier >= 1.0),
    locked_odds      NUMERIC(12,6) NOT NULL CHECK (locked_odds > 1.0),

    status           leg_status    NOT NULL DEFAULT 'PENDING',
    settled_at       TIMESTAMPTZ,
    CHECK ((status = 'PENDING') = (settled_at IS NULL)),

    FOREIGN KEY (market_id, event_id) REFERENCES markets(id, event_id) ON DELETE RESTRICT,
    UNIQUE (prediction_id, leg_index),
    UNIQUE (prediction_id, market_id),
    UNIQUE (prediction_id, event_id)
);
CREATE INDEX idx_legs_open   ON prediction_legs (market_id) WHERE status = 'PENDING';
CREATE INDEX idx_legs_by_pred ON prediction_legs (prediction_id);

CREATE TABLE ledger_entries (
    id              BIGSERIAL PRIMARY KEY,
    user_id         UUID              NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    entry_type      ledger_entry_type NOT NULL,
    amount          BIGINT            NOT NULL CHECK (amount <> 0),
    balance_after   BIGINT            NOT NULL,   -- stamped by trigger
    ref_type        ledger_ref_type,
    ref_id          UUID,
    idempotency_key TEXT              NOT NULL,
    metadata        JSONB             NOT NULL DEFAULT '{}'::JSONB,
    created_at      TIMESTAMPTZ       NOT NULL DEFAULT NOW(),
    CHECK ((ref_type IS NULL) = (ref_id IS NULL))
);

CREATE UNIQUE INDEX uq_ledger_idem ON ledger_entries (user_id, idempotency_key);

CREATE UNIQUE INDEX uq_ledger_ref_once ON ledger_entries (ref_type, ref_id, entry_type)
    WHERE ref_id IS NOT NULL;

CREATE INDEX idx_ledger_user_time ON ledger_entries (user_id, id DESC);
CREATE INDEX idx_ledger_type_time ON ledger_entries (entry_type, created_at DESC);

CREATE FUNCTION fn_post_ledger_entry() RETURNS TRIGGER AS $$
DECLARE
    v_balance BIGINT;
    v_new     BIGINT;
BEGIN
    SELECT coin_balance INTO v_balance
      FROM users WHERE id = NEW.user_id FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'USER_NOT_FOUND: %', NEW.user_id USING ERRCODE = 'PT002';
    END IF;

    v_new := v_balance + NEW.amount;

    IF v_new < 0 THEN
        RAISE EXCEPTION 'INSUFFICIENT_FUNDS: balance %, requested %', v_balance, NEW.amount
            USING ERRCODE = 'PT001';
    END IF;

    NEW.balance_after := v_new;

    UPDATE users SET
        coin_balance      = v_new,
        lifetime_staked   = lifetime_staked
            + CASE WHEN NEW.entry_type IN ('STAKE_DEBIT','INSURANCE_PREMIUM_DEBIT')
                   THEN -NEW.amount ELSE 0 END,
        lifetime_returned = lifetime_returned
            + CASE WHEN NEW.entry_type IN ('PAYOUT_CREDIT','INSURANCE_CREDIT','VOID_REFUND_CREDIT')
                   THEN NEW.amount ELSE 0 END,
        lifetime_stars    = lifetime_stars
            + CASE WHEN NEW.entry_type = 'STAR_PURCHASE_CREDIT'
                   THEN COALESCE((NEW.metadata->>'stars')::BIGINT, 0) ELSE 0 END,
        updated_at        = NOW()
    WHERE id = NEW.user_id;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_ledger_post BEFORE INSERT ON ledger_entries
    FOR EACH ROW EXECUTE FUNCTION fn_post_ledger_entry();

CREATE FUNCTION fn_ledger_immutable() RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'ledger_entries is append-only (attempted %)', TG_OP
        USING ERRCODE = 'PT003';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_ledger_immutable BEFORE UPDATE OR DELETE ON ledger_entries
    FOR EACH ROW EXECUTE FUNCTION fn_ledger_immutable();

CREATE TABLE coin_packages (
    code        TEXT PRIMARY KEY,
    title       TEXT    NOT NULL,
    description TEXT    NOT NULL,
    stars_price INTEGER NOT NULL CHECK (stars_price > 0),
    coins       BIGINT  NOT NULL CHECK (coins > 0),
    bonus_coins BIGINT  NOT NULL DEFAULT 0 CHECK (bonus_coins >= 0),
    sort_order  INTEGER NOT NULL DEFAULT 0,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE telegram_updates (
    update_id    BIGINT PRIMARY KEY,
    update_type  TEXT        NOT NULL,
    payload      JSONB       NOT NULL,
    received_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    error        TEXT
);
CREATE INDEX idx_tg_updates_unprocessed ON telegram_updates (received_at)
    WHERE processed_at IS NULL;

CREATE TABLE star_purchases (
    id                         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                    UUID    NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    package_code               TEXT    NOT NULL REFERENCES coin_packages(code),

    invoice_payload            TEXT    NOT NULL UNIQUE,

    stars_amount               INTEGER NOT NULL CHECK (stars_amount > 0),
    coins_amount               BIGINT  NOT NULL CHECK (coins_amount > 0),

    status                     star_purchase_status NOT NULL DEFAULT 'PENDING',
    telegram_payment_charge_id TEXT UNIQUE,
    provider_payment_charge_id TEXT,

    created_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '1 hour',
    paid_at                    TIMESTAMPTZ,
    refunded_at                TIMESTAMPTZ,
    refund_reason              TEXT,

    CHECK ((status IN ('PAID','REFUNDED')) = (telegram_payment_charge_id IS NOT NULL)),
    CHECK ((status IN ('PAID','REFUNDED')) = (paid_at IS NOT NULL)),
    CHECK ((status = 'REFUNDED') = (refunded_at IS NOT NULL))
);
CREATE INDEX idx_star_purchases_user ON star_purchases (user_id, created_at DESC);
CREATE INDEX idx_star_purchases_open ON star_purchases (expires_at) WHERE status = 'PENDING';

CREATE TABLE daily_claims (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID    NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    claim_date   DATE    NOT NULL,
    base_amount  BIGINT  NOT NULL CHECK (base_amount >= 0),
    streak_bonus BIGINT  NOT NULL DEFAULT 0 CHECK (streak_bonus >= 0),
    streak_after INTEGER NOT NULL CHECK (streak_after > 0),
    claimed_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, claim_date)
);

CREATE TABLE decay_events (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID   NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    run_date       DATE   NOT NULL,
    days_inactive  INTEGER NOT NULL CHECK (days_inactive > 0),
    decay_rate     NUMERIC(7,6) NOT NULL CHECK (decay_rate > 0 AND decay_rate < 1),
    amount         BIGINT NOT NULL CHECK (amount > 0),
    balance_before BIGINT NOT NULL,
    balance_after  BIGINT NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, run_date)
);

CREATE TABLE leaderboard_seasons (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code         TEXT        NOT NULL UNIQUE,          -- e.g. '2026-08'
    starts_at    TIMESTAMPTZ NOT NULL,
    ends_at      TIMESTAMPTZ NOT NULL,
    prize_notes  TEXT,
    is_finalized BOOLEAN     NOT NULL DEFAULT FALSE,
    finalized_at TIMESTAMPTZ,
    CHECK (ends_at > starts_at),
    EXCLUDE USING gist (tstzrange(starts_at, ends_at, '[)') WITH &&)
);

CREATE TABLE leaderboard_entries (
    season_id      UUID    NOT NULL REFERENCES leaderboard_seasons(id) ON DELETE CASCADE,
    user_id        UUID    NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    slips_settled  INTEGER NOT NULL DEFAULT 0,
    slips_won      INTEGER NOT NULL DEFAULT 0,
    total_staked   BIGINT  NOT NULL DEFAULT 0,
    total_returned BIGINT  NOT NULL DEFAULT 0,
    net_profit     BIGINT  NOT NULL DEFAULT 0,
    best_odds      NUMERIC(14,6),
    score          NUMERIC(18,6) NOT NULL DEFAULT 0,
    rank           INTEGER,
    prize_awarded  TEXT,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (season_id, user_id)
);
CREATE INDEX idx_leaderboard_rank ON leaderboard_entries (season_id, score DESC);

CREATE TABLE admin_audit_log (
    id          BIGSERIAL PRIMARY KEY,
    actor       TEXT        NOT NULL,
    action      TEXT        NOT NULL,
    target_type TEXT,
    target_id   TEXT,
    before      JSONB,
    after       JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_audit_time ON admin_audit_log (created_at DESC);


CREATE FUNCTION fn_effective_parlay_odds(p_prediction_id UUID)
RETURNS NUMERIC AS $$
DECLARE
    v_odds NUMERIC := 1.0;
    r      RECORD;
BEGIN
    FOR r IN
        SELECT status, locked_odds FROM prediction_legs
         WHERE prediction_id = p_prediction_id
    LOOP
        IF r.status = 'PENDING' THEN
            RETURN NULL;
        ELSIF r.status = 'LOST' THEN
            RETURN 0;
        ELSIF r.status = 'WON' THEN
            v_odds := v_odds * r.locked_odds;
        END IF;   -- VOID contributes a factor of 1.0
    END LOOP;
    RETURN v_odds;
END;
$$ LANGUAGE plpgsql STABLE;

CREATE FUNCTION fn_settle_prediction(p_prediction_id UUID)
RETURNS slip_status AS $$
DECLARE
    p            predictions%ROWTYPE;
    v_odds       NUMERIC;
    v_lost       INTEGER;
    v_void       INTEGER;
    v_payout     BIGINT;
    v_status     slip_status;
    v_entry      ledger_entry_type;
    v_note       TEXT;
BEGIN
    SELECT * INTO p FROM predictions WHERE id = p_prediction_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'PREDICTION_NOT_FOUND: %', p_prediction_id USING ERRCODE = 'PT004';
    END IF;

    IF p.status <> 'PENDING' THEN
        RETURN p.status;   -- already settled; idempotent no-op
    END IF;

    v_odds := fn_effective_parlay_odds(p_prediction_id);
    IF v_odds IS NULL THEN
        RETURN 'PENDING';  -- legs outstanding
    END IF;

    SELECT COUNT(*) FILTER (WHERE status = 'LOST'),
           COUNT(*) FILTER (WHERE status = 'VOID')
      INTO v_lost, v_void
      FROM prediction_legs WHERE prediction_id = p_prediction_id;

    IF v_odds > 0 AND v_void = p.leg_count THEN
        v_status := 'VOID';
        v_entry  := 'VOID_REFUND_CREDIT';
        v_payout := p.total_cost;
        v_note   := 'All legs voided upstream; stake and premium returned.';

    ELSIF v_odds > 0 THEN
        v_status := 'WON';
        v_entry  := 'PAYOUT_CREDIT';
        v_payout := LEAST(ROUND(p.stake * v_odds)::BIGINT, p.payout_cap);
        v_note   := CASE WHEN v_void > 0
                         THEN format('%s leg(s) voided; odds recomputed to %s.', v_void, v_odds)
                         ELSE NULL END;

    ELSIF p.has_insurance AND v_lost <= p.insurance_max_failed AND v_lost > 0 THEN
        v_status := 'INSURED';
        v_entry  := 'INSURANCE_CREDIT';
        v_payout := p.stake;   -- premium is retained; that is the product
        v_note   := format('Insurance paid: %s failed leg(s) within cover.', v_lost);

    ELSE
        v_status := 'LOST';
        v_payout := 0;
    END IF;

    UPDATE predictions SET
        status          = v_status,
        settled_payout  = v_payout,
        settlement_note = v_note,
        settled_at      = NOW()
     WHERE id = p_prediction_id;

    IF v_payout > 0 THEN
        INSERT INTO ledger_entries (user_id, entry_type, amount, ref_type, ref_id, idempotency_key, metadata)
        VALUES (
            p.user_id, v_entry, v_payout, 'PREDICTION', p_prediction_id,
            'settle:' || p_prediction_id::TEXT,
            jsonb_build_object(
                'effective_odds', v_odds,
                'lost_legs',      v_lost,
                'void_legs',      v_void,
                'capped',         (ROUND(p.stake * v_odds)::BIGINT > p.payout_cap)
            )
        );
    END IF;

    RETURN v_status;
END;
$$ LANGUAGE plpgsql;


CREATE VIEW v_balance_reconciliation AS
SELECT u.id AS user_id,
       u.telegram_id,
       u.coin_balance                     AS cached_balance,
       COALESCE(SUM(l.amount), 0)         AS ledger_balance,
       u.coin_balance - COALESCE(SUM(l.amount), 0) AS drift
  FROM users u
  LEFT JOIN ledger_entries l ON l.user_id = u.id
 GROUP BY u.id, u.telegram_id, u.coin_balance
HAVING u.coin_balance <> COALESCE(SUM(l.amount), 0);

CREATE VIEW v_market_exposure AS
SELECT m.id                       AS market_id,
       m.question,
       pl.side,
       COUNT(DISTINCT p.id)       AS open_slips,
       SUM(p.stake)               AS staked,
       SUM(p.potential_payout)    AS max_liability
  FROM markets m
  JOIN prediction_legs pl ON pl.market_id = m.id AND pl.status = 'PENDING'
  JOIN predictions p      ON p.id = pl.prediction_id AND p.status = 'PENDING'
 GROUP BY m.id, m.question, pl.side;

-- >>> SEED
INSERT INTO app_config (key, value, description) VALUES
  ('odds.vig_rate',              '0.05',   'House margin applied to every leg before display.'),
  ('odds.max_legs',              '5',      'Maximum legs per parlay.'),
  ('odds.min_prob',              '0.02',   'Probabilities are clamped into [min_prob, max_prob].'),
  ('odds.max_prob',              '0.98',   'Upper probability clamp.'),
  ('odds.lock_buffer_seconds',   '300',    'Betting closes this long before upstream end_date.'),
  ('odds.price_staleness_seconds','90',    'Refuse to price a leg from a snapshot older than this.'),
  ('limits.min_stake',           '1000',   'Minimum stake in minor units (10 coins).'),
  ('limits.max_stake',           '5000000','Maximum stake in minor units (50,000 coins).'),
  ('limits.payout_cap',          '500000000','Maximum payout per slip in minor units (5,000,000 coins).'),
  ('insurance.load',             '0.35',   'Margin multiplier over fair insurance cost.'),
  ('insurance.min_rate',         '0.05',   'Premium floor as a fraction of stake.'),
  ('insurance.max_rate',         '0.60',   'Premium ceiling as a fraction of stake.'),
  ('insurance.min_legs',         '4',      'Minimum legs required to buy insurance.'),
  ('insurance.max_failed_legs',  '1',      'Failed legs still covered by the policy.'),
  ('economy.signup_bonus',       '100000', 'Opening balance in minor units (1,000 coins).'),
  ('economy.daily_drip',         '25000',  'Base daily claim in minor units (250 coins).'),
  ('economy.streak_bonus_step',  '5000',   'Added per consecutive day, capped by streak_bonus_max.'),
  ('economy.streak_bonus_max',   '50000',  'Maximum streak bonus in minor units.'),
  ('economy.decay_rate',         '0.05',   'Balance decay per decay interval of inactivity.'),
  ('economy.decay_interval_days','3',      'Days of inactivity between decay charges.'),
  ('economy.decay_floor',        '50000',  'Decay never takes a balance below this.'),
  ('boosts.max_raw_prob',        '0.10',   'Only outcomes below this probability qualify for a boost.'),
  ('boosts.max_multiplier',      '1.50',   'Maximum boost applied to taxed odds.');

INSERT INTO coin_packages (code, title, description, stars_price, coins, bonus_coins, sort_order) VALUES
  ('TIER_1', '5,000 Coins',  'Starter top-up.',              50,   500000,       0, 1),
  ('TIER_2', '15,000 Coins', 'Most popular. +10% bonus.',   125,  1500000,  150000, 2),
  ('TIER_3', '50,000 Coins', 'Best value. +20% bonus.',     350,  5000000, 1000000, 3);
-- <<< SEED

COMMIT;
