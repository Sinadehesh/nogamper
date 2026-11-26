import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { Dashboard } from "@/components/Dashboard";
import { PlayerProvider } from "@/components/PlayerProvider";
import { t } from "@/lib/copy";
import { getViewer } from "@/lib/server/viewer";
import { isTab } from "@/lib/tabs";

export const metadata: Metadata = { title: t.navPlay, robots: { index: false, follow: false } };

export default async function PlayPage({
  searchParams,
}: {
  searchParams: Promise<{ tab?: string }>;
}) {
  // Asked of the API on the server, so the page arrives already knowing who
  // it is for: no spinner, and nobody who is signed out ever sees the game
  // flash up before being sent away.
  const viewer = await getViewer();
  if (!viewer) redirect("/login");

  const requested = (await searchParams).tab;
  const initialTab = isTab(requested) ? requested : "markets";

  return (
    <PlayerProvider initial={viewer}>
      <Dashboard initialTab={initialTab} />
    </PlayerProvider>
  );
}
