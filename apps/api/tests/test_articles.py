"""Articles: who may write, what becomes public, and who decides.

The property everything else here leans on is that **nothing an operator has
not read is ever served by the public routes**. A site that search engines
file under gambling, with a box that publishes what is typed into it, fills
with casino advertisements — so the tests that matter most are the ones that
try to get an unreviewed article out through the front door.

The second is that an author can always take their own writing back: withdraw
it, delete it, or have it go with the account.
"""

from __future__ import annotations

import pytest
from conftest import TEST_PASSWORD, authorise, email_for, make_admin, user_id_for

from backend import db
from backend.config import get_settings
from backend.repositories import articles as articles_repo

PUBLIC = "/v1/articles"
DESK = "/v1/me/articles"
QUEUE = "/v1/admin/articles"

BODY = (
    "A bookmaker's price is not a forecast with a fee on top. It is a forecast with the "
    "fee folded in, which is why the fee is so easy to miss.\n\n"
    "## Where the margin sits\n\n"
    "Take a coin toss. A fair price for heads is two to one: stake one, get two back. "
    "A bookmaker offers 1.91 instead, on both sides. Back both and you are certain to "
    "lose, which is the point.\n\n"
    "## Why it compounds\n\n"
    "Put three such bets on one slip and the three margins multiply. What looked like "
    "five percent is now closer to fourteen, and nothing on the slip says so. That is "
    "the whole trick, and it is not a secret — it is just never the headline.\n\n"
    "- A single pick carries one margin.\n"
    "- Three picks carry three, multiplied.\n"
    "- The more exciting the slip, the worse the price.\n"
)

DRAFT = {
    "title": "Where the bookmaker's margin hides",
    "summary": "A price that looks fair on one bet is doing something else on three. "
    "This is the arithmetic, with nothing left out.",
    "body": BODY,
}


async def write(client, headers, **changes) -> dict:
    response = await client.post(DESK, headers=headers, json={**DRAFT, **changes})
    assert response.status_code == 201, response.text
    return response.json()


async def submit(client, headers, article_id: str):
    return await client.post(f"{DESK}/{article_id}/submit", headers=headers)


async def decide(client, admin, article_id: str, decision: str, note: str | None = None):
    return await client.post(
        f"{QUEUE}/{article_id}/review", headers=admin, json={"decision": decision, "note": note}
    )


async def publish_one(client, author, admin, **changes) -> dict:
    article = await write(client, author, **changes)
    assert (await submit(client, author, article["id"])).status_code == 200
    response = await decide(client, admin, article["id"], "publish")
    assert response.status_code == 200, response.text
    return response.json()


async def public_slugs(client) -> list[str]:
    return [a["slug"] for a in (await client.get(PUBLIC)).json()["articles"]]


async def guest(client) -> dict[str, str]:
    response = await client.post("/v1/auth/guest")
    response.raise_for_status()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


# ----- who may write ----------------------------------------------------------


async def test_a_signed_in_account_can_start_a_draft(app_client):
    author = await authorise(app_client, 6001)
    article = await write(app_client, author)

    assert article["status"] == "DRAFT"
    assert article["title"] == DRAFT["title"]
    assert article["reading_minutes"] >= 1
    assert article["published_at"] is None


async def test_writing_needs_a_session(app_client):
    assert (await app_client.post(DESK, json=DRAFT)).status_code == 401
    assert (await app_client.get(DESK)).status_code == 401


async def test_a_guest_is_told_to_make_an_account_rather_than_given_an_editor(app_client):
    """A guest is a cookie. A byline should outlive a browser being cleared,
    and every article should have an account behind it that can be restricted."""
    visitor = await guest(app_client)

    refused = await app_client.post(DESK, headers=visitor, json=DRAFT)
    assert refused.status_code == 403
    assert refused.json()["code"] == "account_required"

    desk = (await app_client.get(DESK, headers=visitor)).json()
    assert desk["can_write"] is False
    assert desk["articles"] == []


async def test_a_restricted_account_cannot_write_or_submit(app_client):
    author = await authorise(app_client, 6002)
    article = await write(app_client, author)
    async with db.acquire() as conn:
        await conn.execute(
            "UPDATE users SET status = 'RESTRICTED' WHERE email = $1", email_for(6002)
        )

    for response in (
        await app_client.post(DESK, headers=author, json=DRAFT),
        await app_client.put(f"{DESK}/{article['id']}", headers=author, json=DRAFT),
        await submit(app_client, author, article["id"]),
    ):
        assert response.status_code == 403
        assert response.json()["code"] == "account_restricted"

    assert (await app_client.get(DESK, headers=author)).json()["can_write"] is False


async def test_the_desk_states_the_rules_it_enforces(app_client):
    """The form quotes its limits from here, so a limit changed in one place
    cannot leave the form promising the old one."""
    author = await authorise(app_client, 6003)
    limits = (await app_client.get(DESK, headers=author)).json()["limits"]

    assert limits == {
        "title_min": articles_repo.TITLE_MIN,
        "title_max": articles_repo.TITLE_MAX,
        "summary_min": articles_repo.SUMMARY_MIN,
        "summary_max": articles_repo.SUMMARY_MAX,
        "body_min": articles_repo.BODY_MIN,
        "body_max": articles_repo.BODY_MAX,
        "max_open": get_settings().article_max_open,
    }


# ----- what may be written ----------------------------------------------------


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("title", "Short", "title_too_short"),
        ("title", "T" * 111, "title_too_long"),
        ("summary", "Too brief to describe anything.", "summary_too_short"),
        ("summary", "S" * 221, "summary_too_long"),
        ("body", "One paragraph is not an article.", "body_too_short"),
        ("body", "word " * 6_100, "body_too_long"),
    ],
)
async def test_a_draft_outside_the_limits_is_refused_by_name(app_client, field, value, code):
    author = await authorise(app_client, 6004)
    response = await app_client.post(DESK, headers=author, json={**DRAFT, field: value})

    assert response.status_code == 400
    assert response.json()["code"] == code


async def test_padding_does_not_reach_a_minimum(app_client):
    """Whitespace is collapsed before anything is measured."""
    author = await authorise(app_client, 6005)
    response = await app_client.post(
        DESK, headers=author, json={**DRAFT, "title": "Hi" + " " * 40 + "\n\n"}
    )
    assert response.json()["code"] == "title_too_short"


async def test_what_is_stored_is_tidied_but_not_rewritten(app_client):
    author = await authorise(app_client, 6006)
    messy = BODY.replace("\n", "\r\n") + "\n\n\n\n\x00trailing   \n\n\n"
    article = await write(app_client, author, title="  Where   the margin\nhides  ", body=messy)

    assert article["title"] == "Where the margin hides"
    assert "\r" not in article["body"]
    assert "\x00" not in article["body"]
    assert "\n\n\n" not in article["body"]
    assert article["body"].endswith("trailing")
    assert "## Where the margin sits" in article["body"]


async def test_markup_is_kept_as_the_text_it_is(app_client):
    """Nothing is stripped on the way in. The renderer shows HTML as text and
    renders no images, so there is nothing here to sanitise and nothing to get
    wrong by trying."""
    author = await authorise(app_client, 6007)
    hostile = BODY + '\n\n<script>alert("x")</script>\n\n![pixel](https://tracker.example/p.gif)'
    article = await write(app_client, author, body=hostile)

    assert "<script>" in article["body"]


async def test_an_oversized_request_is_refused_before_any_work(app_client):
    author = await authorise(app_client, 6008)
    response = await app_client.post(DESK, headers=author, json={**DRAFT, "body": "x" * 130_000})
    assert response.status_code == 422


async def test_unfinished_articles_are_capped(app_client):
    get_settings().article_max_open = 2
    author = await authorise(app_client, 6009)
    await write(app_client, author)
    await write(app_client, author)

    third = await app_client.post(DESK, headers=author, json=DRAFT)
    assert third.status_code == 409
    assert third.json()["code"] == "too_many_drafts"


# ----- addresses --------------------------------------------------------------


async def test_the_address_is_readable_and_unique(app_client):
    author = await authorise(app_client, 6010)
    first = await write(app_client, author)
    second = await write(app_client, author)

    assert first["slug"].startswith("where-the-bookmaker-s-margin-hides-")
    assert first["slug"] != second["slug"]


@pytest.mark.parametrize(
    ("title", "stem"),
    [
        ("Café society & the 3:1 shot", "cafe-society-the-3-1-shot"),
        ("  --Leading and trailing--  ", "leading-and-trailing"),
        ("چرا شرط نمی‌بندم دیگر", "article"),
        ("A" * 200, "a" * 70),
    ],
)
def test_a_title_becomes_a_plain_address(title, stem):
    assert articles_repo.slug_stem(title) == stem


async def test_the_address_follows_the_title_until_first_publication(app_client):
    author = await authorise(app_client, 6011)
    admin = await make_admin(app_client)
    article = await write(app_client, author)
    suffix = article["slug"].rsplit("-", 1)[-1]

    renamed = await app_client.put(
        f"{DESK}/{article['id']}",
        headers=author,
        json={**DRAFT, "title": "A better headline altogether"},
    )
    assert renamed.json()["slug"] == f"a-better-headline-altogether-{suffix}"

    await submit(app_client, author, article["id"])
    await decide(app_client, admin, article["id"], "publish")
    await app_client.post(f"{DESK}/{article['id']}/withdraw", headers=author)

    again = await app_client.put(
        f"{DESK}/{article['id']}",
        headers=author,
        json={**DRAFT, "title": "Changed after it was public"},
    )
    assert again.json()["slug"] == f"a-better-headline-altogether-{suffix}"


# ----- nothing unreviewed is public -------------------------------------------


async def test_a_draft_is_not_public(app_client):
    author = await authorise(app_client, 6020)
    article = await write(app_client, author)

    assert await public_slugs(app_client) == []
    assert (await app_client.get(f"{PUBLIC}/{article['slug']}")).status_code == 404


async def test_a_submitted_article_is_not_public(app_client):
    author = await authorise(app_client, 6021)
    article = await write(app_client, author)
    submitted = await submit(app_client, author, article["id"])

    assert submitted.json()["status"] == "SUBMITTED"
    assert await public_slugs(app_client) == []
    assert (await app_client.get(f"{PUBLIC}/{article['slug']}")).status_code == 404


async def test_an_author_cannot_publish_their_own_article(app_client):
    """The review route is the operator's. To everybody else it does not
    exist, for the reason the other operator routes do not."""
    author = await authorise(app_client, 6022)
    article = await write(app_client, author)
    await submit(app_client, author, article["id"])

    attempt = await decide(app_client, author, article["id"], "publish")
    assert attempt.status_code == 404
    assert (await app_client.get(QUEUE, headers=author)).status_code == 404
    assert await public_slugs(app_client) == []


async def test_publishing_makes_it_public_with_a_byline(app_client):
    author = await authorise(app_client, 6023)
    admin = await make_admin(app_client)
    published = await publish_one(app_client, author, admin)

    listing = (await app_client.get(PUBLIC)).json()
    assert listing["total"] == 1
    entry = listing["articles"][0]
    assert entry["slug"] == published["slug"]
    assert entry["author"] == "Player 6023"
    assert "body" not in entry

    article = (await app_client.get(f"{PUBLIC}/{published['slug']}")).json()
    assert article["body"] == published["body"]
    assert article["reading_minutes"] >= 1


async def test_the_public_routes_say_nothing_about_review(app_client):
    """No ids, no status, no reviewer's note, no player code: the public
    shape is the article and its byline."""
    author = await authorise(app_client, 6024)
    admin = await make_admin(app_client)
    published = await publish_one(app_client, author, admin)

    article = (await app_client.get(f"{PUBLIC}/{published['slug']}")).json()
    assert set(article) == {
        "slug",
        "title",
        "summary",
        "author",
        "published_at",
        "edited_at",
        "reading_minutes",
        "body",
    }


async def test_only_an_article_awaiting_review_can_be_published(app_client):
    author = await authorise(app_client, 6025)
    admin = await make_admin(app_client)
    article = await write(app_client, author)

    early = await decide(app_client, admin, article["id"], "publish")
    assert early.status_code == 409
    assert early.json()["code"] == "not_awaiting_review"
    assert await public_slugs(app_client) == []


async def test_an_article_cannot_be_changed_while_somebody_is_reading_it(app_client):
    """Otherwise what is approved is not what was read."""
    author = await authorise(app_client, 6026)
    article = await write(app_client, author)
    await submit(app_client, author, article["id"])

    edit = await app_client.put(
        f"{DESK}/{article['id']}", headers=author, json={**DRAFT, "body": BODY + "\n\nCasino!"}
    )
    assert edit.status_code == 409
    assert edit.json()["code"] == "article_locked"


async def test_a_published_article_cannot_be_edited_in_place(app_client):
    author = await authorise(app_client, 6027)
    admin = await make_admin(app_client)
    published = await publish_one(app_client, author, admin)

    edit = await app_client.put(
        f"{DESK}/{published['id']}", headers=author, json={**DRAFT, "body": BODY + "\n\nNew."}
    )
    assert edit.status_code == 409
    article = (await app_client.get(f"{PUBLIC}/{published['slug']}")).json()
    assert "New." not in article["body"]


async def test_changing_a_published_article_takes_it_back_through_review(app_client):
    author = await authorise(app_client, 6028)
    admin = await make_admin(app_client)
    published = await publish_one(app_client, author, admin)

    withdrawn = await app_client.post(f"{DESK}/{published['id']}/withdraw", headers=author)
    assert withdrawn.json()["status"] == "DRAFT"
    assert await public_slugs(app_client) == []

    await app_client.put(
        f"{DESK}/{published['id']}", headers=author, json={**DRAFT, "body": BODY + "\n\nNew."}
    )
    resubmitted = await submit(app_client, author, published["id"])
    assert resubmitted.json()["status"] == "SUBMITTED"
    assert await public_slugs(app_client) == []


async def test_a_banned_author_disappears_from_the_public_pages(app_client):
    author = await authorise(app_client, 6029)
    admin = await make_admin(app_client)
    published = await publish_one(app_client, author, admin)
    async with db.acquire() as conn:
        await conn.execute("UPDATE users SET status = 'BANNED' WHERE email = $1", email_for(6029))

    assert await public_slugs(app_client) == []
    assert (await app_client.get(f"{PUBLIC}/{published['slug']}")).status_code == 404


# ----- the reviewer -----------------------------------------------------------


async def test_the_queue_is_oldest_first_and_counts_what_waits(app_client):
    admin = await make_admin(app_client)
    first = await authorise(app_client, 6030)
    second = await authorise(app_client, 6031)
    one = await write(app_client, first, title="The first one submitted")
    two = await write(app_client, second, title="The second one submitted")
    await submit(app_client, first, one["id"])
    await submit(app_client, second, two["id"])

    queue = (await app_client.get(QUEUE, headers=admin)).json()
    assert [a["id"] for a in queue["articles"]] == [one["id"], two["id"]]
    assert queue["waiting"] == 2
    assert queue["live"] == 0
    assert queue["articles"][0]["author"] == "Player 6030"
    assert len(queue["articles"][0]["author_code"]) == 6


async def test_an_operator_never_sees_an_unsubmitted_draft(app_client):
    """A draft is private, including from the people who run the site."""
    admin = await make_admin(app_client)
    author = await authorise(app_client, 6032)
    await write(app_client, author)

    for status in ("SUBMITTED", "PUBLISHED", "REJECTED", "REMOVED"):
        listed = (await app_client.get(QUEUE, headers=admin, params={"status": status})).json()
        assert listed["articles"] == []
    assert (
        await app_client.get(QUEUE, headers=admin, params={"status": "DRAFT"})
    ).status_code == 422


async def test_sending_an_article_back_takes_a_reason_and_shows_it(app_client):
    admin = await make_admin(app_client)
    author = await authorise(app_client, 6033)
    article = await write(app_client, author)
    await submit(app_client, author, article["id"])

    silent = await decide(app_client, admin, article["id"], "reject", "   ")
    assert silent.status_code == 400
    assert silent.json()["code"] == "note_required"

    sent_back = await decide(
        app_client, admin, article["id"], "reject", "The second section links to a betting site."
    )
    assert sent_back.json()["status"] == "REJECTED"

    mine = (await app_client.get(f"{DESK}/{article['id']}", headers=author)).json()
    assert mine["status"] == "REJECTED"
    assert mine["review_note"] == "The second section links to a betting site."


async def test_a_rejected_article_can_be_fixed_and_sent_again(app_client):
    admin = await make_admin(app_client)
    author = await authorise(app_client, 6034)
    article = await write(app_client, author)
    await submit(app_client, author, article["id"])
    await decide(app_client, admin, article["id"], "reject", "Too thin.")

    fixed = await app_client.put(
        f"{DESK}/{article['id']}", headers=author, json={**DRAFT, "body": BODY + "\n\nMore."}
    )
    assert fixed.json()["status"] == "DRAFT"
    # The note is what the author is working from; it stays until they resubmit.
    assert fixed.json()["review_note"] == "Too thin."

    again = await submit(app_client, author, article["id"])
    assert again.json()["status"] == "SUBMITTED"
    assert again.json()["review_note"] is None


async def test_taking_a_published_article_down_takes_a_reason(app_client):
    admin = await make_admin(app_client)
    author = await authorise(app_client, 6035)
    published = await publish_one(app_client, author, admin)

    assert (await decide(app_client, admin, published["id"], "remove")).status_code == 400

    removed = await decide(app_client, admin, published["id"], "remove", "Out of date.")
    assert removed.json()["status"] == "REMOVED"
    assert await public_slugs(app_client) == []
    assert (await app_client.get(f"{PUBLIC}/{published['slug']}")).status_code == 404

    mine = (await app_client.get(f"{DESK}/{published['id']}", headers=author)).json()
    assert mine["review_note"] == "Out of date."


async def test_only_a_published_article_can_be_taken_down(app_client):
    admin = await make_admin(app_client)
    author = await authorise(app_client, 6036)
    article = await write(app_client, author)
    await submit(app_client, author, article["id"])

    response = await decide(app_client, admin, article["id"], "remove", "No.")
    assert response.status_code == 409
    assert response.json()["code"] == "not_published"


async def test_an_operators_own_article_publishes_when_submitted(app_client):
    """The queue is the operator. Asking them to approve what they just wrote
    adds a click and no second pair of eyes."""
    admin = await make_admin(app_client)
    desk = (await app_client.get(DESK, headers=admin)).json()
    assert desk["publishes_directly"] is True

    article = await write(app_client, admin)
    published = await submit(app_client, admin, article["id"])

    assert published.json()["status"] == "PUBLISHED"
    assert await public_slugs(app_client) == [article["slug"]]


async def test_an_ordinary_author_is_told_review_comes_first(app_client):
    author = await authorise(app_client, 6037)
    assert (await app_client.get(DESK, headers=author)).json()["publishes_directly"] is False


async def test_submissions_are_limited_per_day_and_resubmitting_is_not_counted(app_client):
    settings = get_settings()
    settings.article_submit_rate_max = 2
    author = await authorise(app_client, 6038)
    articles = [
        await write(app_client, author, title=f"Submission number {n} of three") for n in range(3)
    ]

    assert (await submit(app_client, author, articles[0]["id"])).status_code == 200
    assert (await submit(app_client, author, articles[1]["id"])).status_code == 200

    third = await submit(app_client, author, articles[2]["id"])
    assert third.status_code == 429
    assert third.json()["code"] == "too_many_submissions"

    # Taking one back and sending it again is the same article in the queue.
    await app_client.post(f"{DESK}/{articles[0]['id']}/withdraw", headers=author)
    assert (await submit(app_client, author, articles[0]["id"])).status_code == 200


async def test_submitting_twice_is_refused_rather_than_repeated(app_client):
    author = await authorise(app_client, 6039)
    article = await write(app_client, author)
    await submit(app_client, author, article["id"])

    again = await submit(app_client, author, article["id"])
    assert again.status_code == 409
    assert again.json()["code"] == "article_not_submittable"


# ----- it stays the author's --------------------------------------------------


async def test_somebody_elses_article_does_not_exist(app_client):
    """Not found, not forbidden: a different answer would confirm which ids
    are real."""
    owner = await authorise(app_client, 6040)
    stranger = await authorise(app_client, 6041)
    article = await write(app_client, owner)
    url = f"{DESK}/{article['id']}"

    for response in (
        await app_client.get(url, headers=stranger),
        await app_client.put(url, headers=stranger, json=DRAFT),
        await app_client.post(f"{url}/submit", headers=stranger),
        await app_client.post(f"{url}/withdraw", headers=stranger),
        await app_client.delete(url, headers=stranger),
    ):
        assert response.status_code == 404
        assert response.json()["code"] == "article_not_found"

    assert (await app_client.get(url, headers=owner)).status_code == 200


async def test_an_author_can_delete_their_work_in_any_state(app_client):
    admin = await make_admin(app_client)
    author = await authorise(app_client, 6042)
    draft = await write(app_client, author, title="Deleted while a draft")
    waiting = await write(app_client, author, title="Deleted while waiting")
    await submit(app_client, author, waiting["id"])
    live = await publish_one(app_client, author, admin, title="Deleted while live")

    for article in (draft, waiting, live):
        assert (
            await app_client.delete(f"{DESK}/{article['id']}", headers=author)
        ).status_code == 204

    assert (await app_client.get(DESK, headers=author)).json()["articles"] == []
    assert await public_slugs(app_client) == []
    assert (await app_client.get(QUEUE, headers=admin)).json()["waiting"] == 0


async def test_a_restricted_author_can_still_withdraw(app_client):
    """An account that may no longer publish can always stop publishing."""
    admin = await make_admin(app_client)
    author = await authorise(app_client, 6043)
    published = await publish_one(app_client, author, admin)
    async with db.acquire() as conn:
        await conn.execute(
            "UPDATE users SET status = 'RESTRICTED' WHERE email = $1", email_for(6043)
        )

    withdrawn = await app_client.post(f"{DESK}/{published['id']}/withdraw", headers=author)
    assert withdrawn.status_code == 200
    assert await public_slugs(app_client) == []


async def test_deleting_an_account_takes_its_articles_with_it(app_client):
    """Published ones included. Leaving somebody's writing up under "Deleted
    player" keeps the part of them a stranger is most likely to recognise."""
    admin = await make_admin(app_client)
    author = await authorise(app_client, 6044)
    await write(app_client, author, title="A draft that goes too")
    published = await publish_one(app_client, author, admin)
    author_id = await user_id_for(6044)

    erased = await app_client.post("/v1/me/erase", headers=author, json={"password": TEST_PASSWORD})
    assert erased.status_code == 204

    assert await public_slugs(app_client) == []
    assert (await app_client.get(f"{PUBLIC}/{published['slug']}")).status_code == 404
    async with db.acquire() as conn:
        assert (
            await conn.fetchval("SELECT count(*) FROM articles WHERE author_id = $1", author_id)
            == 0
        )


# ----- the listing ------------------------------------------------------------


async def test_the_listing_is_newest_first_and_pages(app_client):
    admin = await make_admin(app_client)
    author = await authorise(app_client, 6050)
    slugs = []
    for n in range(3):
        slugs.append(
            (await publish_one(app_client, author, admin, title=f"Published article number {n}"))[
                "slug"
            ]
        )

    page = (await app_client.get(PUBLIC, params={"limit": 2})).json()
    assert [a["slug"] for a in page["articles"]] == [slugs[2], slugs[1]]
    assert page["total"] == 3

    rest = (await app_client.get(PUBLIC, params={"limit": 2, "offset": 2})).json()
    assert [a["slug"] for a in rest["articles"]] == [slugs[0]]


async def test_an_address_is_matched_exactly(app_client):
    admin = await make_admin(app_client)
    author = await authorise(app_client, 6051)
    published = await publish_one(app_client, author, admin)

    assert (await app_client.get(f"{PUBLIC}/{published['slug'].upper()}")).status_code == 200
    assert (await app_client.get(f"{PUBLIC}/{published['slug'][:-1]}")).status_code == 404
    assert (await app_client.get(f"{PUBLIC}/'; DROP TABLE articles; --")).status_code == 404


# ----- the schema keeps its side ----------------------------------------------


async def test_the_database_refuses_a_refusal_without_a_reason(app_client):
    author = await authorise(app_client, 6060)
    article = await write(app_client, author)

    async with db.acquire() as conn:
        with pytest.raises(Exception, match="ck_articles_refusal_has_note"):
            await conn.execute(
                "UPDATE articles SET status = 'REJECTED' WHERE id = $1::uuid", article["id"]
            )


async def test_the_database_refuses_a_published_article_with_no_date(app_client):
    author = await authorise(app_client, 6061)
    article = await write(app_client, author)

    async with db.acquire() as conn:
        with pytest.raises(Exception, match="ck_articles_published_is_dated"):
            await conn.execute(
                "UPDATE articles SET status = 'PUBLISHED' WHERE id = $1::uuid", article["id"]
            )
