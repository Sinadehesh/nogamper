import { NextResponse, type NextRequest } from "next/server";

/**
 * Refuse a state-changing request that did not come from this site.
 *
 * The session lives in a cookie, and a cookie is attached by the browser to
 * any request for this origin — including one a different site caused. The
 * cookie is `SameSite=Lax`, which already keeps it off cross-site POSTs in
 * every current browser. This is the second lock on the same door, for the
 * browser that predates that default and for the day somebody loosens the
 * cookie without thinking about why it was tight.
 *
 * A browser states where a request came from in `Origin` and, in newer ones,
 * `Sec-Fetch-Site`. A page on another site cannot forge either. So: anything
 * that writes must say it is same-origin, in at least one of those two ways.
 */

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

function isSameOrigin(request: NextRequest): boolean {
  const fetchSite = request.headers.get("sec-fetch-site");
  if (fetchSite) {
    // "none" is a request the user made directly — typed, bookmarked. It is
    // not a way to reach a POST handler, but it is not cross-site either.
    return fetchSite === "same-origin" || fetchSite === "none";
  }

  const origin = request.headers.get("origin");
  if (!origin) return false;

  // Compared against the Host the request arrived with, not against a
  // configured public URL: behind any proxy that rewrites one but not the
  // other this would be wrong, and it would be wrong by refusing everything,
  // which is the direction to be wrong in.
  const host = request.headers.get("x-forwarded-host") ?? request.headers.get("host");
  try {
    return new URL(origin).host === host;
  } catch {
    return false;
  }
}

export function proxy(request: NextRequest) {
  if (SAFE_METHODS.has(request.method) || isSameOrigin(request)) {
    return NextResponse.next();
  }

  return NextResponse.json(
    { code: "cross_site_request", detail: "This request did not come from this site." },
    { status: 403 },
  );
}

export const config = {
  matcher: "/api/:path*",
};
