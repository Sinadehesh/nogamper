import "./reading.css";

import { mission } from "@/lib/content";

// The guesses as dots, filled column by column from the lowest guess to the
// highest, so that the middle guess lands in the middle column: 16 to a
// column on a wide screen, 25 on a narrow one, where 50 columns would be
// too fine to see.
const CELL = 10;
const ARRANGEMENTS = [
  { rows: 16, id: "rd-ox-dot-wide", className: "rd-ox__dots rd-ox__dots--wide" },
  { rows: 25, id: "rd-ox-dot-narrow", className: "rd-ox__dots rd-ox__dots--narrow" },
];
// The bars' scale, a little past the larger weight.
const SCALE_LB = 1300;
const TICKS = [0, 400, 800, 1200];

const lb = (weight: number) => weight.toLocaleString("en-US");
const share = (weight: number) => Math.round((weight / SCALE_LB) * 10_000) / 100;

function Dots({ guesses, rows, id, className }: { guesses: number; rows: number; id: string; className: string }) {
  const columns = Math.ceil(guesses / rows);
  const full = Math.floor(guesses / rows);
  const rest = guesses - full * rows;
  const mid = (guesses - 1) / 2;
  const midX = Math.floor(mid / rows) * CELL + CELL / 2;
  const midY = (mid % rows) * CELL + CELL / 2;
  return (
    <svg className={className} viewBox={`0 0 ${columns * CELL} ${rows * CELL}`} aria-hidden="true" focusable="false">
      <defs>
        <pattern id={id} width={CELL} height={CELL} patternUnits="userSpaceOnUse">
          <circle className="rd-ox__dot" cx={CELL / 2} cy={CELL / 2} r={3} />
        </pattern>
      </defs>
      <rect width={full * CELL} height={rows * CELL} fill={`url(#${id})`} />
      {rest > 0 ? <rect x={full * CELL} width={CELL} height={rest * CELL} fill={`url(#${id})`} /> : null}
      <circle className="rd-ox__ring" cx={midX} cy={midY} r={7} />
      <circle className="rd-ox__mid" cx={midX} cy={midY} r={3.6} />
    </svg>
  );
}

/**
 * The 1907 ox, drawn from the three figures the page's own story gives: how
 * many guesses there were, the middle one, and the ox. Each dot is a guess
 * by its place in order, not by its weight, which this page does not know.
 * The two weights are bars from zero on one scale, so the gap between them
 * is drawn at its true size.
 */
export function OxFigure() {
  const { guesses, middle, ox } = mission.nameNumbers;
  const words = mission.nameFigure;

  const bars = [
    { key: "middle", label: words.middle, weight: middle },
    { key: "ox", label: words.ox, weight: ox },
  ];

  return (
    <figure className="rd-ox" aria-labelledby="ox-label">
      <figcaption id="ox-label" className="rd-fact__k">
        {words.label}
      </figcaption>

      <div>
        <p className="rd-ox__count">
          <span className="rd-ox__big">{lb(guesses)}</span>
          <span className="rd-ox__lab">{words.guessesWord}</span>
        </p>
        {ARRANGEMENTS.map((arrangement) => (
          <Dots key={arrangement.id} guesses={guesses} {...arrangement} />
        ))}
        <div className="rd-ox__ends" aria-hidden="true">
          <span>{words.lower}</span>
          <span>{words.middle}</span>
          <span>{words.higher}</span>
        </div>
        <p className="rd-ox__note">{words.dots}</p>
      </div>

      <div className="rd-ox__bars">
        {bars.map((bar) => (
          <div key={bar.key} className={`rd-ox__bar rd-ox__bar--${bar.key}`}>
            <p className="rd-ox__barhead">
              <span>{bar.label}</span>
              <b>{words.pounds(lb(bar.weight))}</b>
            </p>
            <div className="rd-ox__track" aria-hidden="true">
              <div className="rd-ox__fill" style={{ width: `${share(bar.weight)}%` }} />
            </div>
          </div>
        ))}
        <div className="rd-ox__axis" aria-hidden="true">
          {TICKS.map((tick) => (
            <span key={tick} style={{ left: `${share(tick)}%` }}>
              {/* The unit once, on the first label: it starts flush left, where
                  a last label centred on its tick would run past the edge. */}
              {tick === TICKS[0] ? words.pounds(lb(tick)) : lb(tick)}
            </span>
          ))}
        </div>
        <p className="rd-ox__gap">
          <b>{words.apart(lb(middle - ox))}</b> {words.fromZero}
        </p>
      </div>
    </figure>
  );
}
