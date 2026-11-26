import Link from "next/link";

import { t } from "@/lib/copy";

/**
 * What stands in for the game's buttons and forms on a site built without an
 * API behind it (see GAME_OPEN in lib/site.ts).
 *
 * A site can usefully go live as reading matter before the game does. What it
 * must not do is offer a "Start playing" button that can only fail, so every
 * door into the game shows this instead.
 */
export function NotOpenYet({ page = false }: { page?: boolean }) {
  if (page) {
    return (
      <div className="mx-auto max-w-lg text-center">
        <h1 className="text-2xl font-bold tracking-tight">{t.notOpenTitle}</h1>
        <p className="mt-3 text-muted">{t.notOpenBody}</p>
        <Link href="/articles" className="btn btn-primary mt-6">
          {t.notOpenLink}
        </Link>
      </div>
    );
  }
  return (
    <p className="text-sm text-muted">
      {t.notOpenShort}{" "}
      <Link href="/articles" className="font-semibold text-accent underline underline-offset-2">
        {t.notOpenLink}
      </Link>
    </p>
  );
}
