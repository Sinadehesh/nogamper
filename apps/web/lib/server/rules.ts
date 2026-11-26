import "server-only";

import { callApi } from "@/lib/server/upstream";
import type { GameRules } from "@/lib/types";

/**
 * The game's rules, read from the API for a page that explains them.
 *
 * Null rather than a thrown error when the API cannot be reached: the pages
 * that use this are the ones a visitor reads before anything else, and they
 * should still say what the site is when the game behind it is having a bad
 * minute. The copy is written to read correctly without the figures.
 */
export async function getRules(): Promise<GameRules | null> {
  const result = await callApi<GameRules>("/v1/rules");
  return result.ok ? result.data : null;
}
