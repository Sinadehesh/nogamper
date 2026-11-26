import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { AuthForm } from "@/components/AuthForm";
import { NotOpenYet } from "@/components/NotOpenYet";
import { SiteFooter, SiteHeader } from "@/components/SiteChrome";
import { t } from "@/lib/copy";
import { nextStep } from "@/lib/next-step";
import { getRules } from "@/lib/server/rules";
import { getViewer } from "@/lib/server/viewer";
import { GAME_OPEN } from "@/lib/site";

export const metadata: Metadata = {
  title: t.signUpTitle,
  alternates: { canonical: "/signup" },
  robots: { index: false, follow: true },
};

export default async function SignupPage({
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

  const [viewer, rules, params] = await Promise.all([getViewer(), getRules(), searchParams]);
  const next = nextStep(params.next);
  if (viewer && !viewer.is_guest) redirect(next);

  return (
    <>
      <SiteHeader />
      <main id="main" className="container-page flex-1 py-10 sm:py-16">
        {/* A guest filling in this form keeps the account they have been
            playing on; the page says so, because "create an account" reads
            like starting again. */}
        <AuthForm
          mode={viewer?.is_guest ? "upgrade" : "signup"}
          passwordMin={rules?.password_min_length}
          next={next}
        />
      </main>
      <SiteFooter />
    </>
  );
}
