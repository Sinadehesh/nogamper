import type { CSSProperties, ReactNode } from "react";
import { notFound } from "next/navigation";

import {
  ChanceReadout,
  LineChart,
  MarginBars,
  MoveScale,
  MoveTrack,
  MoveWindows,
  PickFigures,
  RangeBar,
  SlipFigures,
  Sparkline,
  SplitBar,
} from "@/components/viz";
import { categoryLabel, viz } from "@/lib/copy";
import { getMoves, getQuestion } from "@/lib/server/questions";
import { getRules } from "@/lib/server/rules";
import type { PublicQuestion } from "@/lib/types";
import {
  changeWindows,
  closesOn,
  fromToArrow,
  groupByEvent,
  mergeWindows,
  MS,
  priceToShow,
  sideProbability,
  weekRange,
} from "@/lib/viz";

/**
 * A bench for the chart parts in components/viz, on live data from the
 * local API. Development only: it answers 404 in production, and it is
 * deleted before the redesign ships. Its labels are a bench's, not the
 * site's, so they stay here rather than in lib/copy.ts.
 */

export const metadata = { title: "Viz lab", robots: { index: false, follow: false } };

const SLUGS = {
  full: "faa-ground-stop-cause-software-or-configuration-error",
  short: "will-bitcoin-reach-64k-november-23-29-2026-from-november-23",
  yes: "elon-musk-of-tweets-november-20-november-27-2026-240-259",
  no: "elon-musk-of-tweets-november-20-november-27-2026-300-319",
  ceasefire: "israel-x-iran-ceasefire-continues-through-december-15",
  sweden: "will-ulf-kristersson-be-the-next-prime-minister-of-sweden",
};

const LAB = {
  title: "Chart parts",
  intro: "Live data from the local API, then the edge cases. Development only.",
  missing: "Not available from the local API right now:",
  readout: "ChanceReadout",
  split: "SplitBar",
  move: "MoveTrack",
  windows: "MoveWindows (two windows, one scale)",
  moves: "What moved, grouped by event",
  movesDay: "In the last day",
  movesWeek: "In the last week",
  movesMerged: "Day and week together, by question",
  chart: "LineChart",
  chartFull: "Open, a full week",
  chartShort: "Open, four days old (no week figure)",
  chartClosed: "Closed, waiting for its result (derived: a resolved question as it stood before its result)",
  chartClosedMid: "Closed mid-week (synthetic: closes_at moved two days back)",
  chartYes: "Resolved yes",
  chartNo: "Resolved no",
  chartOwn: "The site's own record, with gaps of 8 and 4 hours (synthetic)",
  chartOne: "One price (synthetic)",
  chartNone: "No history (synthetic)",
  chartNarrow: "In a 300px column",
  small: "Sparkline and RangeBar",
  margin: "MarginBars",
  slip: "Slip figures",
  slipOne: "One pick",
  slipNo: "One pick, on No",
  slipThree: "Three real picks",
  slipCapped: "Capped (5,000 points on two 20% picks)",
  slipOver: "Over the combined-odds limit",
  slipSettled: "A pick that is all but settled",
  surface: "On the #1a1a1a surface",
  edges: "Edge cases",
  edgeLow: "0.5%",
  edgeHigh: "99.5%",
  flat: "Unchanged",
} as const;

const page: CSSProperties = {
  background: "#0f0f0f",
  color: "#ffffff",
  minHeight: "100vh",
  padding: "40px 16px 120px",
  fontFamily: '"Schibsted Grotesk", system-ui, sans-serif',
};
const column: CSSProperties = { maxWidth: 1120, margin: "0 auto", display: "grid", gap: 56 };
const grid: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 320px), 1fr))",
  gap: 32,
};
const card: CSSProperties = { background: "#1a1a1a", borderRadius: 16, padding: 20 };
const h1: CSSProperties = { fontSize: 32, fontWeight: 500, letterSpacing: "-0.02em", margin: 0 };
const h2: CSSProperties = { fontSize: 20, fontWeight: 500, margin: "0 0 20px", letterSpacing: "-0.01em" };
const h3: CSSProperties = { fontSize: 13, fontWeight: 500, color: "#8f8f8f", margin: "0 0 12px" };
const question: CSSProperties = { fontSize: 15, lineHeight: 1.35, margin: "0 0 10px" };
const meta: CSSProperties = { fontSize: 12, color: "#8f8f8f", margin: "6px 0 0" };

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h2 style={h2}>{title}</h2>
      {children}
    </section>
  );
}

function Panel({ title, children, surface = false }: { title: string; children: ReactNode; surface?: boolean }) {
  return (
    <div className={surface ? "viz-on-surface" : undefined} style={surface ? card : undefined} data-panel="">
      <h3 style={h3}>{title}</h3>
      {children}
    </div>
  );
}

function derive(source: PublicQuestion, patch: Partial<PublicQuestion>): PublicQuestion {
  return { ...source, ...patch };
}

export default async function VizLab() {
  if (process.env.NODE_ENV === "production") notFound();

  const [full, short, yes, no, ceasefire, sweden, moves, rules] = await Promise.all([
    getQuestion(SLUGS.full),
    getQuestion(SLUGS.short),
    getQuestion(SLUGS.yes),
    getQuestion(SLUGS.no),
    getQuestion(SLUGS.ceasefire),
    getQuestion(SLUGS.sweden),
    getMoves(),
    getRules(),
  ]);
  const answers = { full, short, yes, no, ceasefire, sweden };
  const missing = Object.entries(answers)
    .filter(([, answer]) => answer.status !== "ok")
    .map(([name]) => name);
  if (full.status !== "ok" || short.status !== "ok" || yes.status !== "ok" || no.status !== "ok") {
    return (
      <main style={page}>
        <p>
          {LAB.missing} {missing.join(", ")}
        </p>
      </main>
    );
  }

  const q = full.data;
  const live = priceToShow(q);
  const windows = changeWindows(q);
  const shortWindows = changeWindows(short.data);
  const closedLate = derive(yes.data, { state: "closed", outcome: null, resolved_at: null });
  const closedMid = derive(q, {
    state: "closed",
    closes_at: new Date(Date.parse(q.as_of) - 2 * MS.DAY).toISOString(),
  });
  const ownGaps = derive(q, {
    history_source: "own",
    history: q.history.filter((_, i) => !(i >= 40 && i < 48) && !(i >= 100 && i < 104)),
  });
  const onePoint = derive(q, { state: "closed", history: q.history.slice(-1) });
  const noHistory = derive(q, { history: [], history_source: "none" });
  const range = weekRange(q);
  const shortRange = weekRange(short.data);
  const yesRange = weekRange(yes.data);

  const slipRules = rules ?? {
    min_prob: "0.01",
    max_prob: "0.99",
    max_combined_odds: "1000.0",
    payout_cap: { minor: 10_000_000, display: "100,000" },
    max_legs: 5,
  };
  const realLegs = [
    { side: "NO" as const, probability: q.probability.no, question: q.question },
    ...(ceasefire.status === "ok"
      ? [{ side: "YES" as const, probability: ceasefire.data.probability.yes, question: ceasefire.data.question }]
      : []),
    ...(sweden.status === "ok"
      ? [{ side: "YES" as const, probability: sweden.data.probability.yes, question: sweden.data.question }]
      : []),
  ];

  return (
    <main style={page}>
      <div style={column}>
        <header>
          <h1 style={h1}>{LAB.title}</h1>
          <p style={meta}>{LAB.intro}</p>
        </header>

        <Section title={LAB.readout}>
          <div style={grid}>
            <Panel title={q.question}>
              <ChanceReadout yes={live.value} size="header" showNo />
            </Panel>
            <Panel title={closedLate.question}>
              <ChanceReadout yes={priceToShow(closedLate).value} size="card" showNo kind="last" />
              <p style={{ ...question, marginTop: 16 }}>
                <ChanceReadout yes={live.value} size="inline" />
              </p>
            </Panel>
            <Panel title={`${LAB.edges}: ${LAB.edgeLow} / ${LAB.edgeHigh}`}>
              <ChanceReadout yes={0.005} size="card" showNo />
              <div style={{ height: 16 }} />
              <ChanceReadout yes={0.995} size="card" showNo />
            </Panel>
          </div>
        </Section>

        <Section title={LAB.split}>
          <div style={grid}>
            <Panel title={q.question}>
              <SplitBar yes={live.value} size="lg" />
              <div style={{ height: 20 }} />
              <SplitBar yes={live.value} size="md" />
              <div style={{ height: 20 }} />
              <SplitBar yes={live.value} size="sm" labels={false} />
            </Panel>
            <Panel title={LAB.edges}>
              <SplitBar yes={0.005} />
              <div style={{ height: 20 }} />
              <SplitBar yes={0.5} />
              <div style={{ height: 20 }} />
              <SplitBar yes={0.995} />
            </Panel>
          </div>
        </Section>

        <Section title={LAB.move}>
          <div style={grid}>
            <Panel title={q.question}>
              {windows.day ? (
                <MoveTrack was={windows.day.was} now={windows.day.now} size="large" wasWord={viz.dayAgo} nowWord={viz.now} />
              ) : null}
              <div style={{ height: 24 }} />
              {windows.week ? (
                <MoveTrack was={windows.week.was} now={windows.week.now} size="large" wasWord={viz.weekAgo} nowWord={viz.now} />
              ) : null}
            </Panel>
            <Panel title={LAB.edges}>
              <div style={{ display: "grid", gap: 12 }}>
                <MoveTrack was={0.005} now={0.12} />
                <MoveTrack was={0.88} now={0.995} />
                <MoveTrack was={0.55} now={0.6} />
                <MoveTrack was={0.6} now={0.55} />
                <MoveTrack was={0.616} now={0.624} />
                <MoveScale />
              </div>
            </Panel>
          </div>
        </Section>

        <Section title={LAB.windows}>
          <div style={grid}>
            <Panel title={q.question}>
              <MoveWindows day={windows.day} week={windows.week} />
            </Panel>
            <Panel title={short.data.question}>
              <MoveWindows day={shortWindows.day} week={shortWindows.week} />
            </Panel>
          </div>
        </Section>

        {moves ? (
          <Section title={LAB.moves}>
            <div style={grid}>
              {[
                { title: LAB.movesDay, list: moves.day },
                { title: LAB.movesWeek, list: moves.week },
              ].map((window) => (
                <Panel key={window.title} title={window.title}>
                  <div style={{ display: "grid", gap: 20 }}>
                    {groupByEvent(window.list).map((group) => (
                      <div key={group.title}>
                        <p style={{ ...meta, margin: "0 0 8px" }}>
                          {categoryLabel(group.category)} · {group.title}
                        </p>
                        <div style={{ display: "grid", gap: 14 }}>
                          {group.items.map((move) => (
                            <div key={move.slug}>
                              <p style={question}>{move.question}</p>
                              <MoveTrack was={move.was} now={move.now} />
                              <p style={meta}>
                                {fromToArrow(move.was, move.now)} · {closesOn(move.closes_at, moves.as_of)}
                              </p>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                    <MoveScale />
                  </div>
                </Panel>
              ))}
              <Panel title={LAB.movesMerged}>
                <div style={{ display: "grid", gap: 20 }}>
                  {mergeWindows(moves)
                    .slice(0, 8)
                    .map((row) => (
                      <div key={row.slug}>
                        <p style={question}>{row.question}</p>
                        <MoveWindows
                          day={row.day ? { was: row.day.was, now: row.now } : null}
                          week={row.week ? { was: row.week.was, now: row.now } : null}
                          scale={false}
                          hideMissing
                        />
                      </div>
                    ))}
                </div>
              </Panel>
            </div>
          </Section>
        ) : null}

        <Section title={LAB.chart}>
          <div style={{ display: "grid", gap: 48 }}>
            <Panel title={`${LAB.chartFull}: ${q.question}`}>
              <LineChart question={q} />
            </Panel>
            <div style={grid}>
              <Panel title={`${LAB.chartShort}: ${short.data.question}`}>
                <LineChart question={short.data} />
              </Panel>
              <Panel title={`${LAB.chartClosed}: ${closedLate.question}`}>
                <LineChart question={closedLate} />
              </Panel>
              <Panel title={LAB.chartClosedMid}>
                <LineChart question={closedMid} />
              </Panel>
              <Panel title={`${LAB.chartYes}: ${yes.data.question}`}>
                <LineChart question={yes.data} />
              </Panel>
              <Panel title={`${LAB.chartNo}: ${no.data.question}`}>
                <LineChart question={no.data} />
              </Panel>
              <Panel title={LAB.chartOwn}>
                <LineChart question={ownGaps} />
              </Panel>
              <Panel title={LAB.chartOne}>
                <LineChart question={onePoint} />
              </Panel>
              <Panel title={LAB.chartNone}>
                <LineChart question={noHistory} />
              </Panel>
            </div>
            <div style={{ width: 300, maxWidth: "100%" }}>
              <Panel title={LAB.chartNarrow} surface>
                <LineChart question={q} figures={false} />
              </Panel>
            </div>
          </div>
        </Section>

        <Section title={LAB.small}>
          <div style={grid}>
            {[
              { data: q, range },
              { data: short.data, range: shortRange },
              { data: yes.data, range: yesRange },
            ].map(({ data, range: r }) => (
              <Panel key={data.slug} title={data.question}>
                <Sparkline history={data.history} source={data.history_source} width="8rem" height="2rem" />
                <div style={{ height: 16 }} />
                {r ? <RangeBar low={r.low} high={r.high} now={r.now} kind={r.kind} /> : null}
                <div style={{ height: 20 }} />
                {r ? <RangeBar low={r.low} high={r.high} now={r.now} kind={r.kind} size="large" /> : null}
              </Panel>
            ))}
            <Panel title={LAB.edges}>
              <RangeBar low={0.005} high={0.995} now={0.5} />
              <div style={{ height: 16 }} />
              <RangeBar low={0.61} high={0.63} now={0.62} />
              <div style={{ height: 16 }} />
              <Sparkline history={ownGaps.history} source="own" width="100%" height="2.5rem" />
            </Panel>
          </div>
        </Section>

        <Section title={LAB.margin}>
          <div style={{ maxWidth: 640 }}>
            <MarginBars rules={rules} />
          </div>
        </Section>

        <Section title={LAB.slip}>
          <div style={grid}>
            <Panel title={`${LAB.slipOne}: ${q.question}`} surface>
              <PickFigures side="YES" probability={q.probability.yes} rules={slipRules} />
            </Panel>
            <Panel title={`${LAB.slipNo}: ${q.question}`} surface>
              <PickFigures side="NO" probability={q.probability.no} rules={slipRules} />
            </Panel>
            <Panel title={LAB.slipThree} surface>
              <SlipFigures legs={realLegs} rules={slipRules} />
            </Panel>
            <Panel title={LAB.slipCapped} surface>
              <SlipFigures
                legs={[
                  { side: "YES", probability: "0.2000" },
                  { side: "YES", probability: "0.2000" },
                ]}
                stakeMinor={500_000}
                rules={slipRules}
              />
            </Panel>
            <Panel title={LAB.slipOver} surface>
              <SlipFigures
                legs={[0.06, 0.08, 0.05, 0.1].map((p) => ({ side: "YES" as const, probability: p.toFixed(4) }))}
                rules={slipRules}
              />
            </Panel>
            <Panel title={LAB.slipSettled} surface>
              <PickFigures side="YES" probability="0.9950" rules={slipRules} />
              <div style={{ height: 16 }} />
              <SlipFigures
                legs={[
                  { side: "YES", probability: "0.6200" },
                  { side: "NO", probability: sideProbability("0.9950", "NO") },
                ]}
                rules={slipRules}
              />
            </Panel>
          </div>
        </Section>

        <Section title={LAB.surface}>
          <div style={grid}>
            <div className="viz-on-surface" style={card} data-panel="">
              <p style={meta}>
                {categoryLabel(q.category)} · {closesOn(q.closes_at, q.as_of)}
              </p>
              <p style={{ ...question, fontSize: 17, margin: "8px 0 16px" }}>{q.question}</p>
              <ChanceReadout yes={live.value} size="card" />
              <div style={{ height: 14 }} />
              <SplitBar yes={live.value} size="sm" />
              <div style={{ height: 18 }} />
              <Sparkline history={q.history} width="100%" height="2.25rem" />
              <div style={{ height: 14 }} />
              {windows.day ? <MoveTrack was={windows.day.was} now={windows.day.now} /> : null}
            </div>
            <div className="viz-on-surface" style={card} data-panel="">
              <MoveWindows day={windows.day} week={windows.week} />
              <div style={{ height: 18 }} />
              {range ? <RangeBar low={range.low} high={range.high} now={range.now} size="large" /> : null}
            </div>
          </div>
        </Section>
      </div>
    </main>
  );
}
