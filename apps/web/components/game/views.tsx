"use client";

import Link from "next/link";
import type { MouseEvent, ReactNode } from "react";

import { Mark } from "@/components/SiteChrome";
import { t } from "@/lib/copy";
import { TABS, type Tab } from "@/lib/tabs";

/**
 * The game's bar and its five views.
 *
 * The bar is the site's header (the kit's .nav: fixed, one hairline) with
 * the game's own words in it: on a wide screen the five views sit where the
 * site's words would, and on a phone or a tablet they move to a bar along
 * the bottom, where a thumb reaches them. The help line stays in the top bar
 * at every width.
 *
 * The views are links, so a view can be opened in a new tab and a reload
 * lands on it; a plain click changes the view in place without a
 * navigation, which would fetch the whole page again for a change of view.
 */

export const VIEW_LABEL: Record<Tab, string> = {
  markets: t.tabMarkets,
  history: t.tabHistory,
  leaderboard: t.tabLeaderboard,
  safer: t.tabSafer,
  account: t.tabAccount,
};

const VIEW_SHORT: Record<Tab, string> = {
  markets: t.tabMarkets,
  history: t.tabHistoryShort,
  leaderboard: t.tabLeaderboard,
  safer: t.tabSafer,
  account: t.tabAccount,
};

export function viewHref(tab: Tab): string {
  return tab === "markets" ? "/play" : `/play?tab=${tab}`;
}

function ViewLink({
  tab,
  current,
  onView,
  className,
  children,
}: {
  tab: Tab;
  current: boolean;
  onView: (tab: Tab) => void;
  className?: string;
  children: ReactNode;
}) {
  function open(event: MouseEvent<HTMLAnchorElement>) {
    // A new tab or window is the browser's to open.
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    onView(tab);
  }
  return (
    <a
      href={viewHref(tab)}
      className={className}
      aria-current={current ? "page" : undefined}
      onClick={open}
    >
      {children}
    </a>
  );
}

/**
 * The bar. Signed in, `view` and `onView` are given and the views appear;
 * signed out, it offers sign in instead.
 */
export function GameBar({ view = null, onView }: { view?: Tab | null; onView?: (tab: Tab) => void }) {
  return (
    <header className="nav gm-bar gm" data-m-nav="1">
      <div className="wrap nav__bar">
        {/* The front page is reached by a full page load, as everywhere. */}
        <a className="nav__logo" href="/">
          <Mark />
          <span className="gm-bar__name">{t.appName}</span>
        </a>
        {view && onView ? (
          <nav className="gm-views" aria-label={t.viewsLabel}>
            {TABS.map((tab) => (
              <ViewLink key={tab} tab={tab} current={view === tab} onView={onView} className="nav__link">
                {VIEW_LABEL[tab]}
              </ViewLink>
            ))}
          </nav>
        ) : null}
        <div className="gm-bar__end">
          {view ? null : (
            <Link className="nav__link gm-bar__signin" href="/login" prefetch={false}>
              {t.navSignIn}
            </Link>
          )}
          <Link className="nav__link" href="/help" prefetch={false}>
            {t.navHelp}
          </Link>
        </div>
      </div>
    </header>
  );
}

/** The five views along the foot of a phone's or a tablet's screen. */
export function TabBar({ view, onView }: { view: Tab; onView: (tab: Tab) => void }) {
  return (
    <nav className="gm-tabbar gm" aria-label={t.viewsLabel}>
      {TABS.map((tab) => (
        <ViewLink key={tab} tab={tab} current={view === tab} onView={onView}>
          <ViewIcon tab={tab} />
          <span>{VIEW_SHORT[tab]}</span>
        </ViewLink>
      ))}
    </nav>
  );
}

/** One drawn glyph per view, 24 by 24, stroked in the text's colour. */
function ViewIcon({ tab }: { tab: Tab }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      {tab === "markets" ? (
        <>
          <rect x="3" y="4" width="18" height="7" rx="3.5" />
          <rect x="3" y="13" width="18" height="7" rx="3.5" />
          <path d="M12 4v7M12 13v7" />
        </>
      ) : tab === "history" ? (
        <>
          <path d="M6 3h12v18l-3-2-3 2-3-2-3 2z" />
          <path d="M9 8h6M9 12h6" />
        </>
      ) : tab === "leaderboard" ? (
        <>
          <path d="M4 20V13h5v7M9.5 20V8h5v12M15 20v-9h5v9" />
        </>
      ) : tab === "safer" ? (
        <>
          <path d="M12 3l7 3v5c0 4.5-3 8.2-7 10-4-1.8-7-5.5-7-10V6z" />
          <path d="M10 9.5v5M14 9.5v5" />
        </>
      ) : (
        <>
          <circle cx="12" cy="8.5" r="3.5" />
          <path d="M5 20c.8-3.6 3.6-5.5 7-5.5s6.2 1.9 7 5.5" />
        </>
      )}
    </svg>
  );
}
