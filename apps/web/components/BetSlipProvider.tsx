"use client";


import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import type { MarketSummary, Side, SlipSelection } from "@/lib/types";

export const MAX_LEGS = 5;

type SlipState = {
  legs: SlipSelection[];
  isOpen: boolean;
  add: (
    market: MarketSummary,
    side: Side,
  ) => { ok: true } | { ok: false; reason: string };
  fill: (candidates: { market: MarketSummary; side: Side }[]) => number;
  remove: (marketId: string) => void;
  clear: () => void;
  open: () => void;
  close: () => void;
  has: (marketId: string, side: Side) => boolean;
  blockedBecause: (market: MarketSummary) => string | null;
};

const BetSlipContext = createContext<SlipState | null>(null);

export function useBetSlip(): SlipState {
  const value = useContext(BetSlipContext);
  if (!value)
    throw new Error("useBetSlip must be used inside <BetSlipProvider>.");
  return value;
}

export function BetSlipProvider({ children }: { children: ReactNode }) {
  const [legs, setLegs] = useState<SlipSelection[]>([]);
  const [isOpen, setIsOpen] = useState(false);

  const blockedBecause = useCallback(
    (market: MarketSummary): string | null => {
      if (legs.some((leg) => leg.marketId === market.id)) return null;
      if (legs.some((leg) => leg.eventId === market.event.id)) {
        return "Another outcome from this event is already on your slip.";
      }
      if (legs.length >= MAX_LEGS)
        return `A slip holds at most ${MAX_LEGS} legs.`;
      if (market.probability.stale)
        return "This price is updating. Try again in a moment.";
      return null;
    },
    [legs],
  );

  const add = useCallback(
    (market: MarketSummary, side: Side) => {
      const blocked = blockedBecause(market);
      if (blocked) return { ok: false as const, reason: blocked };

      setLegs((current) => {
        const without = current.filter((leg) => leg.marketId !== market.id);
        const existing = current.find((leg) => leg.marketId === market.id);
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
      return { ok: true as const };
    },
    [blockedBecause],
  );

  const fill = useCallback(
    (candidates: { market: MarketSummary; side: Side }[]) => {
      const chosen: SlipSelection[] = [];
      const events = new Set<string>();

      for (const { market, side } of candidates) {
        if (chosen.length >= MAX_LEGS) break;
        if (market.probability.stale) continue;
        if (events.has(market.event.id)) continue;

        events.add(market.event.id);
        chosen.push({
          marketId: market.id,
          side,
          question: market.question,
          category: market.category,
          eventId: market.event.id,
          lockAt: market.lock_at,
        });
      }

      setLegs(chosen);
      return chosen.length;
    },
    [],
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
      fill,
      isOpen: isOpen && legs.length > 0,
      add,
      remove,
      clear,
      open: () => setIsOpen(true),
      close: () => setIsOpen(false),
      has,
      blockedBecause,
    }),
    [legs, isOpen, add, fill, remove, clear, has, blockedBecause],
  );

  return (
    <BetSlipContext.Provider value={value}>{children}</BetSlipContext.Provider>
  );
}
