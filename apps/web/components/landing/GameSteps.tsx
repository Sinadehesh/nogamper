import { SplitBar } from "@/components/viz";
import { Figure } from "@/components/viz/Figure";
import { landing } from "@/lib/content";
import { categoryLabel, t } from "@/lib/copy";
import { getEditorial } from "@/lib/server/editorial";
import type { GameRules, Move } from "@/lib/types";
import { closesOn, pctDigits, pctHeld, priceBand } from "@/lib/viz";

import { payoutFor, sides, stakeShown, TWO_ON_A_PHONE } from "./figures";
import { PickPair } from "./PickPair";

/**
 * The game in three steps (the kit's steps recipe): pick a question, choose
 * yes or no, stake some points. Each card shows that step in the game's own
 * parts, worked through one real question: the one listed first, the two
 * picks on it, and the slip they make.
 */
export function GameSteps({
  rules,
  step,
  others,
  asOf,
}: {
  rules: GameRules | null;
  step: Move | null;
  others: Move[];
  asOf: string | null;
}) {
  const yes = step ? Number(step.now) : null;
  // The sentence of the second step reads with the figure the card shows,
  // when it is a plain whole percent; otherwise with the guide's 62.
  const whole = yes !== null ? Math.round(yes * 100) : null;
  const sentenceChance =
    yes !== null && whole !== null && pctDigits(yes) === 0 && whole >= 5 && whole <= 95 ? whole : 62;
  const [pickStep, choiceStep, stakeStep] = landing.steps(rules, sentenceChance);
  const choices = yes !== null ? sides(yes, rules) : null;
  const payout = yes !== null && choices?.[0]?.pays ? payoutFor(yes, rules) : null;
  const rows = step ? [step, ...others] : [];
  // A move's "now" is the game's price, held on its band: printed so that
  // it is never false (data.ts keeps these questions 5 points clear anyway).
  const band = priceBand(rules);
  // "a real market" opens the guide to prediction markets, while it exists.
  const intro = landing.gameIntro;
  const introGuide = getEditorial(intro.guide) ? `/articles/${intro.guide}` : null;

  return (
    // Two screens on a phone, where the three steps stack (--hm, layout-v4.md).
    <section className="section lp-game" id="game" aria-labelledby="game-h" style={TWO_ON_A_PHONE}>
      <div className="wrap">
        {/* The heading and its line side by side, on the page's split line
            (the kit's chapter head), so the three steps have the screen. */}
        <div className="grid grid--top lp-head">
          <h2 id="game-h" className="span-5">
            {landing.gameTitle}
          </h2>
          <p className="t-lead span-6 start-7">
            {intro.before}
            {introGuide ? (
              <a className="dp-link" href={introGuide}>
                {intro.link}
              </a>
            ) : (
              intro.link
            )}
            {intro.after}
          </p>
        </div>
        <div className="grid lp-steps">
          <article className="card card--row span-4">
            <span className="step-num">1</span>
            <h3>{pickStep?.title}</h3>
            <p>{pickStep?.body}</p>
            <div className="panel">
              <div className="stage stage--fade-b">
                <div className="at-rise fit lp-at-list">
                  {rows.length ? (
                    <div
                      className="ui lp-frag lp-list"
                      role="img"
                      aria-label={landing.stepListLabel(
                        rows.map((row) => ({ question: row.question, chance: pctHeld(row.now, band) })),
                      )}
                    >
                      <div className="lp-frag__head" aria-hidden="true">
                        <span>{t.navQuestionsWord}</span>
                      </div>
                      {rows.map((row, index) => (
                        <div
                          key={row.slug}
                          className="lp-row"
                          data-on={index === 0 ? "" : undefined}
                          aria-hidden="true"
                        >
                          <span className="lp-row__cat">
                            {categoryLabel(row.category)} · {closesOn(row.closes_at, asOf ?? undefined)}
                          </span>
                          <span className="lp-row__q">{row.question}</span>
                          <Figure className="lp-row__chance" text={pctHeld(row.now, band)} />
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="ui lp-frag lp-frag__empty">{landing.windowEmpty}</p>
                  )}
                </div>
              </div>
            </div>
          </article>

          <article className="card card--row span-4">
            <span className="step-num">2</span>
            <h3>{choiceStep?.title}</h3>
            <p>{choiceStep?.body}</p>
            <div className="panel">
              <div className="stage stage--fade-b">
                <div className="at-corner fit lp-at-picks">
                  {step && choices ? (
                    <div
                      className="ui lp-frag lp-pickcard"
                      role="img"
                      aria-label={landing.stepPickLabel(
                        step.question,
                        choices[0]?.chance ?? "",
                        choices[1]?.chance ?? "",
                        choices[0]?.pays ?? t.settledAlready,
                        choices[1]?.pays ?? t.settledAlready,
                      )}
                    >
                      <span className="lp-pickcard__meta" aria-hidden="true">
                        {categoryLabel(step.category)} · {closesOn(step.closes_at, asOf ?? undefined)}
                      </span>
                      <span className="lp-pickcard__q" aria-hidden="true">
                        {step.question}
                      </span>
                      <SplitBar yes={step.now} size="sm" labels={false} />
                      <PickPair choices={choices} chosen="YES" />
                      <span className="lp-pickcard__note" aria-hidden="true">
                        {t.noMargin}
                      </span>
                    </div>
                  ) : (
                    <p className="ui lp-frag lp-frag__empty">{landing.windowEmpty}</p>
                  )}
                </div>
              </div>
            </div>
          </article>

          <article className="card card--row span-4">
            <span className="step-num">3</span>
            <h3>{stakeStep?.title}</h3>
            <p>{stakeStep?.body}</p>
            <div className="panel">
              <div className="stage stage--fade-b">
                <div className="at-rise fit lp-at-slip">
                  {step && choices && payout ? (
                    <div
                      className="ui lp-frag lp-slipcard"
                      role="img"
                      aria-label={landing.stepSlipLabel(
                        step.question,
                        t.yes,
                        choices[0]?.chance ?? "",
                        stakeShown,
                        payout,
                      )}
                    >
                      <div className="lp-slipcard__head" aria-hidden="true">
                        <span>{t.slipTitle}</span>
                        <span className="lp-muted">{t.slipLegCount(1, rules?.max_legs ?? 1)}</span>
                      </div>
                      <div className="lp-slipcard__pick" aria-hidden="true">
                        <span className="lp-slipcard__q">{step.question}</span>
                        <span className="lp-chip" data-side="yes">
                          {t.yes} <Figure text={choices[0]?.chance ?? ""} />
                        </span>
                      </div>
                      <div className="lp-slipcard__stake" aria-hidden="true">
                        <span className="lp-muted">{t.stake}</span>
                        <span className="lp-field">
                          <Figure text={stakeShown} />
                        </span>
                      </div>
                      <div className="lp-slipcard__win" aria-hidden="true">
                        <span className="lp-muted">{t.toWin}</span>
                        <b>
                          <Figure text={landing.windowPoints(payout)} />
                        </b>
                      </div>
                      <span className="lp-slipcard__go" aria-hidden="true">
                        {t.placeForecast(stakeShown)}
                      </span>
                    </div>
                  ) : (
                    <p className="ui lp-frag lp-frag__empty">{landing.windowEmpty}</p>
                  )}
                </div>
              </div>
            </div>
          </article>
        </div>
      </div>
    </section>
  );
}
