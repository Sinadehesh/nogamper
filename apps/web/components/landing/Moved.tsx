import Link from "next/link";

import { AsOf } from "@/components/AsOf";
import { LinkPending } from "@/components/LinkPending";
import { MoveScale, MoveTrack } from "@/components/viz";
import { FETCHING, FETCHING_SLOWLY, landing } from "@/lib/content";
import { categoryLabel } from "@/lib/copy";
import type { Move } from "@/lib/types";
import { closesOn, fromToArrow, GAME_BAND, groupByEvent, type PriceBand } from "@/lib/viz";

const same = (one: string, other: string) => one.trim().toLowerCase() === other.trim().toLowerCase();

/**
 * What moved: the largest changes the market reported, each a row with its
 * move drawn on the fixed 0-to-100 track and a link to its question's page.
 * It reports and does not advise: one colour whichever way a move went, no
 * ranking words, nothing to act on but reading more (map 5.3).
 */
export function Moved({
  moved,
  asOf,
  band = GAME_BAND,
}: {
  moved: { window: "day" | "week"; items: Move[] } | null;
  asOf: string | null;
  /** The game's band: a move's "now" is the game's price, held on it. */
  band?: PriceBand;
}) {
  const window = moved?.window ?? "day";
  const groups = moved ? groupByEvent(moved.items) : [];
  // Each row knows its place in the whole list, not only in its event.
  let place = 0;
  const numbered = groups.map((group) => ({
    ...group,
    rows: group.items.map((move) => ({ move, place: place++ })),
  }));

  return (
    <section className="section lp-moved" id="moved" aria-labelledby="moved-h">
      <div className="wrap grid grid--top">
        <div className="span-5 lp-moved__head">
          <h2 id="moved-h">{landing.movedTitle(window)}</h2>
          <p className="t-lead">{moved ? landing.movedIntro(window) : landing.movedNone}</p>
          <a className="link" href="/moves">
            {landing.movedAll}
          </a>
          {/* The one time on the page its figures are from: the hero's
              question and these moves were read together. */}
          {asOf ? <AsOf at={asOf} changing /> : null}
        </div>
        {/* The list as the game shows it, on the page's lit ground: real
            rows, each a link to its question's page. */}
        <div className="span-6 start-7 panel lp-moved__panel">
          <div className="lp-movelist">
            <p className="lp-movelist__head">
              <span>{landing.movedListHead(window)}</span>
            </p>
            <ul className="lp-moves">
              {numbered.map((group) => (
                // Each row carries its place in the whole list, and each event
                // its first row's, so a short screen lists the first few
                // (landing.css, what moved).
                <li key={group.title} className="lp-moves__group" data-place={group.rows[0]?.place ?? 0}>
                  <p className="lp-moves__event">
                    {group.items.length > 1 || !same(group.title, group.items[0]?.question ?? "")
                      ? landing.movedMeta(categoryLabel(group.category), group.title)
                      : categoryLabel(group.category)}
                  </p>
                  <ul>
                    {group.rows.map(({ move, place: at }) => (
                      <li key={move.slug} className="lp-move" data-place={at}>
                        <Link className="lp-move__q" href={`/questions/${move.slug}`} prefetch={false}>
                          {move.question}
                          <LinkPending label={FETCHING} slowLabel={FETCHING_SLOWLY} ownLine />
                        </Link>
                        <MoveTrack was={move.was} now={move.now} held={band} />
                        <p className="lp-move__meta">
                          {fromToArrow(move.was, move.now, band)} · {closesOn(move.closes_at, asOf ?? undefined)}
                        </p>
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
            </ul>
            {groups.length ? (
              <div className="lp-movelist__scale" aria-hidden="true">
                <MoveScale />
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </section>
  );
}
