import { NotOpenYet } from "@/components/NotOpenYet";
import { MainAction } from "@/components/SiteChrome";
import { landing } from "@/lib/content";
import { t } from "@/lib/copy";
import type { GameRules } from "@/lib/types";

/**
 * The close (the kit's close-word), row 1 of the footer: the promise once
 * more with one fact, the main action, then the name set across the page.
 * The name is the page's second moment, liquid-type: it ripples under the
 * pointer and stands as written on touch screens and under reduced motion.
 */
export function Close({ rules }: { rules: GameRules | null }) {
  return (
    <div className="closing__cta close--word">
      <div className="section-head--split">
        <div>
          <h2 id="close-h">{landing.closeTitle(rules)}</h2>
          <p className="t-lead">{landing.closeLine}</p>
        </div>
        <MainAction fallback={<NotOpenYet />}>
          <svg className="m-arrow" viewBox="0 0 12 12" aria-hidden="true">
            <path className="m-arrow__stem" d="M1 6h8" />
            <path className="m-arrow__head" d="M4.5 2.5 8 6l-3.5 3.5" />
          </svg>
        </MainAction>
      </div>
      <p className="close__word mo-lt__type lp-close__word" data-moment="liquid-type" aria-hidden="true">
        {t.appName}
      </p>
    </div>
  );
}
