"use client";

import Link from "next/link";
import { useCallback, useEffect, useId, useState } from "react";

import { usePlayer } from "@/components/PlayerProvider";
import { getShop, setSpendLimit, startCheckout } from "@/lib/api";
import { price } from "@/lib/content";
import { Figure } from "@/components/viz/Figure";
import { errorMessage, t } from "@/lib/copy";
import { date, dateTimeUtc } from "@/lib/format";
import type { Shop, ShopBlock } from "@/lib/types";

/**
 * Buying points, and the player's own limit on buying them.
 *
 * Two cards, on two tabs: the shop itself on the account tab, and the
 * spending limit with the other brakes on the safer-play tab. Both ask the
 * server where the player stands and neither decides anything: which packs
 * are affordable under the cap, whether a break closes the shop, whether a
 * limit may be raised yet — all of it comes back from the API, which is the
 * only place those rules are enforced.
 *
 * Deliberately plain. No badge on the tab, no "best value" ribbon, no
 * pre-selected pack, no offer that ends. The free top-up is mentioned first
 * and every time, because nobody should buy points believing they had to.
 */

export function useShop() {
  const [shop, setShop] = useState<Shop | null>(null);
  const [failed, setFailed] = useState(false);

  const reload = useCallback(async () => {
    const result = await getShop();
    if (result.ok) {
      setShop(result.data);
      setFailed(false);
    } else {
      setFailed(true);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { shop, setShop, failed, reload };
}

/** A payment page is https — or this machine, where the tests stand in for Stripe. */
function isPaymentPage(address: string): boolean {
  try {
    const url = new URL(address);
    return (
      url.protocol === "https:" ||
      (url.protocol === "http:" && ["localhost", "127.0.0.1"].includes(url.hostname))
    );
  } catch {
    return false;
  }
}

function blockedText(shop: Shop, block: ShopBlock, until: string | null): string {
  switch (block) {
    case "account_required":
      return t.shopNeedsAccount;
    case "on_break":
      return until ? t.shopOnBreakUntil(dateTimeUtc(until)) : t.shopOnBreak;
    case "shop_closed_by_you":
      return t.shopClosedByYou;
    case "spend_limit_reached":
      return t.shopLimitReached(
        price(shop.mine?.limit_cents ?? shop.monthly_cap_cents, shop.currency),
        until ? date(until) : "",
      );
    case "account_restricted":
      return t.shopRestricted;
    default:
      return t.shopClosed;
  }
}

/** The shop. Renders nothing at all when nothing is for sale. */
export function ShopCard({ onOpenSafer }: { onOpenSafer: () => void }) {
  const { player } = usePlayer();
  const { shop } = useShop();
  const groupId = useId();
  const adultId = useId();

  const [choice, setChoice] = useState<number | null>(null);
  const [adult, setAdult] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!shop) return null;
  // Nothing for sale: said plainly, with the way points do come.
  if (!shop.open || !shop.mine) {
    return (
      <article className="gm-panel gm-tool" aria-labelledby={`${groupId}-title`}>
        <div className="gm-tool__head">
          <h2 id={`${groupId}-title`} className="gm-h">
            {t.shopNoneTitle}
          </h2>
          <p className="gm-small">{t.shopNone(player.daily_topup.display)}</p>
        </div>
      </article>
    );
  }

  const { mine } = shop;
  const ceiling = Math.min(shop.monthly_cap_cents, mine.limit_cents ?? shop.monthly_cap_cents);

  async function buy() {
    if (choice === null) return;
    setBusy(true);
    setError(null);
    const result = await startCheckout(choice, adult);
    if (result.ok && isPaymentPage(result.data.url)) {
      // Off to Stripe's page. The button stays busy: the next thing this
      // person sees should be the payment page, not a second chance to click.
      window.location.assign(result.data.url);
      return;
    }
    setBusy(false);
    setError(result.ok ? t.errorGeneric : (SHOP_ERRORS[result.code] ?? errorMessage(result.code)));
  }

  return (
    <article className="gm-panel gm-tool" id="points" aria-labelledby={`${groupId}-title`}>
      <div className="gm-tool__head">
        <h2 id={`${groupId}-title`} className="gm-h">
          {t.shopTitle}
        </h2>
        <p className="gm-small">{t.shopFreeFirst(player.daily_topup.display)}</p>
        <p className="gm-small">{t.shopWhy}</p>
      </div>

      {mine.blocked ? (
        <p className="gm-note gm-note--line">
          {blockedText(shop, mine.blocked, mine.blocked_until)}{" "}
          {mine.blocked === "account_required" ? (
            <Link href="/signup" prefetch={false} className="gm-link">
              {t.guestBannerAction}
            </Link>
          ) : null}
        </p>
      ) : (
        <>
          <fieldset>
            <legend className="label">{t.shopChoose}</legend>
            <div className="grid gap-2 sm:grid-cols-3">
              {shop.packs.map((pack) => {
                const whole = pack.points.minor / 100;
                const affordable = pack.price_cents <= mine.remaining_cents;
                return (
                  <label
                    key={whole}
                    className={`flex min-h-11 cursor-pointer items-center gap-3 rounded-xl border p-3 text-sm ${
                      choice === whole ? "border-ink bg-sunken" : "border-line"
                    } ${affordable ? "" : "cursor-not-allowed opacity-50"}`}
                  >
                    <input
                      type="radio"
                      name={groupId}
                      checked={choice === whole}
                      disabled={!affordable || busy}
                      onChange={() => setChoice(whole)}
                    />
                    <span>
                      <span className="block font-medium">
                        <Figure text={t.shopPackPoints(pack.points.display)} />
                      </span>
                      <span className="block text-muted">
                        <Figure text={price(pack.price_cents, shop.currency)} />
                      </span>
                    </span>
                  </label>
                );
              })}
            </div>
            <p className="gm-small mt-2">{t.shopSameRate}</p>
          </fieldset>

          <label htmlFor={adultId} className="flex items-start gap-2 text-sm">
            <input
              id={adultId}
              type="checkbox"
              className="mt-1"
              checked={adult}
              onChange={(event) => setAdult(event.target.checked)}
            />
            <span>{t.shopAdult(shop.min_age)}</span>
          </label>

          <button
            type="button"
            className="btn btn--secondary justify-self-start"
            disabled={busy || choice === null || !adult}
            onClick={() => void buy()}
          >
            {busy ? t.shopGoing : t.shopBuy}
          </button>
          <p className="gm-small">{t.shopStripeNote}</p>
        </>
      )}

      {error ? (
        <p role="alert" className="gm-note gm-error">
          {error}
        </p>
      ) : null}

      <p className="gm-small">
        <Figure
          text={t.shopSpentMonth(
            price(mine.spent_month_cents, shop.currency),
            price(ceiling, shop.currency),
          )}
        />{" "}
        <button type="button" className="gm-link" onClick={onOpenSafer}>
          {t.shopSetLimit}
        </button>
      </p>

      {mine.purchases.length > 0 ? (
        <div>
          <h3 className="gm-h gm-h--sm">{t.shopHistory}</h3>
          <ul className="mt-2 divide-y divide-line text-sm">
            {mine.purchases.map((purchase) => (
              <li key={purchase.id} className="flex flex-wrap justify-between gap-x-4 py-2">
                <span>
                  {date(purchase.at)} · {t.shopPackPoints(purchase.points.display)}
                </span>
                <span className="text-muted">
                  {price(purchase.amount_cents, purchase.currency)}
                  {purchase.status === "REFUNDED" ? ` · ${t.shopRefunded}` : ""}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <p className="gm-small">
        {t.shopNoValue}{" "}
        <Link href="/support#terms" prefetch={false} className="gm-link">
          {t.shopTermsLink}
        </Link>
      </p>
    </article>
  );
}

const SHOP_ERRORS: Record<string, string> = {
  account_required: t.shopNeedsAccount,
  on_break: t.shopOnBreak,
  shop_closed: t.shopClosed,
  shop_closed_by_you: t.shopClosedByYou,
  spend_limit_reached: t.shopOverLimit,
  age_required: t.shopAdultRequired,
  unknown_pack: t.shopUnknownPack,
  payment_unavailable: t.shopUnavailable,
  account_restricted: t.shopRestricted,
};

// ----- the player's own spending limit --------------------------------------

/** Choices offered, as fractions of the site's cap, plus "nothing at all". */
function limitChoices(capCents: number): number[] {
  const steps = [0, 0.25, 0.5, 0.75].map((share) => Math.round((capCents * share) / 100) * 100);
  return Array.from(new Set(steps)).sort((a, b) => a - b);
}

/** With the other brakes on the safer-play tab. Hidden when nothing is sold. */
export function SpendLimitCard() {
  const { shop, setShop } = useShop();
  const fieldId = useId();

  const [draft, setDraft] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  if (!shop || !shop.open || !shop.mine) return null;
  const { mine } = shop;
  const cap = price(shop.monthly_cap_cents, shop.currency);

  async function save() {
    if (draft === "") return;
    setBusy(true);
    setMessage(null);
    const result = await setSpendLimit(draft === "none" ? null : Number(draft));
    setBusy(false);
    if (result.ok) {
      setShop(result.data);
      setDraft("");
      setMessage({ ok: true, text: t.limitSaved });
    } else {
      setMessage({
        ok: false,
        text:
          result.code === "limit_locked" && result.until
            ? t.limitLockedUntil(dateTimeUtc(result.until))
            : errorMessage(result.code),
      });
    }
  }

  return (
    <article className="gm-panel gm-tool" aria-labelledby={`${fieldId}-title`}>
      <div className="gm-tool__head">
        <h2 id={`${fieldId}-title`} className="gm-h">
          {t.spendTitle}
        </h2>
        <p className="gm-small">{t.spendIntro(cap)}</p>
      </div>

      <dl className="gm-stats">
        <div>
          <dt>{t.spendThisMonth}</dt>
          <dd>
            <Figure text={price(mine.spent_month_cents, shop.currency)} />
          </dd>
        </div>
        <div>
          <dt>{t.spendAllTime}</dt>
          <dd>
            <Figure text={price(mine.spent_all_cents, shop.currency)} />
          </dd>
        </div>
        <div>
          <dt>{t.spendYourLimit}</dt>
          <dd>
            <Figure
              text={
                mine.limit_cents === null
                  ? t.spendNoLimit(cap)
                  : mine.limit_cents === 0
                    ? t.spendClosed
                    : price(mine.limit_cents, shop.currency)
              }
            />
          </dd>
        </div>
      </dl>

      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label htmlFor={fieldId} className="label">
            {t.spendChange}
          </label>
          <select
            id={fieldId}
            className="field"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
          >
            <option value="">{t.spendChoose}</option>
            {limitChoices(shop.monthly_cap_cents).map((cents) => (
              <option key={cents} value={cents}>
                {cents === 0 ? t.spendOptionZero : t.spendOption(price(cents, shop.currency))}
              </option>
            ))}
            <option value="none">{t.spendOptionNone(cap)}</option>
          </select>
        </div>
        <button
          type="button"
          className="btn btn--secondary"
          disabled={busy || draft === ""}
          onClick={() => void save()}
        >
          {busy ? t.saving : t.limitSet}
        </button>
      </div>

      {message ? (
        <p role={message.ok ? "status" : "alert"} className={message.ok ? "gm-note" : "gm-note gm-error"}>
          {message.text}
        </p>
      ) : null}

      <p className="gm-tool__rule">
        {mine.limit_loosen_at ? t.limitLockedUntil(dateTimeUtc(mine.limit_loosen_at)) : t.spendRule}
      </p>
    </article>
  );
}
