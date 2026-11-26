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

export const APP_NAME = process.env.NEXT_PUBLIC_APP_NAME ?? "NoGamper";

export const t = {
  appName: APP_NAME,
  tagline: "Prediction markets without the gambling.",
  description:
    `${APP_NAME} is a free forecasting game. Real questions, live odds from real ` +
    "prediction markets, and points instead of money — nothing to buy and nothing to cash out.",

  // ----- navigation ---------------------------------------------------------
  navLabel: "Site",
  navPlay: "Play",
  navAbout: "How it works",
  navHelp: "Worried about gambling?",
  navSignIn: "Sign in",
  navSignUp: "Create account",
  navAdmin: "Admin",
  skipToContent: "Skip to content",

  footerNoValue:
    "Points have no cash value. They cannot be bought, sold, transferred or redeemed for anything.",
  footerAdults: "For adults aged 18 and over.",
  footerNotAffiliated:
    "Market questions and prices come from public Polymarket data. This site is not " +
    "affiliated with Polymarket and places no trades anywhere.",

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
  signUpIntro: "Free, and it takes a few seconds. No card, because there is nothing to pay for.",
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

  // ----- the play screen ----------------------------------------------------
  greeting: (name: string) => `Hi, ${name}`,
  balanceLabel: "Your points",
  topUpReady: (amount: string) => `Free daily top-up: +${amount}`,
  topUpClaim: "Claim",
  topUpClaiming: "Claiming…",
  topUpClaimed: (amount: string) => `+${amount} points added.`,
  topUpNext: (when: string) => `Next free top-up in ${when}.`,
  guestBanner: "You are playing as a guest, so this record lives only in this browser.",
  guestBannerAction: "Create an account to keep it",
  breakBanner: (until: string) =>
    `You are taking a break until ${until}. You can look around; forecasting is paused.`,
  limitBanner: (spent: string, limit: string) =>
    `Daily limit: ${spent} of ${limit} points staked today.`,
  limitReachedBanner: (limit: string) =>
    `You have reached the daily limit of ${limit} points you set. Forecasting opens again tomorrow.`,

  tabMarkets: "Questions",
  tabHistory: "My forecasts",
  tabLeaderboard: "Leaderboard",
  tabSafer: "Safer play",
  tabAccount: "Account",

  // ----- questions ----------------------------------------------------------
  categoryAll: "All",
  sortLabel: "Sort",
  sortTossup: "Closest calls",
  sortClosing: "Closing soonest",
  sortBusiest: "Most traded",
  marketsLoading: "Fetching questions…",
  marketsEmpty: "No open questions here right now. Try another category.",
  marketsEmptyAll:
    "No open questions right now. They are refreshed from the market every hour — check back soon.",
  loadMore: "Show more",
  closesIn: (duration: string) => `Closes in ${duration}`,
  closed: "Closed",
  priceUpdating: "Price updating",
  marketSays: "The market says",
  chanceSplit: (yes: string, no: string) => `Yes ${yes}, no ${no}`,
  pays: (multiple: string) => `pays ${multiple}`,
  settledAlready: "All but settled",
  settledAlreadyHint: "This is too close to certain to forecast.",
  pickAdd: (side: string) => `Forecast ${side}`,
  pickRemove: "Remove from slip",
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
  slipReview: "Review",
  removeLeg: "Remove pick",
  slipAllMustWin: (count: number) => `All ${count} picks have to be right for this to pay.`,
  stake: "Stake",
  stakeHint: (min: string, max: string) => `Between ${min} and ${max} points.`,
  balance: "Balance",
  combinedOdds: "Combined odds",
  winChance: "Chance it comes in",
  winChanceNote: (chance: string) =>
    `The market gives this about a ${chance} chance. That is the honest number to look at.`,
  toWin: "If you are right",
  profit: (amount: string) => `That is your stake back plus ${amount}.`,
  cappedAt: (amount: string) => `Payouts are capped at ${amount} points.`,
  noMargin: "Fair odds: 1 ÷ probability. Nothing is taken out.",
  placeForecast: (amount: string) => `Place forecast · ${amount} points`,
  placing: "Placing…",
  placed: "Forecast placed.",
  quoting: "Pricing…",
  keepBrowsing: "Add another question",
  discardOpen: "Clear slip",
  discardTitle: "Clear this slip?",
  discardBody: (count: number) =>
    count === 1 ? "Your pick will be removed." : `Your ${count} picks will be removed.`,
  discardConfirm: "Clear it",
  discardKeep: "Keep it",
  notEnough: (short: string) =>
    `You are ${short} points short. Lower the stake, or claim your free daily top-up.`,
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
  historyEmpty: "Nothing here yet. Forecasts you place show up here with how they turned out.",
  statusPending: "Open",
  statusWon: "Right",
  statusLost: "Wrong",
  statusInsured: "Stake returned",
  statusVoid: "Voided",
  slipSingle: "Single forecast",
  slipCombo: (count: number) => `${count}-pick forecast`,
  slipStakeAtOdds: (stake: string, oddsLabel: string) => `${stake} points at ${oddsLabel}`,
  pendingProgress: (settled: number, total: number, payout: string) =>
    total === 1
      ? `Waiting for the result. Pays ${payout} points if right.`
      : `${settled} of ${total} decided. Pays ${payout} points if all are right.`,
  paidOut: "Returned to you",
  stakeLost: "Stake lost",
  lostSummary: (right: number, total: number) =>
    total === 1 ? "This one did not come in." : `${right} of ${total} picks were right.`,
  voidNote: "Voided at the source. Your stake was returned.",
  insuredNote: "A miss within the cover this slip carried. Your stake was returned.",
  resolvedAs: (answer: string) => `Answer: ${answer}`,

  // ----- leaderboard --------------------------------------------------------
  leaderboardTitle: (season: string) => `${season} leaderboard`,
  leaderboardEnds: (when: string) => `Ends in ${when}`,
  leaderboardIntro:
    "Ranked on settled forecasts this month. Bragging rights only — there are no prizes, " +
    "by design.",
  leaderboardMinimum: (amount: string) =>
    `Stake at least ${amount} points on settled forecasts to be ranked.`,
  leaderboardEmpty:
    "Nobody is ranked yet this season. Standings update every hour as forecasts settle.",
  leaderboardYou: (rank: number) => `You are ranked #${rank} this season.`,
  leaderboardUnranked: "You are not ranked yet this season.",
  colRank: "#",
  colPlayer: "Player",
  colRecord: "Right / settled",
  colStaked: "Staked",
  colNet: "Net",

  // ----- safer play ---------------------------------------------------------
  saferIntro:
    "These are play points, and the tools below are real anyway: they are enforced by the " +
    "server, not suggested by the page.",

  realityTitle: "Reality check",
  realityIntro: "Your own record, stated plainly.",
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
  calibrationTitle: "How well calibrated are you?",
  calibrationIntro:
    "Of the things you backed at around 70%, about 70% should come in. Big gaps mean the " +
    "market knew better — or you did.",
  calibrationBand: "Chance when you picked",
  calibrationPicks: "Picks",
  calibrationHit: "Came in",
  calibrationExpected: "Expected",
  calibrationRange: (low: string, high: string) => `${low}–${high}`,

  limitTitle: "Daily limit",
  limitIntro: "The most you can stake in a day. Tighten it whenever you like.",
  limitCurrent: (amount: string) => `Current limit: ${amount} points a day.`,
  limitNone: "No limit set.",
  limitSpent: (spent: string) => `Staked today: ${spent} points.`,
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
  breakLength: "How long?",
  breakExtend: "Make it longer",
  breakRule: "A break cannot be cancelled or shortened once it starts. That is the point of it.",
  breakConfirmTitle: (length: string) => `Take a break for ${length}?`,
  breakConfirmBody: "You will not be able to place forecasts until it ends, and it cannot be undone.",
  breakConfirm: "Start my break",
  breakStarted: "Your break has started. Well done.",

  reminderTitle: "Session reminder",
  reminderIntro: "A nudge on this device after you have been here a while.",
  reminderOff: "Off",
  reminderEvery: (minutes: number) => `${minutes} min`,
  reminderHeadline: (minutes: number) => `You have been here ${minutes} minutes.`,
  reminderBody: "No rush and nothing to lose — but it is a good moment to stretch your legs.",
  reminderContinue: "Keep going",
  reminderBreak: "Take a break",

  helpPrompt: "Is real-money gambling costing you more than you want it to?",
  helpLink: "Free, confidential help",

  // ----- account ------------------------------------------------------------
  accountTitle: "Your account",
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
    "Removes your email, password, name and messages, and signs you out everywhere. " +
    "This cannot be undone.",
  eraseConfirmLabel: "Enter your password to confirm",
  eraseConfirmGuest: "This guest account will be gone for good.",
  eraseButton: "Delete my account",
  erasing: "Deleting…",

  // ----- operator -----------------------------------------------------------
  adminBack: "← Back to the site",
  adminOverview: "Overview",
  adminPlayers: "Players",
  adminInbox: "Inbox",
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
    "Nothing is sold, so there is no revenue line. Points are granted free; at fair odds the " +
    "gap between staked and returned is luck and skill, and it is nobody's income.",
  adminGranted: "Granted free",
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
