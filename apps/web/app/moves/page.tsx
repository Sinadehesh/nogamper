import Link from "next/link";

import { AsOf } from "@/components/AsOf";
import { JsonLd } from "@/components/JsonLd";
import { LinkPending } from "@/components/LinkPending";
import { SiteFooter, SiteHeader } from "@/components/SiteChrome";
import { FETCHING, FETCHING_SLOWLY, PRICE_SOURCE, changeInWords, movesPage } from "@/lib/content";
import { t } from "@/lib/copy";
import { dateUtc, movement, percent } from "@/lib/format";
import { breadcrumbLd, listLd, pageMetadata } from "@/lib/seo";
import { keepEarlierCopy } from "@/lib/server/public";
import { getMoves } from "@/lib/server/questions";
import type { Move } from "@/lib/types";

// Kept for five minutes, then built again behind the next visitor.
export const revalidate = 300;

export const metadata = pageMetadata({
  title: movesPage.metaTitle,
  description: movesPage.metaDescription,
  path: "/moves",
  absoluteTitle: true,
});

/**
 * The questions whose chances changed most.
 *
 * It reports; it does not explain and it does not predict, and the page says
 * so in as many words. Nothing on it is coloured as a gain or a loss, counts
 * down, or asks to be acted on — a list of prices that just moved is the one
 * thing on this site that could be mistaken for a tip sheet, so it is built
 * not to read like one.
 */
const sameText = (one: string, other: string) =>
  one.trim().toLowerCase() === other.trim().toLowerCase();

function MoveCard({ move }: { move: Move }) {
  const shown = movement(move.was, move.now);
  return (
    <li>
      {/* Not fetched ahead of a click: a question's page is built when it is
          first asked for, and a list of them on screen would otherwise have
          every one of them built for a visitor who reads none. */}
      <Link
        href={`/questions/${move.slug}`}
        prefetch={false}
        className="card block h-full p-5 hover:border-muted"
      >
        <p className="text-xs text-muted">
          {sameText(move.event_title, move.question)
            ? move.category
            : `${move.category} · ${move.event_title}`}
        </p>
        <h3 className="mt-1 text-lg font-bold leading-snug">{move.question}</h3>
        <p className="mt-3 text-2xl font-black tabular-nums" aria-hidden>
          {shown.was} <span className="text-muted">{"→"}</span> {shown.now}
        </p>
        <p className="sr-only">{movesPage.fromTo(shown.was, shown.now)}</p>
        <p className="mt-1 text-sm text-muted">
          {changeInWords(shown.points, shown.direction)} · {t.closesOn(dateUtc(move.closes_at))}
        </p>
        <LinkPending label={FETCHING} slowLabel={FETCHING_SLOWLY} ownLine />
      </Link>
    </li>
  );
}

function MoveList({ id, title, moves, empty }: { id: string; title: string; moves: Move[]; empty: string }) {
  return (
    <section className="mt-12" aria-labelledby={id}>
      <h2 id={id} className="text-2xl font-bold tracking-tight">
        {title}
      </h2>
      {moves.length === 0 ? (
        <p className="mt-4 text-muted">{empty}</p>
      ) : (
        <ul className="mt-5 grid gap-3 md:grid-cols-2">
          {moves.map((move) => (
            <MoveCard key={move.slug} move={move} />
          ))}
        </ul>
      )}
    </section>
  );
}

const asPoints = (probability: string) => percent(probability).replace("%", "");

export default async function MovesPage() {
  const moves = await getMoves();
  // Could not be read, or the figures are out of date (a server just woken
  // has yesterday's until it has read the market again, and says so rather
  // than send them). On the running site either leaves the page as it was
  // last built.
  if (moves === null) keepEarlierCopy("The list of moves");
  const listed = moves ? [...moves.day, ...moves.week] : [];

  return (
    <>
      <JsonLd
        data={breadcrumbLd([
          { name: t.appName, path: "/" },
          { name: t.navMoves, path: "/moves" },
        ])}
      />
      {listed.length > 0 ? (
        <JsonLd
          data={listLd(
            movesPage.title,
            [...new Set(listed.map((move) => `/questions/${move.slug}`))],
          )}
        />
      ) : null}
      <SiteHeader />

      <main id="main" className="container-page flex-1 py-10 sm:py-14">
        <div className="max-w-3xl">
          <h1 className="text-4xl font-black tracking-tight sm:text-5xl">{movesPage.title}</h1>
          <p className="mt-4 text-lg text-muted">{movesPage.lede}</p>
          {moves ? (
            <div className="mt-3">
              <AsOf at={moves.as_of} changing />
            </div>
          ) : null}
        </div>

        {moves === null ? (
          <p className="notice mt-8 max-w-2xl">{movesPage.unavailable}</p>
        ) : (
          <>
            <MoveList
              id="day"
              title={movesPage.dayTitle}
              moves={moves.day}
              empty={movesPage.emptyDay(asPoints(moves.day_threshold))}
            />
            <MoveList
              id="week"
              title={movesPage.weekTitle}
              moves={moves.week}
              empty={movesPage.emptyWeek(asPoints(moves.week_threshold))}
            />
          </>
        )}

        <section className="mt-14 max-w-2xl" aria-labelledby="not-a-tip">
          <h2 id="not-a-tip" className="text-2xl font-bold tracking-tight">
            {movesPage.notATipTitle}
          </h2>
          {movesPage.notATip.map((paragraph) => (
            <p key={paragraph.slice(0, 24)} className="mt-3 text-muted">
              {paragraph}
            </p>
          ))}
        </section>

        {moves ? (
          <section className="mt-12 max-w-2xl" aria-labelledby="rules">
            <h2 id="rules" className="text-xl font-bold tracking-tight">
              {movesPage.rulesTitle}
            </h2>
            <ul className="mt-3 list-disc space-y-2 pl-5 text-muted">
              {movesPage
                .rules(
                  asPoints(moves.day_threshold),
                  asPoints(moves.week_threshold),
                  moves.min_hours_to_close,
                  asPoints(moves.decided_margin),
                )
                .map((rule) => (
                  <li key={rule.slice(0, 24)}>{rule}</li>
                ))}
            </ul>
          </section>
        ) : null}

        <p className="mt-10 max-w-2xl text-sm text-muted">{PRICE_SOURCE}</p>
        <p className="mt-4">
          <Link href="/questions" className="btn btn-secondary btn-sm">
            {movesPage.allLink}
          </Link>
        </p>
      </main>

      <SiteFooter />
    </>
  );
}
