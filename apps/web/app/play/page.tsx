import "@/components/game/game.css";

import type { Metadata } from "next";

import { Dashboard, type AskedQuestion } from "@/components/Dashboard";
import { previewQuestion } from "@/components/game/Preview";
import { GameBar } from "@/components/game/views";
import { Welcome } from "@/components/game/Welcome";
import { NotOpenYet } from "@/components/NotOpenYet";
import { PlayerProvider } from "@/components/PlayerProvider";
import { SiteFooter, SiteHeader } from "@/components/SiteChrome";
import { allQuestions, getMoves } from "@/lib/server/questions";
import { getRules } from "@/lib/server/rules";
import { getViewer } from "@/lib/server/viewer";
import { GAME_OPEN } from "@/lib/site";
import { isTab, VIEW_TITLE } from "@/lib/tabs";

type Params = { tab?: string; purchase?: string; question?: string };

/** Each view has its own title, so a tab, a history entry and a screen reader say which. */
export async function generateMetadata({
  searchParams,
}: {
  searchParams: Promise<Params>;
}): Promise<Metadata> {
  const { tab } = await searchParams;
  return { title: VIEW_TITLE[isTab(tab) ? tab : "markets"], robots: { index: false, follow: false } };
}

/** A question's address as the public pages write it, or null. */
function askedSlug(value: string | undefined): string | null {
  return value && value.length <= 200 && /^[a-z0-9]+(-[a-z0-9]+)*$/.test(value) ? value : null;
}

/**
 * Each open question's public page, by its wording. The game's feed knows a
 * question by an id the public pages do not use, so a card finds its chart
 * through this. Read from the same cached list as /questions; when it cannot
 * be had, the cards simply carry no link. And, the other way round, the
 * question a page's "Make a forecast" asked for (`?question=` its address),
 * by its wording and category, for the feed to open on.
 */
async function questionLinks(
  slug: string | null,
): Promise<{ links: Record<string, string>; asked: AskedQuestion | null }> {
  const all = await allQuestions();
  const links: Record<string, string> = {};
  let asked: AskedQuestion | null = null;
  for (const question of all ?? []) {
    if (question.state !== "open") continue;
    links[question.question] = question.slug;
    if (!asked && question.slug === slug) {
      asked = { slug, question: question.question, category: question.category };
    }
  }
  // Asked for but not open (or the list could not be read): the feed says
  // so and links back to the page it came from.
  if (slug && !asked) asked = { slug, question: "", category: "" };
  return { links, asked };
}

export default async function PlayPage({
  searchParams,
}: {
  searchParams: Promise<Params>;
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
    // game, with signing in and creating an account beside it. Sent from a
    // question's page, the game then opens on that question.
    const [rules, moves, { question }] = await Promise.all([getRules(), getMoves(), searchParams]);
    const move = previewQuestion(moves);
    const slug = askedSlug(question);
    return (
      <>
        <GameBar />
        <Welcome
          rules={rules}
          preview={move && moves ? { move, asOf: moves.as_of } : null}
          next={slug ? `/play?question=${slug}` : "/play"}
        />
        <SiteFooter />
      </>
    );
  }

  const { tab: requested, purchase, question } = await searchParams;
  const { links, asked } = await questionLinks(askedSlug(question));
  const initialTab = isTab(requested) ? requested : "markets";
  const returned = purchase === "done" || purchase === "cancelled" ? purchase : null;

  // The game keeps its own bar; the site's footer, with the help line and
  // the lines every page carries, closes it like every other page.
  return (
    <>
      <PlayerProvider initial={viewer}>
        <Dashboard
          initialTab={initialTab}
          purchase={returned}
          links={links}
          asked={initialTab === "markets" ? asked : null}
        />
      </PlayerProvider>
      <SiteFooter />
    </>
  );
}
