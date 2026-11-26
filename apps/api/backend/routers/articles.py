"""Articles: reading them, writing them, and deciding which are published.

Three routers, because there are three audiences and they share nothing but
the table.

`/v1/articles` is public. It serves what a search engine and a stranger see,
so it returns published articles and nothing else — no status, no ids, no
reviewer's note.

`/v1/me/articles` is the author's desk: their own work in every state.

`/v1/admin/articles` is the review queue, behind the same allowlist as the
rest of the operator pages.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from .. import db
from ..config import Settings, get_settings
from ..repositories import articles as articles_repo
from ..repositories.articles import Article
from ..schemas import (
    ArticleDraft,
    ArticleLimits,
    ArticleOut,
    ArticlePage,
    ArticleQueueOut,
    ArticleReview,
    ArticleSummaryOut,
    MyArticleList,
    MyArticleOut,
    QueuedArticleOut,
)
from ..security.dependencies import CurrentAdmin, CurrentUser, is_admin

public = APIRouter(prefix="/v1/articles", tags=["articles"])
desk = APIRouter(prefix="/v1/me/articles", tags=["articles"])
review = APIRouter(prefix="/v1/admin/articles", tags=["admin"])


def _summary(article: Article) -> ArticleSummaryOut:
    return ArticleSummaryOut(
        slug=article.slug,
        title=article.title,
        summary=article.summary,
        author=article.author_name,
        # Published articles always carry a date; the constraint says so.
        published_at=article.published_at or article.created_at,
        edited_at=article.edited_at,
        reading_minutes=article.reading_minutes,
    )


def _mine(article: Article) -> MyArticleOut:
    return MyArticleOut(
        id=str(article.id),
        slug=article.slug,
        title=article.title,
        summary=article.summary,
        body=article.body,
        status=article.status,
        review_note=article.review_note,
        reading_minutes=article.reading_minutes,
        created_at=article.created_at,
        edited_at=article.edited_at,
        submitted_at=article.submitted_at,
        published_at=article.published_at,
    )


def _queued(article: Article) -> QueuedArticleOut:
    return QueuedArticleOut(
        **_mine(article).model_dump(),
        author=article.author_name,
        author_code=article.author_code,
    )


def _limits(settings: Settings) -> ArticleLimits:
    return ArticleLimits(
        title_min=articles_repo.TITLE_MIN,
        title_max=articles_repo.TITLE_MAX,
        summary_min=articles_repo.SUMMARY_MIN,
        summary_max=articles_repo.SUMMARY_MAX,
        body_min=articles_repo.BODY_MIN,
        body_max=articles_repo.BODY_MAX,
        max_open=settings.article_max_open,
    )


# ----- public -----------------------------------------------------------------


@public.get("", response_model=ArticlePage, summary="Published articles, newest first")
async def list_published(
    limit: Annotated[int, Query(ge=1, le=200)] = 30,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
) -> ArticlePage:
    async with db.acquire() as conn:
        rows, total = await articles_repo.published(conn, limit=limit, offset=offset)
    return ArticlePage(articles=[_summary(a) for a in rows], total=total)


@public.get("/{slug}", response_model=ArticleOut, summary="One published article")
async def read_published(slug: str) -> ArticleOut:
    async with db.acquire() as conn:
        article = await articles_repo.get_published(conn, slug.strip().lower()[:128])
    return ArticleOut(**_summary(article).model_dump(), body=article.body)


# ----- the author's desk ------------------------------------------------------


@desk.get("", response_model=MyArticleList, summary="Your own articles, in every state")
async def my_articles(
    user: CurrentUser, settings: Annotated[Settings, Depends(get_settings)]
) -> MyArticleList:
    """Open to guests too, who get an empty list and `can_write: false` — the
    page needs to know to offer them an account rather than an editor."""
    async with db.acquire() as conn:
        rows = await articles_repo.mine(conn, user["id"])
    return MyArticleList(
        articles=[_mine(a) for a in rows],
        limits=_limits(settings),
        can_write=not user["is_guest"] and user["status"] == "ACTIVE",
        publishes_directly=is_admin(user, settings),
    )


@desk.post("", response_model=MyArticleOut, status_code=201, summary="Start a draft")
async def create_article(
    payload: ArticleDraft,
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> MyArticleOut:
    async with db.transaction() as conn:
        article = await articles_repo.create(
            conn,
            author=user,
            title=payload.title,
            summary=payload.summary,
            body=payload.body,
            max_open=settings.article_max_open,
        )
    return _mine(article)


@desk.get("/{article_id}", response_model=MyArticleOut, summary="One of your articles")
async def my_article(article_id: uuid.UUID, user: CurrentUser) -> MyArticleOut:
    async with db.acquire() as conn:
        article = await articles_repo.get_mine(conn, author_id=user["id"], article_id=article_id)
    return _mine(article)


@desk.put("/{article_id}", response_model=MyArticleOut, summary="Save changes to a draft")
async def update_article(
    article_id: uuid.UUID, payload: ArticleDraft, user: CurrentUser
) -> MyArticleOut:
    async with db.transaction() as conn:
        article = await articles_repo.update(
            conn,
            author=user,
            article_id=article_id,
            title=payload.title,
            summary=payload.summary,
            body=payload.body,
        )
    return _mine(article)


@desk.post(
    "/{article_id}/submit",
    response_model=MyArticleOut,
    summary="Send an article for review",
)
async def submit_article(
    article_id: uuid.UUID,
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> MyArticleOut:
    async with db.transaction() as conn:
        article = await articles_repo.submit(
            conn,
            author=user,
            article_id=article_id,
            publish_directly=is_admin(user, settings),
            window_seconds=settings.article_submit_rate_window_seconds,
            max_in_window=settings.article_submit_rate_max,
        )
    return _mine(article)


@desk.post(
    "/{article_id}/withdraw",
    response_model=MyArticleOut,
    summary="Take an article back out of review, or off the site",
)
async def withdraw_article(article_id: uuid.UUID, user: CurrentUser) -> MyArticleOut:
    async with db.transaction() as conn:
        article = await articles_repo.withdraw(conn, author=user, article_id=article_id)
    return _mine(article)


@desk.delete("/{article_id}", status_code=204, summary="Delete one of your articles")
async def delete_article(article_id: uuid.UUID, user: CurrentUser) -> Response:
    async with db.transaction() as conn:
        await articles_repo.delete(conn, author_id=user["id"], article_id=article_id)
    return Response(status_code=204)


# ----- the review queue -------------------------------------------------------


@review.get("", response_model=ArticleQueueOut, summary="Articles waiting, live, or refused")
async def read_queue(
    _: CurrentAdmin,
    status: Annotated[str, Query(pattern="^(SUBMITTED|PUBLISHED|REJECTED|REMOVED)$")] = "SUBMITTED",
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ArticleQueueOut:
    async with db.acquire() as conn:
        rows, waiting, live = await articles_repo.queue(
            conn, status=status, limit=limit, offset=offset
        )
    return ArticleQueueOut(articles=[_queued(a) for a in rows], waiting=waiting, live=live)


@review.post(
    "/{article_id}/review",
    response_model=QueuedArticleOut,
    summary="Publish an article, send it back, or take it down",
)
async def review_article(
    article_id: uuid.UUID, payload: ArticleReview, admin: CurrentAdmin
) -> QueuedArticleOut:
    async with db.transaction() as conn:
        article = await articles_repo.review(
            conn,
            reviewer_id=admin["id"],
            article_id=article_id,
            decision=payload.decision,
            note=payload.note,
        )
    return _queued(article)
