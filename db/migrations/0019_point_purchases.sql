BEGIN;

-- ---------------------------------------------------------------------------
-- Points can be bought.
--
-- Migration 0016 closed the old store, and the reason it gave still holds in
-- one direction: nothing can ever be taken *out*. Points are not redeemable,
-- not transferable and not worth anything, and nothing here changes that.
-- What changes is that a site with no advertising and no gambling money has
-- to be paid for by somebody, and the people who use it are allowed to be
-- that somebody.
--
-- So this is a shop with the brakes built into the schema rather than left to
-- the application's good manners:
--
--   * every purchase is a row, and a row is credited at most once (the ledger
--     already refuses a second entry for the same reference);
--   * a player may set their own monthly spending limit, down to zero, which
--     closes the shop for them. Like the daily forecast limit, it can be
--     lowered at once and raised only after a wait — `spend_limit_set_at` is
--     what that wait is measured from.
--
-- The site-wide monthly cap is configuration, not schema: it is a number an
-- operator may retune, and it is enforced where purchases are created.
-- ---------------------------------------------------------------------------

CREATE TYPE point_purchase_status AS ENUM ('PENDING', 'PAID', 'REFUNDED', 'EXPIRED');

CREATE TABLE point_purchases (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id               UUID        NOT NULL REFERENCES users(id) ON DELETE RESTRICT,

    -- What was bought and what was charged, fixed at the moment of asking.
    -- A later change to the price list must not rewrite what somebody paid.
    points                BIGINT      NOT NULL,
    amount_cents          INTEGER     NOT NULL,
    currency              TEXT        NOT NULL,

    status                point_purchase_status NOT NULL DEFAULT 'PENDING',

    -- Stripe's names for the same event. The session exists once Stripe has
    -- answered; the payment intent once somebody has actually paid.
    stripe_session_id     TEXT,
    stripe_payment_intent TEXT,

    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at            TIMESTAMPTZ NOT NULL,
    paid_at               TIMESTAMPTZ,
    refunded_at           TIMESTAMPTZ,

    -- On a refund the points come back out. A player may have used some by
    -- then, and a balance cannot go below zero, so this records how many
    -- actually did.
    clawed_back           BIGINT      NOT NULL DEFAULT 0,

    CONSTRAINT ck_point_purchases_points   CHECK (points > 0),
    CONSTRAINT ck_point_purchases_amount   CHECK (amount_cents > 0),
    CONSTRAINT ck_point_purchases_currency CHECK (currency ~ '^[a-z]{3}$'),
    CONSTRAINT ck_point_purchases_window   CHECK (expires_at > created_at),
    CONSTRAINT ck_point_purchases_paid_is_dated
        CHECK ((status IN ('PAID', 'REFUNDED')) = (paid_at IS NOT NULL)),
    CONSTRAINT ck_point_purchases_refund_is_dated
        CHECK ((status = 'REFUNDED') = (refunded_at IS NOT NULL)),
    CONSTRAINT ck_point_purchases_clawback
        CHECK (clawed_back >= 0 AND clawed_back <= points
               AND (clawed_back = 0 OR status = 'REFUNDED'))
);

CREATE UNIQUE INDEX uq_point_purchases_session ON point_purchases (stripe_session_id)
    WHERE stripe_session_id IS NOT NULL;

-- A refund arrives naming the payment, not the purchase.
CREATE INDEX ix_point_purchases_intent ON point_purchases (stripe_payment_intent)
    WHERE stripe_payment_intent IS NOT NULL;

-- "What has this player spent this month" and "what are they in the middle of
-- buying" are both asked on every visit to the shop.
CREATE INDEX ix_point_purchases_user ON point_purchases (user_id, created_at DESC);

COMMENT ON TABLE point_purchases IS
    'Points bought with money through Stripe. A financial record: rows are '
    'kept when an account is erased, and hold no card details at any point.';
COMMENT ON COLUMN point_purchases.points IS
    'Minor units, like every other amount of points: 100 is one point.';

ALTER TABLE point_purchases ENABLE ROW LEVEL SECURITY;

-- ----- the player's own spending limit --------------------------------------

ALTER TABLE users
    ADD COLUMN monthly_spend_limit_cents INTEGER,
    ADD COLUMN spend_limit_set_at        TIMESTAMPTZ;

ALTER TABLE users
    ADD CONSTRAINT ck_users_spend_limit
        CHECK (monthly_spend_limit_cents IS NULL OR monthly_spend_limit_cents >= 0),
    ADD CONSTRAINT ck_users_spend_limit_dated
        CHECK ((monthly_spend_limit_cents IS NULL) = (spend_limit_set_at IS NULL));

COMMENT ON COLUMN users.monthly_spend_limit_cents IS
    'The most this player lets themselves spend on points in a calendar '
    'month. NULL means only the site-wide cap applies; zero closes the shop '
    'for them.';
COMMENT ON COLUMN users.spend_limit_set_at IS
    'When monthly_spend_limit_cents last changed. Lowering is immediate; '
    'raising or removing waits a day from this, exactly like the daily limit.';

COMMIT;
