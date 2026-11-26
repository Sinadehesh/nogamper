import "server-only";

import { cookies } from "next/headers";

import { SESSION_COOKIE } from "@/lib/server/upstream";

/**
 * Whether the visitor is carrying a session cookie.
 *
 * Not whether it is still valid — only the API can say that, and asking it on
 * every page view would put a database round trip in front of pages that do
 * not need one. This is for deciding which link to show. Anything that
 * matters checks properly.
 */
export async function hasSessionCookie(): Promise<boolean> {
  return Boolean((await cookies()).get(SESSION_COOKIE)?.value);
}
