import { odds, points } from "@/lib/format";
import { fairOdds } from "@/lib/odds";
import type { CSSProperties } from "react";

import type { GameRules, Side } from "@/lib/types";
import { pctPair, sideProbability, slipFigures } from "@/lib/viz";

/** The stake the front page shows a pick at: 100 points, in minor units. */
export const SHOWN_STAKE = 10_000;

/** Whether the game would price this side at all (inside its 1% to 99% band). */
export function priceable(probability: number, rules: GameRules | null): boolean {
  if (!rules) return probability > 0 && probability < 1;
  return probability >= Number(rules.min_prob) && probability <= Number(rules.max_prob);
}

/** "pays 1.61×": a side's fair odds, as the game's cards print them. */
export function oddsFor(probability: number): string {
  return odds(fairOdds(probability));
}

/**
 * What a one-pick slip pays back, in whole points as the game prints them,
 * worked out the way the server prices it (lib/viz.ts slipFigures). Without
 * the rules the same arithmetic stands, one divided by the chance; null when
 * the game would not take the slip.
 */
export function payoutFor(probability: number, rules: GameRules | null, stakeMinor = SHOWN_STAKE): string | null {
  if (rules) {
    const figures = slipFigures([{ side: "YES", probability }], stakeMinor, rules);
    return figures.refused === null ? points(figures.payoutMinor) : null;
  }
  if (!(probability > 0 && probability < 1)) return null;
  return points(Math.round(stakeMinor * fairOdds(probability)));
}

/** Both sides of one question: its chance, and what each side's pick pays. */
export function sides(yes: number, rules: GameRules | null) {
  // Both figures from Yes, so the two always add up to 100.
  const pair = pctPair(yes);
  return (["YES", "NO"] as Side[]).map((side) => {
    const probability = sideProbability(yes, side);
    return {
      side,
      chance: side === "YES" ? pair.yes : pair.no,
      probability,
      pays: priceable(probability, rules) ? oddsFor(probability) : null,
    };
  });
}

export const stakeShown = points(SHOWN_STAKE);

/** A section two screens tall on a phone and one elsewhere (the kit's --hm). */
export const TWO_ON_A_PHONE = { "--hm": 2 } as CSSProperties;
