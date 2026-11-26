import { NextRequest, NextResponse } from "next/server";

import { SESSION_COOKIE } from "@/lib/server/upstream";

// This endpoint takes no session and no other credential — it exists to
// catch bootstrap failures that happen *before* auth is possible. That also
// makes it the one route anyone on the internet can throw arbitrary JSON at
// for free, so what it logs is deliberately bounded rather than trusted: a
// flat record of primitives, capped in count and in per-value length, never
// the arbitrarily large or deeply nested body a caller could otherwise hand
// straight to the log.
const MAX_RAW_BYTES = 4096;
const MAX_FIELDS = 20;
const MAX_STRING_LENGTH = 200;

function sanitised(report: Record<string, unknown>): Record<string, string | number | boolean> {
  const safe: Record<string, string | number | boolean> = {};
  for (const key of Object.keys(report).slice(0, MAX_FIELDS)) {
    const value = report[key];
    if (typeof value === "string") {
      safe[key.slice(0, MAX_STRING_LENGTH)] = value.slice(0, MAX_STRING_LENGTH);
    } else if (typeof value === "number" || typeof value === "boolean") {
      safe[key.slice(0, MAX_STRING_LENGTH)] = value;
    }
  }
  return safe;
}

export async function POST(request: NextRequest) {
  const raw = await request.text();
  if (raw.length > MAX_RAW_BYTES) {
    return new NextResponse(null, { status: 204 });
  }

  let report: Record<string, unknown> | null;
  try {
    const parsed: unknown = JSON.parse(raw);
    report = parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : null;
  } catch {
    report = null;
  }
  if (!report) {
    return new NextResponse(null, { status: 204 });
  }

  const hasCookie = Boolean(request.cookies.get(SESSION_COOKIE)?.value);

  console.error(
    "BOOTSTRAP_DIAG " +
      JSON.stringify({
        ...sanitised(report),
        cookieReachedServer: hasCookie,
        ua: request.headers.get("user-agent")?.slice(0, 120) ?? null,
      }),
  );

  return new NextResponse(null, { status: 204 });
}
