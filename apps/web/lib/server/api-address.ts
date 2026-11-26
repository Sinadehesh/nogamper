import "server-only";

/**
 * Where the API lives, and the key that tells it this server is the site.
 *
 * Both are pasted into a hosting dashboard by hand, and a value pasted by hand
 * brings along whatever was next to it: a space, a line break, the slash a
 * browser shows at the end of an address. Any one of those makes every call
 * to the API fail in a way that looks exactly like the API being down — a
 * slash turns `/v1/rules` into `//v1/rules`, which no route answers, and a
 * line break is not a legal header at all.
 *
 * So they are tidied once, here, and everything that calls the API reads
 * them from here.
 */
export const API_BASE_URL = (process.env.API_BASE_URL?.trim() || "http://localhost:8000").replace(
  /\/+$/,
  "",
);

// Shared with the API. It is what lets the API believe the visitor address
// this server sends, and what stops anyone else calling its sign-up routes
// directly.
export const INTERNAL_API_KEY = process.env.INTERNAL_API_KEY?.trim() ?? "";
