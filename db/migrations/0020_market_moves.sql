BEGIN;

-- ---------------------------------------------------------------------------
-- What moved.
--
-- The site has always shown what a question's chance *is*. It is about to
-- start saying how that has *changed* — a page for each question, and a page
-- of the questions that moved most — because a number that has gone from 30%
-- to 55% in a day is the nearest thing a prediction market has to news.
--
-- Three things are kept, all read from the source in the same pass that
-- already brings each question in:
--
--   * `slug`, the source's own name for the question. It becomes the page's
--     address, so it is held to the shape of one.
--   * the change in the YES price over the last hour, day and week, as the
--     source reports them. Signed, and in probability, so 0.25 is "up 25
--     points". Null when the source gave none — a question younger than the
--     window has no such figure, and a made-up zero would say "nothing
--     happened" about a question nobody has measured.
--   * `change_ref_prob`, the YES price those changes were measured *to*, and
--     `changes_at`, when. Without them "up 25 points" cannot be turned back
--     into "from 30% to 55%", which is the form a person actually reads, and
--     nobody could tell an hour-old figure from a week-old one.
--
-- The price the game runs on, `raw_yes_prob`, is untouched. It belongs to the
-- price sync, is refreshed every minute and is clamped to the band the game
-- will price; these figures are the source's own, refreshed with the question
-- list, and exist to be read rather than staked against.
-- ---------------------------------------------------------------------------

ALTER TABLE markets
    ADD COLUMN slug            TEXT,
    ADD COLUMN change_1h       NUMERIC(7,6),
    ADD COLUMN change_24h      NUMERIC(7,6),
    ADD COLUMN change_7d       NUMERIC(7,6),
    ADD COLUMN change_ref_prob NUMERIC(7,6),
    ADD COLUMN changes_at      TIMESTAMPTZ,
    ADD CONSTRAINT markets_slug_is_an_address
        CHECK (slug IS NULL
               OR (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$' AND char_length(slug) <= 200)),
    ADD CONSTRAINT markets_changes_are_probabilities
        CHECK ((change_1h  IS NULL OR change_1h  BETWEEN -1 AND 1)
           AND (change_24h IS NULL OR change_24h BETWEEN -1 AND 1)
           AND (change_7d  IS NULL OR change_7d  BETWEEN -1 AND 1)
           AND (change_ref_prob IS NULL OR change_ref_prob BETWEEN 0 AND 1)),
    -- A change with nothing to measure it from, or no date, is a number
    -- nobody can check.
    ADD CONSTRAINT markets_changes_have_a_reference
        CHECK ((change_ref_prob IS NULL) = (changes_at IS NULL)
           AND (changes_at IS NOT NULL
                OR (change_1h IS NULL AND change_24h IS NULL AND change_7d IS NULL)));

COMMENT ON COLUMN markets.slug IS
    'The source''s own name for the question; the address of its public page.';
COMMENT ON COLUMN markets.change_24h IS
    'Change in the YES price over the last day, as the source reported it at changes_at. Signed probability.';
COMMENT ON COLUMN markets.change_ref_prob IS
    'The YES price the change_* figures were measured to, as the source reported it at changes_at.';

-- Looked up by address on every page view. Not unique: the address is the
-- source's, and a second question arriving under a name already in use must
-- not be able to stop the whole list from being read.
CREATE INDEX idx_markets_slug ON markets (slug) WHERE slug IS NOT NULL;

COMMIT;
