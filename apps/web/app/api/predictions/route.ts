import { NextRequest, NextResponse } from "next/server";

import { callApi } from "@/lib/server/upstream";

export async function GET(request: NextRequest) {
  const query = request.nextUrl.searchParams.toString();
  const result = await callApi(`/v1/predictions${query ? `?${query}` : ""}`, {
    authenticated: true,
  });

  return result.ok
    ? NextResponse.json(result.data)
    : NextResponse.json(result.error, { status: result.status });
}

export async function POST(request: NextRequest) {
  const idempotencyKey = request.headers.get("Idempotency-Key");
  if (!idempotencyKey) {
    return NextResponse.json(
      { code: "idempotency_key_required", detail: "Missing Idempotency-Key." },
      { status: 400 },
    );
  }

  const result = await callApi("/v1/predictions", {
    method: "POST",
    body: JSON.stringify(await request.json()),
    headers: { "Idempotency-Key": idempotencyKey },
    authenticated: true,
  });

  return result.ok
    ? NextResponse.json(result.data, { status: result.status })
    : NextResponse.json(result.error, { status: result.status });
}
