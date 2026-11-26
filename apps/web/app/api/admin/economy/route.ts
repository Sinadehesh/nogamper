import { NextResponse } from "next/server";

import { callApi } from "@/lib/server/upstream";

export async function GET(request: Request) {
  const days = new URL(request.url).searchParams.get("days") ?? "30";
  const result = await callApi(`/v1/admin/economy?days=${encodeURIComponent(days)}`, {
    authenticated: true,
  });

  return result.ok
    ? NextResponse.json(result.data)
    : NextResponse.json(result.error, { status: result.status });
}
