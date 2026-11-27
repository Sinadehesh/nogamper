import { Figure } from "@/components/viz/Figure";
import { breakLength, landing } from "@/lib/content";
import { t } from "@/lib/copy";
import { odds, points } from "@/lib/format";
import { fairOdds } from "@/lib/odds";
import type { GameRules } from "@/lib/types";
import { pct } from "@/lib/viz";

import { payoutFor, stakeShown, TWO_ON_A_PHONE } from "./figures";

/** The guide's example: a pick at 62%. Arithmetic, not a market's price. */
const EXAMPLE = 0.62;

/**
 * What keeps it a game: three open tiles, each the game's own control above
 * its promise (the starting balance and the top-up, the fair price with
 * nothing taken, the limit and the break). Open tiles, the picture first,
 * so they read apart from the boxed steps above them.
 */
export function Keeps({ rules }: { rules: GameRules | null }) {
  const keeps = landing.keeps(rules);
  const exampleOdds = odds(fairOdds(EXAMPLE));
  const examplePays = payoutFor(EXAMPLE, rules) ?? points(Math.round(10_000 * fairOdds(EXAMPLE)));
  const lengths = rules ? rules.break_options_hours.map(breakLength) : [];

  return (
    // Two screens on a phone, where the three tiles stack (--hm, layout-v4.md).
    <section className="section lp-keeps" id="keeps" aria-labelledby="keeps-h" style={TWO_ON_A_PHONE}>
      <div className="wrap">
        <div className="section-head">
          <h2 id="keeps-h">{landing.keepsTitle}</h2>
          <p>{landing.keepsIntro(rules)}</p>
          {/* Every rule in full, on the how-it-works page. */}
          <a className="link lp-keeps__rules" href="/about#rules">
            {landing.keepsRules}
          </a>
        </div>
        <div className="grid lp-keeps__grid">
          <article className="card card--open span-4">
            <div className="panel panel--top panel--wide">
              <div className="stage">
                <div className="at-center lp-at-points">
                  <div
                    className="ui lp-frag lp-balance"
                    role="img"
                    aria-label={
                      rules
                        ? landing.pointsLabel(rules.signup_bonus.display, rules.daily_topup.display)
                        : landing.pointsLabelBare
                    }
                  >
                    <span className="lp-muted" aria-hidden="true">
                      {t.balanceLabel}
                    </span>
                    {rules ? <Figure className="lp-balance__fig" text={rules.signup_bonus.display} /> : null}
                    <span className="lp-balance__topup" aria-hidden="true">
                      {rules ? <span>{t.topUpReady(rules.daily_topup.display)}</span> : null}
                      <span className="lp-balance__claim">{t.topUpClaim}</span>
                    </span>
                  </div>
                </div>
              </div>
            </div>
            <h3>{keeps.points.title}</h3>
            <p>{keeps.points.body}</p>
          </article>

          <article className="card card--open span-4">
            <div className="panel panel--top panel--wide">
              <div className="stage">
                <div className="at-corner lp-at-fair">
                  <div
                    className="ui lp-frag lp-fair"
                    role="img"
                    aria-label={landing.fairLabel(pct(EXAMPLE), exampleOdds, stakeShown, examplePays)}
                  >
                    <div className="lp-fair__row" aria-hidden="true">
                      <span>{landing.fairChance}</span>
                      <Figure text={pct(EXAMPLE)} />
                    </div>
                    <div className="lp-fair__row" aria-hidden="true">
                      <span>{landing.fairOdds(String(EXAMPLE))}</span>
                      <Figure text={exampleOdds} />
                    </div>
                    <div className="lp-fair__row" data-zero="" aria-hidden="true">
                      <span>{landing.fairTaken}</span>
                      <Figure text={pct(0)} />
                    </div>
                    <div className="lp-fair__row lp-fair__total" aria-hidden="true">
                      <span>{landing.fairPays(stakeShown)}</span>
                      <Figure text={examplePays} />
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <h3>{keeps.odds.title}</h3>
            <p>{keeps.odds.body}</p>
          </article>

          <article className="card card--open span-4">
            <div className="panel panel--top panel--wide">
              <div className="stage">
                <div className="at-right lp-at-limits">
                  <div className="ui lp-frag lp-limits" role="img" aria-label={landing.limitsLabel(lengths)}>
                    <div className="lp-limits__row" aria-hidden="true">
                      <span>{t.limitTitle}</span>
                      <span className="lp-muted">{t.limitNone}</span>
                    </div>
                    <div className="lp-limits__break" aria-hidden="true">
                      <span>{t.breakTitle}</span>
                      <span className="lp-limits__opts">
                        {lengths.map((length, index) => (
                          <span key={length} className="lp-opt" data-on={index === 1 ? "" : undefined}>
                            {length}
                          </span>
                        ))}
                      </span>
                    </div>
                    <span className="lp-limits__rule" aria-hidden="true">
                      {t.breakRule}
                    </span>
                  </div>
                </div>
              </div>
            </div>
            <h3>{keeps.limits.title}</h3>
            <p>{keeps.limits.body}</p>
          </article>
        </div>
      </div>
    </section>
  );
}
