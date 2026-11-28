"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import type { AskedQuestion } from "@/components/Dashboard";
import { MarketCard } from "@/components/MarketCard";
import { usePlayer } from "@/components/PlayerProvider";
import { getMarkets } from "@/lib/api";
import { categoryLabel, errorMessage, t } from "@/lib/copy";
import type { MarketRules, MarketSort, MarketSummary } from "@/lib/types";

const PAGE_SIZE = 40;
const REFRESH_MS = 60_000;
/** The API's largest page, and how many of them a search for one question reads. */
const SEARCH_PAGE = 100;
const SEARCH_PAGES = 6;

/**
 * One question of the feed, found by its wording.
 *
 * A question's page ("Make a forecast") sends its address here, and the page
 * that serves the game turns it into the question's wording and category
 * (from the same list as /questions). The API has no way to ask for one
 * question of the feed by either, so this reads the feed of its category,
 * soonest to close first, a hundred at a time, until it is found. A question
 * that is not in the feed at all (one the market has outside the game's band,
 * or one that has closed) is not there to find: the feed then says so and
 * links back to the question's page.
 */
async function findAsked(asked: AskedQuestion): Promise<MarketSummary | null | "error"> {
  let cursor: string | undefined;
  for (let index = 0; index < SEARCH_PAGES; index += 1) {
    const result = await getMarkets({ category: asked.category, sort: "closing", limit: SEARCH_PAGE, cursor });
    if (!result.ok) return "error";
    const found = result.data.markets.find((market) => market.question === asked.question);
    if (found) return found;
    if (!result.data.next_cursor) return null;
    cursor = result.data.next_cursor;
  }
  return null;
}

// "Closest calls" leads, and is where the feed opens. The questions nearest a
// coin flip are the ones with something to disagree with the crowd about; the
// alternative default, soonest to close, opens on whatever is all but decided.
const SORTS: { id: MarketSort; label: string }[] = [
  { id: "tossup", label: t.sortTossup },
  { id: "closing", label: t.sortClosing },
  { id: "volume", label: t.sortBusiest },
];

export function MarketFeed({
  onRules,
  onMarkets,
  asked = null,
}: {
  /** Hands the feed's rules up, so the slip prices against the same ones. */
  onRules: (rules: MarketRules) => void;
  /** Hands each page of questions up, so the slip and the forecasts can show
      a pick's chance without asking the server again. */
  onMarkets?: (markets: MarketSummary[]) => void;
  /** A question asked for by its page: its card leads the feed until the
      reader picks another category or order. */
  asked?: AskedQuestion | null;
}) {
  const { onBreak, limitReached, refresh } = usePlayer();

  const [markets, setMarkets] = useState<MarketSummary[] | null>(null);
  const [rules, setRules] = useState<MarketRules | null>(null);
  const [categories, setCategories] = useState<string[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [category, setCategory] = useState<string | null>(null);
  const [sort, setSort] = useState<MarketSort>("tossup");
  const [error, setError] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  // When the list on screen was read, by this browser's clock: what a card
  // measures "closes soon" and "this year" from.
  const [readAt, setReadAt] = useState(0);
  // The asked-for question's card, while it leads the feed; "missing" when
  // the feed does not have it.
  const [pinned, setPinned] = useState<MarketSummary | "missing" | null>(null);
  const [pinning, setPinning] = useState(Boolean(asked));
  const pinFocused = useRef(false);

  // How many the reader has paged in. A background refresh reloads that many,
  // so prices update under them without the list snapping back to one page.
  const shown = useRef(PAGE_SIZE);
  // Guards against a slow response for a view the reader has already left.
  const view = useRef(0);

  const load = useCallback(
    async (count: number) => {
      const ticket = ++view.current;
      const result = await getMarkets({
        category: category ?? undefined,
        sort,
        limit: Math.min(count, 100),
      });
      if (ticket !== view.current) return;

      if (!result.ok) {
        if (result.status === 401) void refresh();
        setError(errorMessage(result.code));
        return;
      }
      const { markets: page, next_cursor, categories: listed, ...pageRules } = result.data;
      // The asked-for question first, from this page when it is on it, else
      // looked for, before the list is drawn, so the list does not jump.
      if (asked && pinning) {
        const here = page.find((market) => market.question === asked.question);
        // No wording: the question is not open (see the page that serves the game).
        const found = here ?? (asked.question ? await findAsked(asked) : null);
        if (ticket !== view.current) return;
        if (found !== "error") {
          setPinned(found ?? "missing");
          if (found) onMarkets?.([found]);
        }
      }
      setMarkets(page);
      setCursor(next_cursor);
      setCategories(listed);
      setRules(pageRules);
      onRules(pageRules);
      onMarkets?.(page);
      setReadAt(Date.now());
      setError(null);
    },
    [category, sort, onRules, onMarkets, refresh, asked, pinning],
  );

  useEffect(() => {
    shown.current = PAGE_SIZE;
    setMarkets(null);
    void load(PAGE_SIZE);

    // Prices move. Refresh quietly while the tab is in front, and not at all
    // while it is not — a background tab polling once a minute is traffic
    // nobody is looking at.
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void load(shown.current);
    }, REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [load]);

  // The asked-for card, once it is drawn, is brought into view with the focus
  // on it: its question is read out, and its picks are the next stops.
  const pinnedId = pinned && pinned !== "missing" ? pinned.id : null;
  useEffect(() => {
    if (!pinnedId || pinFocused.current || markets === null) return;
    const card = document.querySelector<HTMLElement>(`.gm-card[data-market="${CSS.escape(pinnedId)}"]`);
    if (!card) return;
    pinFocused.current = true;
    card.scrollIntoView({ block: "start" });
    card.focus({ preventScroll: true });
  }, [pinnedId, markets]);

  // Another category or order is the reader's own choice: the feed is theirs.
  const choose = useCallback((next: { category?: string | null; sort?: MarketSort }) => {
    setPinning(false);
    setPinned(null);
    if (next.category !== undefined) setCategory(next.category);
    if (next.sort !== undefined) setSort(next.sort);
  }, []);

  const loadMore = useCallback(async () => {
    if (!cursor) return;
    setLoadingMore(true);
    const ticket = view.current;
    const result = await getMarkets({
      category: category ?? undefined,
      sort,
      limit: PAGE_SIZE,
      cursor,
    });
    setLoadingMore(false);
    if (ticket !== view.current) return;

    if (!result.ok) {
      setError(errorMessage(result.code));
      return;
    }
    onMarkets?.(result.data.markets);
    setMarkets((current) => {
      // The price-ordered views page by offset, and a price that moved between
      // two requests can put one question on both pages. Drop the repeat.
      const seen = new Set((current ?? []).map((market) => market.id));
      const merged = [
        ...(current ?? []),
        ...result.data.markets.filter((market) => !seen.has(market.id)),
      ];
      shown.current = merged.length;
      return merged;
    });
    setCursor(result.data.next_cursor);
  }, [cursor, category, sort, onMarkets]);

  return (
    <section className="gm-feed" aria-labelledby="gm-view-title">
      <div className="gm-toolbar">
        <div className="gm-chips" role="group" aria-label={t.categoryGroup}>
          {[null, ...categories].map((entry) => (
            <button
              key={entry ?? "all"}
              type="button"
              className="gm-chip"
              onClick={() => choose({ category: entry })}
              aria-pressed={category === entry}
            >
              {entry === null ? t.categoryAll : categoryLabel(entry)}
            </button>
          ))}
        </div>

        <label className="gm-sort">
          <span>{t.sortLabel}</span>
          <select
            className="field"
            value={sort}
            onChange={(event) => choose({ sort: event.target.value as MarketSort })}
          >
            {SORTS.map((entry) => (
              <option key={entry.id} value={entry.id}>
                {entry.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {/* Said here, before a pick is made, rather than as a refusal after the
          stake has been typed. A break outranks a limit: it lasts longer. */}
      {onBreak ? (
        <p className="gm-note gm-note--line">{t.onBreakNoPicks}</p>
      ) : limitReached ? (
        <p className="gm-note gm-note--line">{t.limitReachedNoPicks}</p>
      ) : null}

      {error ? (
        <div role="alert" className="gm-note flex flex-wrap items-center justify-between gap-3">
          <span className="gm-error">{error}</span>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => void load(shown.current)}
          >
            {t.retry}
          </button>
        </div>
      ) : null}

      {asked && pinned === "missing" ? (
        <p className="gm-note gm-note--line">
          {t.askedMissing}{" "}
          <Link href={`/questions/${asked.slug}`} prefetch={false} className="gm-link">
            {t.askedMissingLink}
          </Link>
        </p>
      ) : null}

      {markets === null || rules === null ? (
        error ? null : (
          <p className="gm-loading" role="status">
            {t.marketsLoading}
          </p>
        )
      ) : markets.length === 0 && !pinnedId ? (
        <p className="gm-empty">{category ? t.marketsEmpty : t.marketsEmptyAll}</p>
      ) : (
        <>
          {/* The list's own heading, between the view's and each card's. */}
          <h2 className="sr-only">{t.cardsHeading}</h2>
          <ul className="gm-cards">
            {(pinned && pinned !== "missing"
              ? [pinned, ...markets.filter((market) => market.id !== pinned.id)]
              : markets
            ).map((market) => (
              <li key={market.id}>
                <MarketCard
                  market={market}
                  rules={rules}
                  paused={onBreak || limitReached}
                  readAt={readAt}
                  asked={market.id === pinnedId}
                />
              </li>
            ))}
          </ul>

          {cursor ? (
            <div className="gm-more">
              <button
                type="button"
                className="btn btn--secondary"
                onClick={() => void loadMore()}
                disabled={loadingMore}
              >
                {loadingMore ? t.loading : t.loadMore}
              </button>
            </div>
          ) : null}
        </>
      )}
    </section>
  );
}
