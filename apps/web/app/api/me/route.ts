import { NextResponse } from "next/server";

import { SESSION_COOKIE, callApi } from "@/lib/server/upstream";
import type { UserProfile } from "@/lib/types";

export async function GET() {
  const result = await callApi<UserProfile>("/v1/me", { authenticated: true });

  if (!result.ok) {
    const response = NextResponse.json(result.error, { status: result.status });
    if (result.status === 401) {
      response.cookies.delete(SESSION_COOKIE);
    }
    return response;
  }

  return NextResponse.json(result.data);
}
