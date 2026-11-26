"use client";


import { useCallback, useEffect, useState } from "react";

import { createInvoice, getPackages, openInvoice } from "@/lib/api";
import { coins } from "@/lib/format";
import { fa, translateError } from "@/lib/i18n";
import type { CoinPackage } from "@/lib/types";

type Props = {
  shortfallMinor?: number;
  onClose: () => void;
  onFunded: () => void;
};

export function BuyCoinsModal({ shortfallMinor, onClose, onFunded }: Props) {
  const [packages, setPackages] = useState<CoinPackage[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getPackages().then((result) => {
      if (cancelled) return;
      if (!result.ok) {
        setError(translateError(result.code, result.detail));
        return;
      }
      const list = result.data.packages;
      setPackages(list);
      setSelected(smallestThatCovers(list, shortfallMinor)?.code ?? list[0]?.code ?? null);
    });
    return () => {
      cancelled = true;
    };
  }, [shortfallMinor]);

  const handleBuy = useCallback(async () => {
    if (!selected) return;
    setBusy(true);
    setError(null);

    const invoice = await createInvoice(selected);
    if (!invoice.ok) {
      setBusy(false);
      setError(translateError(invoice.code, invoice.detail));
      return;
    }

    const status = await openInvoice(invoice.data.invoice_link);
    setBusy(false);

    if (status === "paid") {
      onFunded();
      return;
    }
    if (status === "failed") setError(fa.paymentFailed);
    if (status === "unsupported") setError(fa.paymentUnsupported);
  }, [selected, onFunded]);

  return (
    <div className="fixed inset-0 z-[70] flex items-end justify-center bg-black/60">
      <section
        role="dialog"
        aria-label={fa.topUpTitle}
        className="w-full rounded-t-3xl bg-tg-secondary-bg p-4 pb-[calc(1rem+env(safe-area-inset-bottom))]"
      >
        <header className="mb-3">
          <h2 className="text-base font-bold">{fa.topUpTitle}</h2>
          {shortfallMinor ? (
            <p className="mt-0.5 text-sm text-tg-hint">
              {fa.topUpShortfall(coins(shortfallMinor))}
            </p>
          ) : (
            <p className="mt-0.5 text-sm text-tg-hint">{fa.topUpGeneric}</p>
          )}
        </header>

        {packages === null ? (
          <p className="py-6 text-center text-sm text-tg-hint">{fa.loading}</p>
        ) : (
          <ul className="space-y-2">
            {packages.map((pack) => {
              const covers = !shortfallMinor || pack.coins.minor >= shortfallMinor;
              return (
                <li key={pack.code}>
                  <button
                    onClick={() => setSelected(pack.code)}
                    aria-pressed={selected === pack.code}
                    className={`flex w-full items-center justify-between rounded-xl px-3 py-3 ring-1 ${
                      selected === pack.code
                        ? "bg-tg-button/10 ring-tg-button/60"
                        : "bg-tg-bg/60 ring-tg-hint/15"
                    }`}
                  >
                    <span className="text-start">
                      <span className="block text-sm font-semibold">
                        {fa.packageCoins(coins(pack.coins.minor))}
                      </span>
                      <span className="mt-0.5 block text-xs text-tg-hint">
                        {pack.bonus_coins.minor > 0
                          ? fa.packageBonus(coins(pack.bonus_coins.minor))
                          : pack.description}
                        {shortfallMinor && !covers ? fa.packageInsufficient : ""}
                      </span>
                    </span>
                    <span className="shrink-0 text-sm font-bold">{pack.stars} ⭐</span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}

        {error ? (
          <p className="mt-3 rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-300">{error}</p>
        ) : null}

        <button
          disabled={!selected || busy}
          onClick={handleBuy}
          className="mt-4 w-full rounded-2xl bg-tg-button py-3.5 text-base font-bold
                     text-tg-button-text disabled:opacity-40"
        >
          {busy ? fa.openingTelegram : fa.buyWithStars}
        </button>
        <button onClick={onClose} className="mt-2 w-full py-2.5 text-sm text-tg-hint">
          {fa.notNow}
        </button>

        <p className="mt-2 text-center text-[11px] leading-relaxed text-tg-hint">
          {fa.starsDisclaimer}
        </p>
      </section>
    </div>
  );
}

function smallestThatCovers(
  packages: CoinPackage[],
  shortfallMinor?: number,
): CoinPackage | undefined {
  if (!shortfallMinor) return undefined;
  return [...packages]
    .sort((a, b) => a.coins.minor - b.coins.minor)
    .find((pack) => pack.coins.minor >= shortfallMinor);
}
