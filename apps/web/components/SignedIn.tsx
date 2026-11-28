"use client";

import { useSyncExternalStore } from "react";

import { SIGNED_IN_COOKIE } from "@/lib/session-marker";
import { GAME_OPEN } from "@/lib/site";

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

/** Shown only to somebody who is not signed in. */
export function WhenSignedOut({ children }: { children: React.ReactNode }) {
  return useSignedIn() ? null : <>{children}</>;
}

/** Shown only when there is a game to play. */
export function WhenGameOpen({ children }: { children: React.ReactNode }) {
  return GAME_OPEN ? <>{children}</> : null;
}

/** Shown only to somebody who is signed in. */
export function WhenSignedIn({ children }: { children: React.ReactNode }) {
  return useSignedIn() ? <>{children}</> : null;
}
