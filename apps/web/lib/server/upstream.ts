import "server-only";

import { cookies, headers } from "next/headers";
import { NextResponse } from "next/server";

import { API_BASE_URL, INTERNAL_API_KEY } from "@/lib/server/api-address";
import { SIGNED_IN_COOKIE } from "@/lib/session-marker";

/**
 * The only code that talks to the API.
 *
 * The browser never does. It holds an HttpOnly cookie it cannot read, sends
 * it to this server, and this server turns it into a Bearer token for the
 * API. So a script running in the page has no credential to steal, and the
 * API's address never has to be known to a browser at all.
 */

export const SESSION_COOKIE = process.env.SESSION_COOKIE_NAME ?? "session";


// The one request header this deployment's platform guarantees carries the
// visitor's address. Unset, the two conventional ones are read — see
// visitorAddress() for when that is and is not safe.
const CLIENT_IP_HEADER = (process.env.CLIENT_IP_HEADER ?? "").trim().toLowerCase();

let warnedAboutKey = false;

/**
 * Say so, once, when a production server has no key.
 *
 * The API refuses to open a session for a caller without it, and answers 404
 * so as not to advertise the route — which from here looks like "sign-up is
 * broken" with nothing pointing at the cause. One line in the log is the
 * difference between a minute and an afternoon.
 */
function warnIfKeyMissing(): void {
  if (warnedAboutKey || INTERNAL_API_KEY || process.env.NODE_ENV !== "production") return;
  warnedAboutKey = true;
  console.error(
    "INTERNAL_API_KEY is not set. The API will refuse sign-up, sign-in and guest " +
      "sessions from this server. Set it to the same value the API has.",
  );
}

export type UpstreamError = { code: string; detail: string } & Record<string, unknown>;

export type UpstreamResult<T> =
  | { ok: true; status: number; data: T }
  | { ok: false; status: number; error: UpstreamError };

async function parse<T>(response: Response): Promise<UpstreamResult<T>> {
  if (response.status === 204) {
    return { ok: true, status: 204, data: undefined as T };
  }

  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }

  if (!response.ok) {
    const error = (body ?? {}) as Partial<UpstreamError>;
    return {
      ok: false,
      status: response.status,
      error: {
        ...error,
        code: error.code ?? "upstream_error",
        detail:
          typeof error.detail === "string"
            ? error.detail
            : "The API could not complete this request.",
      },
    };
  }

  return { ok: true, status: response.status, data: body as T };
}

function firstHop(value: string | null): string | null {
  const hop = value?.split(",")[0]?.trim();
  return hop ? hop : null;
}

/**
 * The visitor's address, as the hosting platform reports it.
 *
 * This is only as trustworthy as the proxy in front of this server. By
 * default it reads `x-real-ip`, then the first hop of `x-forwarded-for` —
 * correct on a platform that *overwrites* those headers with what it saw
 * (Vercel does), and spoofable on one that passes a client's own value
 * through or appends to it, where a visitor could send a new address with
 * every request and walk around the sign-up throttle.
 *
 * On such a platform, set CLIENT_IP_HEADER to the header it does guarantee
 * (`cf-connecting-ip` behind Cloudflare, `fly-client-ip` on Fly, and so on)
 * and nothing else is consulted.
 *
 * With no proxy at all every header is absent, and the API falls back to the
 * address of the socket — this server's — which is one shared bucket: coarse,
 * but never wrong in a way a visitor can exploit.
 */
async function visitorAddress(): Promise<string | null> {
  const incoming = await headers();
  if (CLIENT_IP_HEADER) return firstHop(incoming.get(CLIENT_IP_HEADER));
  return firstHop(incoming.get("x-real-ip")) ?? firstHop(incoming.get("x-forwarded-for"));
}

export async function callApi<T>(
  path: string,
  init: RequestInit & { authenticated?: boolean } = {},
): Promise<UpstreamResult<T>> {
  const { authenticated = false, headers: extra, ...rest } = init;
  const merged = new Headers(extra);
  merged.set("Content-Type", "application/json");

  warnIfKeyMissing();
  if (INTERNAL_API_KEY) {
    merged.set("X-Internal-Key", INTERNAL_API_KEY);
    const address = await visitorAddress();
    if (address) merged.set("X-Client-IP", address);
  }

  if (authenticated) {
    const token = (await cookies()).get(SESSION_COOKIE)?.value;
    if (!token) {
      return {
        ok: false,
        status: 401,
        error: { code: "no_session", detail: "No session cookie present." },
      };
    }
    merged.set("Authorization", `Bearer ${token}`);
  }

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...rest,
      headers: merged,
      cache: "no-store",
    });
    return await parse<T>(response);
  } catch {
    return {
      ok: false,
      status: 502,
      error: { code: "api_unreachable", detail: "The API is not reachable." },
    };
  }
}

type SessionPayload = {
  access_token: string;
  expires_at: string;
  is_new_user: boolean;
  user: unknown;
};

/**
 * Turn a session the API just opened into a cookie, and hand the browser the
 * profile — never the token.
 *
 * `SameSite=Lax`: sent on a link the visitor follows here, withheld from a
 * POST another site submits. A standalone site has no reason to accept its
 * own cookie from somebody else's page.
 */
export function sessionResponse(result: UpstreamResult<SessionPayload>): NextResponse {
  if (!result.ok) {
    return NextResponse.json(result.error, { status: result.status });
  }

  const { access_token, expires_at, is_new_user, user } = result.data;
  const response = NextResponse.json({ isNewUser: is_new_user, user }, { status: result.status });

  const shared = {
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax" as const,
    path: "/",
    expires: new Date(expires_at),
  };
  response.cookies.set({ name: SESSION_COOKIE, value: access_token, httpOnly: true, ...shared });
  // Readable by the page, and worth nothing: see lib/session-marker.ts.
  response.cookies.set({ name: SIGNED_IN_COOKIE, value: "1", httpOnly: false, ...shared });
  return response;
}

/** Drop the session, and the marker that says there is one. */
export function clearSession(response: NextResponse): NextResponse {
  response.cookies.delete(SESSION_COOKIE);
  response.cookies.delete(SIGNED_IN_COOKIE);
  return response;
}

/** The session token currently held, forwarded as-is for a guest upgrade. */
export async function currentToken(): Promise<string | null> {
  return (await cookies()).get(SESSION_COOKIE)?.value ?? null;
}

export async function readJson(request: Request): Promise<Record<string, unknown> | null> {
  try {
    const body: unknown = await request.json();
    return body && typeof body === "object" && !Array.isArray(body)
      ? (body as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}

export function badRequest(detail = "Expected a JSON object."): NextResponse {
  return NextResponse.json({ code: "bad_request", detail }, { status: 400 });
}
