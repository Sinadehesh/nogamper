
BEGIN;

-- ---------------------------------------------------------------------------
-- The product changed shape: it is a website now, and it is free to play.
--
-- Two things follow from that, and this migration does both.
--
--   1. An account is no longer a Telegram identity. A person signs up with an
--      email and a password, or starts as a guest and decides later.
--   2. Nothing can be bought and nothing can be redeemed. Points have no cash
--      value in either direction, so the store and the prize catalogue close.
--
-- Additive on purpose. Nothing is dropped: the tables behind purchases and
-- prizes hold the record of what people once paid and were promised, and that
-- record is not this migration's to destroy. The application simply stops
-- reading them.
-- ---------------------------------------------------------------------------

-- ----- accounts ------------------------------------------------------------

ALTER TABLE users ALTER COLUMN telegram_id DROP NOT NULL;

ALTER TABLE users
    ADD COLUMN email              TEXT,
    ADD COLUMN password_hash      TEXT,
    ADD COLUMN is_guest           BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN daily_limit_set_at TIMESTAMPTZ,
    ADD COLUMN deleted_at         TIMESTAMPTZ;

ALTER TABLE users
    -- Stored lower-cased, so the plain unique index below is a
    -- case-insensitive one and no query has to remember to call lower().
    ADD CONSTRAINT ck_users_email_normalised
        CHECK (email IS NULL OR (email = lower(btrim(email)) AND length(email) BETWEEN 3 AND 254)),
    -- An email without a password is an account nobody can open; a password
    -- without an email is one nobody can address. Neither may exist.
    ADD CONSTRAINT ck_users_credentials_paired
        CHECK ((email IS NULL) = (password_hash IS NULL)),
    ADD CONSTRAINT ck_users_guest_has_no_credentials
        CHECK (NOT (is_guest AND email IS NOT NULL)),
    -- Every row is somebody: a legacy Telegram player, a registered account,
    -- a guest, or an account its owner has erased.
    ADD CONSTRAINT ck_users_has_identity
        CHECK (telegram_id IS NOT NULL OR email IS NOT NULL OR is_guest
               OR deleted_at IS NOT NULL);

CREATE UNIQUE INDEX uq_users_email ON users (email) WHERE email IS NOT NULL;

COMMENT ON COLUMN users.email IS
    'Sign-in address, lower-cased. Not verified: nothing here sends mail, so '
    'it must never be treated as proof of who somebody is.';
COMMENT ON COLUMN users.password_hash IS
    'Argon2id, encoded with its own parameters. Never a reversible value.';
COMMENT ON COLUMN users.is_guest IS
    'Created without credentials. The session cookie is the only key to it '
    'until the player registers, which upgrades this same row in place.';
COMMENT ON COLUMN users.daily_limit_set_at IS
    'When daily_stake_limit last changed. A limit may be tightened at any '
    'time and loosened only a day after this, so it cannot be lifted in the '
    'same moment it starts to bind.';
COMMENT ON COLUMN users.deleted_at IS
    'The owner erased this account. Personal fields are blanked; the ledger '
    'rows stay, because deleting them would rewrite everyone else''s history.';

-- ----- sessions ------------------------------------------------------------

ALTER TABLE auth_sessions ALTER COLUMN init_data_hash DROP NOT NULL;
ALTER TABLE auth_sessions ALTER COLUMN telegram_auth_date DROP NOT NULL;

ALTER TABLE auth_sessions
    ADD COLUMN method TEXT NOT NULL DEFAULT 'telegram'
        CHECK (method IN ('telegram', 'password', 'guest'));

COMMENT ON COLUMN auth_sessions.method IS
    'How this session was opened. Existing rows are Telegram sessions, hence '
    'the default; everything the website opens says so explicitly.';

-- ----- settlement notes, in the language of the ledger ----------------------
--
-- 0002 wrote these in Farsi because the only client was Farsi. The site is
-- English now and renders its own wording from the slip's status, so the
-- stored note is an audit trail rather than display copy. The arithmetic is
-- unchanged, line for line.

CREATE OR REPLACE FUNCTION fn_settle_prediction(p_prediction_id UUID)
RETURNS slip_status AS $$
DECLARE
    p        predictions%ROWTYPE;
    v_odds   NUMERIC;
    v_lost   INTEGER;
    v_void   INTEGER;
    v_payout BIGINT;
    v_status slip_status;
    v_entry  ledger_entry_type;
    v_note   TEXT;
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
        v_note   := 'Every pick was voided at the source; the stake was returned.';

    ELSIF v_odds > 0 THEN
        v_status := 'WON';
        v_entry  := 'PAYOUT_CREDIT';
        v_payout := LEAST(ROUND(p.stake * v_odds)::BIGINT, p.payout_cap);
        v_note   := CASE WHEN v_void > 0
                         THEN format('%s pick(s) voided; odds recomputed to %s.', v_void, v_odds)
                         ELSE NULL END;

    ELSIF p.has_insurance AND v_lost <= p.insurance_max_failed AND v_lost > 0 THEN
        -- No slip placed through the website carries insurance. The branch
        -- stays so a slip opened before this migration still settles on the
        -- terms its owner was shown.
        v_status := 'INSURED';
        v_entry  := 'INSURANCE_CREDIT';
        v_payout := p.stake;
        v_note   := format('Cover paid: %s missed pick(s) within the policy.', v_lost);

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
        INSERT INTO ledger_entries (user_id, entry_type, amount, ref_type, ref_id,
                                    idempotency_key, metadata)
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

-- ----- the store and the prize catalogue close ------------------------------
--
-- The application no longer has a route that reads either table. Switching
-- the rows off as well means an older build pointed at this database finds
-- nothing on sale, rather than relying on nobody ever running one.

-- >>> SEED
UPDATE coin_packages SET is_active = FALSE;
UPDATE rewards       SET is_active = FALSE;

-- Boosts are gone too: a time-limited better price is a reason to act now,
-- and "act now" is the one feeling this product should not manufacture.
UPDATE odds_boosts SET is_active = FALSE WHERE is_active;
-- <<< SEED

COMMIT;
