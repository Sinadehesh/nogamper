"use client";

import { useCallback, useEffect, useState } from "react";

import { Wording } from "@/components/game/Pick";
import { usePlayer } from "@/components/PlayerProvider";
import { MoveTrack } from "@/components/viz";
import { Figure } from "@/components/viz/Figure";
import { getSlips } from "@/lib/api";
import { errorMessage, t } from "@/lib/copy";
import { chance, dateTimeUtc, points } from "@/lib/format";
import type { LegStatus, MarketSummary, SettledLeg, Slip, SlipStatus } from "@/lib/types";

const FILTERS: { label: string; status?: SlipStatus }[] = [
  { label: t.historyAll },
  { label: t.historyOpen, status: "PENDING" },
  { label: t.historyWon, status: "WON" },
  { label: t.historyLost, status: "LOST" },
];

// Neutral marks throughout: a right forecast is not drawn as a win, nor a
// wrong one as a loss. The word carries it; the mark repeats it.
const STATUS: Record<SlipStatus, { label: string; mark: string; tone?: "ink" }> = {
  PENDING: { label: t.statusPending, mark: "" },
  WON: { label: t.statusWon, mark: "✓", tone: "ink" },
  LOST: { label: t.statusLost, mark: "✕" },
  INSURED: { label: t.statusInsured, mark: "" },
  VOID: { label: t.statusVoid, mark: "" },
};

const LEG_MARK: Record<LegStatus, { mark: string; label: string }> = {
  WON: { mark: "✓", label: t.statusWon },
  LOST: { mark: "✕", label: t.statusLost },
  VOID: { mark: "–", label: t.statusVoid },
  PENDING: { mark: "•", label: t.statusPending },
};

/**
 * The chance a pick was placed at, from the odds it was locked at.
 *
 * The game's odds are one divided by the side's probability, truncated to
 * six places, and that probability has four; dividing back and rounding to
 * four places gives it exactly.
 */
function placedAt(leg: SettledLeg): number | null {
  const odds = Number(leg.locked_odds);
  return odds > 0 ? Number((1 / odds).toFixed(4)) : null;
}

export function ForecastHistory({
  refreshToken,
  prices,
}: {
  refreshToken: number;
  /** The questions the feed has shown this visit, by id: each open pick's chance now, where known. */
  prices: ReadonlyMap<string, MarketSummary>;
}) {
  const { refresh } = usePlayer();
  const [filter, setFilter] = useState<SlipStatus | undefined>(undefined);
  const [slips, setSlips] = useState<Slip[] | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const result = await getSlips({ status: filter, limit: 20 });
    if (result.ok) {
      setSlips(result.data.slips);
      setCursor(result.data.next_cursor);
      setError(null);
    } else {
      if (result.status === 401) void refresh();
      setError(errorMessage(result.code));
    }
  }, [filter, refresh]);

  useEffect(() => {
    void load();
  }, [load, refreshToken]);

  const loadMore = useCallback(async () => {
    if (!cursor) return;
    const result = await getSlips({ status: filter, limit: 20, cursor });
    if (!result.ok) {
      setError(errorMessage(result.code));
      return;
    }
    setSlips((current) => [...(current ?? []), ...result.data.slips]);
    setCursor(result.data.next_cursor);
  }, [cursor, filter]);

  const empty =
    filter === undefined ? t.historyEmpty : filter === "PENDING" ? t.historyEmptyOpen : t.historyEmptySettled;

  return (
    <section className="gm-feed" aria-labelledby="gm-view-title">
      <div className="gm-chips" role="group" aria-label={t.historyFilter}>
        {FILTERS.map((entry) => (
          <button
            key={entry.label}
            type="button"
            className="gm-chip"
            onClick={() => setFilter(entry.status)}
            aria-pressed={filter === entry.status}
          >
            {entry.label}
          </button>
        ))}
      </div>

      {error ? (
        <p role="alert" className="gm-note gm-error">
          {error}
        </p>
      ) : null}

      {slips === null ? (
        error ? null : (
          <p className="gm-loading" role="status">
            {t.loading}
          </p>
        )
      ) : slips.length === 0 ? (
        <p className="gm-empty">{empty}</p>
      ) : (
        <>
          <ul className="gm-tickets">
            {slips.map((slip) => (
              <li key={slip.id}>
                <Ticket slip={slip} prices={prices} />
              </li>
            ))}
          </ul>
          {cursor ? (
            <div className="gm-more">
              <button type="button" className="btn btn--secondary" onClick={() => void loadMore()}>
                {t.loadMore}
              </button>
            </div>
          ) : null}
        </>
      )}
    </section>
  );
}

function Ticket({ slip, prices }: { slip: Slip; prices: ReadonlyMap<string, MarketSummary> }) {
  const status = STATUS[slip.status];
  const open = slip.status === "PENDING";
  const when = slip.settled_at ? t.settledOn(dateTimeUtc(slip.settled_at)) : t.placedOn(dateTimeUtc(slip.placed_at));

  return (
    <article className="gm-ticket">
      <header className="gm-ticket__head">
        <div>
          <h3 className="gm-h gm-h--sm">
            {slip.legs.length === 1 ? t.slipSingle : t.slipCombo(slip.legs.length)}
          </h3>
          <p className="gm-ticket__when">{when}</p>
        </div>
        <span className="gm-tag" data-tone={status.tone}>
          {status.mark ? <span aria-hidden>{status.mark}</span> : null}
          {status.label}
        </span>
      </header>

      <ul className="gm-ticket__legs">
        {slip.legs.map((leg) => (
          <TicketLeg key={leg.leg_index} leg={leg} open={open} market={prices.get(leg.market_id)} />
        ))}
      </ul>

      <Outcome slip={slip} />
    </article>
  );
}

function TicketLeg({
  leg,
  open,
  market,
}: {
  leg: SettledLeg;
  open: boolean;
  market: MarketSummary | undefined;
}) {
  const mark = LEG_MARK[leg.status];
  const side = leg.side === "NO" ? t.no : t.yes;
  const then = placedAt(leg);
  // Its own side's chance now, as the feed showed it: the API's own string
  // for that side, never worked out from the other.
  const now = open && market ? (leg.side === "NO" ? market.probability.no : market.probability.yes) : null;

  return (
    <li className="gm-tleg">
      <span className="gm-tleg__mark" data-state={leg.status} aria-hidden>
        {mark.mark}
      </span>
      <div className="min-w-0">
        <p className="gm-tleg__q">
          <Wording text={leg.question} />
        </p>
        <p className="gm-tleg__line">
          <span className="inline-flex items-center gap-2">
            <span className="gm-side" data-side={leg.side === "NO" ? "no" : "yes"} aria-hidden />
            <b>{then !== null ? <Figure text={t.slipPick(side, chance(then))} /> : side}</b>
          </span>
          {leg.status !== "PENDING" ? <span>{mark.label}</span> : <span className="sr-only">{mark.label}</span>}
          {leg.resolution && leg.resolution !== "VOID" ? (
            <span>{t.resolvedAs(leg.resolution === "YES" ? t.yes : t.no)}</span>
          ) : null}
        </p>
        {now !== null && then !== null ? (
          <div className="gm-tleg__track">
            <span className="gm-label">{t.sincePicked}</span>
            <MoveTrack was={then} now={now} size="row" />
          </div>
        ) : null}
      </div>
    </li>
  );
}

function Outcome({ slip }: { slip: Slip }) {
  if (slip.status === "PENDING") {
    const decided = slip.legs.filter((leg) => leg.status !== "PENDING").length;
    return (
      <div className="gm-ticket__sum">
        <span>
          <Figure text={t.slipStakeLine(points(slip.stake.minor))} />
          {" · "}
          {slip.legs.length === 1 ? t.waitingOne : t.waitingMany(decided, slip.legs.length)}
        </span>
        <b>
          <Figure text={t.slipPaysLine(points(slip.potential_payout.minor))} />
        </b>
      </div>
    );
  }

  if (slip.status === "WON") {
    return (
      <div className="gm-ticket__sum">
        <span>
          <Figure text={t.slipStakeLine(points(slip.stake.minor))} />
        </span>
        <b>
          <Figure text={t.paidLine(points(slip.settled_payout.minor))} />
        </b>
      </div>
    );
  }

  if (slip.status === "VOID" || slip.status === "INSURED") {
    return (
      <p className="gm-ticket__sum">{slip.status === "VOID" ? t.voidNote : t.insuredNote}</p>
    );
  }

  return (
    <div className="gm-ticket__sum">
      <span />
      <b>
        <Figure text={t.lostLine(points(slip.total_cost.minor))} />
      </b>
    </div>
  );
}
