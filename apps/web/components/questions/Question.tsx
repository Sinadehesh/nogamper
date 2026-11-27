import "./questions.css";

import { ChanceReadout, MoveScale, MoveTrack, RangeBar, SplitBar } from "@/components/viz";
import { Figure } from "@/components/viz/Figure";
import { questionPage } from "@/lib/content";
import { t, viz } from "@/lib/copy";
import { dateTimeUtc, dateUtc } from "@/lib/format";
import type { PublicQuestion } from "@/lib/types";
import { chanceBand, changeWindows, fromToArrow, inHundred, pct, priceToShow, weekRange } from "@/lib/viz";

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
 */
export function QuestionFigures({ question }: { question: PublicQuestion }) {
  const open = question.state === "open";
  const outcome = outcomeOf(question);
  const shown = priceToShow(question);
  const windows = open ? changeWindows(question) : null;
  const day = windows?.day ? { was: windows.day.was, now: shown.value } : null;
  const week = windows?.week ? { was: windows.week.was, now: shown.value } : null;
  const range = weekRange(question);
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
            <ChanceReadout yes={shown.value} size="card" kind="last" />
          </>
        ) : (
          <>
            <ChanceReadout yes={shown.value} size="header" showNo kind={shown.kind} />
            <SplitBar yes={shown.value} size="lg" labels={false} />
          </>
        )}
      </div>

      {day || week ? (
        <div className="qp-cell dp-panel">
          <h3 id="changes" className="dp-label">
            {questionPage.changesTitle}
          </h3>
          <ChangeLanes day={day} week={week} />
        </div>
      ) : null}

      {range ? (
        <div className="qp-cell dp-panel">
          <h3 className="dp-label">{questionPage.rangeTitle[range.kind]}</h3>
          <RangeBar low={range.low} high={range.high} now={range.now} kind={range.kind} size="large" />
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
function ChangeLanes({ day, week }: { day: Window; week: Window }) {
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
                <Figure text={fromToArrow(lane.window.was, lane.window.now)} />
              </span>
            ) : (
              <span className="qp-lane__none">{lane.none}</span>
            )}
          </p>
          {lane.window ? <MoveTrack was={lane.window.was} now={lane.window.now} /> : null}
        </div>
      ))}
      <MoveScale />
    </div>
  );
}

/** "22 in 100", "fewer than 1 in 100": the chance as a count, from the figure as printed. */
function countOf(probability: number): string {
  const shown = inHundred(probability);
  if (shown === "under1") return questionPage.meaning.fewerThanOne;
  if (shown === "over99") return questionPage.meaning.moreThan99;
  return String(shown);
}

/** The price on the market as a number, for "trades at about 22". */
function priceOf(probability: number): string {
  const shown = inHundred(probability);
  if (shown === "under1") return questionPage.meaning.lessThan("1");
  if (shown === "over99") return questionPage.meaning.moreThan("99");
  return questionPage.meaning.about(String(shown));
}

/**
 * What the number means, for this question: its chance said as a count and
 * in words, then what kind of number it is. Never advice: the words describe
 * where the market stands, not what anyone should do about it.
 */
export function meaningOf(question: PublicQuestion): string[] {
  const shown = priceToShow(question);
  const words = questionPage.meaning;
  const band = words.bands[chanceBand(shown.value)];
  const outcome = outcomeOf(question);
  switch (question.state) {
    case "open":
      return [words.live(countOf(shown.value), band), `${words.contract(priceOf(shown.value))} ${words.estimate}`];
    case "closed":
      return [words.last(countOf(shown.value), band), words.closed];
    case "resolved": {
      const range = weekRange(question);
      if (!outcome) return [words.last(countOf(shown.value), band)];
      return [
        words.resolved(outcomeWord(outcome)),
        ...(range ? [words.resolvedRange(pct(range.low), pct(range.high))] : []),
      ];
    }
    case "void":
      return [words.void];
    case "unfollowed":
      return [words.last(countOf(shown.value), band), words.unfollowed];
  }
}
