import Link from "next/link";

import { t } from "@/lib/copy";

/**
 * The header and footer of every page that is not the game itself.
 *
 * Server components, both: neither needs to know who is signed in. The header
 * is told whether a session cookie exists so it can offer "Play" rather than
 * "Sign in" — a hint about which link is useful, not a claim that the session
 * is still good.
 */

function Mark() {
  return (
    <svg viewBox="0 0 32 32" className="size-7 shrink-0" aria-hidden>
      <rect width="32" height="32" rx="7" className="fill-accent" />
      <path
        d="M7 21.5 13 14l4.5 4.5L25 9"
        fill="none"
        className="stroke-on-accent"
        strokeWidth="2.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="25" cy="9" r="2.75" className="fill-on-accent" />
    </svg>
  );
}

export function Wordmark({ href = "/" }: { href?: string }) {
  return (
    <Link href={href} className="flex items-center gap-2 text-lg font-bold tracking-tight">
      <Mark />
      <span>{t.appName}</span>
    </Link>
  );
}

export function SiteHeader({ signedIn = false }: { signedIn?: boolean }) {
  return (
    <header className="border-b border-line bg-surface">
      {/* One row on a wide screen: name, links, account. On a phone the links
          drop to a row of their own beneath the other two, which is the only
          arrangement in which nothing wraps mid-phrase. The order in the
          markup is the wide one, so a keyboard and a screen reader meet the
          links before the buttons either way. */}
      <div className="container-page flex flex-wrap items-center gap-x-4 gap-y-2 py-3">
        <Wordmark />
        <nav
          aria-label={t.navLabel}
          className="order-last flex w-full flex-wrap items-center gap-x-4 gap-y-1 text-sm sm:order-none sm:ml-auto sm:w-auto"
        >
          <Link href="/about" className="text-muted hover:text-ink">
            {t.navAbout}
          </Link>
          <Link href="/help" className="text-muted hover:text-ink">
            {t.navHelp}
          </Link>
        </nav>
        <div className="ml-auto flex items-center gap-x-3 text-sm sm:ml-0">
          {signedIn ? (
            <Link href="/play" className="btn btn-primary btn-sm">
              {t.navPlay}
            </Link>
          ) : (
            <>
              <Link href="/login" className="font-semibold hover:text-accent">
                {t.navSignIn}
              </Link>
              <Link href="/signup" className="btn btn-primary btn-sm">
                {t.navSignUp}
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}

export function SiteFooter() {
  return (
    <footer className="mt-auto border-t border-line">
      <div className="container-page space-y-3 py-6 text-xs text-muted">
        <nav className="flex flex-wrap gap-x-5 gap-y-1 text-sm">
          <Link href="/about" className="hover:text-ink">
            {t.navAbout}
          </Link>
          <Link href="/help" className="font-semibold text-ink hover:text-accent">
            {t.navHelp}
          </Link>
        </nav>
        <p>{t.footerNoValue}</p>
        <p>{t.footerNotAffiliated}</p>
        <p>{t.footerAdults}</p>
      </div>
    </footer>
  );
}
