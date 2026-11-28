import { NotOpenYet } from "@/components/NotOpenYet";
import { WhenGameOpen, WhenSignedOut } from "@/components/SignedIn";
import { MainAction, Mark } from "@/components/SiteChrome";
import { ChanceReadout, LineChart, SplitBar } from "@/components/viz";
import { landing } from "@/lib/content";
import { categoryLabel, t } from "@/lib/copy";
import type { GameRules, PublicQuestion } from "@/lib/types";
import { closesOn, priceBand, priceToShow } from "@/lib/viz";

import { payoutFor, sides, stakeShown } from "./figures";
import { PickPair } from "./PickPair";

/**
 * The hero, the kit's split: the words on five columns, and on six the game
 * itself, one open question in its window, read from the market when the page
 * was built, with the slip a pick on it makes. The window stands in a frame
 * whose ground is the page's one effect, the halftone screen, printed once.
 */

// The ground's composition: a lit sphere printed in two inks (the ink and the
// lime), across the frame from the window, still. It shows on the frame's left
// third, where the slip lies, and around the window's edges.
const GROUND = {
  seed: "17",
  params: JSON.stringify({ source: 0, secondInk: 1, drift: 0, cell: 7, size: 1.2, calm: 0, calmX: 0.72, calmY: 0.55 }),
};

function WindowBar({ rules }: { rules: GameRules | null }) {
  return (
    <div className="lp-win__bar">
      <span className="lp-win__brand">
        <Mark />
        {t.appName}
      </span>
      <span className="lp-win__crumb">{t.navQuestionsWord}</span>
      <span className="lp-win__sp" />
      {rules ? <span className="lp-win__balance">{landing.windowPoints(rules.signup_bonus.display)}</span> : null}
    </div>
  );
}

function HeroPicture({ rules, hero }: { rules: GameRules | null; hero: PublicQuestion | null }) {
  if (!hero) {
    return (
      <div className="hero__media span-6 start-7 lp-hero__media">
        <div className="lp-hero__pic" role="img" aria-label={landing.windowEmpty}>
          <div className="stage lp-hero__stage" aria-hidden="true">
            <div className="lp-win ui">
              <WindowBar rules={rules} />
              <p className="lp-win__empty">{landing.windowEmpty}</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Its live price sits inside the game's band (data.ts, `showable`), so the
  // chance, the bar, the picks and the slip below are all one figure.
  const band = priceBand(rules);
  const price = priceToShow(hero, band);
  const choices = sides(price.value, rules);
  const [yes, no] = choices;
  const payout = yes?.pays ? payoutFor(price.value, rules) : null;
  const label =
    landing.windowLabel(hero.question, yes?.chance ?? "", no?.chance ?? "") +
    (payout && yes ? ` ${landing.slipLabel(t.yes, yes.chance, stakeShown, payout)}` : "");

  return (
    <div className="hero__media span-6 start-7 lp-hero__media">
      {/* The page's one effect, the frame's ground (effects-usage.md: in a
          split hero the effect is the picture's frame). Its canvas is put in
          by the kit's script after React has the page (KitLifecycle), so
          React renders the box empty and never looks inside it. */}
      <div
        className="lp-hero__fx"
        data-fx="halftone-screen"
        data-fx-seed={GROUND.seed}
        data-fx-params={GROUND.params}
        aria-hidden="true"
        dangerouslySetInnerHTML={{ __html: "" }}
      />
      {/* A picture of the game, so nothing in it is read out or reached by
          the keyboard: its label says what it shows. The frame crops it. */}
      <div className="lp-hero__pic" role="img" aria-label={label}>
        <div className="stage stage--fade-b lp-hero__stage" aria-hidden="true" inert>
          <div className="lp-win ui">
            <WindowBar rules={rules} />
            <div className="lp-win__open">
              <p className="lp-win__meta">
                {categoryLabel(hero.category)} · {closesOn(hero.closes_at, hero.as_of)}
              </p>
              <p className="lp-win__q">{hero.question}</p>
              <ChanceReadout yes={price.value} size="header" className="lp-win__readout" />
              <SplitBar yes={price.value} size="md" labels={false} className="lp-win__split" />
              <PickPair choices={choices} chosen="YES" className="lp-win__picks" />
              <LineChart question={hero} summary={false} figures={false} band={band} className="lp-win__chart" />
            </div>
          </div>
        </div>
        {payout && yes ? (
          <div className="ly-float lp-slip" aria-hidden="true">
            <div className="ly-float__row">
              <span>{t.slipTitle}</span>
            </div>
            <div className="ly-float__title">{landing.slipPick(t.yes, yes.chance)}</div>
            <div className="lp-slip__line">{landing.windowPoints(stakeShown)}</div>
            <div className="lp-slip__line">{landing.slipPays(payout)}</div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function Hero({ rules, hero }: { rules: GameRules | null; hero: PublicQuestion | null }) {
  return (
    // The kit's motion layer marks the hero and lends its h1 masks while it
    // enters, which may be before React has read them: neither is React's.
    <section className="hero hero--split lp-hero" data-enter="" aria-labelledby="hero-h" suppressHydrationWarning>
      <div className="wrap">
        <div className="hero-text grid hero__grid">
          <div className="hero__text span-5">
            <h1 id="hero-h" suppressHydrationWarning>
              {landing.headline}
            </h1>
            <p className="hero__lead">{landing.lede(rules)}</p>
            <div className="btn-row">
              <MainAction fallback={<NotOpenYet />} />
              <a className="btn btn--secondary" href="/moves">
                {landing.heroSecondary}
              </a>
            </div>
            <WhenGameOpen>
              <WhenSignedOut>
                <p className="lp-hero__note">
                  {landing.heroNote} {t.adultsConfirm}
                </p>
              </WhenSignedOut>
            </WhenGameOpen>
          </div>
          <HeroPicture rules={rules} hero={hero} />
        </div>
      </div>
    </section>
  );
}
