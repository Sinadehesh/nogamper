
export type Money = {
  minor: number;
  display: string;
};

export type ApiError = {
  code: string;
  detail: string;
  market_id?: string;
};


export type UserProfile = {
  id: string;
  telegram_id: number;
  player_code: string;
  first_name: string;
  last_name: string | null;
  username: string | null;
  photo_url: string | null;
  balance: Money;
  streak_count: number;
  lifetime_staked: Money;
  lifetime_returned: Money;
  can_claim_daily: boolean;
  is_admin?: boolean;
  member_since: string;
  invite_link: string | null;
  referred_count: number;
  referral_earned: Money;
};


export type Probability = {
  yes: string;
  no: string;
  source: string;
  age_seconds: number;
  stale: boolean;
};

export type MarketBoost = {
  id: string;
  side: Side;
  multiplier: string;
  ends_at: string;
  remaining_stake: Money;
  max_stake_per_user: Money;
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
  boosts: MarketBoost[];
};

export type MarketPage = {
  markets: MarketSummary[];
  next_cursor: string | null;
  min_legs: number;
  max_legs: number;
  vig_rate: string;
  parlay_bonus_by_legs: string[];
  example_stake: Money;
  signup_bonus: Money;
  referral_bonus: Money;
};

export type Side = "YES" | "NO";


export type QuotedLeg = {
  market_id: string;
  question: string;
  category: string;
  side: Side;
  probability: string;
  fair_odds: string;
  locked_odds: string;
  boosted: boolean;
  boost_multiplier: string;
  lock_at: string;
};

export type InsuranceOffer = {
  available: boolean;
  selected: boolean;
  rate: string;
  premium: Money;
  covers_failed_legs: number;
  min_legs: number;
  unavailable_reason: string | null;
};

export type SlipQuote = {
  legs: QuotedLeg[];
  stake: Money;
  combined_odds: string;
  potential_payout: Money;
  gross_potential_payout: Money;
  payout_cap: Money;
  capped: boolean;
  uncapped: boolean;
  parlay_bonus: string;
  insurance: InsuranceOffer;
  total_cost: Money;
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
  has_insurance: boolean;
  insurance_premium: Money;
  total_cost: Money;
  settled_payout: Money;
  settlement_note: string | null;
  placed_at: string;
  settled_at: string | null;
};

export type SlipPage = {
  slips: Slip[];
  next_cursor: string | null;
};


export type ActivityEntry = {
  id: string;
  player: string;
  status: SlipStatus;
  leg_count: number;
  stake: Money;
  payout: Money;
  combined_odds: string;
  settled_at: string;
};

export type CoinPackage = {
  code: string;
  title: string;
  description: string;
  stars: number;
  coins: Money;
  bonus_coins: Money;
};

export type InvoiceIssued = {
  purchase_id: string;
  invoice_link: string;
  stars: number;
  coins: Money;
};


export type SlipSelection = {
  marketId: string;
  side: Side;
  question: string;
  category: string;
  eventId: string;
  lockAt: string;
};


export type RewardBlockedReason =
  | "reward_exhausted"
  | "already_claimed"
  | "not_enough_play"
  | "insufficient_funds";

export type RewardItem = {
  code: string;
  title: string;
  description: string;
  kind: string;
  image_url: string | null;
  cost: Money;
  min_lifetime_staked: Money;
  remaining: number | null;
  held_by_user: number;
  claimable: boolean;
  blocked_reason: RewardBlockedReason | null;
};

export type RewardCatalogue = {
  rewards: RewardItem[];
  balance: Money;
};

export type RewardClaimStatus =
  | "RESERVED"
  | "FULFILLED"
  | "FAILED"
  | "REFUNDED";

export type RewardClaim = {
  id: string;
  reward_code: string;
  title: string;
  kind: string;
  image_url: string | null;
  cost: Money;
  status: RewardClaimStatus;
  created_at: string;
  fulfilled_at: string | null;
  fulfilment: Record<string, unknown>;
};

export type RedeemResult = {
  claim_id: string;
  reward_code: string;
  title: string;
  cost: Money;
  balance: Money;
  status: "RESERVED";
};


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
  layer:
    | "healthy"
    | "degraded"
    | "discovery"
    | "worker"
    | "upstream"
    | "cache"
    | "capacity";
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

export type PlayerMessage = {
  id: string;
  kind: "MESSAGE" | "PRIZE_CLAIM";
  status: "NEW" | "SEEN" | "ANSWERED";
  body: string;
  created_at: string;
  answered_at: string | null;
  reply_body: string | null;
  replied_at: string | null;
};

export type PlayerRow = {
  id: string;
  player_code: string;
  telegram_id: number;
  username: string | null;
  display_name: string;
  status: "ACTIVE" | "RESTRICTED" | "SELF_EXCLUDED" | "BANNED";
  balance: Money;
  lifetime_stars: number;
  staked: Money;
  returned: Money;
  net: Money;
  bought: Money;
  granted: Money;
  adjusted: Money;
  slips: number;
  won: number;
  lost: number;
  open_slips: number;
  created_at: string;
  last_seen_at: string;
};

export type PlayerList = { players: PlayerRow[]; total: number };

export type InboxItem = PlayerMessage & {
  admin_note: string | null;
  reply_delivered: boolean;
  player_code: string;
  username: string | null;
  display_name: string;
  telegram_id: number;
  balance: Money;
  player_status: string;
};

export type Inbox = { messages: InboxItem[]; unread: number; total: number };

export type ReplyResult = {
  id: string;
  status: string;
  reply_body: string;
  replied_at: string;
  delivered: boolean;
  delivery_detail: string | null;
};

export type RevenueBlock = {
  stars_gross: number;
  stars_refunded: number;
  stars_net: number;
  purchases: number;
  refunds: number;
  paying_players: number;
  coins_sold: Money;
};

export type RevenueDay = {
  day: string;
  stars: number;
  stars_refunded: number;
  purchases: number;
  payers: number;
};

export type PackageSales = {
  code: string;
  title: string;
  stars_price: number;
  coins: Money;
  coins_per_star: number;
  purchases: number;
  stars: number;
  share_of_stars: number;
};

export type LedgerFlow = {
  entry_type: string;
  net: Money;
  entries: number;
  players: number;
};

export type EconomyBalance = {
  minted_free: Money;
  minted_purchased: Money;
  house_edge: Money;
  decayed: Money;
  burned_on_rewards: Money;
  net_change: Money;
};

export type BreakEvenBucket = {
  bucket: "far_below" | "below" | "at" | "above" | "far_above";
  players: number;
  daily_stake: Money;
};

export type PlayerBlock = {
  total: number;
  new_in_window: number;
  staked_in_window: number;
  claimed_in_window: number;
  conversion_rate: number;
};

export type EconomyReport = {
  window_days: number;
  since: string;
  generated_at: string;
  revenue: RevenueBlock;
  lifetime: RevenueBlock;
  stars_per_day: number;
  stars_per_paying_player: number;
  daily: RevenueDay[];
  packages: PackageSales[];
  players: PlayerBlock;
  ledger: LedgerFlow[];
  balance: EconomyBalance;
  break_even_daily_stake: Money;
  break_even_buckets: BreakEvenBucket[];
  free_players_share: number;
};
