import "server-only";

import { API_BASE_URL, INTERNAL_API_KEY } from "@/lib/server/api-address";

/**
 * Reads of things the API publishes to everybody: the rules of the game,
 * published articles.
 *
 * Separate from `callApi` on purpose. That one attaches a visitor's session
 * and address, which means it reads the request — and a page that reads the
 * request is rendered again for every single visitor. The pages that use
 * *this* are the ones a search engine and a stranger see first, and they
 * should be built once, served from a cache, and refreshed in the background.
 * So nothing here touches a cookie or a header, and every answer is cached
 * for a stated time.
 *
 * A failure is `null`, never a thrown error, and comes back quickly. A page
 * about quitting gambling should not be slow, or missing, because the game
 * behind it is having a bad minute.
 */

const TIMEOUT_MS = 4_000;

export async function publicApi<T>(
  path: string,
  revalidateSeconds: number,
  tags?: string[],
): Promise<T | null> {
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      headers: INTERNAL_API_KEY ? { "X-Internal-Key": INTERNAL_API_KEY } : undefined,
      next: { revalidate: revalidateSeconds, tags },
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    if (!response.ok) return null;
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

export type PublicAnswer<T> =
  | { status: "ok"; data: T }
  /** The API answered, and it has no such thing. */
  | { status: "missing" }
  /** The API could not be asked, or did not answer in time. */
  | { status: "unavailable" };

/**
 * The same read, for a page that has to tell "there is no such thing" from
 * "I could not find out".
 *
 * `publicApi` folds both into null, which is right for a page that reads the
 * same either way. It is wrong for a page whose whole content is the answer:
 * shown as "not found", a question that exists would be dropped from a search
 * engine because the API was slow for a moment.
 *
 * Only an answer of "yes, here it is" is kept for `revalidateSeconds`. A
 * failure is asked about again the next time, which is what lets the API say
 * "not ready yet" without that being repeated to every caller for five
 * minutes.
 */
export async function publicApiAnswer<T>(
  path: string,
  revalidateSeconds: number,
  options: { tags?: string[]; timeoutMs?: number } = {},
): Promise<PublicAnswer<T>> {
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      headers: INTERNAL_API_KEY ? { "X-Internal-Key": INTERNAL_API_KEY } : undefined,
      next: { revalidate: revalidateSeconds, tags: options.tags },
      signal: AbortSignal.timeout(options.timeoutMs ?? TIMEOUT_MS),
    });
    if (response.status === 404) return { status: "missing" };
    if (!response.ok) return { status: "unavailable" };
    return { status: "ok", data: (await response.json()) as T };
  } catch {
    return { status: "unavailable" };
  }
}

/**
 * True when a page that cannot get its figures has no earlier copy of itself
 * to fall back on: while the site is being built, and in development.
 */
const NO_EARLIER_COPY =
  process.env.NEXT_PHASE === "phase-production-build" || process.env.NODE_ENV !== "production";

/**
 * Called by a page that is built once and refreshed in the background, when
 * the figures it is made of could not be had.
 *
 * On the running site this throws, on purpose. A refresh that fails leaves
 * the page as it was last built still being served — real figures, with the
 * time they are from printed on them — and is tried again shortly. A refresh
 * that "succeeds" in building an apology replaces those figures with it, for
 * every visitor, because the API was asleep for a minute.
 *
 * While the site is being built there is no earlier copy, so this returns and
 * the page is built saying what it could not fetch.
 *
 * It only works where nothing above the page is waiting on its behalf: under a
 * `loading.tsx` the error would be sent to the browser as part of a page that
 * otherwise built, and kept.
 */
export function keepEarlierCopy(what: string): void {
  if (NO_EARLIER_COPY) return;
  throw new Error(`${what} could not be fetched. Keeping the page as it was last built.`);
}
