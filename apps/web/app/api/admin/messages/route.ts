import { NextResponse } from "next/server";

import { callApi } from "@/lib/server/upstream";

export async function GET(request: Request) {
  const status = new URL(request.url).searchParams.get("status");
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  const result = await callApi(`/v1/admin/messages${query}`, { authenticated: true });
  return result.ok
    ? NextResponse.json(result.data)
    : NextResponse.json(result.error, { status: result.status });
}
