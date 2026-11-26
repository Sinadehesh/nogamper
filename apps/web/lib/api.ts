import type {
  ClaimResult,
  Diagnostics,
  Inbox,
  Leaderboard,
  Limits,
  MarketPage,
  MarketSort,
  Money,
  Overview,
  PlayerList,
  PlayerMessage,
  PlayerRow,
  RealityCheck,
  Side,
  Slip,
  SlipPage,
  SlipQuote,
  UserProfile,
} from "@/lib/types";

/**
 * Calls to this site's own /api routes. Nothing here knows the API's address
 * or holds a credential: the browser's HttpOnly cookie rides along on its own
 * and the server turns it into a token.
 */

export type ApiFailure = {
  ok: false;
  status: number;
  code: string;
  detail: string;
  marketId?: string;
  until?: string;
  retryAfter?: number;
};

export type ApiSuccess<T> = { ok: true; status: number; data: T };
export type ApiResult<T> = ApiSuccess<T> | ApiFailure;

async function request<T>(path: string, init: RequestInit = {}): Promise<ApiResult<T>> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
      cache: "no-store",
    });
  } catch {
    return { ok: false, status: 0, code: "network_unavailable", detail: "" };
  }

  if (response.status === 204) {
    return { ok: true, status: 204, data: undefined as T };
  }

  const body = await response.json().catch(() => null);

  if (!response.ok) {
    const error = body as {
      code?: string;
      detail?: unknown;
      market_id?: string;
      until?: string;
      retry_after?: number;
    } | null;
    return {
      ok: false,
      status: response.status,
      // A 422 from the API's own validation has no `code`, only a list of
      // field errors that mean nothing to a visitor. Name it, and let the
      // copy table say something useful.
      code: error?.code ?? (response.status === 422 ? "invalid_request" : "unexpected_error"),
      detail: typeof error?.detail === "string" ? error.detail : "",
      marketId: error?.market_id,
      until: error?.until,
      retryAfter: error?.retry_after,
    };
  }

  return { ok: true, status: response.status, data: body as T };
}

function post<T>(path: string, body?: unknown, headers?: Record<string, string>) {
  return request<T>(path, {
    method: "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
    headers,
  });
}

// ----- session --------------------------------------------------------------

type SessionOpened = { user: UserProfile; isNewUser: boolean };

export const startAsGuest = () => post<SessionOpened>("/api/session/guest");

export const signIn = (email: string, password: string) =>
  post<SessionOpened>("/api/session/login", { email, password });

export const register = (input: { email: string; password: string; display_name: string }) =>
  post<SessionOpened>("/api/session/register", input);

export const signOut = () => request<void>("/api/session", { method: "DELETE" });

export const changePassword = (current_password: string, new_password: string) =>
  post<void>("/api/auth/password", { current_password, new_password });

// ----- the player -----------------------------------------------------------

export const getProfile = () => request<UserProfile>("/api/me");

export const renamePlayer = (display_name: string) =>
  request<UserProfile>("/api/me", { method: "PATCH", body: JSON.stringify({ display_name }) });

export const eraseAccount = (password: string | null) =>
  post<void>("/api/me/erase", { password });

export const setDailyLimit = (daily_limit_minor: number | null) =>
  request<Limits>("/api/me/limits", {
    method: "PUT",
    body: JSON.stringify({ daily_limit_minor }),
  });

export const takeBreak = (hours: number) => post<Limits>("/api/me/break", { hours });

export const getRealityCheck = () => request<RealityCheck>("/api/me/reality-check");

export const claimTopUp = () => post<ClaimResult>("/api/economy/claim");

export const getLeaderboard = () => request<Leaderboard>("/api/economy/leaderboard");

// ----- markets and forecasts ------------------------------------------------

export function getMarkets(
  params: { category?: string; sort?: MarketSort; limit?: number; cursor?: string } = {},
) {
  const query = new URLSearchParams();
  if (params.category) query.set("category", params.category);
  if (params.sort) query.set("sort", params.sort);
  if (params.limit) query.set("limit", String(params.limit));
  if (params.cursor) query.set("cursor", params.cursor);
  const suffix = query.toString();
  return request<MarketPage>(`/api/markets${suffix ? `?${suffix}` : ""}`);
}

export function getSlips(params: { status?: string; limit?: number; cursor?: string } = {}) {
  const query = new URLSearchParams();
  if (params.status) query.set("status", params.status);
  if (params.limit) query.set("limit", String(params.limit));
  if (params.cursor) query.set("cursor", params.cursor);
  const suffix = query.toString();
  return request<SlipPage>(`/api/predictions${suffix ? `?${suffix}` : ""}`);
}

export type SlipBody = {
  legs: { market_id: string; side: Side }[];
  stake: number;
  accepted_odds?: string;
};

export const quoteSlip = (body: SlipBody) => post<SlipQuote>("/api/predictions/quote", body);

/**
 * Place a slip under an idempotency key.
 *
 * The key is what makes a double click, or a retry after a dropped
 * connection, return the slip that was already placed rather than a second
 * one. The caller keeps the same key until the slip is placed or changed.
 */
export const placeSlip = (body: SlipBody, idempotencyKey: string) =>
  post<Slip>("/api/predictions", body, { "Idempotency-Key": idempotencyKey });

// ----- messages -------------------------------------------------------------

export const sendMessage = (body: string) => post<PlayerMessage>("/api/messages", { body });

export const getMyMessages = () => request<{ messages: PlayerMessage[] }>("/api/messages");

// ----- operator -------------------------------------------------------------

export const getOverview = (days: number) =>
  request<Overview>(`/api/admin/overview?days=${days}`);

export function getPlayers(search: string, limit = 50) {
  const query = new URLSearchParams({ limit: String(limit) });
  if (search.trim()) query.set("search", search.trim());
  return request<PlayerList>(`/api/admin/players?${query}`);
}

export const adjustPlayer = (input: {
  player_code: string;
  amount_minor: number;
  reason: string;
  reference: string;
}) => post<{ player_code: string; balance: Money }>("/api/admin/players/adjust", input);

export const setPlayerStatus = (player_code: string, status: PlayerRow["status"]) =>
  post<{ player_code: string; status: string }>("/api/admin/players/status", {
    player_code,
    status,
  });

export const getInbox = (status?: string) =>
  request<Inbox>(`/api/admin/messages${status ? `?status=${status}` : ""}`);

export const resolveMessage = (id: string, status: string, note?: string) =>
  post<PlayerMessage>(`/api/admin/messages/${id}`, { status, note: note || null });

export const replyToMessage = (id: string, body: string) =>
  post<{ id: string; status: string; reply_body: string; replied_at: string }>(
    `/api/admin/messages/${id}/reply`,
    { body },
  );

export const getDiagnostics = () => request<Diagnostics>("/api/admin/diagnostics");
