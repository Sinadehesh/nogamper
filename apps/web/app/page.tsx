import "./landing.css";

import { JsonLd } from "@/components/JsonLd";
import { Close } from "@/components/landing/Close";
import { frontData } from "@/components/landing/data";
import { Faq } from "@/components/landing/Faq";
import { GameSteps } from "@/components/landing/GameSteps";
import { Hero } from "@/components/landing/Hero";
import { Keeps } from "@/components/landing/Keeps";
import { KitHead, KitTail } from "@/components/landing/KitScripts";
import { Margin } from "@/components/landing/Margin";
import { Moved } from "@/components/landing/Moved";
import { SiteFooter, SiteHeader } from "@/components/SiteChrome";
import { landing } from "@/lib/content";
import { organizationLd, pageMetadata, websiteLd } from "@/lib/seo";
import { keepEarlierCopy } from "@/lib/server/public";

// Kept for five minutes, like the questions it shows, then built again
// behind the next visitor.
export const revalidate = 300;

export const metadata = pageMetadata({
  title: landing.metaTitle,
  description: landing.metaDescription,
  path: "/",
  absoluteTitle: true,
});

/**
 * The front page, built with the design kit (the redesign's brief and
 * public/assets): the hero with the game itself in it, the game in three
 * steps, what keeps it a game, the margin, the questions people ask first,
 * what moved, and the close.
 *
 * It shows live figures: one open question whole in the hero, and the day's
 * moves. When those cannot be read, the running site keeps the copy it last
 * built (dated: the moves carry the time they are from) rather than replace
 * it with a page without them; while the site is being built there is no
 * earlier copy, and every part says plainly what it could not read.
 */
export default async function LandingPage() {
  const data = await frontData();
  if (!data.complete) keepEarlierCopy("The front page's questions");
  const asOf = data.moves?.as_of ?? null;

  return (
    <>
      <JsonLd data={websiteLd()} />
      <JsonLd data={organizationLd()} />
      <KitHead />
      <SiteHeader />

      <main id="main">
        <Hero rules={data.rules} hero={data.hero} />
        <GameSteps rules={data.rules} step={data.step} others={data.others} asOf={asOf} />
        <Keeps rules={data.rules} />
        <Margin rules={data.rules} />
        <Faq />
        <Moved moved={data.moved} asOf={asOf} band={data.band} />
      </main>

      <SiteFooter close={<Close rules={data.rules} />} />
      <KitTail />
    </>
  );
}
