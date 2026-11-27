import type { HistoryPoint } from "@/lib/types";

/**
 * A question's chance over time, as a line.
 *
 * Drawn on the server and sent as plain SVG: no script, no charting library,
 * nothing for a reader's browser to fetch from anybody else.
 *
 * **The scale is always 0 to 100%.** A chart that zoomed in on the range the
 * price happened to cover would make a drift from 41% to 43% look like a
 * cliff, and every chart on a betting site is drawn that way for that reason.
 * Here a small move looks small.
 *
 * The line is stretched to whatever width it is given, so the labels are
 * ordinary text beside it rather than text inside the drawing, where they
 * would shrink with it and be unreadable on a phone.
 */

const TICKS = [100, 75, 50, 25, 0];

type Props = {
  points: HistoryPoint[];
  firstLabel: string;
  lastLabel: string;
};

/**
 * The drawing is hidden from a screen reader. Whoever uses this puts the same
 * information beside it as a sentence — where it started, where it ended, how
 * low and how high — which is what a line cannot say aloud, and which then
 * does not need saying twice.
 */
export function PriceChart({ points, firstLabel, lastLabel }: Props) {
  const series = points
    .map((point) => ({ at: new Date(point.at).getTime(), yes: Number(point.yes) }))
    .filter((point) => Number.isFinite(point.at) && Number.isFinite(point.yes))
    .map((point) => ({ at: point.at, yes: Math.min(1, Math.max(0, point.yes)) }));
  const first = series[0];
  const last = series[series.length - 1];
  if (!first || !last) return null;

  const span = Math.max(1, last.at - first.at);
  const path = series
    .map((point, index) => {
      const x = ((point.at - first.at) / span) * 100;
      const y = (1 - point.yes) * 100;
      return `${index === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
    })
    // One point is a place, not a line: carried across so that it shows.
    .concat(series.length === 1 ? [`L100,${((1 - first.yes) * 100).toFixed(2)}`] : [])
    .join(" ");

  return (
    <div>
      <div className="flex gap-2">
        <div className="relative h-48 w-9 shrink-0 text-xs text-muted" aria-hidden>
          {TICKS.map((tick) => (
            <span
              key={tick}
              className="absolute right-0 -translate-y-1/2 tabular-nums"
              style={{ top: `${100 - tick}%` }}
            >
              {`${tick}%`}
            </span>
          ))}
        </div>
        <svg
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          aria-hidden
          className="h-48 w-full overflow-visible"
        >
          {TICKS.map((tick) => (
            <line
              key={tick}
              x1="0"
              x2="100"
              y1={100 - tick}
              y2={100 - tick}
              className="stroke-line"
              strokeWidth="1"
              vectorEffect="non-scaling-stroke"
            />
          ))}
          <path
            d={path}
            fill="none"
            className="stroke-accent"
            strokeWidth="2.5"
            strokeLinejoin="round"
            strokeLinecap="round"
            vectorEffect="non-scaling-stroke"
          />
        </svg>
      </div>
      <div className="mt-2 flex justify-between pl-11 text-xs text-muted" aria-hidden>
        <span>{firstLabel}</span>
        <span>{lastLabel}</span>
      </div>
    </div>
  );
}
