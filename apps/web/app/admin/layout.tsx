import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { AdminNav } from "@/components/admin/AdminNav";
import { StatusBanner } from "@/components/admin/StatusBanner";
import { t } from "@/lib/copy";
import { getViewer } from "@/lib/server/viewer";

export const metadata: Metadata = { title: t.navAdmin, robots: { index: false, follow: false } };

export default async function AdminLayout({ children }: { children: React.ReactNode }) {
  // The same answer the API gives a non-admin: nothing here. The page is not
  // the gate — every admin route on the API checks the allowlist itself — but
  // there is no reason to render the frame of a dashboard for somebody whose
  // every request inside it would 404.
  const viewer = await getViewer();
  if (!viewer?.is_admin) notFound();

  return (
    <>
      <AdminNav />
      <main id="main" className="container-page flex-1 space-y-5 py-5">
        <StatusBanner />
        {children}
      </main>
    </>
  );
}
