import { ReadingLayout } from "@/components/reading/ReadingLayout";
import { SiteFooter, SiteHeader } from "@/components/SiteChrome";
import { PRIVACY_UPDATED, privacy } from "@/lib/content";
import { calendarDate } from "@/lib/format";
import { pageMetadata } from "@/lib/seo";

export const metadata = pageMetadata({
  title: privacy.metaTitle,
  description: privacy.metaDescription,
  path: "/privacy",
});

/**
 * What the site stores and why, as a short document with its own index: the
 * sections listed beside the text on a laptop, in a line that opens on a
 * phone. The date it was last changed is a calendar date, printed in UTC.
 */
export default function PrivacyPage() {
  const entries = privacy.sections.map((section) => ({ id: section.id, text: section.title }));

  return (
    <>
      <SiteHeader />

      <main id="main" className="flex-1">
        <div className="wrap dp rd">
          <ReadingLayout
            label={privacy.indexLabel}
            count={privacy.indexCount(entries.length)}
            entries={entries}
            head={
              <>
                <h1 className="rd-title">{privacy.title}</h1>
                <p className="dp-lede">{privacy.lede}</p>
                <p className="rd-byline">
                  <time dateTime={PRIVACY_UPDATED}>{privacy.updated(calendarDate(PRIVACY_UPDATED))}</time>
                </p>
              </>
            }
          >
            <div className="rd-doc">
              {privacy.sections.map((section) => (
                <section key={section.id} aria-labelledby={section.id}>
                  <h2 id={section.id}>{section.title}</h2>
                  <div className="rd-text">
                    {section.body.map((paragraph) => (
                      <p key={paragraph.slice(0, 24)}>{paragraph}</p>
                    ))}
                  </div>
                </section>
              ))}
            </div>
          </ReadingLayout>
        </div>
      </main>

      <SiteFooter />
    </>
  );
}
