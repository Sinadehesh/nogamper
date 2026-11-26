"use client";

import Link from "next/link";
import { useSyncExternalStore } from "react";

import { GuestButton } from "@/components/GuestButton";
import { landing } from "@/lib/content";
import { t } from "@/lib/copy";
import { SIGNED_IN_COOKIE } from "@/lib/session-marker";

/**
 * The few places a public page changes for somebody who is signed in.
 *
 * Decided in the browser, from a marker cookie, so the page around them can
 * be built once and cached. The server always renders the signed-out version
 * — which is also the right one for a crawler — and a signed-in visitor sees
 * it swap a moment after the page loads.
 */

function readMarker(): boolean {
  return document.cookie.split("; ").includes(`${SIGNED_IN_COOKIE}=1`);
}

// Returning to a tab is when the answer may have changed: signed in or out
// in another one.
function subscribe(onChange: () => void): () => void {
  window.addEventListener("focus", onChange);
  return () => window.removeEventListener("focus", onChange);
}

export function useSignedIn(): boolean {
  return useSyncExternalStore(subscribe, readMarker, () => false);
}

/** The right-hand end of the site header. */
export function AccountLinks() {
  const signedIn = useSignedIn();

  if (signedIn) {
    return (
      <Link href="/play" className="btn btn-primary btn-sm">
        {t.navPlay}
      </Link>
    );
  }
  return (
    <>
      <Link href="/login" className="font-semibold hover:text-accent">
        {t.navSignIn}
      </Link>
      <Link href="/signup" className="btn btn-primary btn-sm">
        {t.navSignUp}
      </Link>
    </>
  );
}

/** The buttons under a headline: start playing, or carry on. */
export function StartActions({ secondary = true }: { secondary?: boolean }) {
  const signedIn = useSignedIn();

  if (signedIn) {
    return (
      <Link href="/play" className="btn btn-primary">
        {landing.ctaContinue}
      </Link>
    );
  }
  return (
    <>
      <GuestButton label={landing.ctaGuest} />
      {secondary ? (
        <Link href="/signup" className="btn btn-secondary">
          {landing.ctaSignUp}
        </Link>
      ) : null}
    </>
  );
}

/** Shown only to somebody who is not signed in. */
export function WhenSignedOut({ children }: { children: React.ReactNode }) {
  return useSignedIn() ? null : <>{children}</>;
}

/** Shown only to somebody who is signed in. */
export function WhenSignedIn({ children }: { children: React.ReactNode }) {
  return useSignedIn() ? <>{children}</> : null;
}
