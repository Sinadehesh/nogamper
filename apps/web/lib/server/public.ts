import "server-only";

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

const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000";
const INTERNAL_API_KEY = process.env.INTERNAL_API_KEY ?? "";
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
