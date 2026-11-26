import { SiteFooter, SiteHeader } from "@/components/SiteChrome";
import { PRIVACY_UPDATED, privacy } from "@/lib/content";
import { date } from "@/lib/format";
import { pageMetadata } from "@/lib/seo";

export const metadata = pageMetadata({
  title: privacy.metaTitle,
  description: privacy.metaDescription,
  path: "/privacy",
});

export default function PrivacyPage() {
  return (
    <>
      <SiteHeader />

      <main id="main" className="container-page flex-1 py-10 sm:py-14">
        <div className="max-w-2xl">
          <h1 className="text-4xl font-black tracking-tight">{privacy.title}</h1>
          <p className="mt-4 text-lg text-muted">{privacy.lede}</p>
          <p className="mt-3 text-sm text-muted">
            {privacy.updatedLabel}: <time dateTime={PRIVACY_UPDATED}>{date(PRIVACY_UPDATED)}</time>
          </p>

          {privacy.sections.map((section) => (
            <section key={section.title} className="mt-9">
              <h2 className="text-xl font-bold tracking-tight">{section.title}</h2>
              <div className="prose-block mt-3 text-muted">
                {section.body.map((paragraph) => (
                  <p key={paragraph.slice(0, 24)}>{paragraph}</p>
                ))}
              </div>
            </section>
          ))}
        </div>
      </main>

      <SiteFooter />
    </>
  );
}
