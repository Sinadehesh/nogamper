import "@/components/game/game.css";

import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { AuthForm } from "@/components/AuthForm";
import { AuthAside } from "@/components/game/AuthAside";
import { NotOpenYet } from "@/components/NotOpenYet";
import { SiteFooter, SiteHeader } from "@/components/SiteChrome";
import { t } from "@/lib/copy";
import { nextStep } from "@/lib/next-step";
import { getRules } from "@/lib/server/rules";
import { getMoves } from "@/lib/server/questions";
import { getViewer } from "@/lib/server/viewer";
import { GAME_OPEN } from "@/lib/site";

export const metadata: Metadata = {
  title: t.signInTitle,
  alternates: { canonical: "/login" },
  robots: { index: false, follow: true },
};

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string | string[] }>;
}) {
  if (!GAME_OPEN) {
    return (
      <>
        <SiteHeader />
        <main id="main" className="gm flex-1">
          <div className="wrap">
            <NotOpenYet page />
          </div>
        </main>
        <SiteFooter />
      </>
    );
  }

  const [viewer, params, rules, moves] = await Promise.all([
    getViewer(),
    searchParams,
    getRules(),
    getMoves(),
  ]);
  const next = nextStep(params.next);
  // A registered player who is already signed in has nothing to do here. A
  // guest does: this is how they get back to an account they made earlier.
  if (viewer && !viewer.is_guest) redirect(next);

  return (
    <>
      <SiteHeader quiet />
      <main id="main" className="gm flex-1">
        <div className="wrap dp gm-auth">
          <AuthForm mode="login" next={next} />
          <AuthAside rules={rules} moves={moves} />
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
