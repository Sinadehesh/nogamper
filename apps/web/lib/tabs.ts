/**
 * The tabs of the play screen.
 *
 * In a module of their own rather than beside the component that renders
 * them: the page that picks the opening tab is a server component, and a
 * value imported into one from a "use client" file arrives as a reference to
 * the client bundle, not as the array.
 */
import { t } from "@/lib/copy";

export const TABS = ["markets", "history", "leaderboard", "safer", "account"] as const;

export type Tab = (typeof TABS)[number];

export function isTab(value: unknown): value is Tab {
  return typeof value === "string" && (TABS as readonly string[]).includes(value);
}

/**
 * Each view's page title (the layout adds " · Middlemost"), so a tab, a
 * history entry and a screen reader's page announcement say which view it
 * is. The questions view is the game's own page, "Play".
 */
export const VIEW_TITLE: Record<Tab, string> = {
  markets: t.navPlay,
  history: t.tabHistory,
  leaderboard: t.tabLeaderboard,
  safer: t.tabSafer,
  account: t.tabAccount,
};
