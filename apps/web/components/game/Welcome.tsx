import Link from "next/link";

import { GamePreview } from "@/components/game/Preview";
import { GuestButton } from "@/components/GuestButton";
import { t } from "@/lib/copy";
import type { GameRules, Move } from "@/lib/types";

/**
 * /play for somebody who is not signed in: where the site's main action,
 * "Start playing free", lands. One click starts a guest game; signing in and
 * creating an account sit beside it. Then how it works in three lines, and
 * the age line. Every figure is the live rules'; without them, each sentence
 * has a version without the figure that is still true.
 */
export function Welcome({
  rules,
  preview,
  next = "/play",
}: {
  rules: GameRules | null;
  preview: { move: Move; asOf: string } | null;
  /** Where a new game opens: the game, or the game on the question a page asked for. */
  next?: string;
}) {
  const carried = next === "/play" ? "" : `?next=${encodeURIComponent(next)}`;
  const steps = t.welcomeSteps(
    rules
      ? { min: rules.min_stake.display, max: rules.max_stake.display, legs: rules.max_legs }
      : null,
  );

  return (
    <main id="main" className="gm flex-1">
      <div className={`wrap dp gm-welcome${preview ? "" : " gm-welcome--solo"}`}>
        <div className="gm-welcome__copy">
          <h1>{t.welcomeTitle}</h1>
          <p className="gm-welcome__lede">{t.welcomeLede(rules?.signup_bonus.display ?? null)}</p>

          <div className="gm-start">
            <div className="gm-start__row">
              <GuestButton label={t.navStart} className="btn btn--primary" next={next} />
              <Link href={`/login${carried}`} prefetch={false} className="btn btn--secondary">
                {t.navSignIn}
              </Link>
              <Link href={`/signup${carried}`} prefetch={false} className="gm-link gm-tap">
                {t.navSignUp}
              </Link>
            </div>
            <p className="gm-start__note">{t.welcomeNoSignUp}</p>
            {/* The age line belongs to the button it is about, as on the front page. */}
            <p className="gm-adult">{t.adultsConfirm}</p>
          </div>

          <section aria-labelledby="gm-how" className="grid gap-3">
            <h2 id="gm-how" className="gm-label">
              {t.welcomeStepsTitle}
            </h2>
            <ol className="gm-steps">
              {steps.map((step, index) => (
                <li key={step.title}>
                  <span className="gm-steps__n" aria-hidden>
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <b>{step.title}</b>
                  <p>{step.body}</p>
                </li>
              ))}
            </ol>
          </section>
        </div>

        {preview ? <GamePreview move={preview.move} asOf={preview.asOf} rules={rules} /> : null}
      </div>
    </main>
  );
}
