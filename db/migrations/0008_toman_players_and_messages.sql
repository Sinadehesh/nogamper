
BEGIN;


CREATE FUNCTION fn_new_player_code() RETURNS TEXT AS $$
DECLARE
    alphabet CONSTANT TEXT := 'ABCDEFGHJKMNPQRSTUVWXYZ23456789';
    candidate TEXT;
    attempt   INT := 0;
BEGIN
    LOOP
        candidate := '';
        FOR i IN 1..6 LOOP
            candidate := candidate || substr(alphabet, floor(random() * length(alphabet))::INT + 1, 1);
        END LOOP;

        EXIT WHEN NOT EXISTS (SELECT 1 FROM users WHERE player_code = candidate);

        attempt := attempt + 1;
        IF attempt > 20 THEN
            RAISE EXCEPTION 'could not allocate a unique player_code in % attempts', attempt;
        END IF;
    END LOOP;

    RETURN candidate;
END;
$$ LANGUAGE plpgsql;

ALTER TABLE users ADD COLUMN player_code TEXT;

UPDATE users SET player_code = fn_new_player_code() WHERE player_code IS NULL;

ALTER TABLE users
    ALTER COLUMN player_code SET DEFAULT fn_new_player_code(),
    ALTER COLUMN player_code SET NOT NULL,
    ADD CONSTRAINT uq_users_player_code UNIQUE (player_code);

COMMENT ON COLUMN users.player_code IS
    'Short human-sayable handle for support. Not a secret and not an '
    'authenticator — it identifies a player in conversation, nothing more.';


CREATE TYPE player_message_kind   AS ENUM ('MESSAGE', 'PRIZE_CLAIM');
CREATE TYPE player_message_status AS ENUM ('NEW', 'SEEN', 'ANSWERED');

CREATE TABLE player_messages (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,

    kind       player_message_kind   NOT NULL DEFAULT 'MESSAGE',
    status     player_message_status NOT NULL DEFAULT 'NEW',

    body       TEXT NOT NULL CHECK (length(btrim(body)) BETWEEN 1 AND 2000),

    admin_note TEXT CHECK (admin_note IS NULL OR length(admin_note) <= 2000),

    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    answered_at TIMESTAMPTZ,

    CHECK ((status = 'ANSWERED') = (answered_at IS NOT NULL))
);

CREATE INDEX idx_player_messages_triage ON player_messages (status, created_at DESC);
CREATE INDEX idx_player_messages_user ON player_messages (user_id, created_at DESC);

ALTER TABLE player_messages ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE player_messages IS
    'One-way: a player writes to the operator. Deliberately not a chat — a '
    'chat needs delivery, read state, notifications and moderation, none of '
    'which is what a prize claim needs.';

-- >>> SEED
UPDATE coin_packages SET
    title       = '۲۰۰٬۰۰۰ تومان',
    description = 'شروع سریع.',
    coins       = 20000000,
    bonus_coins = 0
 WHERE code = 'TIER_1';

UPDATE coin_packages SET
    title       = '۶۶۰٬۰۰۰ تومان',
    description = 'محبوب‌ترین. ۱۰٪ هدیه.',
    coins       = 60000000,
    bonus_coins = 6000000
 WHERE code = 'TIER_2';

UPDATE coin_packages SET
    title       = '۲٬۴۰۰٬۰۰۰ تومان',
    description = 'بهترین ارزش. ۲۰٪ هدیه.',
    coins       = 200000000,
    bonus_coins = 40000000
 WHERE code = 'TIER_3';

UPDATE rewards SET cost = cost * 40, min_lifetime_staked = min_lifetime_staked * 40;
-- <<< SEED

COMMIT;
