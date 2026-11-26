"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useId, useState, type FormEvent } from "react";

import { GuestButton } from "@/components/GuestButton";
import { register, signIn, type ApiFailure } from "@/lib/api";
import { errorMessage, t } from "@/lib/copy";
import { timeUntil } from "@/lib/format";

type Mode = "login" | "signup" | "upgrade";

const HEADINGS: Record<Mode, { title: string; intro: string; submit: string }> = {
  login: { title: t.signInTitle, intro: t.signInIntro, submit: t.submitSignIn },
  signup: { title: t.signUpTitle, intro: t.signUpIntro, submit: t.submitSignUp },
  upgrade: { title: t.upgradeTitle, intro: t.upgradeIntro, submit: t.submitUpgrade },
};

function describe(failure: ApiFailure): string {
  if (failure.code === "rate_limited" && failure.retryAfter) {
    const reopens = new Date(Date.now() + failure.retryAfter * 1000).toISOString();
    return t.rateLimited(timeUntil(reopens));
  }
  return errorMessage(failure.code);
}

export function AuthForm({
  mode,
  passwordMin = 10,
  next = "/play",
}: {
  mode: Mode;
  passwordMin?: number;
  /** Where to go afterwards. Chosen by the page from a fixed list, never
      taken from the address bar as it stands. */
  next?: string;
}) {
  const router = useRouter();
  const carried = next === "/play" ? "" : `?next=${encodeURIComponent(next)}`;
  const ids = { name: useId(), email: useId(), password: useId(), error: useId() };

  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [reveal, setReveal] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const creating = mode !== "login";
  const heading = HEADINGS[mode];

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);

    const result = creating
      ? await register({ email, password, display_name: displayName })
      : await signIn(email, password);

    if (result.ok) {
      router.push(next);
      router.refresh();
      return;
    }
    setBusy(false);
    setError(describe(result));
  }

  return (
    <div className="mx-auto w-full max-w-md">
      <h1 className="text-3xl font-black tracking-tight">{heading.title}</h1>
      <p className="mt-2 text-muted">{heading.intro}</p>

      <form onSubmit={submit} className="card mt-6 space-y-4 p-5" noValidate>
        {creating ? (
          <div>
            <label htmlFor={ids.name} className="label">
              {t.fieldDisplayName}
            </label>
            <input
              id={ids.name}
              className="field"
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              autoComplete="nickname"
              maxLength={24}
              required
            />
            <p className="hint">{t.fieldDisplayNameHint}</p>
          </div>
        ) : null}

        <div>
          <label htmlFor={ids.email} className="label">
            {t.fieldEmail}
          </label>
          <input
            id={ids.email}
            className="field"
            type="email"
            inputMode="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            autoComplete="email"
            autoCapitalize="none"
            spellCheck={false}
            required
          />
          {creating ? <p className="hint">{t.fieldEmailHint}</p> : null}
        </div>

        <div>
          <div className="flex items-baseline justify-between">
            <label htmlFor={ids.password} className="label">
              {t.fieldPassword}
            </label>
            <button
              type="button"
              className="text-xs font-semibold text-accent"
              onClick={() => setReveal((shown) => !shown)}
              aria-pressed={reveal}
            >
              {reveal ? t.hidePassword : t.showPassword}
            </button>
          </div>
          <input
            id={ids.password}
            className="field"
            type={reveal ? "text" : "password"}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete={creating ? "new-password" : "current-password"}
            aria-invalid={error ? true : undefined}
            aria-describedby={error ? ids.error : undefined}
            required
          />
          {creating ? <p className="hint">{t.fieldPasswordHint(passwordMin)}</p> : null}
        </div>

        {error ? (
          <p id={ids.error} role="alert" className="notice notice-error">
            {error}
          </p>
        ) : null}

        <button type="submit" className="btn btn-primary w-full" disabled={busy}>
          {busy ? t.working : heading.submit}
        </button>

        {creating ? <p className="hint">{t.noResetNote}</p> : null}
      </form>

      <p className="mt-5 text-sm text-muted">
        {mode === "login" ? t.needAccount : t.haveAccount}{" "}
        <Link
          href={`${mode === "login" ? "/signup" : "/login"}${carried}`}
          className="font-semibold text-accent underline underline-offset-2"
        >
          {mode === "login" ? t.navSignUp : t.navSignIn}
        </Link>
      </p>

      {mode === "upgrade" ? null : (
        <div className="mt-6 border-t border-line pt-5">
          <p className="text-sm text-muted">{t.orGuest}</p>
          <div className="mt-2">
            <GuestButton label={t.playAsGuest} className="btn btn-secondary" />
          </div>
          <p className="hint">{t.guestExplainer}</p>
        </div>
      )}

      <p className="mt-6 text-xs text-muted">{t.adultsConfirm}</p>
    </div>
  );
}
