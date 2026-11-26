-- Articles written by account holders.
--
-- A site about stepping away from gambling should have something to read on
-- it, and the people best placed to write some of that are the people using
-- it. So anyone with an account can write; nothing is public until an
-- operator has read it.
--
-- That last part is the design, not a caution. An open publishing box on a
-- site that search engines associate with gambling is, within a week, a box
-- full of advertisements for casinos — and it would be this site's name on
-- them. Review before publication is the only version of this feature that
-- does not end up working against the reason the site exists.
--
-- Additive: one type, one table. Nothing existing is altered.

BEGIN;

CREATE TYPE article_status AS ENUM (
    'DRAFT',       -- the author's own; nobody else sees it
    'SUBMITTED',   -- waiting for an operator to read it
    'PUBLISHED',   -- public
    'REJECTED',    -- sent back with a note; the author can edit and resubmit
    'REMOVED'      -- was public, taken down by an operator, with a note
);

CREATE TABLE articles (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    author_id     UUID NOT NULL REFERENCES users(id),

    -- The public address. Derived from the title until the article is first
    -- published and frozen from then on: a link somebody shared must keep
    -- working after the author fixes a typo in the headline.
    slug          TEXT NOT NULL,

    title         TEXT NOT NULL,
    -- One or two sentences. Shown in listings and offered to search engines
    -- as the description, which is why it has a ceiling as well as a floor.
    summary       TEXT NOT NULL,
    -- Markdown. Rendered without raw HTML and without images, so what is
    -- stored here is text and can be treated as text.
    body          TEXT NOT NULL,

    status        article_status NOT NULL DEFAULT 'DRAFT',

    -- The operator's reason for rejecting or removing. Shown to the author:
    -- "no" with no reason teaches nobody anything.
    review_note   TEXT,
    reviewed_by   UUID REFERENCES users(id),

    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- When the words last changed. Separate from updated_at, which also
    -- moves when the status does: a reader is told when an article was last
    -- edited, not when somebody last clicked a button about it.
    edited_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    submitted_at  TIMESTAMPTZ,
    reviewed_at   TIMESTAMPTZ,
    -- First publication, and never cleared afterwards: it is what freezes the
    -- slug, and an article that is withdrawn and published again keeps its
    -- original date.
    published_at  TIMESTAMPTZ,

    CONSTRAINT ck_articles_slug
        CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$' AND char_length(slug) BETWEEN 3 AND 96),
    CONSTRAINT ck_articles_title   CHECK (char_length(title)   BETWEEN 8   AND 110),
    CONSTRAINT ck_articles_summary CHECK (char_length(summary) BETWEEN 40  AND 220),
    CONSTRAINT ck_articles_body    CHECK (char_length(body)    BETWEEN 600 AND 30000),
    CONSTRAINT ck_articles_published_is_dated
        CHECK (status <> 'PUBLISHED' OR published_at IS NOT NULL),
    -- A refusal always carries its reason. COALESCE, because a CHECK passes on
    -- NULL as well as on TRUE: without it, the one case this exists to stop —
    -- no note at all — is the case it would wave through.
    CONSTRAINT ck_articles_refusal_has_note
        CHECK (
            status NOT IN ('REJECTED', 'REMOVED')
            OR COALESCE(char_length(btrim(review_note)), 0) > 0
        )
);

CREATE UNIQUE INDEX uq_articles_slug ON articles (slug);

-- The public listing: newest first, published only.
CREATE INDEX ix_articles_published ON articles (published_at DESC, id DESC)
    WHERE status = 'PUBLISHED';

-- An author's own list.
CREATE INDEX ix_articles_author ON articles (author_id, updated_at DESC);

-- The operator's queue: oldest waiting first.
CREATE INDEX ix_articles_queue ON articles (submitted_at)
    WHERE status = 'SUBMITTED';

CREATE TRIGGER trg_articles_touch BEFORE UPDATE ON articles
    FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at();

-- Every table in this schema has row security on and no policy, which closes
-- it to anything but its owner. See 0006.
ALTER TABLE articles ENABLE ROW LEVEL SECURITY;

COMMIT;
