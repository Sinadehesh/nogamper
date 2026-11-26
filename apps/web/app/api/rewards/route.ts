import { NextResponse } from "next/server";

import { callApi } from "@/lib/server/upstream";

export async function GET() {
  const result = await callApi("/v1/rewards", { authenticated: true });

  return result.ok
    ? NextResponse.json(result.data)
    : NextResponse.json(result.error, { status: result.status });
}
