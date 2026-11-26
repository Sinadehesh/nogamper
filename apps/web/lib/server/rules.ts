import "server-only";

import { publicApi } from "@/lib/server/public";
import type { GameRules } from "@/lib/types";

/**
 * The game's rules, read from the API for a page that explains them.
 *
 * Null rather than a thrown error when the API cannot be reached: the pages
 * that use this are the ones a visitor reads before anything else, and they
 * should still say what the site is when the game behind it is having a bad
 * minute. The copy is written to read correctly without the figures.
 *
 * Cached for ten minutes. The rules change when somebody redeploys, not
 * between one visitor and the next.
 */
export async function getRules(): Promise<GameRules | null> {
  return publicApi<GameRules>("/v1/rules", 600);
}
