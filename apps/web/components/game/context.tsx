"use client";

import { createContext, useContext, useSyncExternalStore, type ReactNode } from "react";

/**
 * Two small things the game's parts share.
 *
 * Whether the screen is wide enough for the slip to sit beside the feed
 * (the same 1024px where the views move into the top bar), read from the
 * browser: the server, and the first paint, assume a phone, which shows no
 * slip until a pick is made, so nothing moves when the answer arrives.
 *
 * And the public page of each open question, by its wording: the game's
 * feed knows a question by its id, the public pages by their address, and
 * the page that serves the game reads the list of addresses for it.
 */

const WIDE = "(min-width: 1024px)";

function subscribe(onChange: () => void): () => void {
  const query = window.matchMedia(WIDE);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

export function useWide(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => window.matchMedia(WIDE).matches,
    () => false,
  );
}

const Links = createContext<Readonly<Record<string, string>>>({});

export function QuestionLinks({
  links,
  children,
}: {
  links: Readonly<Record<string, string>>;
  children: ReactNode;
}) {
  return <Links.Provider value={links}>{children}</Links.Provider>;
}

/** The address of a question's public page, or null when it has none. */
export function useQuestionPage(question: string): string | null {
  const slug = useContext(Links)[question];
  return slug ? `/questions/${slug}` : null;
}
