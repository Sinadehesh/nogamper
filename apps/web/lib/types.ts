/** Wire types. Mirrors apps/api/backend/schemas.py — change them together. */

export type Money = {
  minor: number;
  display: string;
};

export type Limits = {
  daily_limit: Money | null;
  daily_spent: Money;
  daily_limit_loosen_at: string | null;
  break_until: string | null;
  break_options_hours: number[];
};

export type UserProfile = {
  id: string;
  player_code: string;
  display_name: string;
  email: string | null;
  is_guest: boolean;
  balance: Money;
  lifetime_staked: Money;
  lifetime_returned: Money;
  can_claim_daily: boolean;
  daily_topup: Money;
  next_claim_at: string | null;
  member_since: string;
  is_admin: boolean;
  limits: Limits;
  session_expires_at: string;
};

export type Side = "YES" | "NO";

export type Probability = {
  yes: string;
  no: string;
  source: string;
  age_seconds: number;
  stale: boolean;
};

export type MarketSummary = {
  id: string;
  question: string;
  description: string | null;
  category: string;
  image_url: string | null;
  event: { id: string; title: string; slug: string | null };
  probability: Probability;
  liquidity_usd: string;
  volume_usd: string;
  lock_at: string;
  end_date: string;
};

export type MarketRules = {
  max_legs: number;
  min_prob: string;
  max_prob: string;
  max_combined_odds: string;
  min_stake: Money;
  max_stake: Money;
  payout_cap: Money;
};

/** GET /v1/rules — public, and what the explainer pages are rendered from. */
export type GameRules = {
  signup_bonus: Money;
  daily_topup: Money;
  min_stake: Money;
  max_stake: Money;
  payout_cap: Money;
  max_legs: number;
  max_combined_odds: string;
  min_prob: string;
  max_prob: string;
  margin: "0";
  reference_margin: string;
  limit_loosen_delay_hours: number;
  break_options_hours: number[];
  password_min_length: number;
};

export type MarketSort = "tossup" | "closing" | "volume";

export type MarketPage = MarketRules & {
  markets: MarketSummary[];
  next_cursor: string | null;
  categories: string[];
};

export type QuotedLeg = {
  market_id: string;
  question: string;
  category: string;
  side: Side;
  probability: string;
  locked_odds: string;
  lock_at: string;
};

export type SlipQuote = {
  legs: QuotedLeg[];
  stake: Money;
  combined_odds: string;
  win_probability: string;
  potential_payout: Money;
  gross_potential_payout: Money;
  payout_cap: Money;
  capped: boolean;
};

export type SlipStatus = "PENDING" | "WON" | "LOST" | "INSURED" | "VOID";
export type LegStatus = "PENDING" | "WON" | "LOST" | "VOID";

export type SettledLeg = {
  leg_index: number;
  market_id: string;
  question: string;
  side: Side;
  locked_odds: string;
  status: LegStatus;
  resolution: string | null;
  lock_at: string;
};

export type Slip = {
  id: string;
  type: "SINGLE" | "PARLAY";
  status: SlipStatus;
  legs: SettledLeg[];
  stake: Money;
  combined_odds: string;
  potential_payout: Money;
  capped: boolean;
  total_cost: Money;
  settled_payout: Money;
  placed_at: string;
  settled_at: string | null;
};

export type SlipPage = {
  slips: Slip[];
  next_cursor: string | null;
};

/** A pick held in the page before it is sent anywhere. */
export type SlipSelection = {
  marketId: string;
  side: Side;
  question: string;
  category: string;
  eventId: string;
  lockAt: string;
};

export type ClaimResult = {
  claim_date: string;
  amount: Money;
  balance: Money;
  next_claim_at: string;
};

export type LeaderboardRow = {
  rank: number | null;
  player: string;
  slips_settled: number;
  slips_won: number;
  total_staked: Money;
  net_profit: Money;
  best_odds: string | null;
  is_me: boolean;
};

export type Leaderboard = {
  season: string;
  ends_at: string;
  min_volume_to_rank: Money;
  rows: LeaderboardRow[];
  my_rank: number | null;
  my_net_profit: Money;
  my_total_staked: Money;
};

export type CalibrationBucket = {
  low: string;
  high: string;
  picks: number;
  correct: number;
  expected: string | null;
};

export type RealityCheck = {
  member_since: string;
  slips_placed: number;
  slips_open: number;
  slips_settled: number;
  slips_won: number;
  slips_lost: number;
  picks_settled: number;
  picks_correct: number;
  staked: Money;
  returned: Money;
  net: Money;
  reference_margin: string;
  margin_cost: Money;
  net_with_margin: Money;
  active_days_30d: number;
  slips_30d: number;
  calibration: CalibrationBucket[];
};

export type PlayerMessage = {
  id: string;
  kind: string;
  status: "NEW" | "SEEN" | "ANSWERED";
  body: string;
  created_at: string;
  answered_at: string | null;
  reply_body: string | null;
  replied_at: string | null;
};

// ----- articles -------------------------------------------------------------

/** A reader's published article, as a listing shows it. */
export type PublishedArticleSummary = {
  slug: string;
  title: string;
  summary: string;
  author: string;
  published_at: string;
  edited_at: string;
  reading_minutes: number;
};

export type PublishedArticle = PublishedArticleSummary & { body: string };

export type PublishedArticlePage = { articles: PublishedArticleSummary[]; total: number };

export type ArticleStatus = "DRAFT" | "SUBMITTED" | "PUBLISHED" | "REJECTED" | "REMOVED";

/** An author's own article, in whatever state it is in. */
export type MyArticle = {
  id: string;
  slug: string;
  title: string;
  summary: string;
  body: string;
  status: ArticleStatus;
  review_note: string | null;
  reading_minutes: number;
  created_at: string;
  edited_at: string;
  submitted_at: string | null;
  published_at: string | null;
};

export type ArticleLimits = {
  title_min: number;
  title_max: number;
  summary_min: number;
  summary_max: number;
  body_min: number;
  body_max: number;
  max_open: number;
};

export type MyArticles = {
  articles: MyArticle[];
  limits: ArticleLimits;
  can_write: boolean;
  publishes_directly: boolean;
};

export type ArticleDraft = { title: string; summary: string; body: string };

export type QueuedArticle = MyArticle & { author: string; author_code: string };

export type ArticleQueue = { articles: QueuedArticle[]; waiting: number; live: number };

export type ReviewDecision = "publish" | "reject" | "remove";

// ----- operator -------------------------------------------------------------

export type LedgerFlow = {
  entry_type: string;
  net: Money;
  entries: number;
  players: number;
};

export type Overview = {
  window_days: number;
  since: string;
  generated_at: string;
  players: {
    total: number;
    registered: number;
    guests: number;
    new_in_window: number;
    forecast_in_window: number;
    claimed_in_window: number;
  };
  forecasts: { placed: number; settled: number; won: number; lost: number; open: number };
  points: { granted: Money; staked: Money; returned: Money; adjusted: Money; net_change: Money };
  safer_play: { with_daily_limit: number; on_break: number; erased: number };
  daily: { day: string; new_players: number; forecasts: number; forecasters: number }[];
  ledger: LedgerFlow[];
};

export type PlayerRow = {
  id: string;
  player_code: string;
  display_name: string;
  email: string | null;
  is_guest: boolean;
  status: "ACTIVE" | "RESTRICTED" | "SELF_EXCLUDED" | "BANNED";
  balance: Money;
  staked: Money;
  returned: Money;
  net: Money;
  granted: Money;
  adjusted: Money;
  slips: number;
  won: number;
  lost: number;
  open_slips: number;
  daily_limit: Money | null;
  break_until: string | null;
  created_at: string;
  last_seen_at: string;
};

export type PlayerList = { players: PlayerRow[]; total: number };

export type InboxItem = PlayerMessage & {
  admin_note: string | null;
  player_code: string;
  display_name: string;
  is_guest: boolean;
  balance: Money;
  player_status: string;
};

export type Inbox = { messages: InboxItem[]; unread: number; total: number };

export type JobLease = {
  job_name: string;
  holder: string | null;
  held_for_seconds: number;
  expires_in_seconds: number;
};

export type JobRun = {
  job_name: string;
  outcome: "ok" | "error" | "deadline";
  duration_seconds: number;
  finished_ago_seconds: number;
  holder: string | null;
  detail: Record<string, unknown>;
};

export type Diagnostics = {
  layer: "healthy" | "degraded" | "discovery" | "worker" | "upstream" | "cache" | "capacity";
  advice: string;
  staleness_threshold_seconds: number;
  markets_budget: number;
  markets_total: number;
  markets_active: number;
  markets_locked: number;
  markets_fresh: number;
  markets_stale: number;
  newest_price_at: string | null;
  oldest_price_at: string | null;
  seconds_since_newest: number | null;
  cache_reachable: boolean;
  cache_sampled: number;
  cache_hits: number;
  leases: JobLease[];
  runs: JobRun[];
  generated_at: string;
};
