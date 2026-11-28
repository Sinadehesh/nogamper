import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { SiteFooter, SiteHeader } from "@/components/SiteChrome";
import { Writer } from "@/components/Writer";
import { t } from "@/lib/copy";
import { getViewer } from "@/lib/server/viewer";

export const metadata: Metadata = {
  title: t.writeTitle,
  robots: { index: false, follow: false },
};

export default async function WritePage() {
  // Somebody who is not signed in is sent to sign in and brought back here,
  // rather than shown an editor whose every button would fail.
  const viewer = await getViewer();
  if (!viewer) redirect("/login?next=/write");

  return (
    <>
      {/* A guest is asked to create an account here, and that is the one
          action on the page: the header offers no game beside it. */}
      <SiteHeader quiet={viewer.is_guest} />
      <main id="main" className="flex-1">
        <div className="wrap dp rd">
          <Writer displayName={viewer.display_name} />
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
