"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { t } from "@/lib/copy";

const LINKS = [
  { href: "/admin", label: t.adminOverview },
  { href: "/admin/players", label: t.adminPlayers },
  { href: "/admin/messages", label: t.adminInbox },
  { href: "/admin/articles", label: t.adminArticles },
];

export function AdminNav() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-20 border-b border-line bg-surface">
      <div className="container-page flex flex-wrap items-center gap-x-4 gap-y-1 py-2 text-sm">
        <Link href="/play" className="inline-flex min-h-11 items-center font-semibold text-muted hover:text-ink">
          {t.adminBack}
        </Link>
        <nav className="flex flex-wrap gap-1">
          {LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              aria-current={pathname === link.href ? "page" : undefined}
              className={`inline-flex min-h-11 items-center rounded-full px-3.5 font-semibold ${
                pathname === link.href ? "bg-accent text-on-accent" : "text-muted hover:text-ink"
              }`}
            >
              {link.label}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  );
}
