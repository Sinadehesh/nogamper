/**
 * Every word the interface says, in one place.
 *
 * Components hold no text of their own. That is partly so the wording can be
 * read and changed as a whole — the tone of a site like this is a product
 * decision, not a detail — and partly because CI fails on a hard-coded string
 * in JSX, which is what keeps it true.
 *
 * Longer prose for the landing, help and about pages lives in ./content.ts.
 */

export const APP_NAME = process.env.NEXT_PUBLIC_APP_NAME ?? "Middlemost";

export const t = {
  appName: APP_NAME,
  tagline: "Prediction markets without the gambling.",
  description:
    `${APP_NAME} is a free forecasting game. Real questions, live odds from real ` +
    "prediction markets, and points instead of money — free to play, and nothing to cash out.",

  // ----- navigation ---------------------------------------------------------
  // The header's and the footer's link lists are two landmarks, so they need
  // two different names.
  navMainLabel: "Main",
  navFooterLabel: "Site map",
  navMenu: "Menu",
  navShowLinks: (word: string) => `Show the ${word} links`,
  navQuestionsWord: "Questions",
  navGuides: "Guides",
  navHelpWord: "Help",
  // The header's one button, and what it says to somebody already signed in.
  navStart: "Start playing free",
  navOpenGame: "Open the game",
  // One line under each guide topic in the header's Guides panel.
  navGuideLines: {
    "prediction-markets": "What a price means, and how the kinds differ",
    odds: "Where the margin sits, and why it adds up",
    "stepping-back": "Practical steps, blocking tools and real help",
  },
  navPlay: "Play",
  navMission: "Mission",
  navArticles: "Articles",
  navMoves: "What moved",
  navQuestions: "All questions",
  navPrivacy: "Privacy",
  navSupport: "Support the site",

  notOpenTitle: "The game is not open yet",
  notOpenBody:
    "The forecasting game is still being set up and will open here soon. Everything else is " +
    "ready now: the guides, the mission, and the help page.",
  notOpenShort: "The game opens here soon. The guides are ready now.",
  notOpenLink: "Read the guides",
  navAbout: "How it works",
  navHelp: "Worried about gambling?",
  navSignIn: "Sign in",
  navSignUp: "Create account",
  navAdmin: "Admin",
  skipToContent: "Skip to content",

  footerNoValue:
    "Points have no cash value. They cannot be cashed out, transferred or redeemed for anything.",
  footerAdults: "For adults aged 18 and over.",
  footerNotAffiliated:
    "Market questions and prices come from public Polymarket data. This site is not " +
    "affiliated with Polymarket and places no trades anywhere.",
  footerGameTitle: "The game",
  footerLearningTitle: "Learning",
  footerHelpTitle: "Help",
  footerSiteTitle: "The site",
  footerHelpLine:
    "Worried about gambling, yours or someone close to you? The services on the help page " +
    "are free and confidential.",
  footerHelpLink: "See where to get help",
  footerSaferTools: "Limits and breaks",
  footerTerms: "Terms",
  footerCopyright: (year: number) => `© ${year} ${APP_NAME}`,

  // ----- shared -------------------------------------------------------------
  loading: "Loading…",
  retry: "Try again",
  cancel: "Cancel",
  save: "Save",
  saving: "Saving…",
  close: "Close",
  pointsUnit: "points",
  pts: "pts",
  you: "You",
  yes: "Yes",
  no: "No",
  none: "None",

  // ----- sign in / sign up --------------------------------------------------
  signInTitle: "Sign in",
  signInIntro: "Welcome back.",
  signUpTitle: "Create your account",
  signUpIntro: "Free, and it takes a few seconds. No card needed.",
  upgradeTitle: "Keep your progress",
  upgradeIntro:
    "You have been playing as a guest. Add an email and a password and everything you " +
    "have done so far comes with you.",
  fieldEmail: "Email",
  fieldEmailHint: "Only used to sign in. Nothing here sends email.",
  fieldPassword: "Password",
  fieldPasswordHint: (min: number) =>
    `At least ${min} characters. A long phrase you will remember beats a short clever one.`,
  fieldDisplayName: "Display name",
  fieldDisplayNameHint: "2 to 24 characters. Only its first letter is shown on the leaderboard.",
  noResetNote:
    "There is no password reset yet, because nothing here sends email. Keep your password " +
    "somewhere safe.",
  submitSignIn: "Sign in",
  submitSignUp: "Create account",
  submitUpgrade: "Save my account",
  working: "One moment…",
  haveAccount: "Already have an account?",
  needAccount: "New here?",
  orGuest: "Or skip the form:",
  playAsGuest: "Play as a guest",
  guestExplainer: "No sign-up. You can create an account later and keep everything.",
  adultsConfirm: "By playing you confirm you are 18 or over.",
  showPassword: "Show",
  hidePassword: "Hide",
  // The guest option on the sign-in and sign-up pages: above the form on a
  // phone, under it beside the picture of the game on a wide screen.
  guestOptionTitle: "No form needed",
  guestOptionBody: "Start as a guest in one click. Create an account later and keep everything.",
  authAsideLabel: "What playing is like",
  authAsideLines: (start: string | null) => [
    "Each question shows the chance a real market gives it, read from Polymarket.",
    "Pick yes or no, stake some points, and see what it pays before you confirm.",
    start
      ? `You start with ${start} points. They have no cash value and never will.`
      : "Points are free and have no cash value.",
  ],

  // ----- the game, signed out (/play) ---------------------------------------
  welcomeTitle: "The forecasting game",
  welcomeLede: (start: string | null) =>
    "Pick yes or no on real questions at the chance a real market gives. " +
    (start
      ? `You start with ${start} free points, and none of them can be cashed out.`
      : "Points are free, and none of them can be cashed out."),
  welcomeNoSignUp: "No sign-up needed: one click and you are playing as a guest.",
  welcomeHaveAccount: "Played before?",
  welcomeStepsTitle: "How it works",
  welcomeSteps: (rules: { min: string; max: string; legs: number } | null) => [
    {
      title: "Pick a question",
      body: "Elections, crypto prices and the economy, each settled by the real answer.",
    },
    {
      title: "Choose yes or no",
      body: "A 62% chance means the market expects yes about 62 times in 100.",
    },
    {
      title: "Stake some points",
      body: rules
        ? `From ${rules.min} to ${rules.max} points, on up to ${rules.legs} questions at once. ` +
          "You see what it pays before you confirm."
        : "You see what a pick pays before you confirm it.",
    },
  ],
  previewLabel: (question: string, yes: string, no: string, payout: string) =>
    `A question as the game shows it, "${question}": yes at ${yes}, no at ${no}, and a slip ` +
    `with yes picked, 100 points staked, paying ${payout} points if it is right.`,
  previewCaption: "A live question, as the game shows it",

  // ----- the play screen ----------------------------------------------------
  greeting: (name: string) => `Hi, ${name}`,
  balanceLabel: "Your points",
  topUpReady: (amount: string) => `Free daily top-up: +${amount}`,
  topUpClaim: "Claim",
  topUpClaiming: "Adding…",
  topUpClaimed: (amount: string) => `${amount} points added.`,
  // The strip at the top of the game: the balance, the free daily points,
  // and the player's own limit or break when one applies.
  dailyLabel: "Free every day",
  dailyAmount: (amount: string) => `+${amount}`,
  dailyAdd: (amount: string) => `Add today's ${amount}`,
  dailyDone: (when: string) => `Added today. The next are free from ${when}.`,
  limitLabel: "Your daily limit",
  limitOf: (spent: string, limit: string) => `${spent} of ${limit}`,
  limitTodayLine: "points staked today",
  limitMeter: (spent: string, limit: string) => `${spent} of your ${limit} points staked today`,
  limitReachedShort: "Reached for today. Forecasting opens again tomorrow.",
  breakLabel: "Your break",
  breakUntil: (until: string) => `Until ${until}`,
  breakPaused: "Forecasting is paused. Everything else works as usual.",
  saferLink: "Limits and breaks",
  guestBanner: "You are playing as a guest, so this record lives only in this browser.",
  guestBannerAction: "Create an account to keep it",
  breakBanner: (until: string) =>
    `You are taking a break until ${until}. You can look around; forecasting is paused.`,
  limitBanner: (spent: string, limit: string) =>
    `Daily limit: ${spent} of ${limit} points staked today.`,
  limitReachedBanner: (limit: string) =>
    `You have reached the daily limit of ${limit} points you set. Forecasting opens again tomorrow.`,

  // The game's five views: in the bar on a wide screen, in a bar along the
  // bottom on a phone (where the shorter word is used).
  viewsLabel: "Game",
  tabMarkets: "Questions",
  tabHistory: "Your forecasts",
  tabHistoryShort: "Forecasts",
  tabLeaderboard: "Leaderboard",
  tabSafer: "Safer play",
  tabAccount: "Account",
  marketsLede: (max: number) =>
    "Each question shows the chance a real market gives it. Pick yes or no on up to " +
    `${max} questions, then choose a stake.`,
  historyLede:
    "Every forecast you have placed: open ones with their chance now where it is known, " +
    "settled ones with what they paid.",
  saferLede:
    "Limits, breaks and your own record. The server enforces each one; nothing on this page " +
    "can get round them.",
  accountLede: "Your player code, how you sign in, and what is kept about you.",

  // ----- questions ----------------------------------------------------------
  categoryAll: "All",
  categoryGroup: "Category",
  sortLabel: "Sort",
  sortTossup: "Closest calls",
  sortClosing: "Closing soonest",
  sortBusiest: "Most traded",
  marketsLoading: "Fetching questions…",
  marketsEmpty: "No open questions in this category right now. Try another one.",
  marketsEmptyAll:
    "No open questions right now. The list is read from the market every hour.",
  loadMore: "Show more questions",
  closesOn: (when: string) => `Closes ${when}`,
  priceUpdating: "Price updating",
  marketSays: "The market says",
  resolvedLabel: "How it ended",
  seeChart: "See the chart",
  newTab: "(opens in a new tab)",
  pays: (multiple: string) => `pays ${multiple}`,
  onSlip: (side: string) => `${side} is on your slip.`,
  settledAlready: "All but settled",
  settledAlreadyHint: "This is too close to certain to forecast.",
  blockedSameEvent: "You already have a pick from this event on your slip.",
  blockedFull: (max: number) => `A slip holds at most ${max} picks.`,
  blockedStale: "This price is updating. Try again in a moment.",
  onBreakNoPicks: "Forecasting is paused while you are on a break.",
  limitReachedNoPicks:
    "You have reached the daily limit you set, so forecasting is paused until tomorrow.",

  // ----- the slip -----------------------------------------------------------
  slipTitle: "Your forecast",
  slipLegCount: (count: number, max: number) => `${count} of ${max} picks`,
  slipOpenBar: (count: number) => (count === 1 ? "1 pick on your slip" : `${count} picks on your slip`),
  slipReview: "Review slip",
  slipEmptyTitle: "No picks yet",
  slipEmptyBody: (max: number) =>
    `Pick yes or no on a question and it lands here. Up to ${max} questions can go on one ` +
    "slip, and every pick has to be right for it to pay.",
  // The slip's lines, in the order and the words of the front page's picture
  // of it: "Your forecast", "Yes at 22%", "100 points", "pays 462 if right".
  slipPick: (side: string, chance: string) => `${side} at ${chance}`,
  slipStakeLine: (amount: string) => `${amount} points`,
  slipPaysLine: (payout: string) => `pays ${payout} if right`,
  slipChanceLine: (chance: string) => `${chance} chance of being right`,
  removeLeg: "Remove pick",
  removeLegOf: (question: string) => `Remove this pick: ${question}`,
  slipAllMustWin: (count: number) => `All ${count} picks have to be right for this to pay.`,
  stake: "Stake",
  stakeUnit: "points",
  stakeHint: (min: string, max: string) => `From ${min} to ${max} points.`,
  stakeHave: (balance: string) => `You have ${balance}.`,
  quickStakes: "Quick amounts",
  stakeTooSmall: (min: string) => `The smallest stake is ${min} points.`,
  stakeTooLarge: (max: string) => `The largest stake is ${max} points.`,
  balance: "Balance",
  combinedOdds: "Combined odds",
  winChance: "Chance it comes in",
  toWin: "If you are right",
  cappedAt: (amount: string) => `Payouts are capped at ${amount} points.`,
  noMargin: "Fair odds: 1 ÷ probability. Nothing is taken out.",
  placeForecast: (amount: string) => `Place forecast · ${amount} points`,
  placing: "Placing…",
  placed: "Forecast placed.",
  placedTitle: "Forecast placed",
  placedBody: "It is with your forecasts now, and settles when the real answer is in.",
  placedSee: "See your forecasts",
  placedDone: "Done",
  quoting: "Pricing…",
  keepBrowsing: "Add another question",
  discardOpen: "Clear slip",
  discardTitle: "Clear this slip?",
  discardBody: (count: number) =>
    count === 1 ? "Your pick will be removed." : `Your ${count} picks will be removed.`,
  discardConfirm: "Clear it",
  discardKeep: "Keep it",
  notEnough: (short: string) => `That is ${short} points more than you have. Lower the stake.`,
  limitLeft: (left: string) => `${left} points left of today's limit.`,
  overLimit: (left: string) =>
    `That is more than the ${left} points left of the daily limit you set. Lower the stake, ` +
    "or carry on tomorrow.",
  overLimitNone: "You have reached the daily limit you set. Forecasting opens again tomorrow.",

  // ----- my forecasts -------------------------------------------------------
  historyAll: "All",
  historyOpen: "Open",
  historyWon: "Right",
  historyLost: "Wrong",
  historyFilter: "Show",
  historyEmpty: "Nothing here yet. Forecasts you place show up here with how they turned out.",
  historyEmptyOpen: "No open forecasts.",
  historyEmptySettled: "None of your forecasts has settled this way yet.",
  statusPending: "Open",
  statusWon: "Right",
  statusLost: "Wrong",
  statusInsured: "Stake returned",
  statusVoid: "Voided",
  slipSingle: "Single forecast",
  slipCombo: (count: number) => `${count}-pick forecast`,
  placedOn: (when: string) => `Placed ${when}`,
  settledOn: (when: string) => `Settled ${when}`,
  waitingOne: "Waiting for the result.",
  waitingMany: (settled: number, total: number) => `${settled} of ${total} picks decided so far.`,
  sincePicked: "Chance then and now",
  paidLine: (amount: string) => `Paid ${amount} points`,
  lostLine: (amount: string) => `Stake lost: ${amount} points`,
  voidNote: "Voided at the source. Your stake was returned.",
  insuredNote: "A miss within the cover this slip carried. Your stake was returned.",
  resolvedAs: (answer: string) => `Answer: ${answer}`,

  // ----- leaderboard --------------------------------------------------------
  leaderboardTitle: (season: string) => `${season} leaderboard`,
  leaderboardEnds: (when: string) => `This season ends ${when}.`,
  leaderboardIntro:
    "The score is your net points on forecasts settled this month, plus a share for your " +
    "return on what you staked. There are no prizes.",
  leaderboardMinimum: (amount: string) =>
    `Stake at least ${amount} points on settled forecasts to be ranked.`,
  leaderboardEmpty:
    "Nobody is ranked yet this season. Standings update every hour as forecasts settle.",
  leaderboardYou: (rank: number) => `You are ranked ${rank} this season.`,
  leaderboardUnranked: "You are not ranked yet this season.",
  leaderboardYourNet: (net: string, staked: string) =>
    `Your net this season: ${net} points, on ${staked} staked.`,
  leaderboardCaption: (season: string) =>
    `${season}: rank, player, forecasts right of those settled, points staked and net points.`,
  colRank: "Rank",
  colPlayer: "Player",
  colRecord: "Right / settled",
  colStaked: "Staked",
  colNet: "Net points",

  // ----- safer play ---------------------------------------------------------
  saferIntro:
    "These are play points, and the tools below are real anyway: they are enforced by the " +
    "server, not suggested by the page.",

  realityTitle: "Your record",
  realityIntro: "Every settled forecast, counted the same way the leaderboard counts it.",
  realityEmpty: "Once some of your forecasts have settled, your record shows up here.",
  statForecasts: "Forecasts settled",
  statRight: "Right",
  statPicks: "Picks right",
  statOpen: "Still open",
  statStaked: "Points staked",
  statReturned: "Points returned",
  statNet: "Net result",
  statActive: "Active days (last 30)",
  ofTotal: (part: number, total: number) => `${part} of ${total}`,
  marginTitle: "The same record, with real money",
  marginBody: (margin: string) =>
    `A bookmaker does not pay fair odds. It shaves a margin off every pick — ${margin} is a ` +
    "typical illustration — and on a multi-pick bet the margin compounds.",
  marginCost: (cost: string) => `That margin would have kept ${cost} of your winnings.`,
  marginLessThanOne: "less than 1 point",
  marginNet: (here: string, there: string) =>
    `Net result here: ${here}. With the margin: ${there}.`,
  marginNone: "You have no winning forecasts yet, so there is nothing for a margin to take.",
  marginFootnote:
    "An illustration, not a claim about any particular bookmaker. A lost stake is lost either " +
    "way; the margin comes out of what winners are paid.",
  calibrationTitle: "How often your picks came in",
  calibrationIntro:
    "Of the things you backed at around 70%, about 70% should come in. Big gaps mean the " +
    "market knew better — or you did.",
  calibrationBand: "Chance when you picked",
  calibrationPicks: "Picks",
  calibrationHit: "Came in",
  calibrationExpected: "Expected",
  calibrationRange: (low: string, high: string) => `${low}–${high}`,

  // ----- the shop ------------------------------------------------------------
  shopTitle: "Points",
  shopFreeFirst: (topUp: string) =>
    `You get ${topUp} points free every day, so you never need to buy any.`,
  shopWhy:
    "If you would like more to play with, you can buy extra points. There are no adverts " +
    "here, so this is how the site is paid for — thank you for helping it continue.",
  shopChoose: "Choose a pack",
  shopPackPoints: (amount: string) => `${amount} points`,
  shopSameRate: "The price per point is the same for every pack.",
  shopAdult: (age: number) =>
    `I am ${age} or over, and I understand that points have no cash value and cannot be cashed out.`,
  shopBuy: "Pay with card",
  shopGoing: "Opening the payment page…",
  shopStripeNote:
    "Payment is taken on Stripe's secure page. This site never sees your card. Your points " +
    "arrive a few seconds after you pay.",
  shopSpentMonth: (spent: string, ceiling: string) =>
    `Spent this month: ${spent} of a ${ceiling} limit.`,
  shopSetLimit: "Set a lower limit",
  shopHistory: "Your purchases",
  shopRefunded: "refunded",
  shopNoValue: "Points have no cash value and can never be cashed out, traded or redeemed.",
  shopTermsLink: "The terms in full",
  shopLink: "Buy points",
  shopNeedsAccount: "Create an account to buy points. A guest account is only a cookie.",
  shopOnBreak: "You are on a break, and the shop is closed until it ends.",
  shopOnBreakUntil: (when: string) =>
    `You are on a break until ${when}. The shop is closed until it ends.`,
  shopClosedByYou:
    "You have set your spending limit to zero, so the shop is closed for you. That was your " +
    "decision and it is respected: the free top-up carries on as usual.",
  shopLimitReached: (limit: string, resets: string) =>
    `You have reached this month's spending limit of ${limit}` +
    (resets ? `. It starts again on ${resets}` : "") +
    ". The free top-up carries on as usual.",
  shopOverLimit: "That pack would take you past this month's spending limit.",
  shopRestricted: "This account cannot buy points.",
  shopClosed: "Nothing is for sale at the moment.",
  shopNoneTitle: "Buying points",
  shopNone: (daily: string) =>
    `Points are not for sale here. Everyone gets ${daily} free every day, and that is the only way to get more.`,
  shopAdultRequired: "Please confirm that you are old enough.",
  shopUnknownPack: "That pack is no longer on sale. Reload the page and choose again.",
  shopUnavailable: "Payment is unavailable right now. Nothing was charged. Please try later.",
  shopThanks:
    "Thank you — that is what keeps this site running. Your points will appear here within a " +
    "minute.",
  shopArrived: "Thank you — your points have arrived, and you have helped keep this site running.",
  shopCancelled: "No payment was taken.",

  spendTitle: "Spending limit",
  spendIntro: (cap: string) =>
    `Real money, not points. Nobody can spend more than ${cap} a month here, and you can set ` +
    "yourself a lower limit — or close the shop for yourself altogether.",
  spendThisMonth: "Spent this month",
  spendAllTime: "Spent in total",
  spendYourLimit: "Your limit",
  spendNoLimit: (cap: string) => `${cap} (the site's)`,
  spendClosed: "Shop closed",
  spendChange: "Change my monthly limit",
  spendChoose: "Choose…",
  spendOption: (amount: string) => `${amount} a month`,
  spendOptionZero: "Nothing — close the shop for me",
  spendOptionNone: (cap: string) => `No limit of my own (${cap})`,
  spendRule:
    "A limit can be lowered at once. Raising or removing it takes effect only after it has " +
    "stood for a day.",

  limitTitle: "Daily limit",
  limitIntro: "The most you can stake in a day. Tighten it whenever you like.",
  limitCurrent: (amount: string) => `Current limit: ${amount} points a day.`,
  limitNone: "No limit set.",
  limitSpent: (spent: string) => `Staked today: ${spent} points.`,
  limitStakedToday: "Staked today",
  limitPerDay: "A day",
  limitField: "Points per day",
  limitSet: "Set limit",
  limitRemove: "Remove limit",
  limitRule:
    "Lowering a limit takes effect at once. Raising or removing one only works after it has " +
    "been in place for 24 hours — the moment you most want a limit gone is the moment it is " +
    "doing its job.",
  limitLockedUntil: (when: string) => `This limit can be raised or removed after ${when}.`,
  limitSaved: "Limit saved.",

  breakTitle: "Take a break",
  breakIntro:
    "Pause forecasting for a while. You can still sign in, see your record and claim the " +
    "daily top-up — a break should not cost you anything.",
  breakActive: (until: string) => `You are on a break until ${until}.`,
  breakLength: "Length of the break",
  breakExtend: "Make it longer",
  breakRule: "A break cannot be cancelled or shortened once it starts. That is the point of it.",
  breakConfirmTitle: (length: string) => `Take a break for ${length}?`,
  breakConfirmBody: "You will not be able to place forecasts until it ends, and it cannot be undone.",
  breakConfirm: "Start my break",
  breakStarted: "Your break has started.",
  breakOptions: "Break lengths",

  reminderTitle: "Session reminder",
  reminderIntro:
    "A short note on this device after you have been here a while. It is on at 30 minutes " +
    "unless you change it.",
  reminderOptions: "Remind me after",
  reminderChange: "Change the reminder",
  deviceTitle: "On this device",
  reminderOff: "Off",
  reminderEvery: (minutes: number) => `${minutes} min`,
  reminderHeadline: (minutes: number) => `You have been here ${minutes} minutes.`,
  reminderBody: "A good moment for a pause. Your forecasts settle whether you are here or not.",
  reminderContinue: "Keep going",
  reminderBreak: "Take a break",

  helpPrompt: "Is real-money gambling costing you more than you want it to?",
  helpLink: "Free, confidential help",

  // ----- account ------------------------------------------------------------
  accountTitle: "Your account",
  accountSignIn: "How you sign in",
  accountGuestKeep:
    "A guest account is a cookie in this browser. Add an email and a password to keep your " +
    "record on any device.",
  accountSignOutNote: "Signs this browser out. Your record stays with your account.",
  accountSignOutGuest:
    "A guest has no password to come back with, so signing out leaves this record behind " +
    "for good. Create an account first to keep it.",
  accountCode: "Player code",
  accountCodeHint: "Quote this if you write to us. It is not a password.",
  accountEmail: "Email",
  accountGuest: "Guest — not saved to an account yet",
  accountSince: "Playing since",
  accountRename: "Change name",
  renamed: "Name updated.",
  passwordTitle: "Change password",
  passwordCurrent: "Current password",
  passwordNew: "New password",
  passwordChange: "Change password",
  passwordChanged: "Password changed. Other devices have been signed out.",
  contactTitle: "Write to us",
  contactIntro: "A question, a market that looks wrong, something broken. Replies appear here.",
  contactPlaceholder: "What is on your mind?",
  contactSend: "Send",
  contactSending: "Sending…",
  contactSent: "Sent. A reply will show up below.",
  contactHistory: "Your messages",
  contactReply: "Reply",
  messageNew: "Waiting",
  messageSeen: "Seen",
  messageAnswered: "Answered",
  signOut: "Sign out",
  signingOut: "Signing out…",
  eraseTitle: "Delete my account",
  eraseIntro:
    "Removes your email, password, name, messages and articles, and signs you out everywhere. " +
    "This cannot be undone.",
  eraseConfirmLabel: "Enter your password to confirm",
  eraseConfirmGuest: "This guest account will be gone for good.",
  eraseButton: "Delete my account",
  erasing: "Deleting…",

  // ----- articles: reading --------------------------------------------------
  articleByTeam: `By ${APP_NAME}`,
  articleBy: (name: string) => `By ${name}`,
  articlePublished: (when: string) => `Published ${when}`,
  articleUpdated: (when: string) => `Updated ${when}`,
  articleReading: (minutes: number) => `${minutes} min read`,
  articleSources: "Sources",
  articleFromReader: "A reader's article",
  articleReaderNote:
    "Readers' articles are their own views and experience. They are read before they are " +
    `published, but they are not written by ${APP_NAME}.`,
  articleNotAdvice: "General information, not medical, legal or financial advice.",
  articleHelpPrompt: "If gambling is costing you more than you want it to,",
  articleHelpLink: "free, confidential help is here.",
  articleMore: "Keep reading",
  articleBack: "All articles",
  articleTryTitle: "See what forecasting is like with no money in it",
  articleTryBody: "Real questions, live odds, and points that can never be cashed out.",

  // ----- articles: writing --------------------------------------------------
  writeTitle: "Write an article",
  writeIntro:
    "Share what you know, or what you have been through. A person reads everything before " +
    "it is published.",
  writeRulesTitle: "Before you write",
  writeRules: (name: string) => [
    "Write from your own experience, or say where a fact comes from.",
    "Nothing that promotes betting sites, tipsters, or anything that takes money.",
    "No personal details about other people.",
    "Plain Markdown: headings, lists and links. Images are not shown.",
    `It is published under your display name, ${name}.`,
  ],
  writeNeedsAccount:
    "Writing needs an account, so that your articles are still yours if you clear your browser.",
  writeNeedsAccountCta: "Create an account",
  writeRestricted: "This account cannot write articles.",
  writeMine: "Your articles",
  writeNone: "You have not written anything yet.",
  writeNew: "Start a new article",
  writeLink: "Write an article",
  fieldArticleTitle: "Title",
  fieldArticleSummary: "Summary",
  fieldArticleSummaryHint: "One or two sentences. Shown in listings and in search results.",
  fieldArticleBody: "Article",
  fieldArticleBodyHint:
    "Markdown. Start a line with ## for a heading or - for a list; write [text](https://…) for a link.",
  lengthRange: (count: number, min: number, max: number) =>
    `${count.toLocaleString("en-US")} characters — between ${min.toLocaleString("en-US")} and ` +
    `${max.toLocaleString("en-US")}`,
  writeTabEdit: "Write",
  writeTabPreview: "Preview",
  writeTabs: "Show the text or a preview",
  writePreviewEmpty: "Nothing to preview yet.",
  writeSave: "Save draft",
  writeSaved: "Saved.",
  writeSubmit: "Submit for review",
  writePublish: "Publish",
  writeSubmitNote:
    "A person will read it before it is published. You can withdraw it at any time.",
  writePublishNote: "As an operator, your own articles are published straight away.",
  writeWithdraw: "Withdraw",
  writeDelete: "Delete",
  writeDeleteTitle: "Delete this article?",
  writeDeleteBody: "It is removed for good — and from the site, if it is published.",
  writeDeleteConfirm: "Delete it",
  writeDeleteKeep: "Keep it",
  writeDiscard: "You have unsaved changes. Leave without saving them?",
  writeOpen: "Open",
  writeView: "Read it on the site",
  writeReviewNote: "From the reviewer",
  writeEdited: (when: string) => `Edited ${when}`,
  articleStatus: {
    DRAFT: "Draft",
    SUBMITTED: "Waiting for review",
    PUBLISHED: "Published",
    REJECTED: "Sent back",
    REMOVED: "Taken down",
  },
  articleStatusNote: {
    DRAFT: "Only you can see this.",
    SUBMITTED: "Waiting for a person to read it. Withdraw it if you want to keep editing.",
    PUBLISHED: "This is live. To change it, withdraw it, edit, and submit again.",
    REJECTED: "Sent back with a note. Edit it and submit again.",
    REMOVED: "Taken down with a note. Edit it and submit again, or delete it.",
  },

  // ----- operator -----------------------------------------------------------
  adminBack: "← Back to the site",
  adminOverview: "Overview",
  adminPlayers: "Players",
  adminInbox: "Inbox",
  adminArticles: "Articles",
  adminArticlesCounts: (waiting: number, live: number) =>
    `${waiting} waiting · ${live} published`,
  adminArticleTabs: {
    SUBMITTED: "Waiting",
    PUBLISHED: "Published",
    REJECTED: "Sent back",
    REMOVED: "Taken down",
  },
  adminArticlesEmpty: "Nothing here.",
  adminArticlePublish: "Publish",
  adminArticleReject: "Send back",
  adminArticleRemove: "Take down",
  adminArticleNote: "Reason — the author will see this",
  adminArticleRead: "Read it",
  adminArticleHide: "Hide",
  adminArticleByline: (name: string, code: string) => `${name} · ${code}`,
  adminArticleDone: {
    publish: "Published.",
    reject: "Sent back to the author.",
    remove: "Taken down.",
  },
  adminDenied: "There is nothing here.",
  adminWindow: (days: number) => `${days} days`,
  adminGenerated: (when: string) => `Updated ${when}`,
  adminPlayersTotal: "Players",
  adminRegistered: "Registered",
  adminGuests: "Guests",
  adminNew: "New in window",
  adminForecasters: "Placed a forecast",
  adminClaimed: "Claimed a top-up",
  adminForecastsPlaced: "Forecasts placed",
  adminForecastsOpen: "Open now",
  adminForecastsRight: "Right / settled",
  adminPointsTitle: "Where points went",
  adminPointsNote:
    "Points in the game are nobody's income: at fair odds the gap between staked and " +
    "returned is luck and skill. Money from points bought and from donations is in Stripe, " +
    "not here.",
  adminGranted: "Granted free",
  adminBought: "Bought (net of refunds)",
  adminStaked: "Staked",
  adminReturned: "Returned",
  adminAdjusted: "Adjusted by an operator",
  adminNetChange: "Net change in circulation",
  adminSaferTitle: "Safer-play tools in use",
  adminWithLimit: "With a daily limit",
  adminOnBreak: "On a break now",
  adminErased: "Accounts deleted",
  adminDailyTitle: "Day by day",
  adminDay: "Day",
  adminDayNew: "New players",
  adminDayForecasts: "Forecasts",
  adminDayForecasters: "People forecasting",
  adminLedgerTitle: "Ledger by entry type",
  adminEntryType: "Entry type",
  adminEntries: "Entries",
  adminNet: "Net",
  adminSearch: "Search by code, name or email",
  adminShowing: (shown: number, total: number) => `Showing ${shown} of ${total}`,
  adminColPlayer: "Player",
  adminColStatus: "Status",
  adminColBalance: "Balance",
  adminColStaked: "Staked",
  adminColReturned: "Returned",
  adminColNet: "Net",
  adminColSlips: "Forecasts",
  adminColBrakes: "Limit / break",
  adminColSeen: "Last seen",
  adminOpenCount: (count: number) => `${count} open`,
  adminGuestTag: "guest",
  adminLimitTag: (amount: string) => `limit ${amount}`,
  adminBreakTag: (when: string) => `break to ${when}`,
  adminBan: "Ban",
  adminUnban: "Reinstate",
  adminRestrict: "Restrict",
  adminAdjust: "Adjust",
  adminAdjustTitle: (code: string) => `Adjust ${code}`,
  adminAdjustAmount: "Points (negative to remove)",
  adminAdjustReason: "Reason",
  adminAdjustPost: "Post adjustment",
  adminAdjusted2: (code: string, balance: string) => `${code} now holds ${balance} points.`,
  adminStatusSet: (code: string, status: string) => `${code} is now ${status}.`,
  adminNoPlayers: "No players match.",
  adminInboxUnread: (count: number) => `${count} unread`,
  adminInboxEmpty: "No messages.",
  adminFilterAll: "All",
  adminFilterNew: "New",
  adminFilterSeen: "Seen",
  adminFilterAnswered: "Answered",
  adminMarkSeen: "Mark seen",
  adminReplyPlaceholder: "Your reply. The player reads it on their account page.",
  adminReplySend: "Send reply",
  adminReplySent: "Reply saved. The player will see it on their account page.",
  adminNotePlaceholder: "Private note (never shown to the player)",
  adminNoteSave: "Save note",
  adminYourReply: "Your reply",
  adminNote: "Private note",
  adminPrizeClaim: "old prize claim",

  statusTitleHealthy: "Markets are updating normally",
  statusTitleProblem: "Something needs a look",
  statusRefresh: "Refresh",
  statusRefreshing: "Checking…",
  statusMarkets: "Active markets",
  statusFresh: "Fresh prices",
  statusStale: "Stale prices",
  statusNewest: "Newest price",
  statusCache: "Cache",
  statusCacheOk: "reachable",
  statusCacheDown: "unreachable",
  statusRuns: "Last run of each job",
  statusNoRuns: "No job has finished a run yet.",
  statusRunLine: (outcome: string, seconds: number, ago: string) =>
    `${outcome} in ${seconds}s, ${ago}`,
  statusShow: "Show details",
  statusHide: "Hide details",

  // ----- errors that are not tied to a code ---------------------------------
  errorNetwork: "Could not reach the server. Check your connection and try again.",
  errorGeneric: "Something went wrong. Please try again.",
  errorSessionTitle: "You have been signed out",
  errorSessionBody: "Your session ended. Sign in again to carry on.",
  rateLimited: (when: string) => `Too many attempts. Try again in ${when}.`,
} as const;

/**
 * What to say for each error the API can return.
 *
 * Keyed on the stable `code`, never on the API's English `detail`, so the
 * wording here can change without anyone touching the server — and so a new
 * code with no entry falls back to something neutral rather than to a raw
 * message written for a log.
 */
const ERRORS: Record<string, string> = {
  network_unavailable: t.errorNetwork,
  api_unreachable: "The service is not answering right now. Give it a moment and try again.",
  invalid_request: "Some of that was not filled in correctly. Check the form and try again.",
  cross_site_request: "That request did not come from this site. Reload the page and try again.",

  invalid_credentials: "That email and password do not match.",
  email_taken: "There is already an account with that email. Try signing in instead.",
  invalid_email: "That does not look like an email address.",
  invalid_display_name: "Use 2 to 24 characters: letters, numbers, spaces and . _ - '",
  password_too_short: "That password is too short. Use at least 10 characters.",
  password_too_long: "That password is too long.",
  password_too_common: "That password is too easy to guess. Try a longer phrase.",
  not_registered: "A guest account has no password. Create an account first.",
  not_a_guest: "This account is already registered.",
  account_suspended: "This account has been suspended.",
  account_restricted: "This account cannot do that at the moment.",

  no_session: t.errorSessionBody,
  token_missing: t.errorSessionBody,
  token_invalid: t.errorSessionBody,
  token_expired: t.errorSessionBody,
  session_expired: t.errorSessionBody,
  session_revoked: t.errorSessionBody,
  session_unknown: t.errorSessionBody,

  insufficient_funds: "You do not have enough points for that stake.",
  odds_moved: "The price moved while you were deciding. Check the new figure and confirm again.",
  price_stale: "This question's price is being refreshed. Try again in a moment.",
  market_not_open: "This question is no longer taking forecasts.",
  market_locked: "Forecasts on this question have closed.",
  market_not_found: "That question is no longer available.",
  correlated_legs: "Two picks from the same event cannot go on one slip.",
  duplicate_market: "The same question cannot appear twice on one slip.",
  stake_too_small: "That stake is below the minimum.",
  stake_too_large: "That stake is above the maximum.",
  too_many_legs: "That is more picks than one slip can hold.",
  no_legs: "Pick at least one question first.",
  leg_unpriceable: "One of these is all but settled, so there is no forecast left to make on it.",
  odds_exceed_maximum:
    "Together these are too much of a long shot. Remove a pick to bring the odds down.",
  daily_limit_reached: "That would take you past the daily limit you set for yourself.",
  on_break: "You are taking a break. Forecasting opens again when it ends.",
  idempotency_key_reused: "That slip was already sent. Reload and check your forecasts.",

  already_claimed: "You have already claimed today's top-up.",
  topup_disabled: "The daily top-up is switched off at the moment.",

  limit_locked: "A limit can be lowered at any time, but raised or removed only after 24 hours.",
  bad_break_length: "Choose one of the break lengths on offer.",

  too_many_messages: "You have sent several messages already. Give it a little while.",
  message_too_long: "That message is too long.",
  empty_message: "Write something first.",

  account_required: "Create an account to write articles.",
  title_too_short: "The title is too short.",
  title_too_long: "The title is too long.",
  summary_too_short: "The summary is too short.",
  summary_too_long: "The summary is too long.",
  body_too_short: "The article is too short. It needs a few paragraphs.",
  body_too_long: "The article is too long.",
  too_many_drafts: "You have too many unfinished articles. Finish or delete one first.",
  too_many_submissions:
    "You have submitted several articles recently. Give the reviewer a little while.",
  article_locked: "Withdraw this article before changing it.",
  article_not_found: "That article no longer exists.",
  article_not_submittable: "This article has already been submitted.",
  article_not_withdrawable: "There is nothing to withdraw.",
  note_required: "Say why, so the author knows what to change.",
  note_too_long: "That note is too long.",
  not_awaiting_review: "This article is no longer waiting for review.",
  not_published: "This article is not published.",
  payload_too_large: "That is too large to send.",

  player_not_found: "No player with that code.",
  duplicate_adjustment: "An adjustment with that reference has already been posted.",
  zero_adjustment: "An adjustment of zero changes nothing.",
  message_not_found: "That message no longer exists.",
};

export function errorMessage(code: string, fallback?: string): string {
  return ERRORS[code] ?? (fallback || t.errorGeneric);
}

/** Display names for the categories the feed is known to carry. */
const CATEGORY_LABELS: Record<string, string> = {
  Macro: "Economy",
  Crypto: "Crypto",
  Politics: "Politics",
  Iran: "Iran",
};

export function categoryLabel(category: string): string {
  return CATEGORY_LABELS[category] ?? category;
}

// ---------------------------------------------------------------------------
// Charts and figures (components/viz): every word they print or announce.
//
// A change in a chance is "from 54% to 62%", or "54% → 62%". Its size, where
// one is needed, is in percentage points: "points" alone are the game's
// currency and nothing else.
// ---------------------------------------------------------------------------

function percentagePoints(size: string): string {
  return `${size} percentage ${size === "1" ? "point" : "points"}`;
}

export const viz = {
  missing: "—",
  yes: t.yes,
  no: t.no,

  // The figure and the words beside it.
  chanceOfYes: "chance of yes",
  chanceOfNo: "chance of no",
  lastChanceOfYes: "chance of yes at the last price",
  split: (yes: string, no: string) => `${t.yes} ${yes}, ${t.no.toLowerCase()} ${no}`,

  // Changes.
  fromTo: (was: string, now: string) => `from ${was} to ${now}`,
  fromToStart: (was: string, now: string) => `From ${was} to ${now}`,
  arrow: (was: string, now: string) => `${was} → ${now}`,
  unchanged: (now: string) => `unchanged at ${now}`,
  unchangedStart: (now: string) => `Unchanged at ${now}`,
  up: (size: string) => `up ${percentagePoints(size)}`,
  down: (size: string) => `down ${percentagePoints(size)}`,
  sentence: (fromTo: string, by: string) => `${fromTo}, ${by}.`,
  windowSentence: (window: string, change: string) => `${window}: ${change}`,
  now: "now",
  dayAgo: "a day ago",
  weekAgo: "a week ago",
  pastDay: "Past day",
  pastWeek: "Past week",
  noWeek: "No figure for the week yet",
  noDay: "No figure for the day yet",
  noChanges: "No change figures to show right now.",
  scaleStart: "0%",
  scaleMiddle: "50%",
  scaleEnd: "100%",

  // Dates. A time to close is a date, never a countdown.
  closesOn: (date: string) => `Closes ${date}`,
  closedOn: (date: string) => `Closed ${date}`,

  // The 7-day range.
  low: "Low",
  high: "High",
  rangeSentence: (low: string, high: string, nowWord: string, now: string) =>
    `Over 7 days: lowest ${low}, highest ${high}. ${nowWord} ${now}.`,
  rangeNow: "Now",
  rangeLast: "Last price",

  // The small line in a row.
  sparkSentence: (from: string, to: string, low: string, high: string) =>
    `Over 7 days: from ${from} to ${to}. Lowest ${low}, highest ${high}.`,

  // The price chart.
  chartDayAgo: "A day ago",
  chartWeekAgo: "A week ago",
  chartClosed: (date: string) => `Closed ${date}`,
  chartUtc: "UTC",
  endNow: "now",
  endLast: "last price",
  endResult: "result",
  chartEmpty: "There is no price history to show for this question.",
  chartOne: (value: string, date: string) => `One price so far: ${value} on ${date}.`,
  chartSummary: (
    first: string,
    firstAt: string,
    last: string,
    lastAt: string,
    low: string,
    high: string,
  ) => `From ${first} on ${firstAt} to ${last} on ${lastAt}. Lowest ${low}, highest ${high}.`,
  chartSlider: "Price history",
  chartHint:
    "Use the arrow keys to step through the prices, Page Up and Page Down to move a day, " +
    "and Home and End for the first and the last.",
  chartPoint: (time: string, value: string) => `${time}: ${value} chance of yes`,
  chartFigures: "Show the figures",
  chartKeyFigures: "Key figures",
  chartTableCaption: "Every price on the chart, for yes. Times are in UTC.",
  chartColTime: "Time (UTC)",
  chartColChance: "Chance of yes",
  chartColNote: "Note",
  noteHigh: "7-day high",
  noteLow: "7-day low",
  noteNow: "Now",
  noteLast: "Last price",
  noteGap: (hours: string) => `No prices for ${hours} hours after this`,
  keyNow: "Now",
  keyLast: "Last price",
  keyDayAgo: "A day ago",
  keyWeekAgo: "A week ago",
  keyLow: "Lowest",
  keyHigh: "Highest",
  keyClosed: "Closed to forecasts",
  keyResult: "Result",
  keyAt: (value: string, when: string) => `${value} on ${when}`,
  resultWord: (outcome: "yes" | "no") => (outcome === "yes" ? t.yes : t.no),

  // A bookmaker's margin, beside none.
  marginCaption: (margin: string) =>
    `What a bookmaker's margin of ${margin} a pick takes from a stake, by the number of picks on ` +
    `one slip, and what ${APP_NAME} takes.`,
  marginColPicks: "Picks on one slip",
  marginColBookmaker: (margin: string) => `A bookmaker at ${margin} a pick`,
  marginColUs: APP_NAME,
  marginPicks: (count: number) => (count === 1 ? "1 pick" : `${count} picks`),
  marginUnavailable: "The margin figures could not be read just now.",

  // One pick, and a slip of several.
  pickChance: (side: "YES" | "NO") => (side === "YES" ? "chance of yes" : "chance of no"),
  pickOdds: "fair odds",
  pickRule: (probability: string) => `1 ÷ ${probability}`,
  pickReturn: (stake: string) => `points back on a ${stake}-point stake`,
  pickUnpriceable: t.settledAlready,
  pickUnpriceableHint: t.settledAlreadyHint,
  stepsTitle: "The chance that every pick so far is right",
  stepPick: (index: number, side: string, chance: string) => `Pick ${index}: ${side} at ${chance}`,
  allRight: (count: number, chance: string) =>
    count === 1
      ? `1 pick right: ${chance} chance`
      : count === 2
        ? `Both right: ${chance} chance`
        : `All ${count} right: ${chance} chance`,
  slipPays: (multiple: string) => `Pays ${multiple}`,
  slipReturn: (amount: string, stake: string) =>
    `${amount} points back on a ${stake}-point stake`,
  slipCapped: (cap: string) => t.cappedAt(cap),
  slipOverLimit: (limit: string) =>
    `That is over the ${limit} limit for one slip, so the game would not take it.`,
  slipTooMany: (max: number) => `A slip holds up to ${max} picks.`,
  slipUnpriceable: "One pick is all but settled, so this slip has no price.",
  slipEmpty: "No picks yet.",
  stepArrow: "→",
  pickUnpriceableNote: `${t.settledAlready}. ${t.settledAlreadyHint}`,
} as const;
