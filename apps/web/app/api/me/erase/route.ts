import { NextResponse } from "next/server";

import { SESSION_COOKIE, badRequest, callApi, readJson } from "@/lib/server/upstream";

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

  const response = new NextResponse(null, { status: 204 });
  response.cookies.delete(SESSION_COOKIE);
  return response;
}
