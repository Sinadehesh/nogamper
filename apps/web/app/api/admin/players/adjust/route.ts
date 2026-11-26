import { NextResponse } from "next/server";

import { callApi } from "@/lib/server/upstream";

export async function POST(request: Request) {
  const body = await request.json();
  const result = await callApi("/v1/admin/players/adjust", {
    method: "POST",
    body: JSON.stringify(body),
    authenticated: true,
  });

  return result.ok
    ? NextResponse.json(result.data)
    : NextResponse.json(result.error, { status: result.status });
}
