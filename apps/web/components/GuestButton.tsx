"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { startAsGuest } from "@/lib/api";
import { errorMessage, t } from "@/lib/copy";
import { timeUntil } from "@/lib/format";

/**
 * One click from "what is this" to playing.
 *
 * The point of a guest account is that somebody looking for something to do
 * *instead of* placing a bet should not meet a form first.
 */
export function GuestButton({
  label,
  className = "btn btn-primary",
}: {
  label: string;
  className?: string;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function start() {
    setBusy(true);
    setError(null);
    const result = await startAsGuest();
    if (result.ok) {
      router.push("/play");
      return;
    }
    setBusy(false);
    setError(
      result.code === "rate_limited" && result.retryAfter
        ? t.rateLimited(timeUntil(new Date(Date.now() + result.retryAfter * 1000).toISOString()))
        : errorMessage(result.code),
    );
  }

  return (
    <span className="inline-flex flex-col gap-2">
      <button type="button" className={className} onClick={start} disabled={busy}>
        {busy ? t.working : label}
      </button>
      {error ? (
        <span role="alert" className="text-sm text-danger">
          {error}
        </span>
      ) : null}
    </span>
  );
}
