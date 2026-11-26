"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";

import { fa, translateError } from "@/lib/i18n";
import type { UserProfile } from "@/lib/types";

type AuthState =
  | { status: "loading" }
  | { status: "ready"; user: UserProfile; isNewUser: boolean }
  | { status: "error"; code: string; detail: string };

const ProfileContext = createContext<{
  user: UserProfile;
  refresh: () => Promise<void>;
} | null>(null);

export function useProfile() {
  const value = useContext(ProfileContext);
  if (!value) {
    throw new Error("useProfile must be used inside <TelegramGate>.");
  }
  return value;
}

async function loadProfile(): Promise<UserProfile | null> {
  const response = await fetch("/api/me", { cache: "no-store" });
  evidence.meStatus = response.status;
  return response.ok ? ((await response.json()) as UserProfile) : null;
}

type AuthFailure = { code: string; detail: string };

const INIT_DATA_KEY = "app:init-data";

const evidence: Record<string, unknown> = {};

function report(code: string, extra: Record<string, unknown> = {}): void {
  try {
    void fetch("/api/diag", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, ...evidence, ...extra }),
      keepalive: true,
    });
  } catch {
  }
}

function stashed(): string {
  try {
    return sessionStorage.getItem(INIT_DATA_KEY) ?? "";
  } catch {
    return "";
  }
}

function remember(value: string): void {
  try {
    sessionStorage.setItem(INIT_DATA_KEY, value);
  } catch {
  }
}

const initDataReady: Promise<string> =
  typeof window === "undefined"
    ? Promise.resolve("")
    : (async () => {
        const captured = stashed();
        evidence.stashedLen = captured.length;
        evidence.hashLen = location.hash.length;
        evidence.hashHasData = location.hash.includes("tgWebAppData");
        evidence.searchHasData = location.search.includes("tgWebAppData");

        try {
          const { default: WebApp } = await import("@twa-dev/sdk");
          WebApp.ready();
          WebApp.expand();
          const live = WebApp.initData ?? "";
          evidence.sdkLen = live.length;
          evidence.platform = WebApp.platform ?? null;
          evidence.version = WebApp.version ?? null;
          if (live) {
            remember(live);
            return live;
          }
        } catch (exc) {
          evidence.sdkError = exc instanceof Error ? exc.message.slice(0, 120) : "unknown";
        }

        return captured;
      })();

type AuthOutcome =
  | { ok: true; user: UserProfile; isNewUser: boolean }
  | { ok: false; error: AuthFailure };

let pending: Promise<AuthOutcome> | null = null;

function authenticate(): Promise<AuthOutcome> {
  pending ??= runAuthentication().finally(() => {
    pending = null;
  });
  return pending;
}

async function runAuthentication(): Promise<AuthOutcome> {
  const existing = await loadProfile();
  if (existing) return { ok: true, user: existing, isNewUser: false };

  const initData = await initDataReady;
  if (!initData) {
    report("not_in_telegram");
    return { ok: false, error: { code: "not_in_telegram", detail: fa.errorNotInTelegram } };
  }

  const response = await fetch("/api/session", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ initData }),
  });

  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as
      | { code?: string; detail?: string }
      | null;
    const code = body?.code ?? "session_failed";
    report(code, { exchangeStatus: response.status, initDataLen: initData.length });
    return {
      ok: false,
      error: { code, detail: translateError(code, body?.detail ?? fa.errorSessionTitle) },
    };
  }

  const { user, isNewUser } = (await response.json()) as {
    user: UserProfile;
    isNewUser: boolean;
  };
  return { ok: true, user, isNewUser };
}

export function TelegramGate({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const inFlight = useRef(false);

  const refresh = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      const user = await loadProfile();
      if (user) {
        setState((current) =>
          current.status === "ready"
            ? { ...current, user }
            : { status: "ready", user, isNewUser: false },
        );
        return;
      }

      const result = await authenticate();
      setState(
        result.ok
          ? { status: "ready", user: result.user, isNewUser: result.isNewUser }
          : { status: "error", code: result.error.code, detail: result.error.detail },
      );
    } catch (exc) {
      report("bootstrap_failed", {
        thrown: exc instanceof Error ? exc.message.slice(0, 160) : "unknown",
      });
      setState({ status: "error", code: "bootstrap_failed", detail: fa.errorBootstrap });
    } finally {
      inFlight.current = false;
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    authenticate()
      .then((result) => {
        if (cancelled) return;
        setState(
          result.ok
            ? { status: "ready", user: result.user, isNewUser: result.isNewUser }
            : { status: "error", code: result.error.code, detail: result.error.detail },
        );
      })
      .catch((exc) => {
        report("bootstrap_failed", {
          thrown: exc instanceof Error ? exc.message.slice(0, 160) : "unknown",
        });
        if (!cancelled) {
          setState({ status: "error", code: "bootstrap_failed", detail: fa.errorBootstrap });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [attempt]);

  if (state.status === "loading") {
    return (
      <div className="flex min-h-dvh items-center justify-center">
        <div
          className="size-8 animate-spin rounded-full border-2 border-tg-hint border-t-tg-button"
          role="status"
          aria-label={fa.loading}
        />
      </div>
    );
  }

  if (state.status === "error") {
    const expired = state.code === "init_data_expired";

    return (
      <div className="flex min-h-dvh flex-col items-center justify-center gap-3 px-8 text-center">
        <p className="text-lg font-semibold">{fa.errorSessionTitle}</p>
        <p className="text-sm text-tg-hint">{expired ? fa.errorSessionExpired : state.detail}</p>
        <button
          onClick={() => {
            setState({ status: "loading" });
            setAttempt((value) => value + 1);
          }}
          className="mt-2 rounded-xl bg-tg-button px-5 py-2.5 text-sm font-bold
                     text-tg-button-text transition duration-150 active:scale-95"
        >
          {fa.retry}
        </button>
        <p className="font-mono text-xs text-tg-hint/60">{state.code}</p>
      </div>
    );
  }

  return (
    <ProfileContext.Provider value={{ user: state.user, refresh }}>
      {children}
    </ProfileContext.Provider>
  );
}
