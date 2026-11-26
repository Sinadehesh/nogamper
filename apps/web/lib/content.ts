import { APP_NAME } from "@/lib/copy";
import { duration, percent } from "@/lib/format";
import type { GameRules } from "@/lib/types";

/**
 * The prose pages: the landing page, the help page, and the page that
 * explains how the thing works.
 *
 * Kept as data rather than written into JSX so it can be read top to bottom
 * as writing — which is how it should be reviewed — and so the pages that
 * render it stay a few dozen lines of layout.
 *
 * Wherever a sentence states a number the game runs on, it takes the live
 * rules as an argument. The API publishes them at /v1/rules, so the page that
 * says "everyone starts with 1,000" is reading the same setting that pays it.
 * `rules` is null when the API could not be reached; each sentence then says
 * the same thing without the figure rather than guessing at one.
 */

type Rules = GameRules | null;

function list(items: string[]): string {
  if (items.length <= 1) return items.join("");
  return `${items.slice(0, -1).join(", ")} or ${items[items.length - 1]}`;
}

function oddsCeiling(rules: GameRules): string {
  return Number(rules.max_combined_odds).toLocaleString("en-US");
}

export const REPOSITORY_URL =
  process.env.NEXT_PUBLIC_REPOSITORY_URL ?? "https://github.com/Sinadehesh/nogamper";

/** Shown on the about page when set. Nobody's name is published by default. */
export const AUTHOR_NAME = process.env.NEXT_PUBLIC_AUTHOR_NAME ?? "";
export const AUTHOR_URL = process.env.NEXT_PUBLIC_AUTHOR_URL ?? "";

// ---------------------------------------------------------------------------
// Landing
// ---------------------------------------------------------------------------

export const landing = {
  eyebrow: "A free forecasting game",
  headline: "All the fun of calling it. None of the betting.",
  lede:
    `${APP_NAME} is a prediction market you play with points instead of money. Real ` +
    "questions about the news, live odds from real markets, a leaderboard to climb — and " +
    "nothing to lose but an argument.",
  ctaGuest: "Start playing — no sign-up",
  ctaContinue: "Carry on playing",
  ctaSignUp: "Create an account",
  ctaSignIn: "Sign in",
  ctaNote: "Free. No card. Nothing to deposit, ever.",

  promisesTitle: "What makes it not gambling",
  promises: (rules: Rules) => [
    {
      title: "Points, never money",
      body:
        "You cannot buy points, cash them out or win anything worth money. Everybody starts " +
        (rules ? `with the same ${rules.signup_bonus.display}` : "with the same balance") +
        ", and a free top-up every day means nobody is ever stuck.",
    },
    {
      title: "Fair odds, no house",
      body:
        "Every price is exactly 1 ÷ the probability. Nobody takes a cut on the way through, " +
        "so the only way to end up ahead is to be right more often than the crowd.",
    },
    {
      title: "Brakes that actually hold",
      body:
        "Set a daily limit or take a break. A limit is easy to tighten and slow to loosen, " +
        "and a break cannot be cut short — enforced by the server, not left to willpower.",
    },
  ],

  stepsTitle: "How it works",
  steps: (rules: Rules) => [
    {
      title: "Pick a question",
      body: "Will rates be cut? Will Bitcoin close the year above a line? Each has a live price.",
    },
    {
      title: "Say yes or no",
      body: "The price is the market's own estimate of the chance. Back the side you think is right.",
    },
    {
      title: "Stake some points",
      body:
        "A little or a lot. " +
        (rules && rules.max_legs > 1
          ? `Combine up to ${rules.max_legs} questions on one slip if you are feeling sure.`
          : "One question at a time."),
    },
    {
      title: "See how you did",
      body: "When the real-world answer is in, your forecast settles and your record updates.",
    },
  ],

  mathTitle: "The part a bookmaker would rather you skipped",
  mathIntro: (margin: string) =>
    "Somewhere that takes bets does not pay fair odds. It shaves a margin off every pick, and " +
    `on a bet with several picks the margin multiplies. Here is what a ${margin} margin takes ` +
    "from each stake, on average, before luck has had any say:",
  mathColumnPicks: "On one slip",
  mathPicks: (count: number) => (count === 1 ? "1 pick" : `${count} picks`),
  mathThere: (margin: string) => `With a ${margin} margin`,
  mathHere: `On ${APP_NAME}`,
  mathNothing: "0%",
  mathOutro:
    "That is why the multi-pick bet is the product every betting site pushes hardest. " +
    `${APP_NAME} charges nothing at any length, and its reality check will show you what ` +
    "your own record would have cost somewhere that does.",

  whyTitle: "Why this exists",
  why: [
    "Predicting things is genuinely fun. Having a view, putting something behind it, and " +
    "finding out whether you were right is one of the better ways to follow the news.",
    "Most places that let you do it want your money, and are built — carefully, by people " +
    "who are good at it — to keep you coming back after you have lost some. This is the same " +
    "game with the money taken out and those tricks left out: no streaks to protect, no " +
    "limited-time boosts, no balance that shrinks if you stay away.",
    "It is not a treatment, and it will not fix a gambling problem. It is somewhere to enjoy " +
    "the good part without the part that ruins people.",
  ],
  whyHelpPrompt: "If gambling is already costing you more than you want it to,",
  whyHelpLink: "there is real, free help here.",
};

// ---------------------------------------------------------------------------
// Help
// ---------------------------------------------------------------------------

export type Resource = {
  region: string;
  name: string;
  contact?: string;
  body: string;
  href: string;
  linkLabel: string;
};

export const help = {
  title: "Worried about gambling?",
  lede:
    `${APP_NAME} is a game with no money in it. It is not a treatment, and it cannot help ` +
    "with a gambling problem on its own. The services below can. They are free and " +
    "confidential, and they are run by people who do this every day.",

  emergencyTitle: "If you are in immediate danger",
  emergency:
    "If you are thinking about harming yourself, or you are not safe right now, call your " +
    "local emergency number. This cannot wait for a web page.",

  resourcesTitle: "People to talk to",
  resources: [
    {
      region: "Anywhere in the world",
      name: "Gambling Therapy",
      body:
        "Free online support for anyone affected by gambling, in many languages: live text " +
        "chat with an advisor, peer forums and email. Run by the UK charity Gordon Moody. " +
        "If your country is not listed below, start here — they can point you to services near you.",
      href: "https://www.gamblingtherapy.org/",
      linkLabel: "gamblingtherapy.org",
    },
    {
      region: "United Kingdom",
      name: "GamCare — National Gambling Helpline",
      contact: "0808 8020 133",
      body: "Free to call, 24 hours a day, every day of the year. Also by live chat and WhatsApp.",
      href: "https://www.gamcare.org.uk/get-support/talk-to-us-now/",
      linkLabel: "gamcare.org.uk",
    },
    {
      region: "United States",
      name: "National Problem Gambling Helpline",
      contact: "1-800-MY-RESET (1-800-697-3738)",
      body:
        "Call or text, or chat online. Free and confidential, run by the National Council on " +
        "Problem Gambling, and it connects you with help in your state.",
      href: "https://www.ncpgambling.org/help-treatment/",
      linkLabel: "ncpgambling.org",
    },
    {
      region: "Many countries",
      name: "Gamblers Anonymous",
      body:
        "Peer support from people who have been there. Meetings in person and online; the " +
        "site has a directory.",
      href: "https://www.gamblersanonymous.org/",
      linkLabel: "gamblersanonymous.org",
    },
  ] satisfies Resource[],
  resourcesNote:
    "Phone numbers change. Each link goes to the service's own page, which is always the " +
    "authority. Details here were last checked in November 2026.",

  signsTitle: "Signs worth taking seriously",
  signsIntro: "It may be time to talk to someone if gambling means you are:",
  signs: [
    "spending more money or time on it than you meant to",
    "going back to try to win what you lost",
    "hiding it, or lying about it, to people close to you",
    "borrowing, selling things, or missing bills to keep going",
    "feeling restless or irritable when you try to cut down",
    "finding it has pushed aside work, study or people you care about",
  ],
  signsOutro:
    "None of these is a diagnosis. They are just the things people who got help often wish " +
    "they had noticed sooner.",

  toolsTitle: "What this site can and cannot do",
  tools: (rules: Rules) => [
    {
      title: "A daily limit",
      body:
        "Cap what you can stake in a day. You can lower it at once; raising it takes " +
        (rules ? duration(rules.limit_loosen_delay_hours) : "a day") +
        ".",
    },
    {
      title: "A break",
      body:
        "Pause forecasting for " +
        (rules ? list(rules.break_options_hours.map(duration)) : "a while") +
        ". It cannot be cut short.",
    },
    {
      title: "A reality check",
      body: "Your record in plain numbers, and what the same record would have cost with real money.",
    },
    {
      title: "Leaving",
      body: "Delete your account from the account page whenever you like. Nothing is held back.",
    },
  ],
  toolsCta: "Open safer-play settings",

  recoveryTitle: "If you are in recovery",
  recovery:
    "Be honest with yourself about how this feels. For some people a game like this scratches " +
    "the itch safely. For others, odds and stakes of any kind stir up the urge to bet for " +
    "real. If that is you, this is not the right place — take a break or delete your account, " +
    "and talk it through with one of the services above. Stepping away from here costs you nothing.",
};

// ---------------------------------------------------------------------------
// About
// ---------------------------------------------------------------------------

export const about = {
  title: "How it works",
  lede:
    "The rules, the arithmetic, and how it is built. Nothing here is hidden behind a " +
    "terms page, because the whole point is that there is no catch.",

  rulesTitle: "The rules",
  rules: (rules: Rules) => [
    {
      title: "Points have no value",
      body:
        "There is no way to buy points and no way to turn them into money, goods or prizes. " +
        (rules
          ? `Everyone starts with ${rules.signup_bonus.display} and can claim a free ` +
            `${rules.daily_topup.display} every day. `
          : "Everyone starts with the same balance and can claim a free top-up every day. ") +
        "The top-up is the same every day: there is no streak, so missing one costs nothing.",
    },
    {
      title: "Prices are fair",
      body:
        "If the market puts a chance at 40%, a right forecast returns 2.5 times the stake: " +
        "1 ÷ 0.40. That is the whole formula. On average a forecast is worth exactly what " +
        "was staked on it, so over time your points track how good your judgement is.",
    },
    {
      title: "Several picks multiply",
      body:
        (rules ? `Up to ${rules.max_legs} questions` : "Several questions") +
        " can go on one slip. The odds multiply and every pick has to be right. Two picks " +
        "from the same event are refused, because their outcomes are tied together and " +
        "multiplying them would misprice the pair.",
    },
    {
      title: "Long shots are capped",
      body:
        (rules
          ? `A slip can carry at most ${oddsCeiling(rules)} to 1, and questions the market ` +
            `already has above ${percent(rules.max_prob)} or below ${percent(rules.min_prob)} ` +
            "are closed to forecasts. "
          : "The longest price a slip can carry is capped, and questions that are all but " +
            "settled are closed to forecasts. ") +
        "Without that the quickest way up the leaderboard would be a lottery ticket, and " +
        "this is not a lottery.",
    },
    {
      title: "Results come from the real world",
      body:
        "A question settles when the market it mirrors resolves. If the source voids a " +
        "question, that pick is treated as though it was never on the slip and the rest stand.",
    },
    {
      title: "The leaderboard is for bragging",
      body:
        "It ranks settled forecasts each month and shows players by a single initial. There " +
        "are no prizes. Prizes are the thing that turns a game into a reason to chase.",
    },
  ],

  sourceTitle: "Where the questions come from",
  source:
    "Questions and live prices are read from Polymarket's public market data. " +
    `${APP_NAME} is not affiliated with Polymarket, takes no part in its markets and places ` +
    "no trades anywhere. It only borrows the questions and the crowd's estimate of the odds.",

  absentTitle: "What was deliberately left out",
  absentIntro:
    "This codebase started life as a conventional betting-style product. These were removed, " +
    "not switched off:",
  absent: [
    "Buying points with real money",
    "A house margin on every pick, compounding on longer slips",
    "Prizes, and anything redeemable",
    "Limited-time boosted odds",
    "A bonus for adding more picks to a slip",
    "A balance that decays if you stay away",
    "Streak bonuses that punish a missed day",
    "A ticker of other people's wins",
    "Rewards for recruiting friends",
  ],

  buildTitle: "How it is built",
  buildIntro:
    "A small system with the parts a larger one has, each doing one job. The source is open.",
  build: [
    {
      title: "Web tier",
      body:
        "Next.js on the server holds the session in an HttpOnly cookie and forwards an " +
        "explicit allowlist of requests. The browser never sees a token or the API's address.",
    },
    {
      title: "API",
      body:
        "FastAPI over asyncpg. Sign-in is email and password hashed with Argon2id off the " +
        "event loop, throttled per address and per account in Redis.",
    },
    {
      title: "Ledger",
      body:
        "Every point that moves is a row in an append-only PostgreSQL ledger. A trigger keeps " +
        "the balance in step and refuses an overdraft; idempotency keys make a retried request " +
        "safe.",
    },
    {
      title: "Workers",
      body:
        "Scheduled jobs discover markets, sync prices, settle results and roll up the " +
        "leaderboard. A lease in the database keeps several replicas from doing the same work twice.",
    },
    {
      title: "Safer-play rules",
      body:
        "Limits and breaks are checked under a row lock in the same transaction that places a " +
        "forecast, so two requests arriving together cannot both slip through.",
    },
    {
      title: "Tests",
      body:
        "More than five hundred automated tests cover pricing, settlement, sign-in, throttling " +
        "and the safer-play rules, alongside schema invariants checked in SQL.",
    },
  ],
  buildRepo: "Read the source on GitHub",
  buildBy: (name: string) => `Built by ${name}.`,
};
