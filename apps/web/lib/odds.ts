import type { MarketRules, MarketSummary, Side } from "@/lib/types";

/**
 * The price of an outcome, worked out in the page so a card can show it
 * without a round trip. The server prices every slip again at quote and at
 * placement; nothing computed here is ever what gets paid.
 *
 * It is the same arithmetic as apps/api/backend/engine/odds.py, and it is
 * short enough to read: odds are one divided by the probability. There is no
 * margin to subtract because there is no margin.
 */

export function probabilityOf(market: MarketSummary, side: Side): number {
  return Number(side === "YES" ? market.probability.yes : market.probability.no);
}

/** Truncated to six places, as the server does — never rounded up. */
export function fairOdds(probability: number): number {
  if (!(probability > 0)) return 0;
  return Math.floor((1 / probability) * 1e6) / 1e6;
}

/**
 * Whether this side can be forecast at all. An outcome the market puts above
 * the band is all but settled and one below it is all but impossible; neither
 * has a price worth offering, and the server refuses both.
 */
export function isPriceable(market: MarketSummary, side: Side, rules: MarketRules): boolean {
  const probability = probabilityOf(market, side);
  return probability >= Number(rules.min_prob) && probability <= Number(rules.max_prob);
}

/**
 * What a bookmaker's margin of `margin` per pick takes from a slip of `legs`
 * picks, as a share of the stake: 1 − (1 − margin)^legs.
 *
 * Not used to price anything. It is here so the site can show what it does
 * not charge.
 */
export function bookmakerTake(margin: number, legs: number): number {
  return legs < 1 ? 0 : 1 - (1 - margin) ** legs;
}
