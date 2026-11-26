
import { fa } from "@/lib/i18n";

const ODDS = new Intl.NumberFormat("fa-IR", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const WHOLE = new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 0 });

const PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹";

export function toPersianDigits(value: string): string {
  return value.replace(/[0-9]/g, (digit) => PERSIAN_DIGITS[Number(digit)]!);
}

export function coins(minor: number): string {
  return WHOLE.format(Math.floor(minor / 100));
}

const SCALE: { at: number; unit: string }[] = [
  { at: 1e15, unit: "میلیون میلیارد" },
  { at: 1e12, unit: "هزار میلیارد" },
  { at: 1e9, unit: "میلیارد" },
  { at: 1e6, unit: "میلیون" },
];

const SHORT = new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 1 });

export function shortCoins(minor: number): string {
  const toman = Math.floor(minor / 100);
  const step = SCALE.find((entry) => toman >= entry.at);
  if (!step) return WHOLE.format(toman);

  const scaled = toman / step.at;
  const rounded =
    scaled >= 100 ? Math.round(scaled) : Number(scaled.toFixed(1));
  return `${SHORT.format(rounded)} ${step.unit}`;
}

export function odds(value: string): string {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? `${ODDS.format(parsed)} برابر` : value;
}

export function oddsValue(value: string): string {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? ODDS.format(parsed) : value;
}

export function percent(probability: string): string {
  const parsed = Number(probability);
  return Number.isFinite(parsed)
    ? `${WHOLE.format(Math.round(parsed * 100))}٪`
    : probability;
}

export function percentValue(probability: string, fallback = 50): number {
  const parsed = Number(probability);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(100, Math.max(0, Math.round(parsed * 100)));
}

export function isClosingSoon(isoTimestamp: string, now = Date.now()): boolean {
  const remaining = new Date(isoTimestamp).getTime() - now;
  return remaining > 0 && remaining < 3600_000;
}

export function count(value: number): string {
  return WHOLE.format(value);
}

export function closesIn(isoTimestamp: string, now = Date.now()): string {
  const seconds = Math.floor((new Date(isoTimestamp).getTime() - now) / 1000);
  if (seconds <= 0) return "";
  if (seconds < 3600) return `${WHOLE.format(Math.floor(seconds / 60))} دقیقه`;
  if (seconds < 86400)
    return `${WHOLE.format(Math.floor(seconds / 3600))} ساعت`;
  return `${WHOLE.format(Math.floor(seconds / 86400))} روز`;
}

export function timeAgo(isoTimestamp: string, now = Date.now()): string {
  const seconds = Math.floor((now - new Date(isoTimestamp).getTime()) / 1000);
  if (seconds < 60) return "همین حالا";
  if (seconds < 3600)
    return `${WHOLE.format(Math.floor(seconds / 60))} دقیقه پیش`;
  if (seconds < 86400)
    return `${WHOLE.format(Math.floor(seconds / 3600))} ساعت پیش`;
  return `${WHOLE.format(Math.floor(seconds / 86400))} روز پیش`;
}

export function parseAmount(input: string): number {
  const latin = input
    .replace(/[۰-۹]/g, (d) => String("۰۱۲۳۴۵۶۷۸۹".indexOf(d)))
    .replace(/[٠-٩]/g, (d) => String("٠١٢٣٤٥٦٧٨٩".indexOf(d)))
    .replace(/[٫,٬\s]/g, (m) => (m === "٫" ? "." : ""))
    .replace(/[^\d.]/g, "");
  const parsed = Number(latin);
  return Number.isFinite(parsed) ? Math.round(parsed * 100) : 0;
}

function shortCount(value: number): string {
  if (value >= 1e6) return `${SHORT.format(Math.round(value / 1e6))} میلیون`;
  if (value >= 1000) return `${SHORT.format(Math.round(value / 1000))} هزار`;
  return WHOLE.format(value);
}

export function priceAnchor(minor: number): string | null {
  const toman = Math.floor(minor / 100);
  const counted = fa.priceAnchors.map((entry) => ({
    ...entry,
    count: Math.floor(toman / entry.at),
  }));

  const believable = 40;

  const plural = counted.find(
    (entry) => entry.count >= 2 && entry.count <= believable,
  );
  if (plural) return fa.worthAbout(shortCount(plural.count), plural.label);

  const single = counted.find((entry) => entry.count >= 1);
  if (!single) return null;
  return single.count > believable
    ? fa.worthBeyond
    : fa.worthAbout(shortCount(single.count), single.label);
}
