/**
 * The proof of ownership IndexNow asks for.
 *
 * IndexNow is how a site tells Bing, and the other search engines that share
 * the protocol, that a page is new or has changed, without an account with
 * any of them. The site picks a key, publishes it at an address on its own
 * host, and quotes that address when it submits pages; the search engine
 * fetches it and checks the two match. So the key is public by design: all it
 * proves is that whoever is submitting can also publish here.
 *
 * With INDEXNOW_KEY unset this answers 404 and nothing can be submitted.
 * scripts/indexnow.py does the submitting.
 */
export const dynamic = "force-static";

const KEY = process.env.INDEXNOW_KEY?.trim() ?? "";

export function GET(): Response {
  // The protocol's own limits: 8 to 128 characters, letters, digits, dashes.
  if (!/^[A-Za-z0-9-]{8,128}$/.test(KEY)) {
    return new Response(null, { status: 404 });
  }
  return new Response(KEY, {
    headers: { "Content-Type": "text/plain; charset=utf-8" },
  });
}
