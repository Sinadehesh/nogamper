import { NextRequest, NextResponse } from "next/server";

import { callApi } from "@/lib/server/upstream";

export async function GET(request: NextRequest) {
  const query = request.nextUrl.searchParams.toString();
  const result = await callApi(`/v1/markets${query ? `?${query}` : ""}`, {
    authenticated: true,
  });

  return result.ok
    ? NextResponse.json(result.data)
    : NextResponse.json(result.error, { status: result.status });
}
