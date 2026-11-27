import "./questions.css";

import Link from "next/link";

import { LinkPending } from "@/components/LinkPending";
import { MoveScale, MoveTrack } from "@/components/viz";
import { Figure } from "@/components/viz/Figure";
import { FETCHING, FETCHING_SLOWLY, movesPage } from "@/lib/content";
import { categoryLabel } from "@/lib/copy";
import type { Move, Moves } from "@/lib/types";
import { closesOn, fromToArrow, groupByEvent, shortDateTimeUtc } from "@/lib/viz";

const sameText = (one: string, other: string) =>
  one.trim().toLowerCase() === other.trim().toLowerCase();

// A move whose own figure was read this much earlier or later than the list's
// says so: "a day ago" then counts back from another moment.
const READ_APART_MS = 30 * 60_000;

/** A threshold in percentage points, as the rules print it: "0.0500" is "5". */
export function asPercentagePoints(probability: string): string {
  const value = Number(probability) * 100;
  return Number.isFinite(value) ? String(Math.round(value * 10) / 10) : probability;
}

/**
 * How to read a row, and what counts as a move, before the rows themselves:
 * a reader judges a list by its rules, so the rules come first. The drawing
 * is the row's own mark at a larger size, without figures, so nothing in the
 * key could be mistaken for a reading.
 */
export function MovesKey({ moves }: { moves: Moves }) {
  return (
    <aside className="mv-key dp-panel" aria-labelledby="how-to-read">
      <div>
        <h2 id="how-to-read">{movesPage.keyTitle}</h2>
        <svg className="mv-key__drawing" viewBox="0 0 220 44" aria-hidden="true" focusable="false">
          <line className="mv-kd-rail" x1="4" x2="216" y1="14" y2="14" />
          <line className="mv-kd-seg" x1="40" x2="162" y1="14" y2="14" />
          <path className="mv-kd-head" d="M161 9 L170 14 L161 19 Z" />
          <circle className="mv-kd-was" cx="34" cy="14" r="5" />
          <circle className="mv-kd-now" cx="178" cy="14" r="6" />
          <text className="mv-kd-word" x="34" y="40" textAnchor="middle">
            {movesPage.keyThen}
          </text>
          <text className="mv-kd-word" x="178" y="40" textAnchor="middle">
            {movesPage.keyNow}
          </text>
        </svg>
        <ul>
          {movesPage.key.map((line) => (
            <li key={line.slice(0, 24)}>{line}</li>
          ))}
        </ul>
      </div>
      <div>
        <h2 id="rules">{movesPage.rulesTitle}</h2>
        <ul>
          {movesPage
            .rules(
              asPercentagePoints(moves.day_threshold),
              asPercentagePoints(moves.week_threshold),
              moves.min_hours_to_close,
              asPercentagePoints(moves.decided_margin),
            )
            .map((rule) => (
              <li key={rule.slice(0, 24)}>{rule}</li>
            ))}
        </ul>
      </div>
    </aside>
  );
}

function MoveRow({
  move,
  window,
  reference,
  measuredAt,
}: {
  move: Move;
  window: "day" | "week";
  reference: string;
  measuredAt: string | null;
}) {
  const own = Date.parse(move.measured_at);
  const list = measuredAt ? Date.parse(measuredAt) : Number.NaN;
  const apart = Number.isFinite(own) && Number.isFinite(list) && Math.abs(own - list) > READ_APART_MS;

  return (
    <li className="mv-row">
      <div>
        {/* Not fetched ahead of a click: a question's page is built when it is
            first asked for, and a list of them on screen would otherwise have
            every one of them built for a visitor who reads none. */}
        <Link href={`/questions/${move.slug}`} prefetch={false} className="mv-row__link dp-link">
          {move.question}
          <LinkPending label={FETCHING} slowLabel={FETCHING_SLOWLY} ownLine />
        </Link>
        <p className="mv-row__meta">
          {closesOn(move.closes_at, reference)}
          {apart ? ` · ${movesPage.readAt(shortDateTimeUtc(move.measured_at))}` : null}
        </p>
      </div>
      <MoveTrack was={move.was} now={move.now} />
      <p className="mv-row__fig">
        {/* The track says the same to a screen reader, in words. */}
        <span aria-hidden="true">
          <Figure text={fromToArrow(move.was, move.now)} />
        </span>
        <span className="mv-row__when">{movesPage.windowWords[window]}</span>
      </p>
    </li>
  );
}

/**
 * One window's moves, the buckets of one event together under its title:
 * five ranges of one tweet count read as one story, not five. Groups keep
 * the order of their largest move, and moves within a group theirs, which is
 * the API's: largest first. Every track is the same 0-to-100 scale at the
 * same width, so moves compare by length down the page.
 */
export function MovesSection({
  id,
  title,
  window,
  moves,
  empty,
  reference,
  measuredAt,
}: {
  id: string;
  title: string;
  window: "day" | "week";
  moves: Move[];
  empty: string;
  reference: string;
  measuredAt: string | null;
}) {
  const groups = groupByEvent(moves);
  return (
    <section className="mv-section" aria-labelledby={id}>
      <div className="mv-section__head">
        <h2 id={id} className="dp-h2">
          {title}
        </h2>
        {moves.length > 0 ? <p>{movesPage.count(moves.length)}</p> : null}
      </div>
      {moves.length === 0 ? (
        <p className="dp-empty">{empty}</p>
      ) : (
        <>
          <div className="mv-scale" aria-hidden="true">
            <span />
            <MoveScale />
            <span />
          </div>
          <ol className="mv-events">
            {groups.map((group) => {
              const only = group.items.length === 1 ? group.items[0] : undefined;
              const titled = !(only && sameText(group.title, only.question));
              return (
                <li key={group.title} className="mv-event dp-panel">
                  <div className="mv-event__head">
                    <span className="dp-tag">{categoryLabel(group.category)}</span>
                    {titled ? <h3 className="mv-event__title">{group.title}</h3> : null}
                  </div>
                  <ol>
                    {group.items.map((move) => (
                      <MoveRow
                        key={move.slug}
                        move={move}
                        window={window}
                        reference={reference}
                        measuredAt={measuredAt}
                      />
                    ))}
                  </ol>
                </li>
              );
            })}
          </ol>
        </>
      )}
    </section>
  );
}
