"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { t } from "@/lib/copy";
import type { MarketSummary, Side, SlipSelection } from "@/lib/types";

/**
 * The picks a player has gathered but not yet placed. Lives only in the page:
 * nothing is sent anywhere until they open the slip and confirm.
 */

type SlipState = {
  legs: SlipSelection[];
  maxLegs: number;
  isOpen: boolean;
  toggle: (market: MarketSummary, side: Side) => void;
  remove: (marketId: string) => void;
  clear: () => void;
  open: () => void;
  close: () => void;
  has: (marketId: string, side: Side) => boolean;
  /** Why this market cannot be added right now, or null if it can. */
  blockedBecause: (market: MarketSummary) => string | null;
};

const SlipContext = createContext<SlipState | null>(null);

export function useSlip(): SlipState {
  const value = useContext(SlipContext);
  if (!value) throw new Error("useSlip must be used inside <SlipProvider>.");
  return value;
}

export function SlipProvider({ maxLegs, children }: { maxLegs: number; children: ReactNode }) {
  const [legs, setLegs] = useState<SlipSelection[]>([]);
  const [isOpen, setIsOpen] = useState(false);

  const blockedBecause = useCallback(
    (market: MarketSummary): string | null => {
      if (legs.some((leg) => leg.marketId === market.id)) return null;
      // Outcomes of one event are tied together — the server refuses the
      // pair, so the page says why before the round trip rather than after.
      if (legs.some((leg) => leg.eventId === market.event.id)) return t.blockedSameEvent;
      if (legs.length >= maxLegs) return t.blockedFull(maxLegs);
      if (market.probability.stale) return t.blockedStale;
      return null;
    },
    [legs, maxLegs],
  );

  const toggle = useCallback(
    (market: MarketSummary, side: Side) => {
      if (blockedBecause(market)) return;

      setLegs((current) => {
        const existing = current.find((leg) => leg.marketId === market.id);
        const without = current.filter((leg) => leg.marketId !== market.id);
        // Tapping the side already chosen takes it off; tapping the other
        // side swaps it. A question is never on a slip twice.
        if (existing?.side === side) return without;
        return [
          ...without,
          {
            marketId: market.id,
            side,
            question: market.question,
            category: market.category,
            eventId: market.event.id,
            lockAt: market.lock_at,
          },
        ];
      });
    },
    [blockedBecause],
  );

  const remove = useCallback((marketId: string) => {
    setLegs((current) => current.filter((leg) => leg.marketId !== marketId));
  }, []);

  const clear = useCallback(() => {
    setLegs([]);
    setIsOpen(false);
  }, []);

  const has = useCallback(
    (marketId: string, side: Side) =>
      legs.some((leg) => leg.marketId === marketId && leg.side === side),
    [legs],
  );

  const value = useMemo(
    () => ({
      legs,
      maxLegs,
      isOpen: isOpen && legs.length > 0,
      toggle,
      remove,
      clear,
      open: () => setIsOpen(true),
      close: () => setIsOpen(false),
      has,
      blockedBecause,
    }),
    [legs, maxLegs, isOpen, toggle, remove, clear, has, blockedBecause],
  );

  return <SlipContext.Provider value={value}>{children}</SlipContext.Provider>;
}
