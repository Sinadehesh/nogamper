import "./viz.css";

import type { ReactNode } from "react";

import { viz } from "@/lib/copy";
import { figureWidth, layoutTrackLabels, monoWidth, type PriceBand, pct, pctHeld } from "@/lib/viz";

import { Figure } from "./Figure";
import { at, cx, vars } from "./style";

type RangeBarProps = {
  /** The lowest and highest price of the last 7 days, 0 to 1. */
  low: number | string;
  high: number | string;
  /** The price to mark on it: the live one, or a closed question's last. */
  now: number | string;
  /** "live" says "Now"; "last" says "Last price". `weekRange()` gives all four. */
  kind?: "live" | "last";
  size?: "row" | "large";
  /**
   * The game's band, when the range holds a held price (`weekRange()` says
   * `held`): a figure on its edge prints as its bound, "≤1%" or "≥99%".
   */
  held?: PriceBand;
  /**
   * The sentence that says the range in words, from its printed figures. By
   * default "Over 7 days: …"; a range that covers less than the week names
   * the dates it covers instead.
   */
  describe?: (low: string, high: string, nowWord: string, now: string) => string;
  /**
   * The word over the one figure drawn when the lowest and the highest print
   * the same ("Unchanged at" over "0.1%"): a flat week is one label, not a
   * Low, a High and a Now that all say "0.1%". Without it, the price's own
   * word ("Now", "Last price") stands over that figure.
   */
  flat?: string;
  className?: string;
};

const TICKS = [0, 25, 50, 75, 100];
const WORD_PX = 11;
const FIGURE_PX = 20;
/**
 * The narrowest the large bar is drawn: the question page's range cell on a
 * 320px screen is 238px. Its labels are laid out at this width, so they stay
 * clear of each other wherever it is drawn wider (`layoutTrackLabels`).
 */
const NARROWEST = 236;

/**
 * The week's range as a band on a fixed 0-to-100 track, with the price now
 * marked on it: a question that swung from 20% to 98% and one that sat at
 * 61% all week look as different as they are.
 */
export function RangeBar({
  low,
  high,
  now,
  kind = "live",
  size = "row",
  held,
  describe = viz.rangeSentence,
  flat,
  className,
}: RangeBarProps) {
  const lo = Math.min(1, Math.max(0, Number(low)));
  const hi = Math.max(lo, Math.min(1, Math.max(0, Number(high))));
  const current = Math.min(hi, Math.max(lo, Number(now)));
  const nowWord = kind === "last" ? viz.rangeLast : viz.rangeNow;
  const figure = (value: number) => (held ? pctHeld(value, held) : pct(value));
  const sentence = describe(figure(lo), figure(hi), nowWord, figure(current));
  // Lowest, highest and the price shown all print alike (the price sits
  // between the two): one figure says all three.
  const same = figure(lo) === figure(hi);
  const position = vars({ "--viz-low": at(lo), "--viz-high": at(hi), "--viz-now": at(current) });

  const rail = (children?: ReactNode) => (
    <span className="viz-range__rail" aria-hidden="true">
      <span className="viz-range__line" />
      {TICKS.map((tick) => (
        <span
          key={tick}
          className="viz-range__tick"
          data-mid={tick === 50 ? "" : undefined}
          style={vars({ "--viz-at": tick })}
        />
      ))}
      <span className="viz-range__band" />
      <span className="viz-range__now" />
      {children}
    </span>
  );

  if (size !== "large") {
    return (
      <span className={cx("viz-range", "viz-range--row", className)} style={position}>
        <span className="viz-sr">{sentence}</span>
        {rail(
          <>
            {same ? null : (
              <span className="viz-range__end viz-range__end--low">
                <span className="viz-range__fig">{figure(lo)}</span>
              </span>
            )}
            <span className="viz-range__end viz-range__end--high">
              <span className="viz-range__fig">{figure(hi)}</span>
            </span>
          </>,
        )}
      </span>
    );
  }

  const labels = (
    same
      ? [{ key: "flat", x: current, word: flat ?? nowWord, figure: figure(current) }]
      : [
          { key: "low", x: lo, word: viz.low, figure: figure(lo) },
          { key: "high", x: hi, word: viz.high, figure: figure(hi) },
        ]
  ).map((label) => ({
    ...label,
    r: 6,
    width: Math.ceil(Math.max(monoWidth(label.word, WORD_PX), figureWidth(label.figure, FIGURE_PX))) + 4,
  }));
  const nowText = `${nowWord} ${figure(current)}`;
  const nowWidth = same ? 0 : Math.ceil(monoWidth(nowText, WORD_PX)) + 8;
  // The line under the track names the price now, and near an end it needs
  // room beside the track. That room is kept first, and the labels above are
  // laid out on the rail that is left, never on a wider one than is drawn.
  // A flat range has no such line: its one label says it.
  const nowLeft = same ? 0 : Math.max(0, nowWidth / 2 - current * NARROWEST + 2);
  const nowRight = same ? 0 : Math.max(0, nowWidth / 2 - (1 - current) * NARROWEST + 2);
  const layout = layoutTrackLabels(
    labels.map(({ x, width, r }) => ({ x, width, r })),
    NARROWEST - nowLeft - nowRight,
  );
  const padLeft = Math.max(layout.padLeft, nowLeft);
  const padRight = Math.max(layout.padRight, nowRight);
  const rows = Math.max(0, ...layout.places.map((place) => place.row)) + 1;

  return (
    <span
      className={cx("viz-range", "viz-range--large", className)}
      data-flat={same ? "" : undefined}
      style={{
        ...position,
        ...vars({ "--viz-now-w": `${nowWidth}px`, "--viz-pl": `${Math.ceil(padLeft)}px`, "--viz-pr": `${Math.ceil(padRight)}px` }),
        paddingLeft: `${Math.ceil(padLeft)}px`,
        paddingRight: `${Math.ceil(padRight)}px`,
        paddingTop: `${rows * 42 + 4}px`,
      }}
    >
      <span className="viz-sr">{sentence}</span>
      {rail(
        <>
          {labels.map((label, index) => {
            const place = layout.places[index];
            if (!place) return null;
            return (
              <span
                key={label.key}
                className="viz-range__label"
                data-align={place.align}
                style={{
                  left: `calc(${(label.x * 100).toFixed(2)}% + ${place.offset}px)`,
                  width: `${label.width}px`,
                  textAlign: place.align,
                  bottom: `calc(100% + ${6 + place.row * 42}px)`,
                }}
              >
                <span className="viz-range__word">{label.word}</span>
                <Figure className="viz-range__fig" text={label.figure} />
              </span>
            );
          })}
          {same ? null : <span className="viz-range__nowlabel">{nowText}</span>}
        </>,
      )}
    </span>
  );
}
