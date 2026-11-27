"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import type {
  FocusEvent,
  KeyboardEvent as ReactKeyboardEvent,
  MouseEvent as ReactMouseEvent,
  PointerEvent as ReactPointerEvent,
  ReactNode,
} from "react";

import { useSignedIn } from "@/components/SignedIn";
import { articlesPage, help } from "@/lib/content";
import { t } from "@/lib/copy";
import { GAME_OPEN } from "@/lib/site";

/**
 * The header and footer of every page, in the design kit's own markup and
 * classes (public/assets/system.css): the "nav-cards" header and the
 * "footer-dark" footer.
 *
 * No kit script drives them. The kit's system.js binds to the page once, on
 * load, and does not survive a navigation inside the app, so the header's
 * panel and the phone's sheet run on React state here, with the kit's look
 * and timing (and Escape, which the kit's CSS-only panel cannot honour). The
 * header carries data-m-nav so that motion.js, on the one page that loads
 * it, leaves it alone; system.js has no such switch (see the note on the
 * front page in the redesign's hand-over).
 *
 * Neither reads the request: the pages they sit on are built once and served
 * to everybody. The one thing that differs for a signed-in visitor, the
 * header's button, is decided in the browser from the signed_in marker
 * (useSignedIn), after the signed-out version has been drawn.
 *
 * Links to the front page are plain anchors: it is always reached by a full
 * page load, because its kit scripts bind on load. Every other link is a
 * next/link that does not prefetch, so a header and footer on every page do
 * not fetch every page ahead of a click.
 */

/** The dealt mark: a row of three dots, the middle one lit. */
export function Mark() {
  return <span className="mark" data-mark="dots" aria-hidden="true" />;
}

/** The mark and the name, as the header shows them. */
export function Wordmark({ href = "/" }: { href?: string }) {
  if (href === "/") {
    return (
      <a className="nav__logo" href="/">
        <Mark />
        {t.appName}
      </a>
    );
  }
  return (
    <Link className="nav__logo" href={href} prefetch={false}>
      <Mark />
      {t.appName}
    </Link>
  );
}

/**
 * The site's one main action, worded the same wherever it appears: "Start
 * playing free" for everybody, "Open the game" once the browser knows the
 * visitor is signed in. Where there is no game to open (GAME_OPEN is false),
 * it is not offered at all and `fallback` stands in its place. `children`
 * follow the words (the kit's drawn arrow, svg.m-arrow).
 */
export function MainAction({
  className = "btn btn--primary",
  fallback = null,
  children,
}: {
  className?: string;
  fallback?: ReactNode;
  children?: ReactNode;
}) {
  const signedIn = useSignedIn();
  if (!GAME_OPEN) return <>{fallback}</>;
  return (
    <Link className={className} href="/play" prefetch={false}>
      {signedIn ? t.navOpenGame : t.navStart}
      {children}
    </Link>
  );
}

// ---------------------------------------------------------------------------
// The header
// ---------------------------------------------------------------------------

// `wide`: only in the bar from 1280px (and always in the phone's sheet). A
// small laptop's bar holds the other words, the logo and the button.
type Item = { id: string; href: string; label: string; panel?: boolean; wide?: boolean };

const ITEMS: Item[] = [
  { id: "moves", href: "/moves", label: t.navMoves },
  { id: "questions", href: "/questions", label: t.navQuestionsWord },
  { id: "guides", href: "/articles", label: t.navGuides, panel: true },
  { id: "about", href: "/about", label: t.navAbout },
  { id: "mission", href: "/mission", label: t.navMission, wide: true },
  { id: "help", href: "/help", label: t.navHelpWord },
];

/** The cards in the Guides panel: the three topics the guides page is in. */
const GUIDE_TOPICS = ["prediction-markets", "odds", "stepping-back"] as const;

/** The page's own word is "page"; the word of the section it sits in, "true". */
function currentFor(path: string, href: string): "page" | "true" | undefined {
  if (path === href) return "page";
  if (path.startsWith(`${href}/`)) return "true";
  return undefined;
}

const wideScreen = () => window.matchMedia("(min-width: 1024px)").matches;

function Chevron() {
  return (
    <svg className="chev" viewBox="0 0 12 12" aria-hidden="true">
      <path
        d="M3 4.5l3 3 3-3"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function ExpandIcon() {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true">
      <path
        d="M4 6l4 4 4-4"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function MenuIcon({ open }: { open: boolean }) {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
      <path
        d={open ? "M4 4l10 10M14 4L4 14" : "M2 5h14M2 13h14"}
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
    </svg>
  );
}

/** Sign in and the main action, at the right end of the bar (in the sheet, at its foot). */
function NavActions() {
  const signedIn = useSignedIn();
  return (
    <div className="nav__actions" id="site-nav-actions">
      {GAME_OPEN && !signedIn ? (
        <Link className="nav__link" href="/login" prefetch={false} data-wide-only="">
          {t.navSignIn}
        </Link>
      ) : null}
      <MainAction />
    </div>
  );
}

export function SiteHeader() {
  const path = usePathname() ?? "";
  // The phone's and the tablet's full-screen sheet.
  const [sheet, setSheet] = useState(false);
  // In the sheet: the word whose links are shown under it.
  const [expanded, setExpanded] = useState<string | null>(null);
  // On a wide screen: the word whose panel is open under the bar.
  const [panel, setPanel] = useState<string | null>(null);
  const [seenPath, setSeenPath] = useState(path);
  const header = useRef<HTMLElement>(null);
  const toggle = useRef<HTMLButtonElement>(null);
  const intent = useRef<number | undefined>(undefined);
  // Set while Escape hands the focus back to a word, so that focus does not
  // open the panel it has just closed.
  const quietFocus = useRef(false);

  // A new page closes whatever was open, the browser's back button included.
  if (seenPath !== path) {
    setSeenPath(path);
    setSheet(false);
    setExpanded(null);
    setPanel(null);
  }

  useEffect(() => () => window.clearTimeout(intent.current), []);

  // With the sheet open, the page under it stays still and out of reach of
  // the keyboard and the screen reader, and the keyboard starts in the sheet.
  useEffect(() => {
    if (!sheet) return;
    const bar = header.current;
    const body = document.body;
    const behind = Array.from(body.children).filter(
      (el): el is HTMLElement => el instanceof HTMLElement && el !== bar && !el.inert,
    );
    body.classList.add("nav-locked");
    behind.forEach((el) => {
      el.inert = true;
    });
    bar?.querySelector<HTMLElement>(".nav__links a[href]")?.focus();
    return () => {
      body.classList.remove("nav-locked");
      behind.forEach((el) => {
        el.inert = false;
      });
    };
  }, [sheet]);

  // Escape closes the sheet (the focus goes back to its button) or an open
  // panel (back to its word).
  useEffect(() => {
    if (!sheet && panel === null) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (sheet) {
        setSheet(false);
        setExpanded(null);
        toggle.current?.focus();
        return;
      }
      const word = header.current?.querySelector<HTMLElement>(
        `[data-item="${panel}"] > .nav__link`,
      );
      window.clearTimeout(intent.current);
      setPanel(null);
      if (word && header.current?.contains(document.activeElement)) {
        quietFocus.current = true;
        word.focus();
        quietFocus.current = false;
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [sheet, panel]);

  // Crossing 1024px swaps the sheet for the bar's words, and back.
  useEffect(() => {
    const wide = window.matchMedia("(min-width: 1024px)");
    const onChange = () => {
      if (wide.matches) {
        setSheet(false);
        setExpanded(null);
      } else {
        setPanel(null);
      }
    };
    wide.addEventListener("change", onChange);
    return () => wide.removeEventListener("change", onChange);
  }, []);

  // A panel opens after 150ms of the pointer resting on its word; with one
  // already open, the next word swaps it at once. Leaving closes it.
  const openSoon = (id: string) => {
    window.clearTimeout(intent.current);
    if (panel !== null) {
      setPanel(id);
      return;
    }
    intent.current = window.setTimeout(() => setPanel(id), 150);
  };
  const closeNow = () => {
    window.clearTimeout(intent.current);
    setPanel(null);
  };

  // Any link followed from the bar, the panel or the sheet closes them.
  const closeOnLink = (event: ReactMouseEvent<HTMLElement>) => {
    if (!(event.target instanceof Element) || !event.target.closest("a[href]")) return;
    closeNow();
    setSheet(false);
    setExpanded(null);
  };

  // The open sheet keeps the Tab key inside the header.
  const keepFocusIn = (event: ReactKeyboardEvent<HTMLElement>) => {
    if (!sheet || event.key !== "Tab" || !header.current) return;
    const stops = Array.from(
      header.current.querySelectorAll<HTMLElement>("a[href], button:not([disabled])"),
    ).filter((el) => el.getClientRects().length > 0);
    const first = stops[0];
    const last = stops[stops.length - 1];
    if (!first || !last) return;
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  return (
    <header
      ref={header}
      className={sheet ? "nav is-open" : "nav"}
      data-driver="react"
      data-m-nav="1"
      onKeyDown={keepFocusIn}
      onClick={closeOnLink}
    >
      <div className="wrap nav__bar">
        <Wordmark />
        <nav className="nav__links" id="site-nav-links" aria-label={t.navMainLabel}>
          {ITEMS.map((item) => {
            const open = panel === item.id;
            const shown = expanded === item.id;
            const panelId = `site-nav-panel-${item.id}`;
            const pointer = (event: ReactPointerEvent<HTMLDivElement>) =>
              event.pointerType !== "touch";
            return (
              <div
                key={item.id}
                className={shown ? "nav__item is-expanded" : "nav__item"}
                data-item={item.id}
                data-wide-only={item.wide ? "" : undefined}
                data-open={item.panel && open ? "" : undefined}
                onPointerEnter={(event) => {
                  if (!pointer(event)) return;
                  if (item.panel) openSoon(item.id);
                  else closeNow();
                }}
                onPointerLeave={(event) => {
                  if (item.panel && pointer(event)) closeNow();
                }}
                onFocus={() => {
                  if (!item.panel || quietFocus.current || !wideScreen()) return;
                  window.clearTimeout(intent.current);
                  setPanel(item.id);
                }}
                onBlur={(event: FocusEvent<HTMLDivElement>) => {
                  if (!item.panel) return;
                  const next = event.relatedTarget;
                  if (next instanceof Node && event.currentTarget.contains(next)) return;
                  setPanel((was) => (was === item.id ? null : was));
                }}
              >
                <Link
                  className="nav__link"
                  href={item.href}
                  prefetch={false}
                  aria-current={currentFor(path, item.href)}
                  aria-expanded={item.panel ? open : undefined}
                  aria-controls={item.panel ? panelId : undefined}
                >
                  {item.label}
                  {item.panel ? <Chevron /> : null}
                </Link>
                {item.panel ? (
                  <>
                    <button
                      type="button"
                      className="nav__expand"
                      aria-expanded={shown}
                      aria-controls={panelId}
                      aria-label={t.navShowLinks(item.label)}
                      onClick={() => setExpanded(shown ? null : item.id)}
                    >
                      <ExpandIcon />
                    </button>
                    <div className="nav__menu" id={panelId}>
                      <div className="wrap grid">
                        {GUIDE_TOPICS.map((topic) => (
                          <Link
                            key={topic}
                            className="menu-card span-4"
                            href={`/articles#topic-${topic}`}
                            prefetch={false}
                          >
                            <span className="t-card">{articlesPage.topics[topic].title}</span>
                            <span className="t-small muted">{t.navGuideLines[topic]}</span>
                          </Link>
                        ))}
                      </div>
                    </div>
                  </>
                ) : null}
              </div>
            );
          })}
        </nav>
        <NavActions />
        <button
          ref={toggle}
          type="button"
          className="nav__toggle"
          aria-expanded={sheet}
          aria-controls="site-nav-links site-nav-actions"
          aria-label={t.navMenu}
          onClick={() => {
            setSheet(!sheet);
            setExpanded(null);
          }}
        >
          <MenuIcon open={sheet} />
        </button>
      </div>
    </header>
  );
}

// ---------------------------------------------------------------------------
// The footer
// ---------------------------------------------------------------------------

type FooterGroup = { title: string; links: { href: string; label: string }[] };

const FOOTER: FooterGroup[] = [
  {
    title: t.footerGameTitle,
    links: [
      { href: "/moves", label: t.navMoves },
      { href: "/questions", label: t.navQuestionsWord },
      { href: "/about", label: t.navAbout },
    ],
  },
  {
    title: t.footerLearningTitle,
    links: [
      { href: "/articles", label: t.navGuides },
      {
        href: "/articles#topic-prediction-markets",
        label: articlesPage.topics["prediction-markets"].title,
      },
      { href: "/articles#topic-odds", label: articlesPage.topics.odds.title },
      { href: "/write", label: articlesPage.writeCta },
    ],
  },
  {
    title: t.footerHelpTitle,
    links: [
      { href: "/help", label: t.navHelp },
      { href: "/help#resources", label: help.resourcesTitle },
      { href: "/help#tools", label: t.footerSaferTools },
      {
        href: "/articles#topic-stepping-back",
        label: articlesPage.topics["stepping-back"].title,
      },
    ],
  },
  {
    title: t.footerSiteTitle,
    links: [
      { href: "/mission", label: t.navMission },
      { href: "/support", label: t.navSupport },
      { href: "/support#terms", label: t.footerTerms },
    ],
  },
];

/**
 * The footer: the name set large, the help line, four columns of links, the
 * lines every page must carry (no cash value, adults only, where the prices
 * come from) and the legal row.
 *
 * `close` is the front page's closing row (the kit's close-word: its h2, its
 * button and the name set across the page, with id="close-h" on the h2).
 * Given one, the footer becomes the kit's footer.closing, the close and the
 * links together in the page's last screen. Every other page leaves it out
 * and the footer is as tall as its links.
 */
export function SiteFooter({ close }: { close?: ReactNode }) {
  const year = new Date().getUTCFullYear();
  return (
    <footer
      className={close ? "footer closing footer--dark ground-inverse" : "footer footer--dark ground-inverse"}
      aria-labelledby={close ? "close-h" : undefined}
    >
      <div className="wrap">
        {close}
        <div className="closing__links">
          <nav className="grid" aria-label={t.navFooterLabel}>
            <div className="span-4 footer__brand">
              <a className="nav__logo footer__mark" href="/">
                <Mark />
                {t.appName}
              </a>
              <p className="footer__help">
                {t.footerHelpLine}{" "}
                <Link className="link" href="/help" prefetch={false}>
                  {t.footerHelpLink}
                </Link>
              </p>
            </div>
            {FOOTER.map((group) => (
              <div key={group.title} className="span-2 footer__col">
                <h3>{group.title}</h3>
                <ul>
                  {group.links.map((link) => (
                    <li key={link.href}>
                      <Link href={link.href} prefetch={false}>
                        {link.label}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </nav>
          <div className="footer__notes">
            <p>{t.footerNoValue}</p>
            <p>{t.footerAdults}</p>
            <p>{t.footerNotAffiliated}</p>
          </div>
          <div className="footer__legal">
            <span suppressHydrationWarning>{t.footerCopyright(year)}</span>
            <Link href="/privacy" prefetch={false}>
              {t.navPrivacy}
            </Link>
          </div>
        </div>
      </div>
    </footer>
  );
}
