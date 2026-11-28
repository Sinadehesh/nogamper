import { landing } from "@/lib/content";
import { getEditorial } from "@/lib/server/editorial";

/**
 * The questions people ask first, every answer open (the kit's faq). A guide
 * that has been renamed or removed takes its link with it rather than leave
 * one that leads nowhere. On a short screen (a phone, a small laptop) the
 * answer the footer gives on every page, where the chances come from, steps
 * aside, so the rest fit one screen.
 */
export function Faq() {
  const items = landing.faq.map((item) => {
    const link = item.link;
    if (!link) return { ...item, href: null };
    if (link.guide) return { ...item, href: getEditorial(link.guide) ? `/articles/${link.guide}` : null };
    return { ...item, href: link.href ?? null };
  });

  return (
    <section className="section lp-faq" id="questions" aria-labelledby="faq-h">
      <div className="wrap grid grid--top">
        <div className="span-5">
          <h2 id="faq-h">{landing.faqTitle}</h2>
        </div>
        <div className="faq span-6 start-7">
          {items.map((item) => (
            <div key={item.question} className="faq__item" data-spare={item.spare ? "" : undefined}>
              <h3>{item.question}</h3>
              <p>{item.answer}</p>
              {item.link && item.href ? (
                <p>
                  <a className="link" href={item.href}>
                    {item.link.label}
                  </a>
                </p>
              ) : null}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
