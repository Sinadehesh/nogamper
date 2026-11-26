import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { AuthForm } from "@/components/AuthForm";
import { SiteFooter, SiteHeader } from "@/components/SiteChrome";
import { t } from "@/lib/copy";
import { getViewer } from "@/lib/server/viewer";

export const metadata: Metadata = { title: t.signInTitle };

export default async function LoginPage() {
  const viewer = await getViewer();
  // A registered player who is already signed in has nothing to do here. A
  // guest does: this is how they get back to an account they made earlier.
  if (viewer && !viewer.is_guest) redirect("/play");

  return (
    <>
      <SiteHeader />
      <main id="main" className="container-page flex-1 py-10 sm:py-16">
        <AuthForm mode="login" />
      </main>
      <SiteFooter />
    </>
  );
}
