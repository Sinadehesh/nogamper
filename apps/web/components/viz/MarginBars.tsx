import "./viz.css";

import { viz } from "@/lib/copy";
import { marginPercent, marginTakes, pct } from "@/lib/viz";

import { cx, vars } from "./style";

type MarginBarsProps = {
  /** From `getRules()`: `reference_margin`, `margin` and `max_legs`. Null prints a sentence instead. */
  rules: { reference_margin: string; margin: string; max_legs: number } | null;
  className?: string;
};

/**
 * What a bookmaker's margin takes from a stake as a slip grows, pick by pick
 * (1 − (1 − m)^n), beside what this site takes: nothing, at every length.
 *
 * It is a table, because that is what it is; the bars inside it are drawn
 * for the eye and hidden from a screen reader, which reads the figures. All
 * neutral: the longest slip's bar is the one in full ink, and nothing is red.
 */
export function MarginBars({ rules, className }: MarginBarsProps) {
  const margin = rules ? Number(rules.reference_margin) : Number.NaN;
  if (!rules || !Number.isFinite(margin) || margin <= 0 || margin >= 1) {
    return <p className={cx("viz-slip__note", className)}>{viz.marginUnavailable}</p>;
  }

  const rows = marginTakes(margin, rules.max_legs);
  // This site's own margin, from the same rules: none, so 0% at every length.
  const ours = marginTakes(Math.max(0, Number(rules.margin) || 0), rules.max_legs);
  const largest = rows[rows.length - 1]?.take ?? margin;
  // The bars' scale ends at the next 5% above the largest take.
  const ceiling = Math.max(0.05, Math.ceil((largest * 100) / 5) * 0.05);
  const marginText = marginPercent(margin);

  return (
    <table className={cx("viz-margin", className)} style={vars({ "--viz-max": ceiling.toFixed(4) })}>
      <caption className="viz-sr">{viz.marginCaption(marginText)}</caption>
      <thead>
        <tr>
          <th scope="col">{viz.marginColPicks}</th>
          <th scope="col">{viz.marginColBookmaker(marginText)}</th>
          <th scope="col" className="viz-margin__us-col">
            {viz.marginColUs}
          </th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.legs} data-lead={row.legs === rows.length ? "" : undefined}>
            <th scope="row">{viz.marginPicks(row.legs)}</th>
            <td className="viz-margin__cell">
              <span className="viz-margin__bar">
                <span
                  className="viz-margin__fill"
                  aria-hidden="true"
                  style={vars({ "--viz-take": row.take.toFixed(4) })}
                />
                <span className="viz-margin__value">{row.printed}</span>
              </span>
            </td>
            <td className="viz-margin__cell viz-margin__us-col">
              <span className="viz-margin__bar">
                <span className="viz-margin__stub" aria-hidden="true" />
                <span className="viz-margin__zero">
                  {(ours[row.legs - 1]?.take ?? 0) === 0 ? pct(0) : ours[row.legs - 1]?.printed}
                </span>
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
