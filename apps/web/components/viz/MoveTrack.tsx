import "./viz.css";

import { viz } from "@/lib/copy";
import { changeSentence, figureWidth, layoutTrackLabels, monoWidth, printedChange } from "@/lib/viz";

import { Figure } from "./Figure";
import { at, cx, vars } from "./style";

type MoveTrackProps = {
  /** Where the chance was, 0 to 1. */
  was: number | string;
  /** Where it is now, 0 to 1. */
  now: number | string;
  /** "row" for a list (20px tall, rails line up row to row); "large" for a page. */
  size?: "row" | "large";
  /** On "large", the words over each figure: `viz.dayAgo`, `viz.now`. */
  wasWord?: string;
  nowWord?: string;
  className?: string;
};

const TICKS = [0, 25, 50, 75, 100];
/** Large labels: the word in 11px mono over the figure in 20px. */
const WORD_PX = 11;
const FIGURE_PX = 20;
const ROW_PX = 42;

/**
 * A change in a chance as an arrow on a fixed 0-to-100 track: a hollow
 * marker where it was, a filled one where it is now, and between them a line
 * as long as the move, so moves in a list compare by length.
 *
 * One colour whichever way it went. The direction is the arrowhead, and the
 * two figures at the ends say it in numbers.
 */
export function MoveTrack({ was, now, size = "row", wasWord, nowWord, className }: MoveTrackProps) {
  const from = Math.min(1, Math.max(0, Number(was)));
  const to = Math.min(1, Math.max(0, Number(now)));
  const change = printedChange(from, to);
  const flat = change.direction === "flat";
  const large = size === "large";

  const markers = (
    <>
      <span className="viz-mt__line" />
      {TICKS.map((tick) => (
        <span
          key={tick}
          className="viz-mt__tick"
          data-mid={tick === 50 ? "" : undefined}
          style={vars({ "--viz-at": tick })}
        />
      ))}
      {flat ? null : <span className="viz-mt__seg" />}
      {flat ? null : <span className="viz-mt__head" />}
      <span className="viz-mt__was" />
      <span className="viz-mt__now" />
    </>
  );
  const position = vars({
    "--viz-was": at(from),
    "--viz-now": at(to),
    "--viz-lo": at(Math.min(from, to)),
    "--viz-d": Math.abs(at(to) - at(from)),
  });

  if (!large) {
    return (
      <span className={cx("viz-mt", "viz-mt--row", className)} data-dir={change.direction} style={position}>
        <span className="viz-sr">{changeSentence(from, to)}</span>
        <span className="viz-mt__rail" aria-hidden="true">
          {markers}
          {flat ? null : (
            <span className="viz-mt__end viz-mt__end--was">
              <span className="viz-mt__fig">{change.was}</span>
            </span>
          )}
          <span className="viz-mt__end viz-mt__end--now">
            <span className="viz-mt__fig">{change.now}</span>
          </span>
        </span>
      </span>
    );
  }

  // Large: a word over each figure, above the track, laid out so the two
  // never meet and never leave the part.
  const labels = [
    { key: "was", x: from, word: wasWord ?? "", figure: change.was, r: 8 },
    { key: "now", x: to, word: nowWord ?? "", figure: change.now, r: 9 },
  ]
    .filter((label) => !(flat && label.key === "was"))
    .map((label) => ({
      ...label,
      width: Math.ceil(Math.max(monoWidth(label.word, WORD_PX), figureWidth(label.figure, FIGURE_PX))) + 4,
    }))
    .sort((a, b) => a.x - b.x);
  const layout = layoutTrackLabels(labels.map(({ x, width, r }) => ({ x, width, r })));
  const rows = Math.max(0, ...layout.places.map((place) => place.row)) + 1;

  return (
    <span
      className={cx("viz-mt", "viz-mt--large", className)}
      data-dir={change.direction}
      style={{
        ...position,
        // At least the half-width of "100%" under each end of the track.
        paddingLeft: `${Math.max(16, layout.padLeft)}px`,
        paddingRight: `${Math.max(16, layout.padRight)}px`,
        paddingTop: `${rows * ROW_PX + 4}px`,
      }}
    >
      <span className="viz-sr">{changeSentence(from, to)}</span>
      <span className="viz-mt__rail" aria-hidden="true">
        {markers}
        {labels.map((label, index) => {
          const place = layout.places[index];
          if (!place) return null;
          return (
            <span
              key={label.key}
              className="viz-mt__label"
              data-key={label.key}
              data-align={place.align}
              style={{
                left: `calc(${(label.x * 100).toFixed(2)}% + ${place.offset}px)`,
                width: `${label.width}px`,
                textAlign: place.align,
                bottom: `calc(100% + ${6 + place.row * ROW_PX}px)`,
              }}
            >
              {label.word ? <span className="viz-mt__word">{label.word}</span> : null}
              <Figure className="viz-mt__fig" text={label.figure} />
            </span>
          );
        })}
      </span>
      <MoveScale inset />
    </span>
  );
}

/**
 * The 0, 50 and 100 under a list of row tracks, lined up with them: put one
 * under (or over) the list, at the same width as its tracks. `inset` is for
 * a scale inside a part that already has the track's margins.
 */
export function MoveScale({ inset = false, className }: { inset?: boolean; className?: string }) {
  const labels = [
    { at: 0, text: viz.scaleStart },
    { at: 50, text: viz.scaleMiddle },
    { at: 100, text: viz.scaleEnd },
  ];
  return (
    <span className={cx("viz-scale", inset && "viz-scale--inset", className)} aria-hidden="true">
      <span className="viz-scale__inner">
        {labels.map((label) => (
          <span key={label.at} className="viz-scale__label" style={{ left: `${label.at}%` }}>
            {label.text}
          </span>
        ))}
      </span>
    </span>
  );
}

type Window = { was: number | string; now: number | string } | null;

type MoveWindowsProps = {
  /** The last day: where it was and where it is now. Null when there is no figure. */
  day: Window;
  /** The last week. Null for a question younger than a week. */
  week: Window;
  /** Print the 0-50-100 scale under the two. */
  scale?: boolean;
  /**
   * Leave out a window that has no figure instead of saying so. For the
   * moves list: a question missing from one of its lists moved too little, or
   * was left out by the list's other rules, which is not "no figure".
   */
  hideMissing?: boolean;
  className?: string;
};

/**
 * One question's day and week, one above the other on the same scale, so
 * the two arrows end at the same "now" and compare by length.
 */
export function MoveWindows({ day, week, scale = true, hideMissing = false, className }: MoveWindowsProps) {
  const lanes = [
    { name: viz.pastDay, window: day, none: viz.noDay },
    { name: viz.pastWeek, window: week, none: viz.noWeek },
  ].filter((lane) => !hideMissing || lane.window);
  if (!day && !week) {
    return <p className={cx("viz-windows__none", className)}>{viz.noChanges}</p>;
  }
  return (
    <div className={cx("viz-windows", className)}>
      {lanes.map((lane) => (
        <div key={lane.name} className="viz-windows__lane">
          <span className="viz-windows__name">{lane.name}</span>
          {lane.window ? (
            <MoveTrack was={lane.window.was} now={lane.window.now} />
          ) : (
            <span className="viz-windows__none">{lane.none}</span>
          )}
        </div>
      ))}
      {scale ? (
        <div className="viz-windows__lane" aria-hidden="true">
          <span />
          <MoveScale />
        </div>
      ) : null}
    </div>
  );
}
