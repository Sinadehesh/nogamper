import "server-only";

import { hasSessionCookie } from "@/lib/server/session";
import { callApi } from "@/lib/server/upstream";
import type { UserProfile } from "@/lib/types";

/**
 * The signed-in player, asked of the API — or null.
 *
 * Skips the round trip entirely when there is no cookie, which is the case
 * for nearly everybody arriving at the sign-in page.
 */
export async function getViewer(): Promise<UserProfile | null> {
  if (!(await hasSessionCookie())) return null;
  const result = await callApi<UserProfile>("/v1/me", { authenticated: true });
  return result.ok ? result.data : null;
}
