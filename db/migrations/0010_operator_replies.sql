
BEGIN;

ALTER TABLE player_messages
    ADD COLUMN reply_body      TEXT,
    ADD COLUMN replied_at      TIMESTAMPTZ,
    ADD COLUMN reply_delivered BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE player_messages
    ADD CONSTRAINT ck_reply_body_length
        CHECK (reply_body IS NULL OR length(btrim(reply_body)) BETWEEN 1 AND 2000),
    ADD CONSTRAINT ck_reply_pairing
        CHECK ((reply_body IS NULL) = (replied_at IS NULL)),
    ADD CONSTRAINT ck_delivered_needs_reply
        CHECK (NOT reply_delivered OR reply_body IS NOT NULL);

COMMENT ON COLUMN player_messages.reply_body IS
    'The operator answer the player sees. Sent by the bot, so it never '
    'exposes the operator''s Telegram account, and kept here so the answer '
    'survives a delivery Telegram refuses.';

COMMENT ON COLUMN player_messages.reply_delivered IS
    'Telegram accepted the sendMessage. False with a reply present means the '
    'player has never started the bot; the app still shows them the answer.';

COMMENT ON TABLE player_messages IS
    'A player writes to the operator and the operator may answer once, '
    'delivered by the bot. Deliberately not a chat: no threads, no read '
    'receipts, no notifications beyond the single reply.';

COMMIT;
