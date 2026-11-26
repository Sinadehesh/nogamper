
import type { MarketSummary, Side } from "@/lib/types";

export function baseOdds(
  market: MarketSummary,
  side: Side,
  vigRate: number,
): number {
  const probability = Number(
    side === "YES" ? market.probability.yes : market.probability.no,
  );
  if (!Number.isFinite(probability) || probability <= 0) return 0;
  return (1 - vigRate) / probability;
}

const FLOOR = 1.01;

function truncate6(value: number): number {
  return Math.floor(value * 1e6) / 1e6;
}

export function lockedOdds(
  market: MarketSummary,
  side: Side,
  vigRate: number,
  { withBoost = true }: { withBoost?: boolean } = {},
): number {
  const base = baseOdds(market, side, vigRate);
  if (!(base > 0)) return 0;
  const boost = withBoost
    ? market.boosts.find((entry) => entry.side === side)
    : undefined;
  return Math.max(
    truncate6(boost ? base * Number(boost.multiplier) : base),
    FLOOR,
  );
}

export function parlayBonus(legs: number, bonuses: string[]): number {
  const value = Number(bonuses[legs - 1]);
  return Number.isFinite(value) && value > 0 ? value : 1;
}

export function combinedOdds(
  selections: { marketId: string; side: Side }[],
  markets: MarketSummary[],
  vigRate: number,
  bonuses: string[],
): number | null {
  if (selections.length === 0) return null;

  const byId = new Map(markets.map((market) => [market.id, market]));
  let product = 1;
  for (const selection of selections) {
    const market = byId.get(selection.marketId);
    if (!market) return null;
    const odds = lockedOdds(market, selection.side, vigRate);
    if (!(odds > 0)) return null;
    product *= odds;
  }
  return product * parlayBonus(selections.length, bonuses);
}

export function longestOddsSlip(
  markets: MarketSummary[],
  vigRate: number,
  limit: number,
): { market: MarketSummary; side: Side }[] {
  return markets
    .filter((market) => !market.probability.stale)
    .map((market) => {
      const yes = lockedOdds(market, "YES", vigRate);
      const no = lockedOdds(market, "NO", vigRate);
      const side: Side = no > yes ? "NO" : "YES";
      return { market, side, odds: Math.max(yes, no) };
    })
    .filter((entry) => entry.odds > 1)
    .sort((a, b) => b.odds - a.odds)
    .slice(0, limit * 3) // headroom for events collapsing to one leg
    .map(({ market, side }) => ({ market, side }));
}
