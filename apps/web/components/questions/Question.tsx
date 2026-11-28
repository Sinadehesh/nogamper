import "./questions.css";

import { ChanceReadout, MoveScale, MoveTrack, RangeBar, SplitBar } from "@/components/viz";
import { Figure } from "@/components/viz/Figure";
import { questionPage } from "@/lib/content";
import { t, viz } from "@/lib/copy";
import { dateTimeUtc, dateUtc } from "@/lib/format";
import type { PublicQuestion } from "@/lib/types";
import {
  bandPercent,
  chanceBand,
  changeWindows,
  fromToArrow,
  GAME_BAND,
  inHundred,
  onEdge,
  type PriceBand,
  type PriceReading,
  pct,
  pctHeld,
  priceToShow,
  weekRange,
} from "@/lib/viz";

/** Yes or No, for a question resolved one way or the other; null otherwise. */
export function outcomeOf(question: PublicQuestion): "yes" | "no" | null {
  return question.state === "resolved" && (question.outcome === "yes" || question.outcome === "no")
    ? question.outcome
    : null;
}

export function outcomeWord(outcome: "yes" | "no"): string {
  return outcome === "yes" ? t.yes : t.no;
}

/**
 * The state in a word, and beside it the sentence that dates it: set apart
 * from the line that dates the figures, because it is the thing a reader
 * needs first ("Open. Forecasts close on …").
 */
export function StateLine({ question, readAt }: { question: PublicQuestion; readAt: string }) {
  const outcome = outcomeOf(question);
  let word: string;
  let detail: string;
  switch (question.state) {
    case "open":
      word = questionPage.stateWords.open;
      detail = questionPage.states.open(dateTimeUtc(question.closes_at));
      break;
    case "closed":
      word = questionPage.stateWords.closed;
      detail = questionPage.states.closed(dateUtc(question.closes_at));
      break;
    case "resolved":
      word = outcome ? questionPage.stateWords.resolved(outcomeWord(outcome)) : questionPage.stateWords.closed;
      detail = questionPage.states.resolved(dateUtc(question.resolved_at ?? question.ends_at));
      break;
    case "void":
      word = questionPage.stateWords.void;
      detail = questionPage.states.void;
      break;
    case "unfollowed":
      word = questionPage.stateWords.unfollowed;
      detail = questionPage.states.unfollowed(dateUtc(readAt));
      break;
  }
  return (
    <p className="qp-state">
      <span className="qp-badge" data-state={question.state} data-outcome={outcome ?? undefined}>
        {word}
      </span>
      <span>{detail}</span>
    </p>
  );
}

/**
 * What the market says, in three blocks: the chance (or, once resolved, the
 * answer), how it has changed, and the week's range. For a question that is
 * no longer open the price is its history's last, never `probability`, which
 * is what the site stored when it stopped reading and can contradict the
 * chart (map 4.1). Changes are for open questions only: a finished one's
 * were read before it closed, so "a day ago" would no longer be true.
 *
 * Every figure is built on `priceToShow`, so where the API holds the live
 * price on the game's band (`band`, from the rules) they all show the
 * market's own reading together, or, with none, the held price as a bound.
 */
export function QuestionFigures({ question, band = GAME_BAND }: { question: PublicQuestion; band?: PriceBand }) {
  const open = question.state === "open";
  const outcome = outcomeOf(question);
  const shown = priceToShow(question, band);
  const held = shown.held ? band : undefined;
  const windows = open ? changeWindows(question) : null;
  const day = windows?.day ? { was: windows.day.was, now: shown.value } : null;
  const week = windows?.week ? { was: windows.week.was, now: shown.value } : null;
  const range = weekRange(question, band);
  const cells = 1 + (day || week ? 1 : 0) + (range ? 1 : 0);

  return (
    <section className="qp-figures" aria-labelledby="now" data-cells={cells}>
      <div className="qp-cell qp-cell--lead dp-panel">
        <h2 id="now" className="dp-label">
          {outcome ? t.resolvedLabel : open ? t.marketSays : questionPage.lastPrice}
        </h2>
        {outcome ? (
          <>
            <p className="qp-outcome" data-outcome={outcome}>
              <span className="qp-outcome__word">{outcomeWord(outcome)}</span>
              <span className="qp-outcome__words">{questionPage.answerWord}</span>
            </p>
            <ChanceReadout yes={shown.value} size="card" kind="last" held={held} />
          </>
        ) : (
          <>
            <ChanceReadout yes={shown.value} size="header" showNo kind={shown.kind} held={held} />
            <SplitBar yes={shown.value} size="lg" labels={false} held={held} />
          </>
        )}
      </div>

      {day || week ? (
        <div className="qp-cell dp-panel">
          <h3 id="changes" className="dp-label">
            {questionPage.changesTitle}
          </h3>
          <ChangeLanes day={day} week={week} held={held} />
        </div>
      ) : null}

      {range ? (
        <div className="qp-cell dp-panel">
          <h3 className="dp-label">{questionPage.rangeTitle[range.kind]}</h3>
          <RangeBar
            low={range.low}
            high={range.high}
            now={range.now}
            kind={range.kind}
            size="large"
            held={range.held ? band : undefined}
          />
        </div>
      ) : null}
    </section>
  );
}

type Window = { was: number; now: number } | null;

/**
 * The day and the week, each a line of figures over its own track, on one
 * scale so the two arrows end at the same "now" and compare by length. The
 * figures are said once, in the line; the track shows size and direction and
 * tells a screen reader the change in words.
 */
function ChangeLanes({ day, week, held }: { day: Window; week: Window; held?: PriceBand }) {
  const lanes = [
    { key: "day", word: questionPage.windows.day, window: day, none: viz.noDay },
    { key: "week", word: questionPage.windows.week, window: week, none: viz.noWeek },
  ];
  return (
    <div className="qp-lanes">
      {lanes.map((lane) => (
        <div key={lane.key} className="qp-lane">
          <p className="qp-lane__line">
            <span className="qp-lane__word">{lane.word}</span>
            {lane.window ? (
              <span className="qp-lane__fig" aria-hidden="true">
                <Figure text={fromToArrow(lane.window.was, lane.window.now, held)} />
              </span>
            ) : (
              <span className="qp-lane__none">{lane.none}</span>
            )}
          </p>
          {lane.window ? <MoveTrack was={lane.window.was} now={lane.window.now} held={held} /> : null}
        </div>
      ))}
      <MoveScale />
    </div>
  );
}

/** A held price's bound as a count, and its side: "1" at the floor, "99" at the ceiling. */
function heldCount(shown: PriceReading, band: PriceBand): { edge: "min" | "max"; count: string } | null {
  const edge = shown.held ? onEdge(shown.value, band) : null;
  if (!edge) return null;
  return { edge, count: bandPercent(edge === "min" ? band.min : band.max).replace("%", "") };
}

/**
 * "22 in 100", "fewer than 1 in 100": the chance as a count, from the figure
 * as printed. A held price says "at most 1 in 100", which is all it knows.
 */
function countOf(shown: PriceReading, band: PriceBand): string {
  const held = heldCount(shown, band);
  if (held) return held.edge === "min" ? questionPage.meaning.atMost(held.count) : questionPage.meaning.atLeast(held.count);
  const count = inHundred(shown.value);
  if (count === "under1") return questionPage.meaning.fewerThanOne;
  if (count === "over99") return questionPage.meaning.moreThan99;
  return String(count);
}

/** The price on the market as a number, for "trades at about 22", or "1 or less" for a held one. */
function priceOf(shown: PriceReading, band: PriceBand): string {
  const held = heldCount(shown, band);
  if (held) return held.edge === "min" ? questionPage.meaning.orLess(held.count) : questionPage.meaning.orMore(held.count);
  const count = inHundred(shown.value);
  if (count === "under1") return questionPage.meaning.lessThan("1");
  if (count === "over99") return questionPage.meaning.moreThan("99");
  return questionPage.meaning.about(String(count));
}

/**
 * What the number means, for this question: its chance said as a count and
 * in words, then what kind of number it is. Never advice: the words describe
 * where the market stands, not what anyone should do about it. Said of the
 * figure the page leads with (`priceToShow`), so the words and the readout
 * above them always describe the same number.
 */
export function meaningOf(question: PublicQuestion, priceBand: PriceBand = GAME_BAND): string[] {
  const shown = priceToShow(question, priceBand);
  const words = questionPage.meaning;
  const band = words.bands[chanceBand(shown.value)];
  const outcome = outcomeOf(question);
  const count = countOf(shown, priceBand);
  switch (question.state) {
    case "open":
      return [words.live(count, band), `${words.contract(priceOf(shown, priceBand))} ${words.estimate}`];
    case "closed":
      return [words.last(count, band), words.closed];
    case "resolved": {
      const range = weekRange(question, priceBand);
      const figure = (value: number) => (range?.held ? pctHeld(value, priceBand) : pct(value));
      if (!outcome) return [words.last(count, band)];
      return [
        words.resolved(outcomeWord(outcome)),
        ...(range ? [words.resolvedRange(figure(range.low), figure(range.high))] : []),
      ];
    }
    case "void":
      return [words.void];
    case "unfollowed":
      return [words.last(count, band), words.unfollowed];
  }
}
