"""Articles written by account holders, and the review that stands between
writing one and anybody else reading it.

## The shape

An author drafts, submits, and waits. An operator reads it and either
publishes it or sends it back with a reason. A published article can be
withdrawn by its author or taken down by an operator. Nothing is public that
an operator has not read.

    DRAFT ──submit──▶ SUBMITTED ──publish──▶ PUBLISHED ──remove──▶ REMOVED
      ▲                   │                      │                    │
      │                reject                 withdraw              edit
      │                   ▼                      │                    │
      └──────edit──── REJECTED                   └────────▶ DRAFT ◀───┘

## Why review comes first

A site that search engines associate with gambling, offering a box that
publishes whatever is typed into it, becomes a billboard for casinos about as
fast as a crawler can find it — under this site's name, on a domain whose
whole purpose is the opposite. Reading before publishing is not a courtesy
here; it is the only form in which the feature does not undo the product.

It is also why a body is text and nothing else. No raw HTML is rendered and
images are not allowed, so an article cannot carry a tracking pixel, an
embedded frame or a script, whatever a reviewer overlooks.

## What an author can always do

Delete their own work, in any state. It is theirs.
"""

from __future__ import annotations

import re
import secrets
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime

import asyncpg

# Mirrored by CHECK constraints in 0017_articles.sql. The database has the last
# word; these exist so the refusal names the field and the limit.
TITLE_MIN, TITLE_MAX = 8, 110
SUMMARY_MIN, SUMMARY_MAX = 40, 220
BODY_MIN, BODY_MAX = 600, 30_000
NOTE_MAX = 1_000

WORDS_PER_MINUTE = 220
"""A middling adult reading pace for prose on a screen. Only ever shown
rounded to the minute, so the exact figure matters less than having one."""

# States an author may still be working on. They count against the cap on
# unfinished articles and are the only ones that can be edited or submitted.
EDITABLE = ("DRAFT", "REJECTED", "REMOVED")

# What an operator may list. Drafts are absent on purpose: an unsubmitted
# draft is private, including from the people who run the site.
REVIEWABLE = ("SUBMITTED", "PUBLISHED", "REJECTED", "REMOVED")

_SLUG_STEM_MAX = 70
# No vowels-that-look-like-digits and no digits-that-look-like-letters, for
# the same reason player codes avoid them: these get read aloud and retyped.
_SLUG_SUFFIX_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
_SLUG_SUFFIX_LENGTH = 5

# Everything below U+0020 except tab and newline, plus DEL. None of it is
# visible and none of it belongs in prose; it arrives by paste.
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_RUN_OF_SPACE = re.compile(r"\s+")
_NOT_SLUG = re.compile(r"[^a-z0-9]+")
_BLANK_RUN = re.compile(r"\n{3,}")


class ArticleError(Exception):
    def __init__(self, code: str, detail: str, *, status: int = 400) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status = status


@dataclass(frozen=True, slots=True)
class Article:
    id: uuid.UUID
    slug: str
    title: str
    summary: str
    body: str
    status: str
    review_note: str | None
    author_id: uuid.UUID
    author_name: str
    author_code: str
    words: int
    created_at: datetime
    edited_at: datetime
    submitted_at: datetime | None
    reviewed_at: datetime | None
    published_at: datetime | None

    @property
    def reading_minutes(self) -> int:
        return max(1, round(self.words / WORDS_PER_MINUTE))


# ----- cleaning what was typed ------------------------------------------------


def _clean_line(raw: str, *, field: str, minimum: int, maximum: int) -> str:
    """One line of text: a title or a summary.

    Whitespace is collapsed before the length is measured, so a title cannot
    reach the minimum by padding and a pasted line break does not survive
    into a headline.
    """
    text = _RUN_OF_SPACE.sub(" ", _CONTROL.sub("", unicodedata.normalize("NFC", raw))).strip()
    if len(text) < minimum:
        raise ArticleError(
            f"{field}_too_short", f"The {field} needs at least {minimum} characters."
        )
    if len(text) > maximum:
        raise ArticleError(f"{field}_too_long", f"Keep the {field} under {maximum} characters.")
    return text


def clean_title(raw: str) -> str:
    return _clean_line(raw, field="title", minimum=TITLE_MIN, maximum=TITLE_MAX)


def clean_summary(raw: str) -> str:
    return _clean_line(raw, field="summary", minimum=SUMMARY_MIN, maximum=SUMMARY_MAX)


def clean_body(raw: str) -> str:
    """The article itself, as Markdown, tidied but not rewritten.

    Line endings are made uniform, trailing spaces and invisible control
    characters are dropped, and runs of blank lines are reduced to one. What
    the author wrote is otherwise left alone — including any HTML, which is
    stored as the text it is and shown as text by the renderer.
    """
    text = unicodedata.normalize("NFC", raw).replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL.sub("", text)
    text = "\n".join(line.rstrip() for line in text.split("\n")).strip()
    text = _BLANK_RUN.sub("\n\n", text)

    if len(text) < BODY_MIN:
        raise ArticleError(
            "body_too_short",
            f"An article needs at least {BODY_MIN} characters — a few paragraphs.",
        )
    if len(text) > BODY_MAX:
        raise ArticleError("body_too_long", f"Keep the article under {BODY_MAX:,} characters.")
    return text


def clean_note(raw: str | None) -> str | None:
    note = _RUN_OF_SPACE.sub(" ", raw or "").strip()
    if len(note) > NOTE_MAX:
        raise ArticleError("note_too_long", f"Keep the note under {NOTE_MAX:,} characters.")
    return note or None


def count_words(body: str) -> int:
    return len(body.split())


# ----- addresses --------------------------------------------------------------


def slug_stem(title: str) -> str:
    """The readable part of an address: the title, in lower-case ASCII.

    Accents are folded rather than dropped, so "Café" becomes "cafe" and not
    "caf". A title with nothing left after folding — one written entirely in
    another script — still gets an address, just not a descriptive one.
    """
    folded = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    stem = _NOT_SLUG.sub("-", folded.lower()).strip("-")
    return stem[:_SLUG_STEM_MAX].strip("-") or "article"


def _suffix() -> str:
    return "".join(secrets.choice(_SLUG_SUFFIX_ALPHABET) for _ in range(_SLUG_SUFFIX_LENGTH))


def _slug(title: str, suffix: str) -> str:
    return f"{slug_stem(title)}-{suffix}"


def _suffix_of(slug: str) -> str:
    return slug.rsplit("-", 1)[-1]


# ----- who may write ----------------------------------------------------------


def require_author(user: asyncpg.Record) -> None:
    """A registered account in good standing.

    Not a guest: a guest is a cookie, and a byline should outlive a browser
    being cleared. It also means every article has an account behind it that
    an operator can restrict if they have to.
    """
    if user["is_guest"]:
        raise ArticleError("account_required", "Create an account to write articles.", status=403)
    if user["status"] != "ACTIVE":
        raise ArticleError("account_restricted", "This account cannot write articles.", status=403)


# ----- reading rows -----------------------------------------------------------

_COLUMNS = """
    a.id, a.slug, a.title, a.summary, a.body, a.status::text AS status, a.review_note,
    a.author_id, u.first_name AS author_name, u.player_code AS author_code,
    a.created_at, a.edited_at, a.submitted_at, a.reviewed_at, a.published_at
"""

_FROM = "FROM articles a JOIN users u ON u.id = a.author_id"

# An article is public when it is published and its author is not banned. A
# ban is for abuse, and leaving a banned account's writing up under the
# site's name until somebody remembers to take each piece down is the wrong
# default.
_PUBLIC = "a.status = 'PUBLISHED' AND u.status <> 'BANNED'"


def _article(row: asyncpg.Record) -> Article:
    return Article(
        id=row["id"],
        slug=row["slug"],
        title=row["title"],
        summary=row["summary"],
        body=row["body"],
        status=row["status"],
        review_note=row["review_note"],
        author_id=row["author_id"],
        author_name=row["author_name"] or "",
        author_code=row["author_code"],
        words=count_words(row["body"]),
        created_at=row["created_at"],
        edited_at=row["edited_at"],
        submitted_at=row["submitted_at"],
        reviewed_at=row["reviewed_at"],
        published_at=row["published_at"],
    )


async def _load(conn: asyncpg.Connection, article_id: uuid.UUID) -> Article:
    row = await conn.fetchrow(f"SELECT {_COLUMNS} {_FROM} WHERE a.id = $1", article_id)  # noqa: S608
    return _article(row)


async def _lock_own(
    conn: asyncpg.Connection, *, author_id: uuid.UUID, article_id: uuid.UUID
) -> asyncpg.Record:
    """The author's own article, locked for the rest of the transaction.

    Somebody else's article and one that does not exist are the same answer.
    Telling them apart would let anyone test which ids are real.
    """
    row = await conn.fetchrow(
        """
        SELECT id, slug, status::text AS status, published_at
          FROM articles
         WHERE id = $1 AND author_id = $2
           FOR UPDATE
        """,
        article_id,
        author_id,
    )
    if row is None:
        raise ArticleError("article_not_found", "No such article.", status=404)
    return row


# ----- the author's side ------------------------------------------------------


async def create(
    conn: asyncpg.Connection,
    *,
    author: asyncpg.Record,
    title: str,
    summary: str,
    body: str,
    max_open: int,
) -> Article:
    require_author(author)
    title, summary, body = clean_title(title), clean_summary(summary), clean_body(body)

    unfinished = await conn.fetchval(
        "SELECT count(*) FROM articles WHERE author_id = $1 AND status::text = ANY($2::text[])",
        author["id"],
        list(EDITABLE),
    )
    if unfinished >= max_open:
        raise ArticleError(
            "too_many_drafts",
            f"You have {unfinished} unfinished articles. Finish or delete one first.",
            status=409,
        )

    # The suffix makes a collision a one-in-tens-of-millions event per title,
    # which is not the same as never. A savepoint per attempt, because a
    # unique violation otherwise aborts the caller's whole transaction.
    for _ in range(4):
        try:
            async with conn.transaction():
                article_id = await conn.fetchval(
                    """
                    INSERT INTO articles (author_id, slug, title, summary, body)
                    VALUES ($1, $2, $3, $4, $5)
                    RETURNING id
                    """,
                    author["id"],
                    _slug(title, _suffix()),
                    title,
                    summary,
                    body,
                )
        except asyncpg.UniqueViolationError:
            continue
        return await _load(conn, article_id)

    raise ArticleError("try_again", "That could not be saved. Try again.", status=503)


async def update(
    conn: asyncpg.Connection,
    *,
    author: asyncpg.Record,
    article_id: uuid.UUID,
    title: str,
    summary: str,
    body: str,
) -> Article:
    """Save changes to an article that is not in front of anybody.

    Editing something that was sent back, or taken down, returns it to a
    draft. The operator's note is left where it is until the article is
    submitted again: it is what the author is working from.
    """
    require_author(author)
    title, summary, body = clean_title(title), clean_summary(summary), clean_body(body)
    current = await _lock_own(conn, author_id=author["id"], article_id=article_id)

    if current["status"] not in EDITABLE:
        raise ArticleError(
            "article_locked",
            "Withdraw this article before changing it.",
            status=409,
        )

    # The address follows the title until the article has been public once.
    # After that it is frozen: links to it exist.
    slug = current["slug"]
    if current["published_at"] is None:
        slug = _slug(title, _suffix_of(slug))

    for attempt in range(4):
        try:
            async with conn.transaction():
                await conn.execute(
                    """
                    UPDATE articles
                       SET title = $2, summary = $3, body = $4, slug = $5,
                           status = 'DRAFT', edited_at = NOW()
                     WHERE id = $1
                    """,
                    article_id,
                    title,
                    summary,
                    body,
                    slug,
                )
        except asyncpg.UniqueViolationError:
            if current["published_at"] is not None or attempt == 3:
                raise ArticleError(
                    "try_again", "That could not be saved. Try again.", status=503
                ) from None
            slug = _slug(title, _suffix())
            continue
        return await _load(conn, article_id)

    raise ArticleError("try_again", "That could not be saved. Try again.", status=503)


async def submit(
    conn: asyncpg.Connection,
    *,
    author: asyncpg.Record,
    article_id: uuid.UUID,
    publish_directly: bool,
    window_seconds: int,
    max_in_window: int,
) -> Article:
    """Send an article for review — or, for an operator, publish it.

    An operator's own article skips the queue because the queue is the
    operator: asking them to approve what they just wrote adds a click and no
    second pair of eyes.
    """
    require_author(author)
    current = await _lock_own(conn, author_id=author["id"], article_id=article_id)

    if current["status"] not in EDITABLE:
        raise ArticleError(
            "article_not_submittable",
            "This article has already been submitted.",
            status=409,
        )

    if publish_directly:
        await conn.execute(
            """
            UPDATE articles
               SET status = 'PUBLISHED', review_note = NULL,
                   submitted_at = NOW(), reviewed_at = NOW(), reviewed_by = $2,
                   published_at = COALESCE(published_at, NOW())
             WHERE id = $1
            """,
            article_id,
            author["id"],
        )
        return await _load(conn, article_id)

    # Counted per article, not per press of the button: resubmitting the same
    # piece moves its timestamp and occupies one place in the queue. What is
    # bounded is how many different things one person can put in front of a
    # reviewer in a day.
    recent = await conn.fetchval(
        """
        SELECT count(*) FROM articles
         WHERE author_id = $1 AND id <> $2
           AND submitted_at > NOW() - make_interval(secs => $3)
        """,
        author["id"],
        article_id,
        float(window_seconds),
    )
    if recent >= max_in_window:
        raise ArticleError(
            "too_many_submissions",
            "You have submitted several articles recently. Give the reviewer a little while.",
            status=429,
        )

    await conn.execute(
        """
        UPDATE articles
           SET status = 'SUBMITTED', review_note = NULL, submitted_at = NOW()
         WHERE id = $1
        """,
        article_id,
    )
    return await _load(conn, article_id)


async def withdraw(
    conn: asyncpg.Connection, *, author: asyncpg.Record, article_id: uuid.UUID
) -> Article:
    """Take an article back, out of the queue or off the site.

    Open to an author whatever their standing: a restricted account cannot
    publish, but it can always stop publishing.
    """
    current = await _lock_own(conn, author_id=author["id"], article_id=article_id)
    if current["status"] not in ("SUBMITTED", "PUBLISHED"):
        raise ArticleError("article_not_withdrawable", "There is nothing to withdraw.", status=409)
    await conn.execute("UPDATE articles SET status = 'DRAFT' WHERE id = $1", article_id)
    return await _load(conn, article_id)


async def delete(conn: asyncpg.Connection, *, author_id: uuid.UUID, article_id: uuid.UUID) -> None:
    deleted = await conn.fetchval(
        "DELETE FROM articles WHERE id = $1 AND author_id = $2 RETURNING id",
        article_id,
        author_id,
    )
    if deleted is None:
        raise ArticleError("article_not_found", "No such article.", status=404)


async def delete_all_by(conn: asyncpg.Connection, author_id: uuid.UUID) -> int:
    """Everything one person wrote. For account erasure."""
    result = await conn.execute("DELETE FROM articles WHERE author_id = $1", author_id)
    return int(result.rsplit(" ", 1)[-1])


async def mine(conn: asyncpg.Connection, author_id: uuid.UUID, limit: int = 100) -> list[Article]:
    rows = await conn.fetch(
        f"SELECT {_COLUMNS} {_FROM} WHERE a.author_id = $1 "  # noqa: S608
        "ORDER BY a.updated_at DESC LIMIT $2",
        author_id,
        limit,
    )
    return [_article(row) for row in rows]


async def get_mine(
    conn: asyncpg.Connection, *, author_id: uuid.UUID, article_id: uuid.UUID
) -> Article:
    row = await conn.fetchrow(
        f"SELECT {_COLUMNS} {_FROM} WHERE a.id = $1 AND a.author_id = $2",  # noqa: S608
        article_id,
        author_id,
    )
    if row is None:
        raise ArticleError("article_not_found", "No such article.", status=404)
    return _article(row)


# ----- the public side --------------------------------------------------------


async def published(
    conn: asyncpg.Connection, *, limit: int, offset: int
) -> tuple[list[Article], int]:
    rows = await conn.fetch(
        f"SELECT {_COLUMNS} {_FROM} WHERE {_PUBLIC} "  # noqa: S608
        "ORDER BY a.published_at DESC, a.id DESC LIMIT $1 OFFSET $2",
        limit,
        offset,
    )
    total = await conn.fetchval(f"SELECT count(*) {_FROM} WHERE {_PUBLIC}")  # noqa: S608
    return [_article(row) for row in rows], int(total)


async def get_published(conn: asyncpg.Connection, slug: str) -> Article:
    row = await conn.fetchrow(
        f"SELECT {_COLUMNS} {_FROM} WHERE a.slug = $1 AND {_PUBLIC}",  # noqa: S608
        slug,
    )
    if row is None:
        raise ArticleError("article_not_found", "No such article.", status=404)
    return _article(row)


# ----- the operator's side ----------------------------------------------------


async def queue(
    conn: asyncpg.Connection, *, status: str, limit: int, offset: int
) -> tuple[list[Article], int, int]:
    """Articles in one state, with how many are waiting and how many are live.

    The waiting ones come oldest first — a queue. Everything else comes
    newest first, because there the question is "what happened lately".
    """
    if status not in REVIEWABLE:
        raise ArticleError("bad_status", "Unknown status.")

    order = "a.submitted_at ASC, a.id" if status == "SUBMITTED" else "a.updated_at DESC, a.id"
    rows = await conn.fetch(
        f"SELECT {_COLUMNS} {_FROM} WHERE a.status = $1::article_status "  # noqa: S608
        f"ORDER BY {order} LIMIT $2 OFFSET $3",
        status,
        limit,
        offset,
    )
    counts = await conn.fetchrow(
        """
        SELECT count(*) FILTER (WHERE status = 'SUBMITTED') AS waiting,
               count(*) FILTER (WHERE status = 'PUBLISHED') AS live
          FROM articles
        """
    )
    return [_article(row) for row in rows], int(counts["waiting"]), int(counts["live"])


async def review(
    conn: asyncpg.Connection,
    *,
    reviewer_id: uuid.UUID,
    article_id: uuid.UUID,
    decision: str,
    note: str | None,
) -> Article:
    """Publish, send back, or take down.

    Saying no always takes a reason, and the author is shown it. A refusal
    with nothing attached leaves somebody guessing what to change, and the
    next submission is the same article.
    """
    note = clean_note(note)
    current = await conn.fetchrow(
        "SELECT status::text AS status FROM articles WHERE id = $1 FOR UPDATE", article_id
    )
    if current is None:
        raise ArticleError("article_not_found", "No such article.", status=404)
    status = current["status"]

    if decision == "publish":
        if status != "SUBMITTED":
            raise ArticleError(
                "not_awaiting_review", "This article is not waiting for review.", status=409
            )
        await conn.execute(
            """
            UPDATE articles
               SET status = 'PUBLISHED', review_note = NULL,
                   reviewed_at = NOW(), reviewed_by = $2,
                   published_at = COALESCE(published_at, NOW())
             WHERE id = $1
            """,
            article_id,
            reviewer_id,
        )
        return await _load(conn, article_id)

    if decision == "reject":
        required, new_status = "SUBMITTED", "REJECTED"
        wrong = ("not_awaiting_review", "This article is not waiting for review.")
    elif decision == "remove":
        required, new_status = "PUBLISHED", "REMOVED"
        wrong = ("not_published", "This article is not published.")
    else:
        raise ArticleError("bad_decision", "Decision must be publish, reject or remove.")

    if status != required:
        raise ArticleError(wrong[0], wrong[1], status=409)
    if note is None:
        raise ArticleError("note_required", "Say why, so the author knows what to change.")

    await conn.execute(
        """
        UPDATE articles
           SET status = $2::article_status, review_note = $3,
               reviewed_at = NOW(), reviewed_by = $4
         WHERE id = $1
        """,
        article_id,
        new_status,
        note,
        reviewer_id,
    )
    return await _load(conn, article_id)
