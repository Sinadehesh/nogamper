"use client";

import { createContext, useContext, useSyncExternalStore, type ReactNode } from "react";

import type { SlipQuote } from "@/lib/types";

/**
 * Three small things the game's parts share.
 *
 * Whether the screen is wide enough for the slip to sit beside the feed
 * (the same 1024px where the views move into the top bar), read from the
 * browser: the server, and the first paint, assume a phone, which shows no
 * slip until a pick is made, so nothing moves when the answer arrives.
 *
 * And the public page of each open question, by its wording: the game's
 * feed knows a question by its id, the public pages by their address, and
 * the page that serves the game reads the list of addresses for it.
 */

const WIDE = "(min-width: 1024px)";

function subscribe(onChange: () => void): () => void {
  const query = window.matchMedia(WIDE);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

export function useWide(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => window.matchMedia(WIDE).matches,
    () => false,
  );
}

const Links = createContext<Readonly<Record<string, string>>>({});

export function QuestionLinks({
  links,
  children,
}: {
  links: Readonly<Record<string, string>>;
  children: ReactNode;
}) {
  return <Links.Provider value={links}>{children}</Links.Provider>;
}

/** The address of a question's public page, or null when it has none. */
export function useQuestionPage(question: string): string | null {
  const slug = useContext(Links)[question];
  return slug ? `/questions/${slug}` : null;
}

/**
 * The price the slip was last quoted for each question on it.
 *
 * The feed is read once a minute and a quote is asked for whenever the slip
 * changes, so a quote can carry a newer price than the card shows. A card
 * whose question is on the slip shows the quoted price, so the card, its two
 * picks and the slip never print different figures for one pick. Both sides
 * from the quoted one, at the API's four places.
 */
export type QuotedPrice = { yes: string; no: string };

export function quotedPrices(quote: SlipQuote | null): ReadonlyMap<string, QuotedPrice> {
  const prices = new Map<string, QuotedPrice>();
  for (const leg of quote?.legs ?? []) {
    const other = (1 - Number(leg.probability)).toFixed(4);
    prices.set(
      leg.market_id,
      leg.side === "NO" ? { yes: other, no: leg.probability } : { yes: leg.probability, no: other },
    );
  }
  return prices;
}

const Quoted = createContext<ReadonlyMap<string, QuotedPrice>>(new Map());

export function QuotedPrices({
  prices,
  children,
}: {
  prices: ReadonlyMap<string, QuotedPrice>;
  children: ReactNode;
}) {
  return <Quoted.Provider value={prices}>{children}</Quoted.Provider>;
}

/** The slip's quoted price for one question, or null when it is not on a quoted slip. */
export function useQuotedPrice(marketId: string): QuotedPrice | null {
  return useContext(Quoted).get(marketId) ?? null;
}

/**
 * The way from a card to the slip. On a wide screen the slip is a rail that
 * comes after every card in the page's order, forty or more stops away by
 * keyboard; this goes straight to its stake. On a phone it opens the sheet.
 */
const Review = createContext<(() => void) | null>(null);

export function ReviewSlip({ onReview, children }: { onReview: () => void; children: ReactNode }) {
  return <Review.Provider value={onReview}>{children}</Review.Provider>;
}

export function useReviewSlip(): (() => void) | null {
  return useContext(Review);
}
