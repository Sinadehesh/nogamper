"use client";

import { type KeyboardEvent, type PointerEvent, useCallback, useRef, useState } from "react";

import { viz } from "@/lib/copy";
import { MS, pct, shortDateTimeUtc } from "@/lib/viz";

import { Figure } from "./Figure";
import { vars } from "./style";

type ScrubberProps = {
  /** Every reading on the chart, in time order: milliseconds and 0..1. */
  times: number[];
  values: number[];
  /** What the table calls a reading, if anything: "7-day high", "Now". */
  notes: (string | null)[];
  /** A reading's figure where it is not `pct(value)`: a held price's bound, "≤1%". */
  figures?: (string | null)[];
  start: number;
  end: number;
  /** The id of the sentence that says how to use the keys. */
  hintId: string;
};

/**
 * The chart's interactive layer: a crosshair that snaps to the nearest
 * reading under a pointer or a finger, a tooltip with its time and chance,
 * and the same from the keyboard with the arrow keys, Page Up and Down, Home
 * and End.
 *
 * It only adds. The chart is drawn on the server and reads completely
 * without it, and every figure the tooltip shows is in the table below the
 * chart. It renders nothing visible until it is used, so the page looks the
 * same before and after it starts.
 */
export function LineChartScrubber({ times, values, notes, figures, start, end, hintId }: ScrubberProps) {
  const [index, setIndex] = useState<number | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  // Focus that a pointer press brings must not jump the reading to the end,
  // and a mouse leaving must not take away a reading the keyboard chose. On
  // a touch screen the press is over before focus arrives, so it is timed.
  const pressedAt = useRef(-Infinity);
  const keyIndex = useRef<number | null>(null);
  const count = times.length;
  const span = Math.max(1, end - start);
  const lastIndex = count - 1;

  const nearest = useCallback(
    (t: number) => {
      let lo = 0;
      let hi = lastIndex;
      while (lo < hi) {
        const mid = (lo + hi) >> 1;
        if ((times[mid] ?? 0) < t) lo = mid + 1;
        else hi = mid;
      }
      const before = lo > 0 ? lo - 1 : lo;
      return Math.abs((times[before] ?? 0) - t) <= Math.abs((times[lo] ?? 0) - t) ? before : lo;
    },
    [times, lastIndex],
  );

  const fromPointer = (event: PointerEvent<HTMLDivElement>) => {
    const box = ref.current?.getBoundingClientRect();
    if (!box || box.width <= 0) return;
    const fraction = Math.min(1, Math.max(0, (event.clientX - box.left) / box.width));
    setIndex(nearest(start + fraction * span));
  };

  const figureAt = (i: number, v: number) => figures?.[i] ?? pct(v);

  const describe = (i: number) => {
    const t = times[i];
    const v = values[i];
    if (t === undefined || v === undefined) return "";
    const note = notes[i];
    const text = viz.chartPoint(shortDateTimeUtc(t), figureAt(i, v));
    return note ? `${text}. ${note}` : text;
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const current = index ?? lastIndex;
    const t = times[current] ?? end;
    let next: number | null = null;
    switch (event.key) {
      case "ArrowRight":
      case "ArrowUp":
        next = Math.min(lastIndex, current + 1);
        break;
      case "ArrowLeft":
      case "ArrowDown":
        next = Math.max(0, current - 1);
        break;
      case "PageUp":
        next = nearest(Math.min(end, t + MS.DAY));
        break;
      case "PageDown":
        next = nearest(Math.max(start, t - MS.DAY));
        break;
      case "Home":
        next = 0;
        break;
      case "End":
        next = lastIndex;
        break;
      case "Escape":
        keyIndex.current = null;
        setIndex(null);
        return;
      default:
        return;
    }
    event.preventDefault();
    keyIndex.current = next;
    setIndex(next);
  };

  const shown = index === null ? null : { t: times[index], v: values[index], note: notes[index] };
  const fx = shown?.t === undefined ? 0 : (shown.t - start) / span;

  return (
    <div
      ref={ref}
      className="viz-lc__scrub"
      role="slider"
      tabIndex={0}
      aria-label={viz.chartSlider}
      aria-describedby={hintId}
      aria-orientation="horizontal"
      aria-valuemin={0}
      aria-valuemax={lastIndex}
      aria-valuenow={index ?? lastIndex}
      aria-valuetext={describe(index ?? lastIndex)}
      onPointerDown={(event) => {
        pressedAt.current = event.timeStamp;
        fromPointer(event);
      }}
      onPointerMove={(event) => {
        // A finger only moves the crosshair while it is down; a mouse always.
        if (event.pointerType !== "mouse" && event.buttons === 0) return;
        fromPointer(event);
      }}
      onPointerLeave={(event) => {
        // Lifting a finger leaves the reading up to be read. A mouse moving
        // away puts back whatever the keyboard last chose, or nothing.
        if (event.pointerType === "mouse") setIndex(keyIndex.current);
      }}
      onFocus={(event) => {
        if (event.timeStamp - pressedAt.current < 1500) return;
        keyIndex.current = lastIndex;
        setIndex(lastIndex);
      }}
      onBlur={() => {
        pressedAt.current = -Infinity;
        keyIndex.current = null;
        setIndex(null);
      }}
      onKeyDown={onKeyDown}
    >
      {shown && shown.t !== undefined && shown.v !== undefined ? (
        <>
          <span className="viz-lc__cross" style={{ left: `${fx * 100}%` }} />
          <span
            className="viz-lc__hover"
            // The layer reaches 6px past the plot at the top and the bottom.
            style={{ left: `${fx * 100}%`, top: `calc(${(1 - shown.v).toFixed(4)} * (100% - 12px) + 6px)` }}
          />
          <span
            className="viz-lc__tip"
            data-side={fx > 0.6 ? "left" : "right"}
            data-at={shown.v > 0.55 ? "bottom" : "top"}
            style={vars({ "--viz-fx": fx.toFixed(4) })}
          >
            <span>
              <Figure className="viz-lc__tip-value" text={figureAt(index ?? lastIndex, shown.v)} />{" "}
              <span className="viz-lc__tip-words">{viz.chanceOfYes}</span>
            </span>
            <span>{shortDateTimeUtc(shown.t)}</span>
            {shown.note ? <span className="viz-lc__tip-note">{shown.note}</span> : null}
          </span>
        </>
      ) : null}
    </div>
  );
}
