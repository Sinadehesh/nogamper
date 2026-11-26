import { NextResponse } from "next/server";

import { callApi, clearSession } from "@/lib/server/upstream";

/**
 * Sign out. The cookie is cleared whatever the API says: if the session was
 * already dead there, "signed out" is still the truth the browser should be
 * left holding.
 */
export async function DELETE() {
  await callApi<null>("/v1/auth/session", { method: "DELETE", authenticated: true });

  return clearSession(new NextResponse(null, { status: 204 }));
}
