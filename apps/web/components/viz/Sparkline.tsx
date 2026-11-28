import "./viz.css";

import { viz } from "@/lib/copy";
import type { HistoryPoint, PublicQuestion } from "@/lib/types";
import { extremes, gapLimit, parseHistory, pct, segmentByGaps } from "@/lib/viz";

import { cx, vars } from "./style";

type SparklineProps = {
  history: HistoryPoint[];
  source?: PublicQuestion["history_source"];
  /** Width and height in any CSS length; 6rem by 1.75rem unless given. */
  width?: string;
  height?: string;
  className?: string;
};

/**
 * A week of a question's price in the space of a word, on the same fixed
 * 0-to-100 scale as the full chart, so a flat week looks flat. A faint line
 * marks 50%. A screen reader hears where it started and ended.
 */
export function Sparkline({ history, source = "source", width, height, className }: SparklineProps) {
  const points = parseHistory(history);
  const first = points[0];
  const last = points[points.length - 1];
  const range = extremes(points);
  const style = vars({ ...(width ? { "--viz-spark-w": width } : {}), ...(height ? { "--viz-spark-h": height } : {}) });
  if (!first || !last || !range) {
    return (
      <span className={cx("viz-spark", className)} style={style}>
        <span className="viz-sr">{viz.chartEmpty}</span>
      </span>
    );
  }

  const start = first.t;
  const span = Math.max(1, last.t - start);
  const x = (t: number) => (points.length === 1 ? 100 : ((t - start) / span) * 100);
  const d = segmentByGaps(points, gapLimit(source))
    .map((segment) =>
      segment
        .map((point, i) => `${i ? "L" : "M"}${x(point.t).toFixed(2)},${((1 - point.v) * 100).toFixed(2)}`)
        .join(""),
    )
    .join("");

  return (
    <span className={cx("viz-spark", className)} style={style}>
      <span className="viz-sr">
        {viz.sparkSentence(pct(first.v), pct(last.v), pct(range.low.v), pct(range.high.v))}
      </span>
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true" focusable="false">
        <line className="viz-spark__mid" x1="0" x2="100" y1="50" y2="50" vectorEffect="non-scaling-stroke" />
        <path className="viz-spark__line" d={d} vectorEffect="non-scaling-stroke" />
      </svg>
      <span
        className="viz-spark__end"
        aria-hidden="true"
        style={{ left: `${x(last.t)}%`, top: `${(1 - last.v) * 100}%` }}
      />
    </span>
  );
}
