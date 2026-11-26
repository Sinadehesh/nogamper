"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { MarketCard } from "@/components/MarketCard";
import { usePlayer } from "@/components/PlayerProvider";
import { getMarkets } from "@/lib/api";
import { categoryLabel, errorMessage, t } from "@/lib/copy";
import type { MarketRules, MarketSort, MarketSummary } from "@/lib/types";

const PAGE_SIZE = 40;
const REFRESH_MS = 60_000;

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
}: {
  /** Hands the feed's rules up, so the slip prices against the same ones. */
  onRules: (rules: MarketRules) => void;
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
      setMarkets(page);
      setCursor(next_cursor);
      setCategories(listed);
      setRules(pageRules);
      onRules(pageRules);
      setError(null);
    },
    [category, sort, onRules, refresh],
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
  }, [cursor, category, sort]);

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-1.5" role="group" aria-label={t.tabMarkets}>
          {[null, ...categories].map((entry) => (
            <button
              key={entry ?? "all"}
              type="button"
              onClick={() => setCategory(entry)}
              aria-pressed={category === entry}
              className={`rounded-full border px-3 py-1.5 text-sm font-semibold ${
                category === entry
                  ? "border-accent bg-accent text-on-accent"
                  : "border-line bg-surface text-muted hover:text-ink"
              }`}
            >
              {entry === null ? t.categoryAll : categoryLabel(entry)}
            </button>
          ))}
        </div>

        <label className="flex items-center gap-2 text-sm text-muted">
          <span>{t.sortLabel}</span>
          <select
            className="field !min-h-9 !w-auto !py-1 text-sm"
            value={sort}
            onChange={(event) => setSort(event.target.value as MarketSort)}
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
        <p className="notice notice-warn">{t.onBreakNoPicks}</p>
      ) : limitReached ? (
        <p className="notice notice-warn">{t.limitReachedNoPicks}</p>
      ) : null}

      {error ? (
        <p role="alert" className="notice notice-error flex items-center justify-between gap-3">
          <span>{error}</span>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => void load(shown.current)}
          >
            {t.retry}
          </button>
        </p>
      ) : null}

      {markets === null || rules === null ? (
        error ? null : (
          <p className="py-10 text-center text-muted">{t.marketsLoading}</p>
        )
      ) : markets.length === 0 ? (
        <p className="py-10 text-center text-muted">
          {category ? t.marketsEmpty : t.marketsEmptyAll}
        </p>
      ) : (
        <>
          <ul className="grid gap-3 md:grid-cols-2">
            {markets.map((market) => (
              <li key={market.id}>
                <MarketCard market={market} rules={rules} paused={onBreak || limitReached} />
              </li>
            ))}
          </ul>

          {cursor ? (
            <div className="flex justify-center pt-2">
              <button
                type="button"
                className="btn btn-secondary"
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
