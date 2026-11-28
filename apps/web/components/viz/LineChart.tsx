import "./viz.css";

import { useId } from "react";

import { viz } from "@/lib/copy";
import type { PublicQuestion } from "@/lib/types";
import {
  LINE_CHART,
  type LineChartModel,
  lineChartModel,
  type PriceBand,
  pct,
  timeUtc,
  utcDay,
  weekdayDateUtc,
} from "@/lib/viz";

import { Figure } from "./Figure";
import { LineChartScrubber } from "./LineChartScrubber";
import { cx, vars } from "./style";

type LineChartProps = {
  question: PublicQuestion;
  /** Mark where it stood a day and a week ago. On by default; open questions only. */
  references?: boolean;
  /** The sentence under the chart that says the same in words. */
  summary?: boolean;
  /** The "Show the figures" table. */
  figures?: boolean;
  /** The id of the heading that names the chart, if the page has one. */
  labelledBy?: string;
  /**
   * The game's band, from the rules where the page has them: where the API
   * holds the live price on it, the line ends on the market's own reading
   * (`priceToShow`), and a held price prints as its bound.
   */
  band?: PriceBand;
  className?: string;
};

const GRID = [100, 75, 50, 25, 0];

/** Per-breakpoint custom properties: `--viz-dx-s`, `--viz-vis-m` and so on. */
function placementVars(
  placements: Record<string, { dx: number; dy: number; show: boolean; leader?: { top: number; length: number } }>,
  withY: boolean,
) {
  const out: Record<`--${string}`, string> = {};
  for (const [bp, place] of Object.entries(placements)) {
    out[`--viz-dx-${bp}`] = `${place.dx}px`;
    if (withY) out[`--viz-dy-${bp}`] = `${place.dy}px`;
    out[`--viz-vis-${bp}`] = place.show ? "visible" : "hidden";
    if (place.leader) {
      out[`--viz-lt-${bp}`] = `${place.leader.top}px`;
      out[`--viz-ll-${bp}`] = `${place.leader.length}px`;
    }
  }
  return out;
}

function frameVars() {
  const out: Record<`--${string}`, string> = {};
  for (const bp of LINE_CHART.breakpoints) {
    out[`--viz-lc-top-${bp.id}`] = `${bp.top}px`;
    out[`--viz-lc-h-${bp.id}`] = `${bp.plotH}px`;
    out[`--viz-lc-left-${bp.id}`] = `${bp.left}px`;
    out[`--viz-lc-right-${bp.id}`] = `${bp.right}px`;
    out[`--viz-lc-x-${bp.id}`] = `${bp.xBand}px`;
  }
  return vars(out);
}

/**
 * A question's chance over time, on a fixed 0-to-100 scale.
 *
 * Drawn on the server as SVG and plain HTML, so it is complete without
 * JavaScript and does not move when the page wakes up: gridlines at every
 * 25 (50 a little stronger), a tick for every UTC day, the line in the
 * accent with a faint wash under it, the price now at its end, where it
 * stood a day and a week ago, the week's low and high, the moment forecasts
 * closed, and the result. Where the site's own record has holes the line
 * stops rather than draw prices nobody read.
 *
 * Every label's place at each width is worked out beforehand (`lineChartModel`),
 * so none overlaps another at any width from 256px up; a label that cannot
 * be placed is left out there, and its figure stays in the tooltip and the
 * table. On top sits one small client part for the crosshair, the tooltip
 * and the keyboard.
 */
export function LineChart({
  question,
  references = true,
  summary = true,
  figures = true,
  labelledBy,
  band,
  className,
}: LineChartProps) {
  const model = lineChartModel(question, { references, band });
  // Sent to the browser only when some reading is a held price.
  const figureTexts = model.rows.some((row) => row.text) ? model.rows.map((row) => row.text ?? null) : undefined;
  const washId = `viz-wash-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const hintId = `${washId}-hint`;

  return (
    <figure className={cx("viz-lc", className)} aria-labelledby={labelledBy}>
      <div className="viz-lc__frame" style={frameVars()}>
        <div className="viz-lc__y" aria-hidden="true">
          {GRID.map((tick) => (
            <span key={tick} className="viz-lc__ylabel" style={{ top: `${100 - tick}%` }}>
              {pct(tick / 100)}
            </span>
          ))}
        </div>

        <div className="viz-lc__plot">
          <svg
            className="viz-lc__svg"
            viewBox="0 0 100 100"
            preserveAspectRatio="none"
            aria-hidden="true"
            focusable="false"
          >
            <defs>
              <linearGradient id={washId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0" className="viz-lc__wash-top" />
                <stop offset="1" className="viz-lc__wash-bottom" />
              </linearGradient>
            </defs>
            {GRID.map((tick) => (
              <line
                key={tick}
                className="viz-lc__grid"
                data-mid={tick === 50 ? "" : undefined}
                x1="0"
                x2="100"
                y1={100 - tick}
                y2={100 - tick}
                vectorEffect="non-scaling-stroke"
              />
            ))}
            {model.area ? <path d={model.area} fill={`url(#${washId})`} /> : null}
            {model.line ? (
              <path className="viz-lc__line" d={model.line} vectorEffect="non-scaling-stroke" />
            ) : null}
          </svg>

          {model.rules.map((fx) => (
            <span key={fx} className="viz-lc__rule" aria-hidden="true" style={{ left: `${fx * 100}%` }} />
          ))}

          {model.markers.map((marker, index) => (
            <span
              key={`${marker.kind}-${index}`}
              className={`viz-lc__mk viz-lc__mk--${marker.kind}`}
              data-outcome={marker.outcome}
              aria-hidden="true"
              style={{ left: `${marker.fx * 100}%`, top: `${(1 - marker.v) * 100}%` }}
            />
          ))}

          {model.labels.map((label) => {
            const text = label.value ? `${label.word} ${label.value}` : label.word;
            return (
              <span
                key={label.id}
                className="viz-lc__label"
                data-kind={label.id}
                aria-hidden="true"
                style={{
                  left: `${label.fx * 100}%`,
                  top: label.mode === "top" ? "0%" : `${(1 - label.v) * 100}%`,
                  ...vars({ "--viz-chars": text.length, ...placementVars(label.placements, true) }),
                }}
              >
                {label.word}
                {label.value ? (
                  <>
                    {" "}
                    <span className="viz-lc__label-value">{label.value}</span>
                  </>
                ) : null}
                <span className="viz-lc__leader" />
              </span>
            );
          })}

          {model.empty ? (
            <p className="viz-lc__empty">{model.summary}</p>
          ) : (
            <>
              <span id={hintId} className="viz-sr">
                {viz.chartHint}
              </span>
              <LineChartScrubber
                times={model.points.map((point) => point.t)}
                values={model.points.map((point) => point.v)}
                notes={model.rows.map((row) => row.note)}
                figures={figureTexts}
                start={model.start}
                end={model.end}
                hintId={hintId}
              />
            </>
          )}
        </div>

        <div className="viz-lc__end" aria-hidden="true">
          {model.empty ? null : (
            <span
              className="viz-lc__endlabel"
              data-outcome={model.end_label.outcome ?? undefined}
              data-long={model.end_label.value.length >= 5 ? "" : undefined}
              style={vars({ "--viz-top": `${(1 - model.end_label.v) * 100}%` })}
            >
              <Figure className="viz-lc__endvalue" text={model.end_label.value} />
              <span className="viz-lc__endword">{model.end_label.word}</span>
            </span>
          )}
        </div>

        <div className="viz-lc__x" aria-hidden="true">
          {model.ticks.map((tick) => (
            <span key={tick.fx} className="viz-lc__tick" style={{ left: `${tick.fx * 100}%` }} />
          ))}
          {model.ticks.map((tick) => (
            <span
              key={`label-${tick.fx}`}
              className="viz-lc__xl"
              data-xs={tick.placements.xs.text}
              data-s={tick.placements.s.text}
              data-m={tick.placements.m.text}
              data-l={tick.placements.l.text}
              style={{ left: `${tick.fx * 100}%`, ...vars(placementVars(tick.placements, false)) }}
            >
              <span className="viz-lc__xl-long">{tick.long}</span>
              <span className="viz-lc__xl-short">{tick.short}</span>
            </span>
          ))}
        </div>
        <div className="viz-lc__unit" aria-hidden="true">
          {model.empty ? null : viz.chartUtc}
        </div>
      </div>

      {summary && !model.empty ? <figcaption className="viz-lc__summary">{model.summary}</figcaption> : null}
      {model.empty ? <figcaption className="viz-sr">{model.summary}</figcaption> : null}
      {figures && !model.empty ? <Figures model={model} /> : null}
    </figure>
  );
}

/** The readings as a table, by UTC day, with the ones a reader looks for marked. */
function Figures({ model }: { model: LineChartModel }) {
  const days: { day: number; rows: LineChartModel["rows"] }[] = [];
  for (const row of model.rows) {
    const day = utcDay(row.t);
    const current = days[days.length - 1];
    if (current && current.day === day) current.rows.push(row);
    else days.push({ day, rows: [row] });
  }

  return (
    <details className="viz-lc__figures">
      <summary>{viz.chartFigures}</summary>
      <dl className="viz-lc__keys" aria-label={viz.chartKeyFigures}>
        {model.keyFigures.map((item) => (
          <div key={item.term} style={{ display: "contents" }}>
            <dt>{item.term}</dt>
            <dd>{item.value}</dd>
          </div>
        ))}
      </dl>
      <div className="viz-lc__tablewrap" tabIndex={0} role="region" aria-label={viz.chartTableCaption}>
        <table className="viz-lc__table">
          <caption className="viz-sr">{viz.chartTableCaption}</caption>
          <thead>
            <tr>
              <th scope="col">{viz.chartColTime}</th>
              <th scope="col">{viz.chartColChance}</th>
              <th scope="col">{viz.chartColNote}</th>
            </tr>
          </thead>
          {days.map((group) => (
            <tbody key={group.day}>
              <tr>
                <th scope="rowgroup" colSpan={3}>
                  {weekdayDateUtc(group.rows[0]?.t ?? group.day * 86_400_000)}
                </th>
              </tr>
              {group.rows.map((row) => (
                <tr key={row.t}>
                  <th scope="row">{timeUtc(row.t)}</th>
                  <td className="viz-num">{row.text ?? pct(row.v)}</td>
                  <td>{row.note ?? ""}</td>
                </tr>
              ))}
            </tbody>
          ))}
        </table>
      </div>
    </details>
  );
}
