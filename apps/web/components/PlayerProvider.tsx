"use client";

import Link from "next/link";
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

import { getProfile } from "@/lib/api";
import { t } from "@/lib/copy";
import type { Limits, UserProfile } from "@/lib/types";

/**
 * The signed-in player, shared with everything on the play screen.
 *
 * The profile arrives from the server with the page, so there is no spinner
 * before the first paint. After that it is refreshed whenever something that
 * changes it happens — a forecast, a top-up, a limit — and any refresh that
 * comes back "not signed in" swaps the whole screen for a way to sign in
 * again, rather than leaving a page full of buttons that all fail.
 */

type PlayerState = {
  player: UserProfile;
  refresh: () => Promise<void>;
  /** Apply limits a route just returned, without a second round trip. */
  applyLimits: (limits: Limits) => void;
  onBreak: boolean;
  /** Today's self-set limit is used up; nothing more can be staked today. */
  limitReached: boolean;
};

const PlayerContext = createContext<PlayerState | null>(null);

export function usePlayer(): PlayerState {
  const value = useContext(PlayerContext);
  if (!value) throw new Error("usePlayer must be used inside <PlayerProvider>.");
  return value;
}

export function PlayerProvider({
  initial,
  children,
}: {
  initial: UserProfile;
  children: ReactNode;
}) {
  const [player, setPlayer] = useState(initial);
  const [signedOut, setSignedOut] = useState(false);

  const refresh = useCallback(async () => {
    const result = await getProfile();
    if (result.ok) setPlayer(result.data);
    else if (result.status === 401) setSignedOut(true);
    // Anything else — the network, a bad minute on the server — keeps the
    // profile already on screen. Stale is better than blank.
  }, []);

  const applyLimits = useCallback((limits: Limits) => {
    setPlayer((current) => ({ ...current, limits }));
  }, []);

  const value = useMemo(() => {
    const { break_until: until, daily_limit: limit, daily_spent: spent } = player.limits;
    return {
      player,
      refresh,
      applyLimits,
      onBreak: until !== null && new Date(until).getTime() > Date.now(),
      limitReached: limit !== null && spent.minor >= limit.minor,
    };
  }, [player, refresh, applyLimits]);

  if (signedOut) {
    return (
      <main id="main" className="container-page flex flex-1 flex-col items-center justify-center py-20 text-center">
        <h1 className="text-2xl font-bold">{t.errorSessionTitle}</h1>
        <p className="mt-2 text-muted">{t.errorSessionBody}</p>
        <Link href="/login" className="btn btn-primary mt-6">
          {t.navSignIn}
        </Link>
      </main>
    );
  }

  return <PlayerContext.Provider value={value}>{children}</PlayerContext.Provider>;
}
