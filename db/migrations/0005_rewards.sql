
BEGIN;

CREATE TYPE reward_claim_status AS ENUM ('RESERVED','FULFILLED','FAILED','REFUNDED');

CREATE TABLE rewards (
    code        TEXT PRIMARY KEY,
    title       TEXT   NOT NULL,   -- Farsi, shown to the player
    description TEXT   NOT NULL,   -- Farsi
    kind        TEXT   NOT NULL,
    image_url   TEXT,

    cost        BIGINT NOT NULL CHECK (cost > 0),

    min_lifetime_staked BIGINT NOT NULL DEFAULT 0 CHECK (min_lifetime_staked >= 0),

    total_supply   INTEGER CHECK (total_supply IS NULL OR total_supply > 0),
    claimed_count  INTEGER NOT NULL DEFAULT 0 CHECK (claimed_count >= 0),

    per_user_limit INTEGER CHECK (per_user_limit IS NULL OR per_user_limit > 0),

    sort_order  INTEGER     NOT NULL DEFAULT 0,
    is_active   BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (total_supply IS NULL OR claimed_count <= total_supply)
);

CREATE TRIGGER trg_rewards_touch BEFORE UPDATE ON rewards
    FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at();

CREATE INDEX idx_rewards_visible ON rewards (sort_order, code) WHERE is_active;

CREATE TABLE reward_claims (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID   NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    reward_code TEXT   NOT NULL REFERENCES rewards(code) ON DELETE RESTRICT,

    cost        BIGINT NOT NULL CHECK (cost > 0),
    status      reward_claim_status NOT NULL DEFAULT 'RESERVED',

    fulfilment     JSONB NOT NULL DEFAULT '{}'::JSONB,
    failure_reason TEXT,

    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    fulfilled_at TIMESTAMPTZ,
    refunded_at  TIMESTAMPTZ,

    CHECK ((status = 'FULFILLED') = (fulfilled_at IS NOT NULL)),
    CHECK ((status = 'REFUNDED')  = (refunded_at  IS NOT NULL)),
    CHECK (status <> 'FAILED' OR failure_reason IS NOT NULL)
);

CREATE INDEX idx_reward_claims_user ON reward_claims (user_id, created_at DESC);

CREATE INDEX idx_reward_claims_pending ON reward_claims (status, created_at)
    WHERE status IN ('RESERVED','FAILED');

CREATE INDEX idx_reward_claims_held ON reward_claims (user_id, reward_code)
    WHERE status <> 'REFUNDED';

-- >>> SEED
INSERT INTO rewards (code, title, description, kind, cost, min_lifetime_staked,
                     total_supply, per_user_limit, sort_order, is_active)
VALUES
    ('gold_badge',
     'نشان طلایی',
     'نشان طلایی کنار نام شما در جدول رده‌بندی.',
     'BADGE',
     500000000,      -- 5,000,000 coins
     100000000,      -- must have staked 1,000,000 coins to qualify
     NULL, 1, 10, FALSE),

    ('telegram_gift',
     'هدیهٔ تلگرام',
     'هدیهٔ تلگرام که یک‌راست به حساب شما می‌رسد.',
     'TELEGRAM_GIFT',
     1200000000,     -- 12,000,000 coins
     300000000,      -- 3,000,000 coins staked
     NULL, NULL, 20, FALSE),

    ('founders_nft',
     'ان‌اف‌تی بنیان‌گذاران',
     'ان‌اف‌تی محدود بنیان‌گذاران — فقط ۱۰۰ نسخه، برای نخستین قهرمانان.',
     'NFT',
     3000000000,     -- 30,000,000 coins
     600000000,      -- 6,000,000 coins staked
     100, 1, 30, FALSE);
-- <<< SEED

COMMIT;
