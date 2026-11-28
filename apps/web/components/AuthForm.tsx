"use client";

import "@/components/game/game.css";

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

/** Which field an error is about, so it can be said under that field. */
type Field = "name" | "email" | "password" | "form";

function fieldOf(code: string): Field {
  switch (code) {
    case "invalid_display_name":
      return "name";
    case "email_taken":
    case "invalid_email":
      return "email";
    case "invalid_credentials":
    case "password_too_short":
    case "password_too_long":
    case "password_too_common":
    case "not_registered":
      return "password";
    default:
      return "form";
  }
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
  const ids = {
    name: useId(),
    email: useId(),
    password: useId(),
    nameHint: useId(),
    emailHint: useId(),
    passwordHint: useId(),
    error: useId(),
  };

  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [reveal, setReveal] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ field: Field; text: string } | null>(null);

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
    setError({ field: fieldOf(result.code), text: describe(result) });
  }

  /** The error under one field, or nothing. */
  const errorFor = (field: Field) =>
    error?.field === field ? (
      <p id={ids.error} role="alert" className="gm-error">
        {error.text}
      </p>
    ) : null;
  const describedBy = (field: Field, hint?: string) =>
    [error?.field === field ? ids.error : null, hint].filter(Boolean).join(" ") || undefined;

  const guest =
    mode === "upgrade"
      ? null
      : (place: "before" | "after") => (
          <div className="gm-guest" data-place={place}>
            <p className="gm-h gm-h--sm">{t.guestOptionTitle}</p>
            <p className="gm-small">{t.guestOptionBody}</p>
            <GuestButton label={t.navStart} className="btn btn--secondary" />
          </div>
        );

  return (
    <div className="gm-auth__main">
      <header className="gm-auth__head">
        <h1>{heading.title}</h1>
        <p className="dp-lede">{heading.intro}</p>
      </header>

      {guest?.("before")}

      <form onSubmit={submit} className="gm-panel gm-form" noValidate>
        {creating ? (
          <div className="gm-field">
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
              aria-invalid={error?.field === "name" ? true : undefined}
              aria-describedby={describedBy("name", ids.nameHint)}
            />
            {errorFor("name")}
            <p id={ids.nameHint} className="gm-field__hint">
              {t.fieldDisplayNameHint}
            </p>
          </div>
        ) : null}

        <div className="gm-field">
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
            aria-invalid={error?.field === "email" ? true : undefined}
            aria-describedby={describedBy("email", creating ? ids.emailHint : undefined)}
          />
          {errorFor("email")}
          {creating ? (
            <p id={ids.emailHint} className="gm-field__hint">
              {t.fieldEmailHint}
            </p>
          ) : null}
        </div>

        <div className="gm-field">
          <div className="gm-field__top">
            <label htmlFor={ids.password} className="label">
              {t.fieldPassword}
            </label>
            <button
              type="button"
              className="gm-reveal"
              onClick={() => setReveal((shown) => !shown)}
              aria-pressed={reveal}
              aria-controls={ids.password}
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
            aria-invalid={error?.field === "password" ? true : undefined}
            aria-describedby={describedBy("password", creating ? ids.passwordHint : undefined)}
            required
          />
          {errorFor("password")}
          {creating ? (
            <p id={ids.passwordHint} className="gm-field__hint">
              {t.fieldPasswordHint(passwordMin)}
            </p>
          ) : null}
        </div>

        {errorFor("form")}

        <button type="submit" className="btn btn--primary w-full" disabled={busy}>
          {busy ? t.working : heading.submit}
        </button>

        {creating ? <p className="gm-field__hint">{t.noResetNote}</p> : null}
      </form>

      <p className="gm-switch">
        {mode === "login" ? t.needAccount : t.haveAccount}{" "}
        <Link
          href={`${mode === "login" ? "/signup" : "/login"}${carried}`}
          prefetch={false}
          className="gm-link"
        >
          {mode === "login" ? t.navSignUp : t.navSignIn}
        </Link>
      </p>

      {guest?.("after")}

      <p className="gm-adult">{t.adultsConfirm}</p>
    </div>
  );
}
