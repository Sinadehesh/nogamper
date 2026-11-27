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

/**
 * Whether points are on sale right now.
 *
 * The site can run with the shop open or closed, and every sentence about
 * money has to be true in both. So the pages ask, rather than assume — and
 * when the API cannot be reached they say the shop is closed, because a page
 * should never advertise something it cannot see.
 */
function selling(rules: Rules): rules is GameRules {
  return rules?.shop?.open === true;
}

/** "$2" or "$2.50" — whole amounts lose their decimals. */
export function price(cents: number, currency = "usd"): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency.toUpperCase(),
    minimumFractionDigits: cents % 100 === 0 ? 0 : 2,
  }).format(cents / 100);
}

function httpsOnly(value: string | undefined): string {
  const trimmed = (value ?? "").trim();
  return trimmed.startsWith("https://") ? trimmed : "";
}

/**
 * Where the Donate button goes — a Stripe payment link, normally. Empty means
 * donations are not open and no button is shown. Anything that is not an
 * https address is treated as empty rather than rendered as a link.
 */
export const DONATE_URL = httpsOnly(process.env.DONATE_URL);

/**
 * The name Stripe's page gives for whoever receives a donation, when that is
 * not this site's own name. The Support page says it, so that nobody presses
 * Donate here and then wonders who they are about to pay there.
 */
export const DONATE_PAYEE = (process.env.DONATE_PAYEE ?? "").trim();

export const REPOSITORY_URL =
  process.env.NEXT_PUBLIC_REPOSITORY_URL ?? "https://github.com/Sinadehesh/nogamper";

/** Shown on the about page when set. Nobody's name is published by default. */
export const AUTHOR_NAME = process.env.NEXT_PUBLIC_AUTHOR_NAME ?? "";
export const AUTHOR_URL = process.env.NEXT_PUBLIC_AUTHOR_URL ?? "";

// ---------------------------------------------------------------------------
// Landing
// ---------------------------------------------------------------------------

export const landing = {
  metaTitle: `${APP_NAME} — prediction markets without the gambling`,
  metaDescription:
    `${APP_NAME} is a free forecasting game: real questions, live odds from real prediction ` +
    "markets, and points instead of money. Free to play, and nothing can ever be cashed out.",

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
  ctaNote: "Free to play. No card needed, and nothing to win or lose but points.",

  promisesTitle: "What makes it not gambling",
  promises: (rules: Rules) => [
    {
      title: "Points, never money",
      body:
        (selling(rules)
          ? "Points cannot be cashed out, traded or won as anything worth money. "
          : "You cannot buy points, cash them out or win anything worth money. ") +
        "Everybody starts " +
        (rules ? `with the same ${rules.signup_bonus.display}` : "with the same balance") +
        ", and a free top-up every day means nobody is ever stuck" +
        (selling(rules)
          ? " or ever has to pay. You can buy extra points to support the site, and they are " +
            "worth exactly as little as the free ones."
          : "."),
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
  whyMissionLink: "Read the mission",

  readTitle: "Worth reading first",
  readIntro:
    "Plain answers to the questions people actually ask, each with its sources listed.",
  // One from each group, in the order somebody new would want them.
  readSlugs: [
    "what-is-a-prediction-market",
    "why-parlays-are-a-bad-bet",
    "how-to-stop-gambling",
  ],
  readAll: "All the guides",
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
  metaTitle: "Worried about gambling? Where to get free help",
  metaDescription:
    "Free, confidential help for a gambling problem: helplines and services around the world, " +
    "the signs worth taking seriously, and tools for stepping back.",

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
  metaDescription:
    `How ${APP_NAME} works: fair odds with no house margin, points with no cash value, real ` +
    "questions from live prediction markets — and what was deliberately left out.",

  title: "How it works",
  lede:
    "The rules, the arithmetic, and how it is built. Nothing here is hidden behind a " +
    "terms page, because the whole point is that there is no catch.",

  rulesTitle: "The rules",
  rules: (rules: Rules) => [
    {
      title: "Points have no value",
      body:
        (selling(rules)
          ? "There is no way to turn points into money, goods or prizes. "
          : "There is no way to buy points and no way to turn them into money, goods or prizes. ") +
        (rules
          ? `Everyone starts with ${rules.signup_bonus.display} and can claim a free ` +
            `${rules.daily_topup.display} every day. `
          : "Everyone starts with the same balance and can claim a free top-up every day. ") +
        "The top-up is the same every day: there is no streak, so missing one costs nothing.",
    },
    ...(selling(rules)
      ? [
          {
            title: "Paying is optional, and capped",
            body:
              "You never need to pay to play. If you want a bigger balance you can buy one: " +
              `${price(rules.shop.price_per_thousand_cents, rules.shop.currency)} per 1,000 ` +
              "points, at the same rate whatever the size of the pack, so there is no reason " +
              "to buy more than you came for. No account can spend more than " +
              `${price(rules.shop.monthly_cap_cents, rules.shop.currency)} in a month, you ` +
              "can set a lower limit of your own, and nothing is sold to anyone on a break. " +
              "Bought points are the same as free ones: they cannot be cashed out either.",
          },
        ]
      : []),
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

// ---------------------------------------------------------------------------
// Mission
// ---------------------------------------------------------------------------

export type Source = { label: string; href: string };

export const mission = {
  metaTitle: "Our mission",
  metaDescription:
    `Why ${APP_NAME} exists: to keep the pleasure of forecasting and remove the money, ` +
    "the hidden margin and the tricks that make gambling harmful. What we do, and what we will not.",

  eyebrow: "Our mission",
  title: "Keep the game. Lose the gambling.",
  lede:
    `${APP_NAME} exists so that calling an outcome — having a view, committing to it, ` +
    "finding out whether you were right — is something anyone can enjoy without putting " +
    "their money or their peace of mind on the table.",

  beliefsTitle: "What we believe",
  beliefs: [
    {
      title: "Forecasting is worth enjoying",
      body:
        "Guessing what happens next is one of the oldest games there is, and one of the few " +
        "that makes you better at thinking. It rewards paying attention, changing your mind " +
        "and being honest about what you do not know. None of that needs money.",
    },
    {
      title: "The harm is in the design, not the person",
      body:
        "Betting products are built — carefully, by capable people — to keep someone playing " +
        "past the point they meant to stop: a fee folded into every price, offers with a " +
        "clock on them, streaks that punish a day off. People hurt by them are not weak. " +
        "They are outmatched.",
    },
    {
      title: "An alternative has to be good",
      body:
        "Telling people to stop is not a plan. Something to do instead only works if it is " +
        "worth choosing for its own sake — real questions, live prices, a record that means " +
        "something — and if it is free of the things that do the damage.",
    },
  ],

  scaleTitle: "Why it matters",
  scale: [
    "The World Health Organization estimates that about 1.2% of the world's adults have a " +
    "gambling disorder. A commission published in The Lancet Public Health in 2024 put the " +
    "number living with gambling disorder or problematic gambling at around 80 million " +
    "adults, with close to 450 million at some risk of harm, and expects what people lose " +
    "to gambling each year to approach 700 billion US dollars by 2028.",
    "Those are large numbers and they are hard to feel. Each one is a person, and usually a " +
    "household around them. Most never ask for help. Many started with something that " +
    "looked like a bit of fun on a phone.",
  ],
  scaleSources: [
    {
      label: "World Health Organization — Gambling fact sheet (December 2024)",
      href: "https://www.who.int/news-room/fact-sheets/detail/gambling",
    },
    {
      label: "The Lancet Public Health Commission on gambling (2024)",
      href: "https://doi.org/10.1016/S2468-2667(24)00167-1",
    },
  ] satisfies Source[],
  sourcesLabel: "Sources",

  doTitle: "What we do",
  commitments: (rules: Rules) => [
    {
      title: "A place to play that never needs your money",
      body:
        (rules
          ? `Playing is free, for good: everyone starts with ${rules.signup_bonus.display} ` +
            `points and can claim ${rules.daily_topup.display} more each day. `
          : "Playing is free, for good: everyone starts with the same points and can claim " +
            "more each day. ") +
        "There is nothing to win and no way to take anything out. That is not a policy that " +
        "might change next quarter: the code that would pay out does not exist." +
        (selling(rules)
          ? " You can buy extra points to help keep the site running, within a monthly cap " +
            "that nobody can raise in a hurry."
          : ""),
    },
    {
      title: "Honest numbers",
      body:
        "Odds here are exactly one divided by the probability, with nothing taken out. Every " +
        "forecast shows the chance it comes in beside what it would pay, and a reality " +
        "check shows your own record alongside what it would have cost at a bookmaker.",
    },
    {
      title: "Brakes that hold",
      body:
        "A daily limit you can lower in a second and raise only after a day. A break that " +
        "cannot be cancelled once it starts. A reminder when you have been here a while. " +
        "They are enforced by the server, because willpower is the wrong tool for the job.",
    },
    {
      title: "Things worth reading",
      body:
        "Plain-English guides to how odds, margins and prediction markets really work, and " +
        "to stepping back from gambling — written carefully, with their sources listed. " +
        "Anyone with an account can write too, and everything is read before it is published.",
    },
    {
      title: "A clear door to real help",
      body:
        "This is a game, not a treatment. Every page links to free, confidential services " +
        "run by people who do this every day, and we would rather you used them than us.",
    },
  ],

  wontTitle: "What we will not do",
  wont: (rules: Rules) => [
    "Pay out, in any form. Points cannot be cashed out, traded or redeemed, so there is " +
    "nothing to win and nothing to chase.",
    "Make anyone pay to play. The free points never stop.",
    ...(selling(rules)
      ? [
          "Sell points without a limit, on credit, at a discount for buying more, or to " +
          "anyone who is on a break.",
        ]
      : []),
    "Carry advertising, sponsorship or affiliate links from gambling companies.",
    "Earn anything from sending someone to a betting or trading site.",
    "Use streaks, countdowns, near-miss messages or anything else built to bring you back.",
    "Sell or share personal data, or run advertising trackers.",
    "Pretend that a game can treat an addiction.",
  ],

  forTitle: "Who this is for",
  forBody: [
    "People who enjoy calling sport, politics or markets and would rather not lose money " +
    "doing it. People cutting down who want somewhere for the same itch to go. People who " +
    "are simply curious how odds work, and would like to understand a margin before they " +
    "ever meet one.",
  ],
  notForTitle: "And who it is not for",
  notForBody: [
    "Anyone under 18. And anyone for whom odds and stakes of any kind stir up the urge to " +
    "bet for real. If that is you, the kindest thing this site can do is point you to " +
    "people who can help — and step out of the way.",
  ],
  notForLink: "Free, confidential help",

  measureTitle: "How we will know it is working",
  measureIntro:
    "Not by how long people stay. Nothing here counts that, on purpose. We would call it " +
    "a success when:",
  measures: [
    "someone who was about to place a bet makes a forecast here instead, and that is enough;",
    "someone reads how a bookmaker's margin multiplies across an accumulator and never " +
    "builds one again;",
    "someone sets a limit, takes a break, or closes their account, and it simply works;",
    "someone opens the help page and makes the call.",
  ],

  // The story behind the name, shown only while the site carries that name:
  // under any other, the section would be explaining a word that is not there.
  nameApplies: APP_NAME === "Middlemost",
  nameTitle: `Why it is called ${APP_NAME}`,
  name: [
    "In 1907 the journal Nature printed a short report on a competition at a livestock " +
    "show in Plymouth. For sixpence, visitors could guess what a fat ox would weigh once it " +
    "had been slaughtered and dressed, and the closest guesses won prizes. 787 people took " +
    "part. Their guesses ranged widely. The one in the middle, with as many guesses above " +
    "it as below, was 1,207 pounds. The ox weighed 1,198.",
    "The report called that guess “the middlemost estimate”. It is the oldest demonstration " +
    "of something that still surprises people: ask enough of them an honest question, take " +
    "the middle of their answers, and you will usually be closer than almost any one of " +
    "them. Later studies found that it does not take money to work — only people who are " +
    "trying to be right. That is the idea this site is built on.",
  ],
  nameSources: [
    {
      label: "“Vox Populi”, Nature, 7 March 1907",
      href: "https://doi.org/10.1038/075450a0",
    },
    {
      label: "Servan-Schreiber and others, “Prediction markets: does money matter?” (2004)",
      href: "https://doi.org/10.1080/1019678042000245254",
    },
  ] satisfies Source[],

  paidTitle: "How it is paid for",
  paid: (rules: Rules, donations: boolean) => [
    "Not by advertising, and not by the gambling industry: no sponsorship, no affiliate " +
    "links, no selling of data. Those are the usual ways a site like this earns its keep, " +
    "and each of them would put it on the wrong side of the people it is for.",
    selling(rules) || donations
      ? "That leaves the people who use it. " +
        (selling(rules) && donations
          ? "You can donate, or buy extra points to play with."
          : selling(rules)
            ? "You can buy extra points to play with."
            : "You can donate.") +
        " Nobody has to, the game is the same either way, and what comes in goes on servers " +
        "and the time it takes to keep the place honest."
      : "For now that leaves the person who built it, who pays the bills. If that changes, " +
        "this page and the support page will say so before anything is asked of you.",
  ],
  paidLink: "How to support the site",

  independenceTitle: "Independent, free and open",
  independence:
    `${APP_NAME} is free to play and its source code is public, so anyone can check that it ` +
    "does what this page says. It is run independently and takes no money from the gambling " +
    "industry.",

  ctaPlay: "Start playing — no sign-up",
  ctaRead: "Read the guides",
  ctaHelp: "Worried about gambling?",
};

// ---------------------------------------------------------------------------
// Privacy
// ---------------------------------------------------------------------------

export const PRIVACY_UPDATED = "2026-11-26";

export const privacy = {
  metaTitle: "Privacy",
  metaDescription:
    `What ${APP_NAME} stores about you, what it never collects, and how to delete it. ` +
    "Written in plain language.",

  title: "What this site knows about you",
  lede:
    "As little as it can. This page says exactly what is stored, why, and how to remove it. " +
    "It is a plain description of how the site works rather than a legal document.",
  updatedLabel: "Last updated",

  sections: [
    {
      title: "If you play as a guest",
      body: [
        "A guest account is a random identifier kept in a cookie in your browser, with your " +
        "points and your forecasts stored against it. There is no name and no email. Clear " +
        "the cookie and the account is unreachable.",
      ],
    },
    {
      title: "If you create an account",
      body: [
        "Your email address, used only to sign in. Nothing on this site sends email, so the " +
        "address is never written to and never verified.",
        "Your password, stored only as an Argon2id hash. Nobody who runs the site can read it.",
        "The display name you choose, your forecasts and points, any limits or breaks you " +
        "set, messages you send through the account page, and articles you write.",
      ],
    },
    {
      title: "What other people can see",
      body: [
        "The leaderboard shows the first letter of your display name and nothing else. If " +
        "you publish an article, your display name appears on it as the byline. Everything " +
        "else is private to you and to the person who runs the site.",
      ],
    },
    {
      title: "Cookies and your browser",
      body: [
        "Two cookies, both set when you start playing: one that holds your session and " +
        "cannot be read by scripts, and one that says only that you are signed in, so the " +
        "page can show the right links. Your session-reminder setting is kept in your " +
        "browser and never sent anywhere.",
        "There are no advertising cookies, no tracking pixels and no third-party scripts.",
      ],
    },
    {
      title: "Counting visits",
      body: [
        "Page views are counted in aggregate, without cookies, using the privacy-friendly " +
        "analytics provided by the site's host. It records which page was viewed, the site " +
        "that linked to it, the country, and the type of device and browser. It does not " +
        "identify you and does not follow you to other sites.",
        "To slow down abuse, the address you connect from is used for a few minutes to limit " +
        "repeated sign-up and sign-in attempts. It is not stored with your account.",
      ],
    },
    {
      title: "Who else is involved",
      body: [
        "The companies that host the site, its database and its application process data on " +
        "its behalf and keep ordinary server logs for a limited time. Market prices come " +
        "from Polymarket's public data, fetched by the site's own servers; your browser " +
        "never contacts Polymarket.",
        "Your data is not sold, and nothing is shared with advertisers or gambling companies.",
      ],
    },
    {
      title: "If you pay for anything",
      body: [
        "Payments are taken by Stripe, on Stripe's own page. Your card details go to Stripe " +
        "and never reach this site; what Stripe does with them is covered by Stripe's " +
        "privacy policy. When a purchase is started, Stripe is sent the amount and a random " +
        "reference for it — not your name, your email address or your account.",
        "This site keeps a record of each purchase: the amount, the date, how many points it " +
        "was for, and Stripe's reference. That record is kept even if you delete your " +
        "account, because it is a financial record and may be needed for a refund or for " +
        "accounts. It is not linked to your email once the account is gone.",
        "A donation is made entirely on Stripe's page and is not connected to your account " +
        "here at all.",
      ],
    },
    {
      title: "Changing or deleting it",
      body: [
        "You can change your display name, withdraw or delete anything you have written, and " +
        "delete your account, all from the account page. Deleting an account takes effect " +
        "at once: your email, password, name, messages and articles are removed. Your past " +
        "forecasts remain as anonymous entries, because other people's results and the " +
        "season's standings were worked out from them.",
      ],
    },
    {
      title: "Questions",
      body: [
        "Use “Write to us” on the account page. Replies appear there too.",
      ],
    },
  ],
};

// ---------------------------------------------------------------------------
// Articles
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// What moved, and a page for each question
// ---------------------------------------------------------------------------

/** Where the prices come from, said the same way wherever they are shown. */
export const PRICE_SOURCE =
  "Prices are read from Polymarket's public market data. " +
  `${APP_NAME} is not affiliated with Polymarket and takes no money from it.`;

function pointsWord(points: string): string {
  return Number(points) === 1 ? "point" : "points";
}

/** "up 25 points", "down 1 point", "unchanged" — a change, in words. */
export function changeInWords(points: string, direction: "up" | "down" | "flat"): string {
  if (direction === "flat") return "unchanged";
  return `${direction} ${points} ${pointsWord(points)}`;
}

/** The line that dates a page's figures, and what it says while newer ones are fetched. */
export const asOf = {
  // Printed as "As of <the time>. Dates and times are in UTC."
  label: "As of",
  zone: "Dates and times are in UTC.",
  looking: "That is a while ago. Newer figures are being fetched.",
  gaveUp: "Newer figures could not be fetched just now.",
};

/** Shown inside a link to a question while its page is on the way: the first
 * after half a second, the second only if it is still not there after six. */
export const FETCHING = "Fetching…";
export const FETCHING_SLOWLY = "The server was resting. This can take up to a minute.";

export const movesPage = {
  metaTitle: "What moved: the biggest changes in prediction market odds",
  metaDescription:
    "The questions whose chances changed most over the last day and week, and from what to " +
    "what. Results being settled are left out. No tips, and nothing to bet.",

  title: "What moved",
  lede:
    "The questions whose chances changed most, and from what to what. A change is reported " +
    "here. It is not explained, and it is not a tip.",

  dayTitle: "In the last day",
  weekTitle: "In the last week",
  fromTo: (was: string, now: string) => `From ${was} to ${now}`,
  emptyDay: (points: string) =>
    `Nothing has moved by ${points} points or more in the last day.`,
  emptyWeek: (points: string) =>
    `Nothing has moved by ${points} points or more in the last week.`,
  unavailable:
    "The figures could not be fetched just now, or are being read again. That takes a " +
    "minute or two. The rest of the site is unaffected.",

  rulesTitle: "What counts as a move",
  rules: (day: string, week: string, hours: number, margin: string) => [
    `A change of ${day} points or more in a day, or ${week} or more in a week. Less than ` +
    "that is the ordinary noise of a market, and a page of it would be a page of nothing.",
    `Only questions that are still open: more than ${hours} hours from closing, and not ` +
    `within ${margin} points of certain at either end. A price collapsing as a question ` +
    "is decided is a result arriving, not news.",
    "The change is measured from where the question stood a day or a week ago to its " +
    "price now. A move that has already come back is not listed.",
  ],

  notATipTitle: "A move is not a tip",
  notATip: [
    "A price moves when the people trading on it change their minds, or when one large " +
    "trade pushes it. Sometimes that is news arriving. Sometimes it is one opinion and a " +
    "thin market. This page cannot tell you which, and neither can anyone who says they can.",
    "Some moves hold. Many drift back. Nothing here says what happens next — and on this " +
    "site there is nothing to win by guessing, which is rather the point.",
  ],

  allLink: "Browse every question",
};

export const questionsPage = {
  metaTitle: "Every question: live prediction market odds, without the betting",
  metaDescription:
    "Every question this site follows, by subject: what is asked, and what the market " +
    "currently puts the chance at. Read them freely; nothing here can be bet on.",
  title: "Every question",
  lede:
    "Every question this site follows, by subject. Each has a page of its own: what the " +
    "market says, how that has changed, and how it ended once it has.",
  open: "Open",
  finished: "Finished",
  finishedIntro: "Questions that have closed or been resolved. Their pages keep the record.",
  unavailable: "The list of questions could not be fetched just now.",
  empty: "There are no questions to list yet. They are read from the market every hour.",
  count: (shown: number) => (shown === 1 ? "1 question" : `${shown} questions`),
};

export const questionPage = {
  // No figure in either: a search result is read days after it was written,
  // and a chance quoted there would by then be somebody else's old number
  // under this site's name.
  metaDescription: (question: string) =>
    "What the market puts the chance at, how that has changed over the last week, when " +
    `the question closes, and what the number does and does not mean. Asked: ${question}`,
  resolvedDescription: (question: string, outcome: string) =>
    `Resolved: ${outcome}. How the market's chance moved before the end, and how the ` +
    `answer was decided. Asked: ${question}`,

  trail: "Questions",
  states: {
    open: (closes: string) => `Open. Forecasts close on ${closes}.`,
    closed: (when: string) => `Closed to forecasts on ${when}, and waiting for its result.`,
    resolved: (outcome: string, when: string) => `Resolved ${outcome} on ${when}.`,
    void: "Cancelled by its source. Nobody was right or wrong about it.",
    unfollowed: (when: string) =>
      `No longer followed here. The price shown is the last one this site read, on ${when}.`,
  },
  lastPrice: "Last price",

  changesTitle: "How it has changed",
  windows: { day: "In the last day", week: "In the last week" },
  changesNote: "From where it stood a day and a week ago to the price above.",

  // Not "the last week": a new question has less than a week to show, and a
  // finished one's week is not the last. The dates are under the chart.
  chartTitle: "Price history",
  chartSummary: (
    first: string,
    firstAt: string,
    last: string,
    lastAt: string,
    low: string,
    high: string,
  ) => `From ${first} on ${firstAt} to ${last} on ${lastAt}. Lowest ${low}, highest ${high}.`,
  chartSource: {
    source: "Hourly prices from the market's own history, for Yes.",
    own: "Prices for Yes as this site recorded them. There are gaps where it was not running.",
    none: "There is no price history to show for this question.",
  },

  meaningTitle: "What the number means",
  meaning: [
    "It is the price, from 0 to 100, at which people are trading a contract that pays 100 " +
    "if the answer is yes. Read as a chance: at 55%, the market is saying this happens a " +
    "little more often than not.",
    "It is the opinion of the people trading, weighted by their money. It is often a good " +
    "estimate. It is not knowledge, and it can be wrong for a long time.",
  ],
  meaningLink: "How to read prediction market odds",

  decidedTitle: "How the answer is decided",
  decidedIntro: "In the market's own words:",
  decidedMore: "Read the rest of the rules",

  playTitle: "Think the market has it wrong?",
  playBody:
    "Say so with points instead of money. There is nothing to win here, and nothing to " +
    "lose but points that are free.",
  playCta: "Make a forecast",
  movesLink: "See what else moved",

};

export const articlesPage = {
  metaTitle: "Articles on odds, prediction markets and quitting gambling",
  metaDescription:
    "Plain-English guides to how betting odds and prediction markets really work, and to " +
    "stepping back from gambling — with sources, and no affiliate links.",

  title: "Plain answers, no sales pitch",
  lede:
    "How odds and prediction markets really work, and how to step back from gambling when " +
    "it stops being fun. Written carefully, with the sources listed.",

  // In the order they appear on the page.
  topics: {
    "prediction-markets": {
      title: "Prediction markets",
      blurb:
        "What they are, what a price means, and how the real-money and play-money kinds differ.",
    },
    odds: {
      title: "How odds really work",
      blurb:
        "Where a bookmaker's margin sits, why it multiplies, and what your mind does with a near miss.",
    },
    "stepping-back": {
      title: "Stepping back from gambling",
      blurb: "Practical steps, the tools that block betting, and the people who can help.",
    },
  },

  readersTitle: "From readers",
  readersIntro:
    "Written by people who use the site: their own views and experience, read before publishing.",
  readersEmpty: "Nothing from readers yet. Yours could be the first.",

  writeTitle: "Have something worth saying?",
  writeBody:
    "Anyone with an account can write here — what worked, what did not, what you wish you " +
    "had known sooner. Everything is read by a person before it is published.",
  writeCta: "Write an article",

  methodTitle: "How these are written",
  method:
    `The guides are written by the ${APP_NAME} project with the help of AI tools, checked ` +
    "against the sources listed at the foot of each one, and corrected when they turn out to " +
    "be wrong. They are general information, not medical, legal or financial advice.",
};

// ---------------------------------------------------------------------------
// Support
// ---------------------------------------------------------------------------

export const support = {
  metaTitle: `Support ${APP_NAME}`,
  metaDescription:
    `How ${APP_NAME} is paid for: no advertising and no gambling money, only optional ` +
    "support from the people who use it. What your money does, and the limits on taking it.",

  title: "Keeping this going",
  lede:
    "There is no advertising here and no money from gambling companies. That is the point of " +
    "the place, and it means the bills are paid by the person who built it and by the " +
    "people who use it. If it has been useful to you, this is how to help it continue.",

  nothingYet:
    "Right now there is nothing to pay for: donations are not open and nothing is for sale. " +
    "The site is paid for by the person who built it. If that changes, this page is where " +
    "it will say so — and the game will stay free either way.",

  costsTitle: "What the money is for",
  costs: [
    "Servers, a database and a domain name.",
    "The time it takes to keep the questions fresh, read every article before it is " +
    "published, and answer the people who write in.",
    "Staying independent: every month this is paid for by its users is a month it does not " +
    "need an advertiser.",
  ],

  donateTitle: "Donate",
  donateBody:
    "The simplest way to help. A donation buys nothing — no points, no perks, no badge — it " +
    "just helps this continue. Payment is taken by Stripe on Stripe's page, which shows the " +
    "amount before you pay, and this site never sees your card.",
  donateCta: "Donate",
  donateNote: "Opens Stripe's secure payment page.",
  donatePayee: (name: string) =>
    `Stripe's page will name ${name} as who you are paying. That is the account of the ` +
    "person who built this site, and it is where the money goes.",

  pointsTitle: "Buy extra points",
  pointsBody: (rules: GameRules) =>
    `You never need to: everyone starts with ${rules.signup_bonus.display} points and gets ` +
    `${rules.daily_topup.display} more every day, free. But if you would like a bigger ` +
    "balance to play with you can buy one, and the money goes to keeping the site running.",
  pointsPriceLabel: "Packs",
  pointsPack: (pointsDisplay: string, cost: string) => `${pointsDisplay} points — ${cost}`,
  pointsTermsTitle: "The terms, in full",
  pointsTerms: (rules: GameRules) => [
    "Points have no cash value. They cannot be cashed out, transferred or exchanged for " +
    "anything, whether they were bought or free. You are paying to support the site and " +
    "to have more to play with, and for nothing else.",
    "One price per point. A bigger pack is never cheaper per point, so there is no reason " +
    "to buy more than you want.",
    `No account can spend more than ${price(rules.shop.monthly_cap_cents, rules.shop.currency)} ` +
    "in a calendar month. You can set a lower limit of your own, down to zero, which closes " +
    "the shop for you. Lowering it takes effect at once; raising it takes a day.",
    "Nothing is sold to anyone on a break, and buying points does not raise a daily " +
    "forecast limit.",
    `You must be ${rules.shop.min_age} or over and have an account.`,
  ],
  pointsCta: "Buy points",
  pointsCtaNote: "On your account page, in the game.",

  cautionTitle: "If buying points starts to feel like chasing",
  cautionBody:
    "Running out and wanting to win it back is the feeling this site was built to get people " +
    "away from. If you notice it here, treat it as a signal rather than a plan: set your " +
    "spending limit to zero on the Safer play page, and let the free points be enough. And " +
    "if it is a feeling you know from somewhere else,",
  cautionLink: "there is free, confidential help.",

  refundsTitle: "Refunds",
  refundsBody:
    "Changed your mind? Use “Write to us” on your account page within 14 days of a purchase " +
    "and it will be refunded in full, and the points it bought removed from your balance. " +
    "Donations can be refunded the same way.",

  otherTitle: "Other ways to help",
  other: [
    {
      title: "Write something",
      body:
        "Anyone with an account can write an article. Something you learned the hard way " +
        "about odds, or about stopping, may be exactly what the next reader needs.",
      href: "/write",
      cta: "Write an article",
    },
    {
      title: "Tell one person",
      body:
        "Somebody you know likes calling the football, or is trying to bet less. A link from " +
        "a friend does more than any advertisement this site will never buy.",
      href: "/",
      cta: "The front page",
    },
    {
      title: "Check our work",
      body:
        "The source code is public. If anything here does not do what it says, saying so is " +
        "a contribution.",
      href: REPOSITORY_URL,
      cta: "Read the code",
    },
  ],
};
