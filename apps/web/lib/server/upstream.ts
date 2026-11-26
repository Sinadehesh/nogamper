import "server-only";

import { cookies } from "next/headers";


export const SESSION_COOKIE = process.env.SESSION_COOKIE_NAME ?? "session";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000";

export type UpstreamError = { code: string; detail: string } & Record<
  string,
  unknown
>;

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
        detail: error.detail ?? "The API could not complete this request.",
      },
    };
  }

  return { ok: true, status: response.status, data: body as T };
}

export async function callApi<T>(
  path: string,
  init: RequestInit & { authenticated?: boolean } = {},
): Promise<UpstreamResult<T>> {
  const { authenticated = false, headers, ...rest } = init;
  const merged = new Headers(headers);
  merged.set("Content-Type", "application/json");

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
