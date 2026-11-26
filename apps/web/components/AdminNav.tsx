"use client";


import { usePathname } from "next/navigation";

const PAGES = [
  { href: "/admin", label: "Economy" },
  { href: "/admin/players", label: "Players" },
  { href: "/admin/messages", label: "Messages" },
] as const;

export function AdminNav({ note }: { note?: string }) {
  const pathname = usePathname();

  return (
    <nav className="admin-nav" aria-label="Admin">
      {/* A plain link rather than history.back(): the admin pages are often
       *  opened from a deep link or after a reload, where there is no history
       *  to go back through and the button would do nothing. */}
      {/* No aria-label: the visible text is the accessible name, so a screen
       *  reader and a sighted user hear and read the same thing. */}
      <a className="admin-back" href="/">
        ← App
      </a>

      <div className="admin-tabs">
        {PAGES.map((page) => (
          <a
            key={page.href}
            href={page.href}
            aria-current={pathname === page.href ? "page" : undefined}
            className={pathname === page.href ? "is-on" : ""}
          >
            {page.label}
          </a>
        ))}
      </div>

      {note ? <span className="admin-nav-note">{note}</span> : null}
    </nav>
  );
}
