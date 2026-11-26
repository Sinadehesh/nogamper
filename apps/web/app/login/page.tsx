import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { AuthForm } from "@/components/AuthForm";
import { NotOpenYet } from "@/components/NotOpenYet";
import { SiteFooter, SiteHeader } from "@/components/SiteChrome";
import { t } from "@/lib/copy";
import { nextStep } from "@/lib/next-step";
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
        <main id="main" className="container-page flex-1 py-10 sm:py-16">
          <NotOpenYet page />
        </main>
        <SiteFooter />
      </>
    );
  }

  const [viewer, params] = await Promise.all([getViewer(), searchParams]);
  const next = nextStep(params.next);
  // A registered player who is already signed in has nothing to do here. A
  // guest does: this is how they get back to an account they made earlier.
  if (viewer && !viewer.is_guest) redirect(next);

  return (
    <>
      <SiteHeader />
      <main id="main" className="container-page flex-1 py-10 sm:py-16">
        <AuthForm mode="login" next={next} />
      </main>
      <SiteFooter />
    </>
  );
}
