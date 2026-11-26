"""Market text is translated on ingestion, cached, and never at the cost of it."""

from __future__ import annotations

import httpx
import pytest
from conftest import mock_http_client
from fixtures import gamma_events as fx

from backend import db
from backend.config import Settings, get_settings
from backend.services import translation
from backend.workers import polymarket_discovery as discovery


class RecordingProvider:
    """Translates by prefixing, so a translated string is unmistakable."""

    name = "recording"

    def __init__(self) -> None:
        self.batches: list[list[str]] = []
        self.fail = False

    async def translate(self, texts, *, source_lang, target_lang):
        if self.fail:
            raise translation.UpstreamUnavailable("provider is down")
        self.batches.append(list(texts))
        return [f"[fa] {text}" for text in texts]

    @property
    def calls(self) -> int:
        return len(self.batches)

    @property
    def translated_count(self) -> int:
        return sum(len(batch) for batch in self.batches)


def gamma_serving(events):
    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("offset", 0))
        return httpx.Response(200, json=events if offset == 0 else [])

    return handler


async def run_discovery_with(provider, settings, events=None):
    """Drive discovery with a substituted translation provider."""
    events = events or [fx.event("1")]
    original = translation.build_provider
    translation.build_provider = lambda client, s: provider
    discovery.build_provider = lambda client, s: provider
    try:
        async with mock_http_client(gamma_serving(events)) as client:
            return await discovery.run_discovery(client, settings)
    finally:
        translation.build_provider = original
        discovery.build_provider = original


async def market_rows():
    async with db.acquire() as conn:
        return [dict(r) for r in await conn.fetch("SELECT * FROM markets")]


async def event_rows():
    async with db.acquire() as conn:
        return [dict(r) for r in await conn.fetch("SELECT * FROM market_events")]


async def test_player_facing_text_is_translated_before_it_is_stored(resources):
    provider = RecordingProvider()
    report = await run_discovery_with(provider, resources)

    assert report.markets_created == 1
    market = (await market_rows())[0]
    event = (await event_rows())[0]

    assert market["question"].startswith("[fa] ")
    assert event["title"].startswith("[fa] ")
    assert report.translation["translated"] > 0


async def test_the_english_source_is_kept_alongside_it(resources):
    """A mistranslated market has to be checkable against what Polymarket
    actually asked, and a second locale must not translate Farsi to Farsi."""
    await run_discovery_with(RecordingProvider(), resources)

    market = (await market_rows())[0]
    event = (await event_rows())[0]

    assert market["question_source"] == "Will the Fed cut rates by 25 bps in September?"
    assert market["question"] == f"[fa] {market['question_source']}"
    assert event["title_source"] == "Fed decision in September"


async def test_join_keys_are_never_translated(resources):
    """Translating one of these would silently detach the market from the
    price feed and from resolution."""
    await run_discovery_with(RecordingProvider(), resources)
    market = (await market_rows())[0]

    assert market["polymarket_market_id"] == "51234"
    assert market["condition_id"] == "0xcond51234"
    assert market["yes_token_id"] == "tok-yes-51234"
    assert market["no_token_id"] == "tok-no-51234"
    assert market["category"] == "Macro"


async def test_a_second_run_translates_nothing_new(resources):
    """Discovery re-upserts hourly. Without the cache that is one paid call
    per market per hour, forever, for text that has not changed."""
    provider = RecordingProvider()

    first = await run_discovery_with(provider, resources)
    calls_after_first = provider.calls
    second = await run_discovery_with(provider, resources)

    assert first.translation["translated"] > 0
    assert second.translation["translated"] == 0
    assert second.translation["from_cache"] == first.translation["translated"]
    assert provider.calls == calls_after_first


async def test_only_genuinely_new_text_reaches_the_provider(resources):
    provider = RecordingProvider()
    await run_discovery_with(provider, resources)
    seen_first = provider.translated_count

    changed = fx.event("1", markets=[fx.binary_market("51234")])
    changed["markets"][0]["question"] = "Will the Fed cut rates by 50 bps in September?"
    await run_discovery_with(provider, resources, events=[changed])

    assert provider.translated_count == seen_first + 1
    assert provider.batches[-1] == ["Will the Fed cut rates by 50 bps in September?"]


async def test_the_cache_is_content_addressed(resources):
    await run_discovery_with(RecordingProvider(), resources)

    async with db.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM translations")

    assert rows
    for row in rows:
        assert row["source_hash"] == translation.source_hash(row["source_text"])
        assert row["source_lang"] == "en"
        assert row["target_lang"] == "fa"
        assert row["provider"] == "recording"


async def test_translations_survive_a_caller_transaction_that_rolls_back(resources):
    """The bug that kept the translations table empty forever.

    Localisation ran inside the transaction that also writes the markets, and
    that transaction is abandoned whole when a pass overruns its deadline. So
    against a provider slow enough to make a run overrun — which is every run,
    with a reasoning model — every translation the run had already paid for
    was rolled back with it, and the next hour started from an empty cache and
    overran in exactly the same place.
    """
    from backend.services.translation import TranslationService

    service = TranslationService(provider=RecordingProvider(), batch_size=2)

    with pytest.raises(RuntimeError):
        async with db.transaction() as conn:
            await service.translate_many(conn, ["alpha", "beta", "gamma"])
            raise RuntimeError("the pass was abandoned after translating")

    async with db.acquire() as conn:
        rows = await conn.fetch("SELECT source_text, translated_text FROM translations")

    assert {r["source_text"] for r in rows} == {"alpha", "beta", "gamma"}
    assert all(r["translated_text"].startswith("[fa] ") for r in rows)


async def test_each_batch_is_committed_as_it_lands(resources):
    """Committing once at the end is the same failure with a smaller window.

    A pass that dies partway through must keep what it had already bought, so
    the next run resumes against a warm cache instead of paying for the same
    strings again and dying in the same place.

    A batch is stored inside its own `run()` task the moment it finishes
    translating, not in the loop that consumes `asyncio.gather` — that loop
    only runs once every batch has finished, so storing there would hold a
    fast batch hostage to a slow sibling. This holds one batch open with an
    event the test controls, standing in for the deadline that cuts a real
    pass off mid-flight, and checks the batches that did finish were already
    committed while the slow one was still in flight.
    """
    import asyncio

    from backend.services.translation import TranslationService

    release = asyncio.Event()

    class StaggeredProvider(RecordingProvider):
        async def translate(self, texts, *, source_lang, target_lang):
            if texts == ["slow"]:
                await release.wait()
            return await super().translate(texts, source_lang=source_lang, target_lang=target_lang)

    service = TranslationService(provider=StaggeredProvider(), batch_size=1, concurrency=3)

    async def run_it() -> None:
        async with db.transaction() as conn:
            await service.translate_many(conn, ["one", "two", "slow"])

    task = asyncio.create_task(run_it())
    try:
        for _ in range(100):
            await asyncio.sleep(0.01)
            async with db.acquire() as conn:
                stored = {
                    r["source_text"]
                    for r in await conn.fetch("SELECT source_text FROM translations")
                }
            if len(stored) >= 2:
                break
    finally:
        release.set()
        await task

    assert stored == {"one", "two"}, (
        "batches that already finished must be visible before the slow one lands"
    )

    async with db.acquire() as conn:
        final = {r["source_text"] for r in await conn.fetch("SELECT source_text FROM translations")}
    assert final == {"one", "two", "slow"}

    assert stored == {"one", "two"}, "batches that already finished must survive the timeout"


async def test_a_translation_outage_still_ingests_markets(resources):
    """A market listed in English is degraded. No markets at all is a dead app."""
    provider = RecordingProvider()
    provider.fail = True

    report = await run_discovery_with(provider, resources)

    assert report.markets_created == 1
    assert report.translation["failed"] > 0

    market = (await market_rows())[0]
    assert market["question"] == "Will the Fed cut rates by 25 bps in September?"
    assert market["question_source"] == market["question"]


async def test_a_failed_translation_is_not_cached_as_itself(resources):
    """Caching the fallback would make an outage permanent."""
    provider = RecordingProvider()
    provider.fail = True
    await run_discovery_with(provider, resources)

    async with db.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM translations") == 0

    provider.fail = False
    await run_discovery_with(provider, resources)
    assert (await market_rows())[0]["question"].startswith("[fa] ")


async def test_the_null_provider_passes_text_through(resources):
    """The default. An unconfigured deployment ingests readable English."""
    report = await run_discovery_with(translation.NullTranslationProvider(), resources)

    assert report.markets_created == 1
    assert (await market_rows())[0]["question"].startswith("Will the Fed")

    async with db.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM translations") == 0


def settings_for(provider: str, **extra) -> Settings:
    return Settings(
        telegram_bot_token="x",
        jwt_secret="y",
        translation_provider=provider,
        translation_api_url="http://translate.test",
        **extra,
    )


async def test_the_openai_provider_pins_the_model_to_strict_json():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as jsonlib

        captured.update(jsonlib.loads(request.content))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"translations": ["سلام", "دنیا"]}'}}]},
        )

    async with mock_http_client(handler) as client:
        provider = translation.OpenAICompatibleProvider(
            client, settings_for("openai", translation_api_key="sk-test")
        )
        result = await provider.translate(["hello", "world"], source_lang="en", target_lang="fa")

    assert result == ["سلام", "دنیا"]
    assert captured["response_format"] == {"type": "json_object"}
    assert "temperature" not in captured, (
        "temperature is omitted unless configured: it was pinned to 0, and a "
        "model that allows exactly one value rejected every request"
    )


async def _system_prompt(target_lang: str = "fa", **overrides) -> str:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as jsonlib

        captured.update(jsonlib.loads(request.content))
        return httpx.Response(
            200, json={"choices": [{"message": {"content": '{"translations": ["x"]}'}}]}
        )

    async with mock_http_client(handler) as client:
        provider = translation.OpenAICompatibleProvider(client, settings_for("openai", **overrides))
        await provider.translate(["hello"], source_lang="en", target_lang=target_lang)

    return captured["messages"][0]["content"]


async def test_farsi_markets_are_dated_in_the_persian_calendar():
    """A reader of a Farsi market question dates their life by that calendar.

    "31 December" is a translation only in the sense that the words changed —
    the reader still has to do the arithmetic the translation was for.
    """
    prompt = await _system_prompt("fa")
    assert "Jalali" in prompt
    assert "Preserve dates exactly" not in prompt


async def test_another_target_language_keeps_the_source_dates():
    """`auto` follows the target, so this is off for everyone but Farsi."""
    prompt = await _system_prompt("es")
    assert "Preserve dates exactly" in prompt
    assert "Jalali" not in prompt


async def test_the_calendar_rewrite_can_be_turned_off():
    """The conversion is the model's arithmetic, and a market question says
    when a bet resolves — so there has to be a way back to the source dates."""
    prompt = await _system_prompt("fa", translation_date_calendar="source")
    assert "Preserve dates exactly" in prompt
    assert "Jalali" not in prompt


def test_an_unknown_calendar_is_rejected_at_startup():
    with pytest.raises(ValueError, match="translation_date_calendar"):
        Settings(telegram_bot_token="x", jwt_secret="y", translation_date_calendar="mayan")


async def test_an_endpoint_that_refuses_strict_json_is_retried_without_it():
    """Same shape as Gamma's rejected sort key.

    Strict JSON aids the parser, it is not a requirement of it — the reply is
    unwrapped and searched either way — so an endpoint that refuses the flag
    can still be translated against.
    """
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json as jsonlib

        body = jsonlib.loads(request.content)
        seen.append(body)
        if "response_format" in body:
            return httpx.Response(
                400, json={"error": {"message": "response_format is not supported"}}
            )
        return httpx.Response(
            200, json={"choices": [{"message": {"content": '{"translations": ["سلام"]}'}}]}
        )

    async with mock_http_client(handler) as client:
        provider = translation.OpenAICompatibleProvider(client, settings_for("openai"))
        assert await provider.translate(["hello"], source_lang="en", target_lang="fa") == ["سلام"]

        # The flag is dropped for good: the rejection costs one request per
        # process, not one per batch.
        assert await provider.translate(["hello"], source_lang="en", target_lang="fa") == ["سلام"]

    assert [("response_format" in body) for body in seen] == [True, False, False]


async def test_a_rejection_for_any_other_reason_is_not_retried():
    """Retrying every refusal without the flag would turn a wrong model name
    or an exhausted quota into two failed requests and a misleading log."""
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(400, json={"error": {"message": "model not found"}})

    async with mock_http_client(handler) as client:
        provider = translation.OpenAICompatibleProvider(client, settings_for("openai"))
        with pytest.raises(translation.UpstreamUnavailable, match="model not found"):
            await provider.translate(["hello"], source_lang="en", target_lang="fa")

    assert calls == 1


async def test_a_translation_gets_longer_than_the_shared_http_timeout():
    """The failure that looked like an unreachable provider.

    `http_timeout_seconds` is ten and right for the price APIs it was written
    for. A reasoning model spends most of its budget thinking before it writes
    a word, so a batch takes minutes; under the shared default every request
    was aborted, retried, and reported as "POST failed after 3 attempts" while
    the provider was answering perfectly well.
    """
    seen: list[float | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.extensions.get("timeout", {}).get("read"))
        return httpx.Response(
            200, json={"choices": [{"message": {"content": '{"translations": ["سلام"]}'}}]}
        )

    async with mock_http_client(handler) as client:
        provider = translation.OpenAICompatibleProvider(
            client, settings_for("openai", http_timeout_seconds=10, translation_timeout_seconds=180)
        )
        await provider.translate(["hello"], source_lang="en", target_lang="fa")

    assert seen == [180], "the batch call must not inherit the 10s API default"


async def test_a_configured_temperature_is_sent():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as jsonlib

        captured.update(jsonlib.loads(request.content))
        return httpx.Response(
            200, json={"choices": [{"message": {"content": '{"translations": ["سلام"]}'}}]}
        )

    async with mock_http_client(handler) as client:
        provider = translation.OpenAICompatibleProvider(
            client, settings_for("openai", translation_temperature=1)
        )
        await provider.translate(["hello"], source_lang="en", target_lang="fa")

    assert captured["temperature"] == 1


async def test_a_rejected_request_reports_the_provider_s_own_reason():
    """The failure that cost a day: a 400 whose body said exactly what was
    wrong, flattened into "could not read the response" because post_json
    hands non-retryable bodies back rather than raising."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": {
                    "message": "invalid temperature: only 1 is allowed for this model",
                    "type": "invalid_request_error",
                }
            },
        )

    async with mock_http_client(handler) as client:
        provider = translation.OpenAICompatibleProvider(client, settings_for("openai"))
        with pytest.raises(translation.UpstreamUnavailable) as exc:
            await provider.translate(["one"], source_lang="en", target_lang="fa")

    assert "only 1 is allowed" in str(exc.value)


async def test_a_model_that_returns_the_wrong_count_is_refused():
    """A chat model asked for a list can decide to explain itself instead."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"choices": [{"message": {"content": '{"translations": ["فقط یکی"]}'}}]}
        )

    async with mock_http_client(handler) as client:
        provider = translation.OpenAICompatibleProvider(client, settings_for("openai"))
        with pytest.raises(translation.UpstreamUnavailable):
            await provider.translate(["one", "two"], source_lang="en", target_lang="fa")


async def test_prose_instead_of_json_is_refused():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Sure! Here are your translations:"}}]},
        )

    async with mock_http_client(handler) as client:
        provider = translation.OpenAICompatibleProvider(client, settings_for("openai"))
        with pytest.raises(translation.UpstreamUnavailable):
            await provider.translate(["one"], source_lang="en", target_lang="fa")


async def _translated_from(content: str) -> list[str]:
    """Run one reply shape through the provider and return what it read."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    async with mock_http_client(handler) as client:
        provider = translation.OpenAICompatibleProvider(client, settings_for("openai"))
        return await provider.translate(["one", "two"], source_lang="en", target_lang="fa")


async def test_a_fenced_reply_is_read_rather_than_refused():
    """`response_format=json_object` is a request, not a guarantee.

    A provider that wraps the same JSON in a markdown fence is complying as it
    understands the instruction. Refusing it costs a whole ingest, which
    silently falls back to English against a model answering perfectly well.
    """
    assert await _translated_from('```json\n{"translations": ["یک", "دو"]}\n```') == ["یک", "دو"]


async def test_a_bare_array_is_read():
    assert await _translated_from('["یک", "دو"]') == ["یک", "دو"]


async def test_a_reasoning_preamble_is_stripped():
    """Any model with reasoning on can put its thinking in the content."""
    assert await _translated_from(
        '<think>The user wants Farsi.</think>{"translations": ["یک", "دو"]}'
    ) == ["یک", "دو"]


async def test_the_array_is_found_under_a_name_the_model_chose():
    assert await _translated_from('{"result": ["یک", "دو"]}') == ["یک", "دو"]


async def test_json_wrapped_in_a_sentence_is_still_read():
    assert await _translated_from(
        'Here you go: {"translations": ["یک", "دو"]} — hope that helps'
    ) == ["یک", "دو"]


async def test_two_candidate_lists_are_refused_rather_than_guessed_at():
    """Tolerance stops where ambiguity starts: picking one at random would
    hand players the wrong text with no error anywhere."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"a": ["یک", "دو"], "b": ["سه", "چهار"]}'}}]
            },
        )

    async with mock_http_client(handler) as client:
        provider = translation.OpenAICompatibleProvider(client, settings_for("openai"))
        with pytest.raises(translation.UpstreamUnavailable):
            await provider.translate(["one", "two"], source_lang="en", target_lang="fa")


async def test_an_empty_message_is_refused():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": ""}}]})

    async with mock_http_client(handler) as client:
        provider = translation.OpenAICompatibleProvider(client, settings_for("openai"))
        with pytest.raises(translation.UpstreamUnavailable):
            await provider.translate(["one"], source_lang="en", target_lang="fa")


async def test_an_unreadable_reply_is_logged_with_a_sample(caplog):
    """The log line that turns "translation is broken" into a two-minute fix."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "I cannot do that."}}]}
        )

    async with mock_http_client(handler) as client:
        provider = translation.OpenAICompatibleProvider(client, settings_for("openai"))
        with pytest.raises(translation.UpstreamUnavailable):
            await provider.translate(["one"], source_lang="en", target_lang="fa")

    assert "I cannot do that." in caplog.text


async def test_a_reasoning_only_reply_names_the_model_as_the_cause():
    """A model whose answer never reaches `content` is a configuration
    problem, and the log has to say so — otherwise it reads as a parser bug."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": "", "reasoning_content": "Thinking..."},
                        "finish_reason": "length",
                    }
                ]
            },
        )

    async with mock_http_client(handler) as client:
        provider = translation.OpenAICompatibleProvider(client, settings_for("openai"))
        with pytest.raises(translation.UpstreamUnavailable):
            await provider.translate(["one"], source_lang="en", target_lang="fa")


async def test_an_error_body_returned_as_200_still_reports_its_reason():
    """Some endpoints answer 200 with an error object. The reason has to reach
    the caller either way, or it reads as an unparseable answer."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": {"message": "quota exceeded"}})

    async with mock_http_client(handler) as client:
        provider = translation.OpenAICompatibleProvider(client, settings_for("openai"))
        with pytest.raises(translation.UpstreamUnavailable) as exc:
            await provider.translate(["one"], source_lang="en", target_lang="fa")

    assert "quota exceeded" in str(exc.value)


async def test_an_empty_choices_list_is_reported_as_such(caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    async with mock_http_client(handler) as client:
        provider = translation.OpenAICompatibleProvider(client, settings_for("openai"))
        with pytest.raises(translation.UpstreamUnavailable):
            await provider.translate(["one"], source_lang="en", target_lang="fa")

    assert "no choices" in caplog.text


async def test_the_libretranslate_provider_speaks_its_contract():
    def handler(request: httpx.Request) -> httpx.Response:
        import json as jsonlib

        body = jsonlib.loads(request.content)
        assert body["source"] == "en" and body["target"] == "fa"
        return httpx.Response(200, json={"translatedText": [f"fa:{q}" for q in body["q"]]})

    async with mock_http_client(handler) as client:
        provider = translation.LibreTranslateProvider(client, settings_for("libretranslate"))
        assert await provider.translate(["a", "b"], source_lang="en", target_lang="fa") == [
            "fa:a",
            "fa:b",
        ]


async def test_an_api_key_never_reaches_an_error_message():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={})

    async with mock_http_client(handler) as client:
        provider = translation.OpenAICompatibleProvider(
            client,
            settings_for("openai", translation_api_key="sk-super-secret", http_max_retries=1),
        )
        with pytest.raises(translation.UpstreamUnavailable) as exc:
            await provider.translate(["x"], source_lang="en", target_lang="fa")

    assert "sk-super-secret" not in str(exc.value)


def test_an_unknown_provider_is_rejected_at_startup():
    with pytest.raises(ValueError, match="translation_provider"):
        Settings(telegram_bot_token="x", jwt_secret="y", translation_provider="googletrans")


def test_the_default_provider_is_the_pass_through():
    assert get_settings().translation_provider == "null"


def test_the_default_batch_size_can_finish_inside_its_own_timeout():
    """The bug that spent a production run's entire 1800s deadline failing to
    translate a single batch, and never got to try a second one.

    A reasoning model burns roughly 594 reasoning tokens per sentence; a
    batch of 50 is tens of thousands of tokens and reliably outruns even a
    generous per-request timeout. Every attempt then fails outright rather
    than degrading, and at concurrency=1 that failure eats the whole run.
    Small batches finish and get cached as they land instead.
    """
    assert get_settings().translation_batch_size <= 10


def test_the_default_concurrency_matches_a_single_concurrent_slot():
    """The bug that made every batch but one 429 forever.

    Kimi's account allows exactly one request in flight; a default of 8 sent
    up to eight batches at once, one won the race and the other seven were
    refused with HTTP 429 before that one had time to finish — and because it
    holds its slot for minutes, the few short retries `post_json` allows ran
    out long before it freed up. The same race, and the same near-total
    loss, repeated on every single run.
    """
    assert get_settings().translation_concurrency == 1


def _client_without_base_url(handler) -> httpx.AsyncClient:
    """A mock client shaped like build_client(): no base_url to lean on."""
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _openai_ok(seen: list[httpx.Request]):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": '{"translations": ["سلام"]}'}}]}
        )

    return handler


async def test_the_openai_provider_works_with_no_url_configured():
    seen: list[httpx.Request] = []
    settings = Settings(
        telegram_bot_token="x",
        jwt_secret="y",
        translation_provider="openai",
        translation_api_key="sk-test",
    )
    assert settings.translation_api_url == ""

    async with _client_without_base_url(_openai_ok(seen)) as client:
        provider = translation.OpenAICompatibleProvider(client, settings)
        result = await provider.translate(["hello"], source_lang="en", target_lang="fa")

    assert result == ["سلام"]
    assert str(seen[0].url) == "https://api.openai.com/v1/chat/completions"


async def test_an_explicit_url_still_wins_over_the_default():
    """The provider speaks to any OpenAI-compatible host, not only OpenAI."""
    seen: list[httpx.Request] = []
    settings = Settings(
        telegram_bot_token="x",
        jwt_secret="y",
        translation_provider="openai",
        translation_api_url="https://openrouter.ai/api/v1",
    )

    async with _client_without_base_url(_openai_ok(seen)) as client:
        provider = translation.OpenAICompatibleProvider(client, settings)
        await provider.translate(["hello"], source_lang="en", target_lang="fa")

    assert str(seen[0].url) == "https://openrouter.ai/api/v1/chat/completions"


async def test_a_provider_failing_outside_the_network_still_fails_open():
    """Fail-open has to mean *any* failure, not a list of the expected ones.

    Calling the private method directly is the point: this is the one place
    that decides whether a broken translator degrades the app or empties it.
    """

    class BrokenProvider:
        name = "broken"

        async def translate(self, texts, *, source_lang, target_lang):
            raise ValueError("unknown url type: '/chat/completions'")

    service = translation.TranslationService(provider=BrokenProvider())
    assert await service._translate_uncached(["one", "two"]) == {}
    assert service.stats.failed == 2


def test_libretranslate_without_a_url_is_refused_at_boot():
    """No canonical host to fall back on, so say so now rather than in an hour."""
    settings = Settings(
        telegram_bot_token="x", jwt_secret="y", translation_provider="libretranslate"
    )
    with pytest.raises(RuntimeError, match="TRANSLATION_API_URL"):
        settings.require_secrets()


def test_openai_without_a_url_boots_fine():
    Settings(
        telegram_bot_token="x", jwt_secret="y", translation_provider="openai"
    ).require_secrets()


class SlowProvider:
    """A provider that takes a fixed time per batch and records overlap."""

    name = "slow"

    def __init__(self, delay: float = 0.05) -> None:
        self.delay = delay
        self.in_flight = 0
        self.peak = 0
        self.batches = 0

    async def translate(self, texts, *, source_lang, target_lang):
        import asyncio

        self.in_flight += 1
        self.peak = max(self.peak, self.in_flight)
        self.batches += 1
        try:
            await asyncio.sleep(self.delay)
            return [f"fa:{t}" for t in texts]
        finally:
            self.in_flight -= 1


async def test_batches_are_translated_several_at_a_time(resources):
    """The sequential loop is what made a first ingest look like a hang.

    A few hundred markets is a thousand-odd strings and forty-odd batches, and
    forty provider round trips in a row is minutes of a job that holds its
    lease throughout — the bulk of the eighty-six minutes one discovery pass
    took before it was abandoned.
    """
    from backend import db
    from backend.services.translation import TranslationService

    provider = SlowProvider()
    service = TranslationService(provider=provider, batch_size=2, concurrency=4)

    async with db.transaction() as conn:
        result = await service.translate_many(conn, [f"text {i}" for i in range(16)])

    assert len(result) == 16
    assert provider.batches == 8
    assert provider.peak > 1, "batches ran one at a time"
    assert provider.peak <= 4, "the bound was not respected"


async def test_the_concurrency_bound_is_respected_exactly(resources):
    """Bounded rather than unbounded because every batch goes to the same
    provider, and a burst of hundreds is how a rate limit is earned."""
    from backend import db
    from backend.services.translation import TranslationService

    provider = SlowProvider()
    service = TranslationService(provider=provider, batch_size=1, concurrency=3)

    async with db.transaction() as conn:
        await service.translate_many(conn, [f"t{i}" for i in range(30)])

    assert provider.peak == 3


async def test_one_failing_batch_does_not_take_the_others_with_it(resources):
    """Each batch is its own request and its own failure. Running them
    together must not turn one bad batch into a failed ingest — untranslated
    markets are a bad day, an empty market list is a dead app."""
    from backend import db
    from backend.services.translation import TranslationService

    class Flaky(SlowProvider):
        async def translate(self, texts, *, source_lang, target_lang):
            if "boom" in texts[0]:
                raise RuntimeError("provider said no")
            return await super().translate(texts, source_lang=source_lang, target_lang=target_lang)

    service = TranslationService(provider=Flaky(), batch_size=1, concurrency=4)

    async with db.transaction() as conn:
        result = await service.translate_many(conn, ["fine one", "boom", "fine two"])

    assert result["fine one"] == "fa:fine one"
    assert result["fine two"] == "fa:fine two"
    assert result["boom"] == "boom"


def test_the_startup_line_names_the_provider_actually_in_use(caplog):
    """A misconfigured translator does not fail; it falls back to the
    pass-through, returns every string unchanged, writes nothing and raises
    nothing. That is indistinguishable in the logs from a provider refusing
    every request, so the configuration says which one is running."""
    from backend.services.translation import log_translation_config

    settings = Settings(
        telegram_bot_token="x",
        jwt_secret="y",
        translation_provider="openai",
        translation_api_key="sk-secret-value-do-not-log",
        translation_model="kimi-k2.6",
    )
    with caplog.at_level("INFO"):
        log_translation_config(settings)

    assert "provider=openai" in caplog.text
    assert "model=kimi-k2.6" in caplog.text
    assert "sk-secret-value-do-not-log" not in caplog.text, "the key must never be printed"
    assert "set (26 chars)" in caplog.text


def test_the_pass_through_announces_itself_as_a_warning(caplog):
    from backend.services.translation import log_translation_config

    settings = Settings(telegram_bot_token="x", jwt_secret="y")
    with caplog.at_level("INFO"):
        log_translation_config(settings)

    assert "provider=null" in caplog.text
    assert "ingested in its source language" in caplog.text


def test_an_openai_provider_without_a_key_is_called_out(caplog):
    from backend.services.translation import log_translation_config

    settings = Settings(telegram_bot_token="x", jwt_secret="y", translation_provider="openai")
    with caplog.at_level("INFO"):
        log_translation_config(settings)

    assert "api_key=MISSING" in caplog.text
