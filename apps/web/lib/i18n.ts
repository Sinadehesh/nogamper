
export const fa = {
  appName: "تومان پیش‌بینی",
  tagline:
    "نتیجهٔ رویدادهای اقتصادی و بازار رمزارز را حدس بزنید. رایگان است و پول واقعی در کار نیست.",
  greeting: (name: string) => `سلام ${name}`,
  coinsUnit: "تومان",
  balance: "موجودی",
  topUp: "افزایش موجودی",
  adminLink: "وضعیت برنامه",
  streak: (days: string) => `${days} روز پیاپی`,
  addMoreLegs: (more: string) => `${more} انتخاب دیگر اضافه کنید`,
  parlayOnlyHint: (needed: string) =>
    `هر برگه به کم‌ترین ${needed} انتخاب نیاز دارد؛ ضریب‌ها در هم ضرب می‌شوند.`,
  loading: "در حال بارگذاری…",

  tabMarkets: "بازارها",
  tabHistory: "پیش‌بینی‌های من",

  viewClosing: "نزدیک به بسته‌شدن",
  viewClosingHint: "زودترین مهلت در ابتدا",
  viewFavourites: "محتمل‌ترین‌ها",
  viewFavouritesHint: "نتایجی که احتمال وقوعشان بیشتر است",
  viewLongshots: "کم‌احتمال‌ها",
  viewLongshotsHint: "بیشترین ضریب، کمترین احتمال",
  viewBoosted: "ضریب ویژه",
  viewBoostedHint: "بازارهایی با ضریب ویژهٔ فعال",
  viewBusiest: "پرمعامله‌ترین‌ها",
  viewBusiestHint: "بیشترین حجم معاملات در منبع",

  categoryAll: "همه",
  categoryIran: "ایران",
  categoryMacro: "کلان‌اقتصاد",
  categoryCrypto: "رمزارز",
  categoryPolitics: "سیاست",

  marketsEmpty: "در این نما فعلاً بازاری وجود ندارد.",
  marketsLoading: "در حال دریافت بازارها…",
  closesIn: (duration: string) => `${duration} تا بسته‌شدن`,
  closed: "بسته شد",
  priceUpdating: "در حال به‌روزرسانی قیمت",
  sideYes: "بله",
  sideNo: "خیر",
  boosted: "ضریب ویژه",
  boostEndsIn: (duration: string) => `تا ${duration} دیگر`,

  chance: "شانس",
  oddsLabel: "ضریب",
  chanceSplit: (yes: string, no: string) => `شانس بله ${yes}، شانس خیر ${no}`,
  marketSays: "نظر بازار",
  closingSoon: "به‌زودی بسته می‌شود",

  activityWon: "برد",
  activityRefunded: "بازگشت مبلغ",
  activityLost: "باخت",
  activityOn: (legs: string) => `روی ${legs} انتخاب`,

  slipTitle: "برگهٔ پیش‌بینی",
  slipLegCount: (count: string, max: string) => `${count} از ${max} انتخاب`,
  slipOpenBar: (count: string) => `${count} انتخاب در برگهٔ شما`,
  slipBarUnlock: (more: string) => `${more} انتخاب دیگر تا ضریب کامل`,
  slipReview: "بررسی",
  close: "بستن",
  removeLeg: "حذف انتخاب",
  slipFull: (max: string) =>
    `برگه پر شد؛ هر ${max} انتخاب باید درست از آب دربیاید.`,
  slipTradeoff: "هر انتخاب، ضریب شما را چند برابر می‌کند",

  stakeBecomes: (stake: string, payout: string) =>
    `${stake} تومان تبدیل می‌شود به ${payout} تومان`,
  unlockMultiplier: (more: string) =>
    `${more} انتخاب مانده تا ضریب کامل فعال شود`,
  noCeiling: "بی‌سقف؛ هر مقدار که ببرید تمام‌وکمال پرداخت می‌شود",
  multiplierNow: (times: string) => `ضریب فعلی: ${times} برابر`,

  goldenKeyOn: (percent: string) => `کلید طلایی: ${percent}٪ بیشتر`,
  goldenKeyLocked: "با یک انتخاب دیگر کلید طلایی فعال می‌شود",
  goldenKeyNext: (percent: string) => `یک انتخاب دیگر: ${percent}٪ بیشتر`,

  keepPicking: "🔑 انتخاب بعدی را اضافه کنید",
  exampleWin: (stake: string, payout: string) =>
    `با ${stake} تومان: ${payout} تومان`,

  biggestMultiplier: "🔑 بزرگ‌ترین ضریب را برایم بساز",

  priceAnchors: [
    { at: 200_000_000_000, label: "خانه در بهترین محلهٔ شهر" },
    { at: 40_000_000_000, label: "خودروی لوکس" },
    { at: 25_000_000_000, label: "ویلای ساحلی" },
    { at: 18_800_000_000, label: "آپارتمان ۸۰ متری" },
    { at: 12_000_000_000, label: "خودروی خارجی" },
    { at: 1_800_000_000, label: "خودروی صفر داخلی" },
    { at: 1_100_000_000, label: "خودروی اقتصادی صفر" },
    { at: 900_000_000, label: "سفر زیارتی" },
    { at: 750_000_000, label: "خودروی کارکرده" },
    { at: 277_000_000, label: "گوشی پرچم‌دار" },
    { at: 264_000_000, label: "موتورسیکلت" },
    { at: 200_000_000, label: "سفر خارجی" },
    { at: 186_500_000, label: "سکهٔ تمام طلا" },
    { at: 150_000_000, label: "بلیت رفت‌وبرگشت خارجی" },
    { at: 98_000_000, label: "کنسول بازی" },
    { at: 90_000_000, label: "لپ‌تاپ" },
    { at: 70_000_000, label: "یخچال فریزر" },
    { at: 60_000_000, label: "تلویزیون ۵۵ اینچ" },
    { at: 45_000_000, label: "ماشین لباسشویی" },
    { at: 30_000_000, label: "دوچرخه" },
    { at: 18_000_000, label: "گرم طلا" },
    { at: 12_000_000, label: "ماه اجارهٔ خانه" },
    { at: 8_000_000, label: "دست کت و شلوار" },
    { at: 5_000_000, label: "جفت کفش ورزشی" },
    { at: 2_500_000, label: "کیسه برنج پنج کیلویی" },
    { at: 1_800_000, label: "کیلو گوشت گوساله" },
    { at: 1_200_000, label: "پرس چلوکباب" },
    { at: 640_000, label: "شانه تخم‌مرغ" },
    { at: 570_000, label: "کیلو برنج مرغوب" },
    { at: 350_000, label: "ماه اینترنت موبایل" },
    { at: 250_000, label: "بلیت سینما" },
    { at: 99_000, label: "کیلو نارنگی" },
    { at: 69_000, label: "کیلو خیار" },
    { at: 15_500, label: "نان سنگک" },
    { at: 10_000, label: "نان بربری" },
    { at: 2_700, label: "نان لواش" },
  ] as { at: number; label: string }[],
  worthBeyond: "به اندازهٔ یک کوچهٔ پر از خانه در بالای شهر",

  worthAbout: (count: string, thing: string) => `به اندازهٔ ${count} ${thing}`,
  biggestMultiplierWin: (stake: string, payout: string) =>
    `${stake} تومان → ${payout} تومان`,

  stake: "مبلغ",
  stakePercent: (percent: string) => `${percent}٪`,
  stakeMax: "بیشترین",
  combinedOdds: "ضریب کل",
  toWin: "برد احتمالی",
  cover: "حق بیمه",
  cappedAt: (amount: string) => `سقف برد ${amount} تومان اعمال شد.`,

  placePrediction: (amount: string) => `ثبت پیش‌بینی · ${amount}`,
  placeAndTopUp: (amount: string) => `افزایش موجودی و ثبت · ${amount}`,
  placing: "در حال ثبت…",
  allLegsMustWin: (count: string) => `هر ${count} انتخاب باید برنده شود.`,

  insuranceTitleOne: (refund: string) =>
    `با یک انتخاب اشتباه، ${refund} تومان به شما بازمی‌گردد`,
  insuranceTitleMany: (count: string, refund: string) =>
    `تا ${count} انتخاب اشتباه، ${refund} تومان به شما بازمی‌گردد`,
  insuranceBody: (premium: string) =>
    `${premium} تومان — فقط اصل مبلغ بازمی‌گردد، نه برد.`,

  discardTitle: "این برگه حذف شود؟",
  discardBody: (count: string) =>
    `${count} انتخاب ثبت‌شدهٔ شما پاک می‌شود.`,
  discardKeep: "نگه‌داشتن و ادامهٔ مرور",
  discardBack: "بازگشت به برگه",
  discardConfirm: "حذف",

  historyAll: "همه",
  historyOpen: "باز",
  historyWon: "برنده",
  historyLost: "بازنده",
  historyEmpty:
    "اینجا هنوز خالی است. هر پیش‌بینی که ثبت کنید همراه نتیجه‌اش در همین صفحه می‌نشیند.",

  statusPending: "باز",
  statusWon: "برنده",
  statusLost: "بازنده",
  statusInsured: "مبلغ بازگشت",
  statusVoid: "باطل",

  slipSingle: "تکی",
  slipParlay: (count: string) => `شرط ترکیبی ${count} انتخابی`,
  slipStakeAtOdds: (stakeAmount: string, oddsValue: string) =>
    `${stakeAmount} با ضریب ${oddsValue}`,

  pendingProgress: (settled: string, total: string, payout: string) =>
    `${settled} از ${total} مشخص شد · اگر همهٔ انتخاب‌ها بگیرد ${payout} بازمی‌گردد`,
  paidOut: "پرداخت شد",
  insuredHeadline: "اصل مبلغ با بیمه بازگشت",
  insuredDetail: (lost: string, premium: string) =>
    `${lost} انتخاب نگرفت. حق بیمهٔ ${premium} بازنمی‌گردد.`,
  voidFallback: "در مرجع باطل اعلام شد؛ اصل مبلغ به شما بازگشت.",
  lostSummary: (won: string, total: string) =>
    `${won} انتخاب از ${total} درست بود.`,
  lostInsuranceOne:
    "بیمه فعال نشد؛ پرداخت بیمه تنها با یک انتخاب بازنده انجام می‌شود.",
  lostInsuranceMany:
    "بیمه فعال نشد؛ شمار انتخاب‌های بازنده از سقف پوشش گذشت.",
  stakeLost: "مبلغ از دست رفته",

  topUpTitle: "افزایش موجودی",
  topUpShortfall: (amount: string) => `برای این برگه ${amount} تومان کم دارید.`,
  topUpGeneric: "با استارز تلگرام تومان پیش‌بینی بخرید.",
  packageCoins: (amount: string) => `${amount} تومان`,
  packageBonus: (amount: string) => `شامل ${amount} تومان هدیه`,
  packageInsufficient: " · برای این برگه کافی نیست",
  buyWithStars: "خرید با استارز",
  openingTelegram: "در حال باز کردن تلگرام…",
  notNow: "فعلاً نه",
  starsDisclaimer:
    "تومان پیش‌بینی تنها واحد درون‌بازی است و به پول واقعی ربطی ندارد؛ نه برداشت می‌شود، نه انتقال، نه تبدیل به پول.",
  paymentFailed: "پرداخت انجام نشد.",
  paymentUnsupported:
    "برای خرید درون برنامه، نسخهٔ تلگرام خود را تازه کنید.",

  tabRewards: "جایزه‌ها",

  tabPrize: "جایزهٔ من",
  prizeTitle: "جایزهٔ من",
  prizeIntro:
    "برنده شده‌اید یا پرسشی دارید؟ از همین‌جا بنویسید؛ پاسخ در تلگرام به دستتان می‌رسد.",
  prizeCodeLabel: "کد شما",
  prizeCodeHint: "این کد را در پیام بیاورید تا حسابتان را پیدا کنیم.",
  prizeCodeCopied: "کپی شد",
  prizeTelegramIdLabel: "شناسهٔ تلگرام شما",
  prizeReplyLabel: "پاسخ ما",

  inviteTitle: "دوستت رو دعوت کن",
  inviteBody: (amount: string) =>
    `دوستت با لینک تو بیاد و اولین برگه‌شو ببنده، ${amount} تومان به تو می‌رسه.`,
  inviteShare: "دعوت کن",
  inviteCopyLink: "کپی لینک",
  inviteLinkCopied: "لینک کپی شد",
  inviteStatsReferred: (count: string) => `${count} دوست پیوسته`,
  inviteStatsEarned: (amount: string) => `${amount} تومان گرفتی`,
  inviteBannerHeadline: (signupBonus: string) =>
    `دوستتو دعوت کن تا ${signupBonus} تومان رایگان بگیره`,
  inviteBannerSub: (referralBonus: string) =>
    `اولین برگه‌شو که بست، ${referralBonus} تومان به تو می‌رسه`,

  inviteShareText: (signupBonus: string, referralBonus: string) =>
    `اینجا ${signupBonus} تومان رایگان گرفتم! تو هم با لینک من ثبت‌نام کن ` +
    `تا با بستن اولین برگه‌ات ${referralBonus} تومان هم به من برسه 🎁`,
  prizePlaceholder: "پیام‌تان را بنویسید…",
  prizeSend: "ارسال پیام",
  prizeSending: "در حال ارسال…",
  prizeSent: "پیامتان ثبت شد. پاسخ را به‌زودی در تلگرام می‌فرستیم.",
  prizeEmpty: "هنوز پیامی نفرستاده‌اید.",
  prizeHistory: "پیام‌های شما",
  prizeStatusNew: "در انتظار بررسی",
  prizeStatusSeen: "دیده شد",
  prizeStatusAnswered: "پاسخ داده شد",
  prizeKindClaim: "درخواست جایزه",
  prizeKindMessage: "پیام",
  prizeAsClaim: "این یک درخواست جایزه است",
  prizeNoValueNote:
    "جایزه‌ها جنبهٔ یادگاری دارند و ارزش مالی ندارند؛ نه فروختنی‌اند و نه تبدیل‌شدنی به پول.",
  rewardsTitle: "جایزه‌ها",
  rewardsIntro:
    "تومان خود را خرج کنید و جایزه بگیرید؛ این مبلغ کسر می‌شود و بازنمی‌گردد.",
  rewardsEmpty: "فعلاً جایزه‌ای برای دریافت وجود ندارد.",
  rewardsLoading: "در حال دریافت جایزه‌ها…",
  rewardCost: (amount: string) => `${amount} تومان`,
  rewardRemaining: (count: string) => `${count} عدد باقی مانده`,
  rewardUnlimited: "بدون محدودیت تعداد",
  rewardOwned: (count: string) => `${count} عدد دریافت کرده‌اید`,
  rewardRedeem: "دریافت جایزه",
  rewardRedeeming: "در حال ثبت…",

  rewardBlockedFunds: "موجودی کافی ندارید",
  rewardBlockedPlay: "باید بیشتر بازی کنید",
  rewardBlockedClaimed: "قبلاً دریافت کرده‌اید",
  rewardBlockedGone: "ظرفیت تمام شد",
  rewardNeedStaked: (amount: string) =>
    `با رسیدن به ${amount} تومان پیش‌بینی باز می‌شود`,

  rewardConfirmTitle: "دریافت این جایزه؟",
  rewardConfirmBody: (cost: string, balance: string) =>
    `${cost} تومان از موجودی کسر می‌شود و بازنمی‌گردد. ` +
    `موجودی شما پس از آن ${balance} تومان می‌شود.`,
  rewardConfirmYes: "بله، دریافت کن",
  rewardConfirmNo: "انصراف",

  rewardClaimedTitle: "ثبت شد",
  rewardClaimedBody: "جایزه‌تان ثبت شد و به‌زودی به دستتان می‌رسد.",
  myRewards: "جایزه‌های من",
  rewardStatusReserved: "در انتظار تحویل",
  rewardStatusFulfilled: "تحویل شد",
  rewardStatusFailed: "تحویل ناموفق",
  rewardStatusRefunded: "مبلغ بازگشت",

  errorNetwork: "اتصال به سرور برقرار نشد. شبکهٔ خود را بررسی کنید.",
  errorGeneric: "مشکلی پیش آمد.",
  errorSessionTitle: "شروع نشست ممکن نشد",
  errorSessionExpired:
    "نشست شما به پایان رسید. برنامه را ببندید و از تلگرام دوباره بازش کنید.",
  retry: "تلاش دوباره",
  errorNotInTelegram: "برای بازی، برنامه را از درون تلگرام باز کنید.",
  errorBootstrap: "هنگام راه‌اندازی برنامه مشکلی پیش آمد.",
} as const;

const ERROR_CODES: Record<string, string> = {
  insufficient_funds: "موجودی ناکافی",
  odds_moved:
    "ضریب این بازار جابه‌جا شد. برای ثبت با ضریب تازه دوباره تأیید کنید.",
  price_stale: "قیمت این بازار دارد تازه می‌شود. لحظه‌ای بعد دوباره امتحان کنید.",
  market_not_open: "این بازار دیگر پیش‌بینی نمی‌پذیرد.",
  market_locked: "زمان پیش‌بینی روی این بازار تمام شده است.",
  correlated_legs: "دو انتخاب از یک رویداد در یک برگه جا نمی‌شوند.",
  duplicate_market: "یک بازار دو بار در یک برگه نمی‌آید.",
  stake_too_small: "مبلغ واردشده از حداقل مجاز کمتر است.",
  stake_too_large: "مبلغ واردشده از حداکثر مجاز بیشتر است.",
  too_many_legs: "هر برگه حداکثر پنج انتخاب می‌پذیرد.",
  too_few_legs: "برای بستن برگه انتخاب بیشتری لازم است.",
  too_many_messages:
    "پیام‌ها را پشت‌سرهم فرستاده‌اید. کمی بعد دوباره امتحان کنید.",
  message_too_long: "پیام خیلی طولانی است.",
  empty_message: "اول چیزی بنویسید.",
  leg_unpriceable:
    "احتمال این نتیجه چنان بالاست که ضریبی برایش گذاشته نمی‌شود.",
  odds_exceed_maximum: "ضریب کل این برگه از سقف مجاز بیشتر است.",
  market_at_capacity: "این بازار فعلاً پیش‌بینی تازه نمی‌پذیرد.",
  boost_exhausted: "ظرفیت ضریب ویژهٔ این بازار تمام شد.",
  boost_limit_reached: "ضریب ویژهٔ این بازار برای هر حساب سقف دارد.",
  insurance_unavailable: "برای این برگه بیمه ارائه نمی‌شود.",
  account_restricted: "این حساب فعلاً نمی‌تواند پیش‌بینی ثبت کند.",
  daily_limit_reached: "این مبلغ از سقف روزانهٔ حساب شما فراتر می‌رود.",
  unknown_package: "چنین بسته‌ای وجود ندارد.",
  too_many_open_invoices:
    "پیش از خرید تازه، خریدهای باز را تمام یا رها کنید.",
  invoice_unavailable:
    "تلگرام این فاکتور را نساخت. کمی بعد دوباره امتحان کنید.",
  network_unavailable: fa.errorNetwork,
  init_data_expired: fa.errorSessionExpired,
  init_data_future: "ساعت دستگاه شما با سرور هم‌خوان نیست.",
  init_data_malformed:
    "داده‌های ورود تلگرام خوانده نشد. برنامه را دوباره باز کنید.",
  session_expired: fa.errorSessionExpired,
  session_revoked: fa.errorSessionExpired,
  session_unknown: fa.errorSessionExpired,
};

export function translateError(code: string, fallback: string): string {
  return ERROR_CODES[code] ?? fallback;
}

export const CATEGORIES = ["Iran", "Macro", "Crypto", "Politics"] as const;

/** The tab the feed opens on. Must be one of CATEGORIES, or undefined for all. */
export const DEFAULT_CATEGORY: (typeof CATEGORIES)[number] | undefined = "Iran";

const CATEGORY_LABELS: Record<string, string> = {
  Iran: fa.categoryIran,
  Macro: fa.categoryMacro,
  Crypto: fa.categoryCrypto,
  Politics: fa.categoryPolitics,
};

export function categoryLabel(category: string): string {
  return CATEGORY_LABELS[category] ?? category;
}
