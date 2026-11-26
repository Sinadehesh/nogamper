import { NextRequest, NextResponse } from "next/server";

import { callApi } from "@/lib/server/upstream";

export async function POST(request: NextRequest) {
  const result = await callApi("/v1/payments/invoices", {
    method: "POST",
    body: JSON.stringify(await request.json()),
    authenticated: true,
  });

  return result.ok
    ? NextResponse.json(result.data, { status: 201 })
    : NextResponse.json(result.error, { status: result.status });
}
