
BEGIN;

ALTER TABLE market_events
    ADD COLUMN IF NOT EXISTS title_source TEXT;

ALTER TABLE markets
    ADD COLUMN IF NOT EXISTS question_source    TEXT,
    ADD COLUMN IF NOT EXISTS description_source TEXT;

COMMENT ON COLUMN markets.question_source IS
    'Polymarket''s original English. `question` is what the player reads.';

UPDATE market_events SET title_source = title WHERE title_source IS NULL;
UPDATE markets
   SET question_source    = COALESCE(question_source, question),
       description_source = COALESCE(description_source, description)
 WHERE question_source IS NULL OR (description IS NOT NULL AND description_source IS NULL);

CREATE TABLE IF NOT EXISTS translations (
    id              BIGSERIAL PRIMARY KEY,
    source_hash     TEXT        NOT NULL,
    source_lang     TEXT        NOT NULL,
    target_lang     TEXT        NOT NULL,
    source_text     TEXT        NOT NULL,
    translated_text TEXT        NOT NULL,
    provider        TEXT        NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (source_hash, source_lang, target_lang)
);

CREATE INDEX IF NOT EXISTS idx_translations_lookup
    ON translations (source_lang, target_lang, created_at DESC);

COMMENT ON TABLE translations IS
    'Content-addressed translation cache. Safe to TRUNCATE: the next discovery '
    'run refills it from *_source, which is why the source columns are kept.';

COMMIT;
