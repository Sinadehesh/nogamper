import { NextResponse } from "next/server";

import { callApi } from "@/lib/server/upstream";

export async function GET(request: Request) {
  const incoming = new URL(request.url).searchParams;
  const query = new URLSearchParams();
  for (const key of ["search", "limit", "offset"]) {
    const value = incoming.get(key);
    if (value) query.set(key, value);
  }

  const result = await callApi(`/v1/admin/players?${query}`, { authenticated: true });
  return result.ok
    ? NextResponse.json(result.data)
    : NextResponse.json(result.error, { status: result.status });
}
