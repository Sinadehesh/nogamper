import { NextRequest, NextResponse } from "next/server";

import { refreshReaderArticles } from "@/lib/server/articles";
import { callApi, clearSession } from "@/lib/server/upstream";

/**
 * Every signed-in request the page makes, forwarded to the API.
 *
 * One handler rather than a file per endpoint, with an explicit list of what
 * may pass. The list is the point: this server holds the visitor's session
 * and attaches it to whatever it forwards, so "forward anything under /api"
 * would make every route the API ever grows reachable from a browser by
 * default. A path that is not written down here does not exist.
 *
 * The routes that open or close a session are not here. They set and clear
 * the cookie, and live in their own files under ./session.
 */

const UUID = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";

const ALLOWED: Record<string, RegExp[]> = {
  GET: [
    /^me$/,
    /^me\/limits$/,
    /^me\/reality-check$/,
    /^markets$/,
    /^predictions$/,
    new RegExp(`^predictions/${UUID}$`),
    /^economy\/leaderboard$/,
    /^shop$/,
    /^messages$/,
    /^me\/articles$/,
    new RegExp(`^me/articles/${UUID}$`),
    /^admin\/(overview|players|messages|diagnostics|articles)$/,
  ],
  POST: [
    /^me\/break$/,
    /^predictions$/,
    /^predictions\/quote$/,
    /^economy\/claim$/,
    /^shop\/checkout$/,
    /^messages$/,
    /^auth\/password$/,
    /^admin\/players\/(adjust|status)$/,
    new RegExp(`^admin/messages/${UUID}(/reply)?$`),
    /^me\/articles$/,
    new RegExp(`^me/articles/${UUID}/(submit|withdraw)$`),
    new RegExp(`^admin/articles/${UUID}/review$`),
  ],
  PUT: [/^me\/limits$/, /^shop\/limit$/, new RegExp(`^me/articles/${UUID}$`)],
  PATCH: [/^me$/],
  DELETE: [new RegExp(`^me/articles/${UUID}$`)],
};

// Writes that can change which readers' articles are public: anything an
// author or a reviewer does to one, and a ban, which hides its author's.
const CHANGES_PUBLIC_ARTICLES = /^(me\/articles|admin\/articles|admin\/players\/status$)/;

const MAX_BODY_BYTES = 16 * 1024;
// An article is the one thing a visitor sends that is meant to be long. The
// API holds it to 30,000 characters; this is that with room for the JSON
// around it and for text that is not all ASCII.
const MAX_ARTICLE_BODY_BYTES = 160 * 1024;

type Context = { params: Promise<{ path: string[] }> };

async function forward(request: NextRequest, context: Context): Promise<NextResponse> {
  const path = (await context.params).path.join("/");
  const allowed = ALLOWED[request.method]?.some((pattern) => pattern.test(path)) ?? false;
  if (!allowed) {
    return NextResponse.json({ code: "not_found", detail: "Not found." }, { status: 404 });
  }

  const init: RequestInit & { authenticated: boolean } = {
    method: request.method,
    authenticated: true,
  };

  if (request.method !== "GET") {
    const body = await request.text();
    const ceiling = path.startsWith("me/articles") ? MAX_ARTICLE_BODY_BYTES : MAX_BODY_BYTES;
    if (body.length > ceiling) {
      return NextResponse.json(
        { code: "payload_too_large", detail: "That request is too large." },
        { status: 413 },
      );
    }
    if (body) init.body = body;

    // The one request header the API needs from the browser. Everything else
    // the browser sent — cookies above all — stops here.
    const idempotencyKey = request.headers.get("Idempotency-Key");
    if (idempotencyKey) init.headers = { "Idempotency-Key": idempotencyKey.slice(0, 255) };
  }

  const query = request.nextUrl.searchParams.toString();
  const result = await callApi(`/v1/${path}${query ? `?${query}` : ""}`, init);

  if (result.ok) {
    if (request.method !== "GET" && CHANGES_PUBLIC_ARTICLES.test(path)) refreshReaderArticles();
    return result.status === 204
      ? new NextResponse(null, { status: 204 })
      : NextResponse.json(result.data, { status: result.status });
  }

  const response = NextResponse.json(result.error, { status: result.status });
  if (result.status === 401) {
    // The session is gone on the API's side — expired, revoked, erased. Keep
    // sending its cookie and every request repeats this; drop it and the page
    // can show the sign-in form once.
    clearSession(response);
  }
  return response;
}

export const GET = forward;
export const POST = forward;
export const PUT = forward;
export const PATCH = forward;
export const DELETE = forward;
