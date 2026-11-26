import { NextResponse } from "next/server";

import { refreshReaderArticles } from "@/lib/server/articles";
import { badRequest, callApi, clearSession, readJson } from "@/lib/server/upstream";

/** Erase the account. On success there is no session left to hold a cookie for. */
export async function POST(request: Request) {
  const body = await readJson(request);
  if (!body) return badRequest();

  const result = await callApi<null>("/v1/me/erase", {
    method: "POST",
    body: JSON.stringify({ password: body.password ?? null }),
    authenticated: true,
  });

  if (!result.ok) {
    return NextResponse.json(result.error, { status: result.status });
  }

  // Their articles went with the account; the public pages should agree.
  refreshReaderArticles();
  return clearSession(new NextResponse(null, { status: 204 }));
}
