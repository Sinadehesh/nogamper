import "@/components/game/game.css";

import type { Metadata } from "next";

import { Dashboard } from "@/components/Dashboard";
import { previewQuestion } from "@/components/game/Preview";
import { GameBar } from "@/components/game/views";
import { Welcome } from "@/components/game/Welcome";
import { NotOpenYet } from "@/components/NotOpenYet";
import { PlayerProvider } from "@/components/PlayerProvider";
import { SiteFooter, SiteHeader } from "@/components/SiteChrome";
import { t } from "@/lib/copy";
import { allQuestions, getMoves } from "@/lib/server/questions";
import { getRules } from "@/lib/server/rules";
import { getViewer } from "@/lib/server/viewer";
import { GAME_OPEN } from "@/lib/site";
import { isTab } from "@/lib/tabs";

export const metadata: Metadata = { title: t.navPlay, robots: { index: false, follow: false } };

/**
 * Each open question's public page, by its wording. The game's feed knows a
 * question by an id the public pages do not use, so a card finds its chart
 * through this. Read from the same cached list as /questions; when it cannot
 * be had, the cards simply carry no link.
 */
async function questionLinks(): Promise<Record<string, string>> {
  const all = await allQuestions();
  const links: Record<string, string> = {};
  for (const question of all ?? []) {
    if (question.state === "open") links[question.question] = question.slug;
  }
  return links;
}

export default async function PlayPage({
  searchParams,
}: {
  searchParams: Promise<{ tab?: string; purchase?: string }>;
}) {
  // Asked of the API on the server, so the page arrives already knowing who
  // it is for: no spinner, and nobody who is signed out ever sees the game
  // flash up before being told how to start.
  const viewer = await getViewer();

  if (!viewer) {
    // No game behind the site: the same not-open page every door shows.
    if (!GAME_OPEN) {
      return (
        <>
          <SiteHeader />
          <main id="main" className="gm flex-1">
            <div className="wrap">
              <NotOpenYet page />
            </div>
          </main>
          <SiteFooter />
        </>
      );
    }
    // Where the site's "Start playing free" lands: one click from here to a
    // game, with signing in and creating an account beside it.
    const [rules, moves] = await Promise.all([getRules(), getMoves()]);
    const move = previewQuestion(moves);
    return (
      <>
        <GameBar />
        <Welcome rules={rules} preview={move && moves ? { move, asOf: moves.as_of } : null} />
        <SiteFooter />
      </>
    );
  }

  const [{ tab: requested, purchase }, links] = await Promise.all([searchParams, questionLinks()]);
  const initialTab = isTab(requested) ? requested : "markets";
  const returned = purchase === "done" || purchase === "cancelled" ? purchase : null;

  // The game keeps its own bar; the site's footer, with the help line and
  // the lines every page carries, closes it like every other page.
  return (
    <>
      <PlayerProvider initial={viewer}>
        <Dashboard initialTab={initialTab} purchase={returned} links={links} />
      </PlayerProvider>
      <SiteFooter />
    </>
  );
}
