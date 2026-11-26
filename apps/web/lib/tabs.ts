/**
 * The tabs of the play screen.
 *
 * In a module of their own rather than beside the component that renders
 * them: the page that picks the opening tab is a server component, and a
 * value imported into one from a "use client" file arrives as a reference to
 * the client bundle, not as the array.
 */
export const TABS = ["markets", "history", "leaderboard", "safer", "account"] as const;

export type Tab = (typeof TABS)[number];

export function isTab(value: unknown): value is Tab {
  return typeof value === "string" && (TABS as readonly string[]).includes(value);
}
