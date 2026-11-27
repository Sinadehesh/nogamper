import { preloadModule } from "react-dom";

import { KitLifecycle } from "./KitLifecycle";

/**
 * The design kit's scripts, on this page only (the brief, decision 5). The
 * kit binds to the page once, on load: so the front page is the one page
 * that loads it, as plain files from /assets.
 *
 * Not system.js: it binds the first `.nav` on the page with no way to opt
 * out, and the header is React's (components/SiteChrome.tsx). What this page
 * needs of the kit is loaded on its own, each part as its reference says:
 * the motion layer (motion.md), the halftone ground (effects-usage.md: drawn
 * once and kept as a picture, as system.js does with a still ground) and the
 * two moments (moments.md, through their loader).
 */

// The head lines the kit asks for before the first paint: the hero's words
// wait for the motion layer (700ms at most, motion.md), and the moments know
// script is running (2.5 s at most before everything shows, moments.md).
const ENTER =
  "document.documentElement.classList.add('m-enter');setTimeout(()=>document.documentElement.classList.add('m-enter-done'),700)";
const MOMENTS =
  "document.documentElement.classList.add('mo-js');setTimeout(()=>document.documentElement.classList.add('mo-safe'),2500)";

const MODULES = [
  "/assets/motion/motion.js",
  "/assets/moments/moments.js",
  "/assets/moments/lib.js",
  "/assets/moments/word-highlight/moment.js",
  "/assets/moments/liquid-type/moment.js",
  "/assets/effects/fx.js",
  "/assets/effects/halftone-screen/effect.js",
  "/assets/ui/ui.js",
];

/** Before the hero: the two head lines. */
export function KitHead() {
  for (const href of MODULES) preloadModule(href);
  return (
    <>
      <script dangerouslySetInnerHTML={{ __html: ENTER }} />
      <script dangerouslySetInnerHTML={{ __html: MOMENTS }} />
    </>
  );
}

/**
 * After the page: the motion layer as its own file, so the hero's entrance
 * starts as soon as the page is read; then the rest once React has taken
 * the page over (KitLifecycle), so nothing the kit adds is in React's way.
 */
export function KitTail() {
  return (
    <>
      <script type="module" src="/assets/motion/motion.js" />
      <KitLifecycle />
    </>
  );
}
