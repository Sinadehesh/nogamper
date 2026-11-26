import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { AuthForm } from "@/components/AuthForm";
import { SiteFooter, SiteHeader } from "@/components/SiteChrome";
import { t } from "@/lib/copy";
import { getRules } from "@/lib/server/rules";
import { getViewer } from "@/lib/server/viewer";

export const metadata: Metadata = { title: t.signUpTitle };

export default async function SignupPage() {
  const [viewer, rules] = await Promise.all([getViewer(), getRules()]);
  if (viewer && !viewer.is_guest) redirect("/play");

  return (
    <>
      <SiteHeader signedIn={Boolean(viewer)} />
      <main id="main" className="container-page flex-1 py-10 sm:py-16">
        {/* A guest filling in this form keeps the account they have been
            playing on; the page says so, because "create an account" reads
            like starting again. */}
        <AuthForm
          mode={viewer?.is_guest ? "upgrade" : "signup"}
          passwordMin={rules?.password_min_length}
        />
      </main>
      <SiteFooter />
    </>
  );
}
