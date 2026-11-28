"use client";

import { useEffect } from "react";

/**
 * Mounts the kit's ground and moments once React has the page, and takes
 * them down again when a visitor leaves for another page inside the site.
 *
 * The kit binds to the page on load and is not built for a page that comes
 * and goes. A full load of the front page runs everything once. A visit that
 * arrives or leaves by the site's own links does not reload the page, so this
 * does what a load would: mounts the hero's ground and the two moments when
 * the page appears, and frees them (the ground's canvas, the moments'
 * listeners) when it goes.
 *
 * The files are the kit's own, loaded from /assets as they are (never
 * bundled), and each is asked to do exactly what its reference says.
 */

type Controller = { destroy(): void };
type FxModule = {
  default: { get(el: Element): Controller | null };
};
type UiModule = {
  default: { grounds(root: Element, fx: FxModule["default"]): Promise<void> };
};
type MomentsModule = {
  default: { mountAll(root: Document | Element): Promise<unknown>; unmountAll(root: Document | Element): void };
};
type MotionModule = { default: { refresh(): void } };

// The kit's files are served from /assets and imported by the browser as
// they are: the bundler is told to leave these imports alone.
const kit = <T,>(path: string): Promise<T> =>
  import(/* webpackIgnore: true */ /* turbopackIgnore: true */ path) as Promise<T>;

/**
 * The margin statement, read once by a screen reader. The statement moment
 * (word-highlight) wraps each word in a span of its own, hides the spans and
 * names the paragraph with the whole sentence instead, as its library does
 * for any split text. A paragraph takes no name, so the sentence would not be
 * read at all: the words are given back and the name taken away, so the
 * paragraph reads as written. The moment only colours the spans as the page
 * scrolls; it never reads these attributes again.
 */
function readStatementAloud(root: Document) {
  for (const statement of Array.from(root.querySelectorAll(".mo-wh__text"))) {
    if (!statement.querySelector(".mo-w")) continue;
    statement.removeAttribute("aria-label");
    for (const word of Array.from(statement.querySelectorAll(".mo-w"))) word.removeAttribute("aria-hidden");
  }
}

export function KitLifecycle() {
  useEffect(() => {
    const html = document.documentElement;
    let live = true;
    let undo: (() => void) | null = null;

    (async () => {
      try {
        const [fxModule, uiModule, momentsModule, motionModule] = await Promise.all([
          kit<FxModule>("/assets/effects/fx.js"),
          kit<UiModule>("/assets/ui/ui.js"),
          kit<MomentsModule>("/assets/moments/moments.js"),
          kit<MotionModule>("/assets/motion/motion.js"),
        ]);
        if (!live) return;
        const fx = fxModule.default;
        const moments = momentsModule.default;

        // The entrance runs from its own script on a full load; on a visit
        // from inside the site this finds the hero and lets it stand.
        motionModule.default.refresh();

        // The hero's ground: drawn once, kept as a picture, its WebGL
        // context freed (ui.grounds, as system.js does for a still ground).
        const ground = document.querySelector<HTMLElement>(".lp-hero__fx[data-fx]");
        const drawn = ground ? uiModule.default.grounds(ground, fx).catch(() => undefined) : Promise.resolve();
        // The two moments, through their own loader (it mounts each once),
        // then the statement's words given back to screen readers.
        const mounted = moments
          .mountAll(document)
          .then(() => {
            if (live) readStatementAloud(document);
          })
          .catch(() => undefined);

        undo = () => {
          moments.unmountAll(document);
          if (ground) fx.get(ground)?.destroy();
        };
        await Promise.all([drawn, mounted]);
        // The kit's checks wait for this before they look (perf.md).
        if (live) html.dataset.ready = "1";
      } catch (error) {
        console.warn("front page: the kit's scripts did not load", error);
        if (live) html.dataset.ready = "1";
      }
    })();

    return () => {
      live = false;
      undo?.();
      delete html.dataset.ready;
    };
  }, []);

  return null;
}
