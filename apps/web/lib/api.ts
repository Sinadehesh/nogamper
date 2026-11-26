
import type {
  ActivityEntry,
  CoinPackage,
  Diagnostics,
  EconomyReport,
  Inbox,
  InvoiceIssued,
  MarketPage,
  Money,
  PlayerList,
  PlayerMessage,
  PlayerRow,
  RedeemResult,
  ReplyResult,
  RewardCatalogue,
  RewardClaim,
  Side,
  Slip,
  SlipPage,
  SlipQuote,
  UserProfile,
} from "@/lib/types";

export type ApiFailure = {
  ok: false;
  status: number;
  code: string;
  detail: string;
  marketId?: string;
  requiredLegs?: number;
};

export type ApiSuccess<T> = { ok: true; status: number; data: T };
export type ApiResult<T> = ApiSuccess<T> | ApiFailure;

async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<ApiResult<T>> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
      cache: "no-store",
    });
  } catch {
    return {
      ok: false,
      status: 0,
      code: "network_unavailable",
      detail: "Couldn't reach the server. Check your connection.",
    };
  }

  if (response.status === 204) {
    return { ok: true, status: 204, data: undefined as T };
  }

  const body = await response.json().catch(() => null);

  if (!response.ok) {
    const error = body as {
      code?: string;
      detail?: string;
      market_id?: string;
      required_legs?: number;
    } | null;
    return {
      ok: false,
      status: response.status,
      code: error?.code ?? "unexpected_error",
      detail: error?.detail ?? "Something went wrong.",
      marketId: error?.market_id,
      requiredLegs: error?.required_legs,
    };
  }

  return { ok: true, status: response.status, data: body as T };
}


export function getProfile() {
  return request<UserProfile>("/api/me");
}

export function getMarkets(
  params: { category?: string; limit?: number; cursor?: string } = {},
) {
  const query = new URLSearchParams();
  if (params.category) query.set("category", params.category);
  if (params.limit) query.set("limit", String(params.limit));
  if (params.cursor) query.set("cursor", params.cursor);
  const suffix = query.toString();
  return request<MarketPage>(`/api/markets${suffix ? `?${suffix}` : ""}`);
}

export function getActivity(limit = 15, includeLosses = false) {
  const query = new URLSearchParams({
    limit: String(limit),
    include_losses: String(includeLosses),
  });
  return request<{ entries: ActivityEntry[] }>(`/api/activity?${query}`);
}

export function getSlips(
  params: { status?: string; limit?: number; cursor?: string } = {},
) {
  const query = new URLSearchParams();
  if (params.status) query.set("status", params.status);
  if (params.limit) query.set("limit", String(params.limit));
  if (params.cursor) query.set("cursor", params.cursor);
  const suffix = query.toString();
  return request<SlipPage>(`/api/predictions${suffix ? `?${suffix}` : ""}`);
}

export function getPackages() {
  return request<{ packages: CoinPackage[] }>("/api/payments/packages");
}

export function getRewards() {
  return request<RewardCatalogue>("/api/rewards");
}

export function getRewardClaims() {
  return request<{ claims: RewardClaim[] }>("/api/rewards/claims");
}

export function redeemReward(code: string) {
  return request<RedeemResult>("/api/rewards/redeem", {
    method: "POST",
    body: JSON.stringify({ reward_code: code }),
  });
}


export type SlipBody = {
  legs: { market_id: string; side: Side }[];
  stake: number;
  insurance: boolean;
  accepted_odds?: string;
};

export function quoteSlip(body: SlipBody) {
  return request<SlipQuote>("/api/predictions/quote", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export type PlacementResult =
  | { kind: "placed"; slip: Slip; replayed: boolean }
  | {
      kind: "insufficient_funds";
      code: string;
      shortfallMinor: number;
      detail: string;
    }
  | { kind: "odds_moved"; code: string; detail: string }
  | { kind: "unavailable"; code: string; detail: string; marketId?: string };

export async function placeSlip(
  body: SlipBody,
  idempotencyKey: string,
  totalCostMinor: number,
  balanceMinor: number,
): Promise<PlacementResult> {
  const result = await request<Slip>("/api/predictions", {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "Idempotency-Key": idempotencyKey },
  });

  if (result.ok) {
    return {
      kind: "placed",
      slip: result.data,
      replayed: result.status === 200,
    };
  }

  if (result.status === 402 || result.code === "insufficient_funds") {
    return {
      kind: "insufficient_funds",
      code: "insufficient_funds",
      shortfallMinor: Math.max(0, totalCostMinor - balanceMinor),
      detail: result.detail,
    };
  }

  if (result.code === "odds_moved") {
    return { kind: "odds_moved", code: result.code, detail: result.detail };
  }

  return {
    kind: "unavailable",
    code: result.code,
    detail: result.detail,
    marketId: result.marketId,
  };
}


export function createInvoice(packageCode: string) {
  return request<InvoiceIssued>("/api/payments/invoices", {
    method: "POST",
    body: JSON.stringify({ package_code: packageCode }),
  });
}

export async function openInvoice(
  link: string,
): Promise<"paid" | "cancelled" | "failed" | "pending" | "unsupported"> {
  const { default: WebApp } = await import("@twa-dev/sdk");
  if (typeof WebApp.openInvoice !== "function") return "unsupported";

  return new Promise((resolve) => {
    WebApp.openInvoice(link, (status) => resolve(status));
  });
}


export function getEconomyReport(days: number) {
  return request<EconomyReport>(`/api/admin/economy?days=${days}`);
}


export function sendMessage(
  body: string,
  kind: "MESSAGE" | "PRIZE_CLAIM" = "MESSAGE",
) {
  return request<PlayerMessage>("/api/messages", {
    method: "POST",
    body: JSON.stringify({ body, kind }),
  });
}

export function getMyMessages() {
  return request<{ messages: PlayerMessage[] }>("/api/messages");
}


export function getPlayers(search: string, limit = 50) {
  const query = new URLSearchParams({ limit: String(limit) });
  if (search.trim()) query.set("search", search.trim());
  return request<PlayerList>(`/api/admin/players?${query}`);
}

export function adjustPlayer(input: {
  player_code?: string;
  telegram_id?: number;
  amount_minor: number;
  reason: string;
  reference: string;
}) {
  return request<{ player_code: string; balance: Money }>(
    "/api/admin/players/adjust",
    {
      method: "POST",
      body: JSON.stringify(input),
    },
  );
}

export function setPlayerStatus(
  player_code: string,
  status: PlayerRow["status"],
) {
  return request<{ player_code: string; status: string }>(
    "/api/admin/players/status",
    {
      method: "POST",
      body: JSON.stringify({ player_code, status }),
    },
  );
}

export function getInbox(status?: string) {
  const query = status ? `?status=${status}` : "";
  return request<Inbox>(`/api/admin/messages${query}`);
}

export function resolveMessage(id: string, status: string, note?: string) {
  return request<PlayerMessage>(`/api/admin/messages/${id}`, {
    method: "POST",
    body: JSON.stringify({ status, note: note || null }),
  });
}

export function replyToMessage(id: string, body: string) {
  return request<ReplyResult>(`/api/admin/messages/${id}/reply`, {
    method: "POST",
    body: JSON.stringify({ body }),
  });
}

export function getDiagnostics() {
  return request<Diagnostics>("/api/admin/diagnostics");
}
