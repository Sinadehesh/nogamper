/**
 * Families of near-identical titles, for the list of every question.
 *
 * The market asks many questions that differ in one place only: "Will Bitcoin
 * reach $90,000 by December 31, 2026?" and twenty more amounts, "Will Gavin
 * Newsom win the 2028 Democratic presidential nomination?" and seventy more
 * names. Listed one per line they are a wall. Grouped under the words they
 * share, with only the part that differs printed, they can be scanned.
 *
 * A family is only ever made where it is certain: at least three titles that
 * are word for word the same before one slot and word for word the same after
 * it, where the shared words are most of each title and the slot is short.
 * Anything less certain stays a title of its own. Nothing here guesses at
 * meaning; it compares words.
 */

/** The fewest titles that make a family. */
const MIN_MEMBERS = 3;
/** The longest slot, in words: a name, an amount, a range. */
const MAX_SLOT_WORDS = 6;
/** How much of each title the shared words must be, at least. */
const MIN_SHARED_SHARE = 0.6;

export type Titled = { slug: string; question: string };

export type Family<T extends Titled> = {
  /** The shared words before and after the slot: "Will Bitcoin reach", "by December 31, 2026?". */
  before: string;
  after: string;
  /** Each member with the words of its slot: "$90,000", "Gavin Newsom". */
  members: { item: T; slot: string }[];
};

export type Entry<T extends Titled> =
  | { kind: "family"; family: Family<T> }
  | { kind: "single"; item: T };

/** Words, with a closing question mark as a word of its own, so "2026?" and "2026" are not two words. */
function words(title: string): string[] {
  const parts = title.trim().split(/\s+/);
  const last = parts[parts.length - 1];
  if (last && last.length > 1 && last.endsWith("?")) {
    parts[parts.length - 1] = last.slice(0, -1);
    parts.push("?");
  }
  return parts;
}

/** A word that starts with a capital: part of a name, unless it opens the sentence. */
function capital(word: string | undefined): boolean {
  return word !== undefined && /^\p{Lu}/u.test(word);
}

function join(parts: string[]): string {
  return parts.join(" ").replace(/ \?$/, "?");
}

type Candidate = { key: string; before: number; after: number; shared: number };

/** The first number in a slot, for putting "$5,000" before "$10,000" and "$1,000,000" after both. */
function amount(slot: string): number | null {
  const match = /^([<>]?)\$?(\d[\d,]*(?:\.\d+)?)/.exec(slot.trim());
  if (!match) return null;
  const value = Number((match[2] ?? "").replace(/,/g, ""));
  if (!Number.isFinite(value)) return null;
  // "<40" comes before "40-64"; ">500" after "500".
  return match[1] === "<" ? value - 0.5 : match[1] === ">" ? value + 0.5 : value;
}

const collator = new Intl.Collator("en", { numeric: true });

/** A family's members in order: by amount when every slot is one, otherwise as words, numbers as numbers. */
function orderMembers<T extends Titled>(members: { item: T; slot: string }[]) {
  const amounts = members.map((member) => amount(member.slot));
  if (amounts.every((value) => value !== null)) {
    return members
      .map((member, index) => ({ member, value: amounts[index] as number }))
      .sort((a, b) => a.value - b.value || collator.compare(a.member.slot, b.member.slot))
      .map(({ member }) => member);
  }
  return [...members].sort((a, b) => collator.compare(a.slot, b.slot));
}

/**
 * The titles as families and single titles. Families come first, in the order
 * of their shared words; single titles after them, in their own order. Titles
 * are compared as numbers where they hold numbers, so "$5,000" comes before
 * "$10,000".
 */
export function titleFamilies<T extends Titled>(items: T[]): Entry<T>[] {
  const split = items.map((item) => words(item.question));

  // Every way of cutting each title into shared words, a slot, and shared
  // words, with how many titles share each cut.
  const byKey = new Map<string, number[]>();
  const candidates: Candidate[][] = split.map((parts, index) => {
    const own: Candidate[] = [];
    for (let before = 1; before < parts.length; before += 1) {
      for (let after = 1; before + after < parts.length; after += 1) {
        const slotWords = parts.length - before - after;
        if (slotWords > MAX_SLOT_WORDS) continue;
        // Never through the middle of a name: "Will François ___" would part
        // François Bayrou from the other candidates in his election, and
        // "Will ___ Trump" three Trumps from theirs. The first word opens the
        // sentence and is a capital whatever follows it.
        if (before > 1 && capital(parts[before - 1]) && capital(parts[before])) continue;
        if (capital(parts[parts.length - after - 1]) && capital(parts[parts.length - after])) continue;
        const shared = before + after;
        if (shared / parts.length < MIN_SHARED_SHARE) continue;
        const key = `${parts.slice(0, before).join(" ")}\u0000${parts.slice(parts.length - after).join(" ")}`;
        own.push({ key, before, after, shared });
        const holders = byKey.get(key);
        if (holders) {
          if (holders[holders.length - 1] !== index) holders.push(index);
        } else byKey.set(key, [index]);
      }
    }
    return own;
  });

  // The most specific cuts first: most shared words, then most titles. A
  // title joins the first family that still has enough members without it
  // being claimed by another.
  const ranked = [...byKey.entries()]
    .filter(([, holders]) => holders.length >= MIN_MEMBERS)
    .map(([key, holders]) => {
      const sample = candidates[holders[0] ?? 0]?.find((candidate) => candidate.key === key);
      return { key, holders, shared: sample?.shared ?? 0 };
    })
    .sort((a, b) => b.shared - a.shared || b.holders.length - a.holders.length || collator.compare(a.key, b.key));

  const taken = new Set<number>();
  const families: Family<T>[] = [];
  for (const { key, holders } of ranked) {
    const free = holders.filter((index) => !taken.has(index));
    if (free.length < MIN_MEMBERS) continue;
    const [beforeText = "", afterText = ""] = key.split("\u0000");
    const members: { item: T; slot: string }[] = [];
    for (const index of free) {
      const item = items[index];
      const parts = split[index];
      if (!item || !parts) continue;
      const cut = candidates[index]?.find((candidate) => candidate.key === key);
      if (!cut) continue;
      const slot = parts.slice(cut.before, parts.length - cut.after);
      // A slot that is empty, or only punctuation, is not a difference worth a family.
      if (!slot.some((word) => /[\p{L}\p{N}]/u.test(word))) continue;
      members.push({ item, slot: slot.join(" ") });
    }
    if (members.length < MIN_MEMBERS) continue;
    for (const member of members) taken.add(items.indexOf(member.item));
    families.push({
      before: join(beforeText.split(" ")),
      after: join(afterText.split(" ")),
      members: orderMembers(members),
    });
  }

  families.sort((a, b) => collator.compare(`${a.before} ${a.after}`, `${b.before} ${b.after}`));
  const singles = items
    .filter((_, index) => !taken.has(index))
    .sort((a, b) => collator.compare(a.question, b.question));

  return [
    ...families.map((family) => ({ kind: "family" as const, family })),
    ...singles.map((item) => ({ kind: "single" as const, item })),
  ];
}
