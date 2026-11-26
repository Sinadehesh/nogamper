"""Translating ingested market text before it reaches the database.

## Shape

A provider does the translating; the service wraps one with a cache and a
failure policy. Providers are swappable because nobody should have to edit
ingestion code to change translation vendor.

Deliberately **not** included: `googletrans`. It scrapes the consumer Google
Translate endpoint, has no stability guarantee, breaks whenever that page
changes, and using it at volume is against Google's terms. It is fine in a
notebook and wrong in an ingestion pipeline that runs hourly forever.

## Two policies that matter more than the provider

**Fail open.** A translation outage must not stop ingestion. When the provider
errors, the source text is stored and the run continues — a market listed in
English is a degraded market; no markets at all is a dead app. The failure is
counted and logged.

**Cache by content.** Discovery re-upserts the same markets every hour. Without
a cache that is one API call per market per hour forever, for text that has not
changed. Keyed on a hash of the source, so a sentence is translated once.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Protocol

import asyncpg
import httpx

from .. import db
from ..clients.http import UpstreamUnavailable, post_json
from ..config import Settings

logger = logging.getLogger(__name__)

__all__ = [
    "NullTranslationProvider",
    "OpenAICompatibleProvider",
    "LibreTranslateProvider",
    "TranslationService",
    "TranslationStats",
    "build_provider",
]


class TranslationProvider(Protocol):
    name: str

    async def translate(self, texts: list[str], *, source_lang: str, target_lang: str) -> list[str]:
        """Return one translation per input, in order and of equal length."""
        ...


@dataclass
class TranslationStats:
    requested: int = 0
    from_cache: int = 0
    translated: int = 0
    failed: int = 0
    skipped_empty: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "requested": self.requested,
            "from_cache": self.from_cache,
            "translated": self.translated,
            "failed": self.failed,
            "skipped_empty": self.skipped_empty,
        }


class NullTranslationProvider:
    """Returns the source unchanged.

    The default. An unconfigured deployment ingests readable English rather
    than silently shipping half-translated text or refusing to start.
    """

    name = "null"

    async def translate(self, texts: list[str], *, source_lang: str, target_lang: str) -> list[str]:
        return list(texts)


class LibreTranslateProvider:
    """LibreTranslate, or anything speaking its `/translate` contract.

    Open source and self-hostable, which for a pipeline translating public
    market questions on a schedule is usually the cheapest correct answer.
    """

    name = "libretranslate"

    def __init__(self, client: httpx.AsyncClient, settings: Settings) -> None:
        self._client = client
        self._url = settings.translation_api_url.rstrip("/")
        self._api_key = settings.translation_api_key
        self._retries = settings.http_max_retries

    async def translate(self, texts: list[str], *, source_lang: str, target_lang: str) -> list[str]:
        payload: dict[str, object] = {
            "q": texts,
            "source": source_lang,
            "target": target_lang,
            "format": "text",
        }
        if self._api_key:
            payload["api_key"] = self._api_key

        body = await post_json(
            self._client,
            f"{self._url}/translate",
            payload,
            max_retries=self._retries,
            scrub=self._api_key or None,
        )

        if isinstance(body, dict):
            translated = body.get("translatedText")
            if isinstance(translated, list):
                return [str(item) for item in translated]
            if isinstance(translated, str) and len(texts) == 1:
                return [translated]

        raise UpstreamUnavailable("translation response was not in the expected shape")


class OpenAICompatibleProvider:
    """Any `/v1/chat/completions` endpoint — OpenAI, Azure, vLLM, OpenRouter.

    An LLM translates market questions better than a phrase-based engine,
    because "Will the Fed cut by 25 bps?" needs the domain vocabulary rather
    than a literal rendering. The cost is that it must be pinned to returning
    strict JSON, and checked, because a chat model asked for a list can decide
    to explain itself instead.
    """

    name = "openai-compatible"

    DEFAULT_API_URL = "https://api.openai.com/v1"

    _SYSTEM = (
        "You are a professional translator for a financial prediction market. "
        "Translate each input string into {target}. Preserve numbers, tickers, "
        "currency symbols and proper nouns exactly. {dates} Keep the register "
        "neutral and factual — these are market questions, not marketing. "
        'Reply with JSON only, in the form {{"translations": ["...", "..."]}}, '
        "with exactly one entry per input, in the same order."
    )

    _KEEP_DATES = "Preserve dates exactly as written."

    _PERSIAN_DATES = (
        "Convert every calendar date to the Persian (Jalali/Shamsi) calendar, "
        "writing the month by name — 31 December 2026 becomes ۱۰ دی ۱۴۰۵. "
        "Convert the whole date or none of it: never mix a Gregorian month "
        "with a Jalali year. A year alone stays as it is unless the day and "
        "month are given too."
    )

    def __init__(self, client: httpx.AsyncClient, settings: Settings) -> None:
        self._client = client
        self._url = (settings.translation_api_url or self.DEFAULT_API_URL).rstrip("/")
        self._api_key = settings.translation_api_key
        self._model = settings.translation_model
        self._temperature = settings.translation_temperature
        self._calendar = settings.translation_date_calendar
        self._retries = settings.http_max_retries
        self._timeout = settings.translation_timeout_seconds
        self._json_mode = True
        """Whether this process still asks for strict JSON. Cleared for good the
        first time an endpoint refuses the flag, so the cost is one rejection
        per process rather than one per batch."""

    def _date_rule(self, target_lang: str) -> str:
        """Whether this run rewrites dates, and into what.

        `auto` reads the target language rather than a separate switch, so a
        deployment that changes locale does not silently keep a calendar its
        readers do not use.
        """
        wanted = self._calendar
        if wanted == "auto":
            wanted = "persian" if target_lang.lower().startswith("fa") else "source"
        return self._PERSIAN_DATES if wanted == "persian" else self._KEEP_DATES

    def _body(self, texts: list[str], target_lang: str) -> dict[str, object]:
        body: dict[str, object] = {
            "model": self._model,
            "messages": [
                {
                    "role": "system",
                    "content": self._SYSTEM.format(
                        target=target_lang,
                        dates=self._date_rule(target_lang),
                    ),
                },
                {"role": "user", "content": json.dumps(texts, ensure_ascii=False)},
            ],
        }
        if self._json_mode:
            body["response_format"] = {"type": "json_object"}
        if self._temperature is not None:
            body["temperature"] = self._temperature
        return body

    async def _post(self, body: dict[str, object]) -> object:
        return await post_json(
            self._client,
            f"{self._url}/chat/completions",
            body,
            max_retries=self._retries,
            timeout=self._timeout,
            scrub=self._api_key or None,
            headers={"Authorization": f"Bearer {self._api_key}"} if self._api_key else None,
        )

    async def translate(self, texts: list[str], *, source_lang: str, target_lang: str) -> list[str]:
        try:
            response = await self._post(self._body(texts, target_lang))
            translations = _extract_translations(response)
        except UpstreamUnavailable as exc:
            if not (self._json_mode and _rejected_json_mode(exc)):
                raise
            # The same shape as Gamma's rejected sort key: a request the
            # upstream will not take is worth retrying once without the part
            # it named, and worth never sending again this process. Strict
            # JSON is an aid to the parser, not a requirement of it — the
            # reply is unwrapped and searched either way — so an endpoint
            # that refuses the flag can still be translated against.
            logger.warning(
                "the provider refused response_format=json_object (%s); "
                "retrying without it and dropping it for the rest of this run",
                exc,
            )
            self._json_mode = False
            response = await self._post(self._body(texts, target_lang))
            translations = _extract_translations(response)

        if len(translations) != len(texts):
            raise UpstreamUnavailable(
                f"model returned {len(translations)} translations for {len(texts)} inputs"
            )
        return translations


def _rejected_json_mode(exc: Exception) -> bool:
    """Whether a rejection names the strict-JSON flag as its reason.

    Narrow on purpose. Retrying every refusal without `response_format` would
    turn a wrong model name or an exhausted quota into two failed requests and
    a misleading log line.
    """
    reason = str(exc).lower()
    return "response_format" in reason or "json_object" in reason or "json mode" in reason


_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _decode_content(content: str) -> object:
    """Parse a chat model's reply into JSON, allowing for how they actually write.

    `response_format=json_object` is a request, not a guarantee. The same
    prompt comes back as bare JSON from one provider, wrapped in a ```json
    fence from another, and preceded by a <think> block from any model with
    reasoning turned on. All three are the model complying as it understands
    the instruction, so all three are read rather than refused — the
    alternative is an ingest that silently falls back to English against a
    provider that is answering perfectly well.

    What is not tolerated is prose: if there is no JSON value in there, the
    caller raises, because a model that decided to explain itself has not
    translated anything.
    """
    text = _THINK.sub("", content).strip()
    text = _FENCE.sub("", text).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # A model that wrote a sentence around otherwise valid JSON. Take the
    # widest bracketed span and try that before giving up.
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = text.find(opener), text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise json.JSONDecodeError("no JSON value in the reply", text, 0)


def _translations_from(payload: object) -> list[object] | None:
    """Find the list of translations in whatever shape the model chose.

    Asked for `{"translations": [...]}`, models also return the bare array, or
    the same array under a name of their own. Each of those is unambiguous on
    its own, so each is accepted; a payload with two candidate lists is not,
    and is refused rather than guessed at.
    """
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return None
    if isinstance(payload.get("translations"), list):
        return payload["translations"]

    lists = [value for value in payload.values() if isinstance(value, list)]
    return lists[0] if len(lists) == 1 else None


def _message_of(response: dict) -> dict:
    """The assistant message, or a raised error that says what arrived instead.

    An OpenAI-compatible endpoint can answer 200 with something that is not an
    answer: an error object, an empty `choices`, or a message whose text is
    somewhere other than `content`. Naming which of those happened — and
    showing the body — is the difference between a one-line configuration fix
    and a day spent guessing at a provider.
    """
    error = response.get("error")
    if error is not None:
        # A rejected request, not a bad answer. post_json hands back the body
        # for any status it does not retry, because Telegram reads its error
        # codes out of exactly that; here the message is the whole diagnosis,
        # so it goes into the exception rather than being flattened into
        # "unreadable response".
        detail = error.get("message") if isinstance(error, dict) else error
        raise UpstreamUnavailable(f"the provider rejected the request: {detail}")

    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        logger.error(
            "translation response had no choices; keys=%s body=%.400s",
            sorted(response),
            json.dumps(response, ensure_ascii=False),
        )
        raise UpstreamUnavailable("the response carried no choices")

    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        logger.error(
            "translation choice had no message; body=%.400s",
            json.dumps(response, ensure_ascii=False),
        )
        raise UpstreamUnavailable("the response carried no message")
    return message


def _extract_translations(response: object) -> list[str]:
    if not isinstance(response, dict):
        raise UpstreamUnavailable("translation response was not a JSON object")

    message = _message_of(response)
    content = message.get("content")

    if not isinstance(content, str) or not content.strip():
        # A reasoning model that returned only its thinking. Worth naming
        # separately: it is a model choice, not a bug, and the fix is to
        # configure one whose answer arrives in `content`.
        if message.get("reasoning_content") or message.get("reasoning"):
            logger.error(
                "the model answered with reasoning but no content — "
                "TRANSLATION_MODEL looks like a thinking-only model; "
                "set one that returns its answer in `content`. finish_reason=%r",
                response["choices"][0].get("finish_reason"),
            )
            raise UpstreamUnavailable("the model returned reasoning but no answer")
        logger.error(
            "translation message had no usable content; message keys=%s body=%.400s",
            sorted(message),
            json.dumps(response, ensure_ascii=False),
        )
        raise UpstreamUnavailable("the model returned an empty message")

    try:
        payload = _decode_content(content)
    except json.JSONDecodeError as exc:
        logger.error("translation reply was not JSON; first 300 chars: %r", content[:300])
        raise UpstreamUnavailable("could not read translations from the response") from exc

    translations = _translations_from(payload)
    if translations is None:
        logger.error("translation reply had no list; first 300 chars: %r", content[:300])
        raise UpstreamUnavailable("could not read translations from the response")

    if not all(isinstance(t, str) for t in translations):
        raise UpstreamUnavailable("translations were not a list of strings")
    return list(translations)


def build_provider(client: httpx.AsyncClient, settings: Settings) -> TranslationProvider:
    match settings.translation_provider:
        case "libretranslate":
            return LibreTranslateProvider(client, settings)
        case "openai":
            return OpenAICompatibleProvider(client, settings)
        case _:
            return NullTranslationProvider()


_READ_CACHE = """
SELECT source_hash, translated_text
  FROM translations
 WHERE source_lang = $2 AND target_lang = $3 AND source_hash = ANY($1::text[])
"""

_WRITE_CACHE = """
INSERT INTO translations (source_hash, source_lang, target_lang, source_text,
                          translated_text, provider)
SELECT * FROM unnest($1::text[], $2::text[], $3::text[], $4::text[], $5::text[], $6::text[])
ON CONFLICT (source_hash, source_lang, target_lang) DO NOTHING
"""


def source_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


@dataclass
class TranslationService:
    provider: TranslationProvider
    source_lang: str = "en"
    target_lang: str = "fa"
    batch_size: int = 25
    concurrency: int = 8
    stats: TranslationStats = field(default_factory=TranslationStats)

    async def translate_many(self, conn: asyncpg.Connection, texts: list[str]) -> dict[str, str]:
        """Map each distinct input to its translation.

        Anything that cannot be translated maps to itself, so a caller can
        always substitute unconditionally.
        """
        distinct = {text for text in texts if text and text.strip()}
        self.stats.requested += len(distinct)
        self.stats.skipped_empty += len(texts) - len([t for t in texts if t and t.strip()])

        if not distinct or isinstance(self.provider, NullTranslationProvider):
            return {text: text for text in distinct}

        by_hash = {source_hash(text): text for text in distinct}
        resolved: dict[str, str] = {}

        cached = await conn.fetch(_READ_CACHE, list(by_hash), self.source_lang, self.target_lang)
        for row in cached:
            resolved[by_hash[row["source_hash"]]] = row["translated_text"]
        self.stats.from_cache += len(resolved)

        outstanding = [text for text in distinct if text not in resolved]
        if not outstanding:
            return resolved

        fresh = await self._translate_uncached(outstanding)
        resolved.update(fresh)

        for text in outstanding:
            resolved.setdefault(text, text)
        return resolved

    async def _translate_uncached(self, texts: list[str]) -> dict[str, str]:
        """Translate what the cache did not have, several batches at a time.

        This was a plain sequential loop, and that is what made a first ingest
        so slow it looked like a hang. A few hundred markets is a thousand-odd
        strings and forty-odd batches; against a provider that answers in a
        few seconds each, forty round trips in a row is minutes of a job that
        is holding its lease the whole time.

        Batches are independent — each is its own request and its own failure —
        so there is nothing to serialise them for. The concurrency is bounded
        because they all go to one provider, and a burst of hundreds is how a
        rate limit is earned.

        Order is not preserved and does not need to be: results are matched
        back to their own batch's inputs, not to a position in the whole list.

        Each batch is stored the moment its own call returns, inside `run`,
        rather than after `gather` collects every batch. `gather` only
        resolves once every task has finished, so storing in the loop that
        consumes it would hold a batch that answered in ten seconds hostage to
        one still running two minutes later — exactly the transaction this
        was written to get out from under, just moved into this function
        instead of the caller's. A batch that lands stays landed the instant
        it lands, whatever its siblings do.
        """
        batches = [
            texts[start : start + self.batch_size]
            for start in range(0, len(texts), self.batch_size)
        ]
        semaphore = asyncio.Semaphore(max(1, self.concurrency))

        async def run(batch: list[str]) -> dict[str, str]:
            async with semaphore:
                results = await self._one_batch(batch)
            if results is None:
                return {}
            done: dict[str, str] = {}
            for source, result in zip(batch, results, strict=False):
                cleaned = result.strip()
                if cleaned:
                    done[source] = cleaned
                    self.stats.translated += 1
                else:
                    self.stats.failed += 1
            if done:
                await self._store(done)
            return done

        translated: dict[str, str] = {}
        for done in await asyncio.gather(*(run(b) for b in batches)):
            translated.update(done)

        return translated

    async def _one_batch(self, batch: list[str]) -> list[str] | None:
        """One provider call. Returns None if it could not be made at all."""
        try:
            return await self.provider.translate(
                batch, source_lang=self.source_lang, target_lang=self.target_lang
            )
        except Exception as exc:
            self.stats.failed += len(batch)
            logger.error(
                "translation batch of %s failed (%s: %s); ingesting source text",
                len(batch),
                type(exc).__name__,
                exc,
            )
            return None

    async def _store(self, translated: dict[str, str]) -> None:
        """Commit one batch's translations on their own connection.

        Not the caller's. Discovery localises inside the transaction that also
        writes the markets, and that transaction is abandoned whole when the
        pass overruns its deadline — so against a provider slow enough to make
        a run overrun, every translation it had already paid for was rolled
        back, and the next run started from nothing. Work that has been paid
        for is committed as it lands, and a later failure cannot un-earn it:
        the cache is keyed by source text, so a row is true whether or not the
        run that fetched it ever finished.
        """
        sources = list(translated)
        async with db.transaction() as conn:
            await conn.execute(
                _WRITE_CACHE,
                [source_hash(text) for text in sources],
                [self.source_lang] * len(sources),
                [self.target_lang] * len(sources),
                sources,
                [translated[text] for text in sources],
                [self.provider.name] * len(sources),
            )


def log_translation_config(settings: Settings) -> None:
    """State the translation setup at boot, before anything can go wrong.

    A misconfigured translator does not fail: `build_provider` falls back to
    the pass-through, which returns every string unchanged, writes nothing,
    and raises nothing. The feed then serves English and the logs are silent
    — the same picture as a provider that is refusing every request, and the
    two were told apart only by reading the code. One line at startup names
    which one is running, so the question is answered before it is asked.

    The key is never printed; only whether one is present, and how long it is,
    which is enough to tell "unset" from "pasted with a newline in it".
    """
    endpoint = settings.translation_api_url or "(provider default)"
    logger.info(
        "translation: provider=%s model=%s endpoint=%s api_key=%s "
        "batch=%s concurrency=%s timeout=%ss %s->%s calendar=%s",
        settings.translation_provider,
        settings.translation_model,
        endpoint,
        f"set ({len(settings.translation_api_key)} chars)"
        if settings.translation_api_key
        else "MISSING",
        settings.translation_batch_size,
        settings.translation_concurrency,
        settings.translation_timeout_seconds,
        settings.translation_source_lang,
        settings.translation_target_lang,
        settings.translation_date_calendar,
    )
    if settings.translation_provider == "null":
        logger.warning(
            "TRANSLATION_PROVIDER is 'null': every market will be ingested in its "
            "source language and nothing will be written to the translation cache. "
            "Set it to 'openai' for any OpenAI-compatible endpoint."
        )
    elif settings.translation_provider == "openai" and not settings.translation_api_key:
        logger.warning(
            "TRANSLATION_PROVIDER is 'openai' but TRANSLATION_API_KEY is empty: "
            "requests will go out unauthenticated and the provider will refuse them"
        )
