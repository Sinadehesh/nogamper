
BEGIN;

-- >>> SEED
UPDATE coin_packages SET
    title       = '۲۵٬۰۰۰٬۰۰۰ تومان',
    description = 'شروع سریع.',
    coins       = 2500000000,
    bonus_coins = 0
 WHERE code = 'TIER_1';

UPDATE coin_packages SET
    title       = '۸۲٬۵۰۰٬۰۰۰ تومان',
    description = 'محبوب‌ترین. ۱۰٪ هدیه.',
    coins       = 7500000000,
    bonus_coins = 750000000
 WHERE code = 'TIER_2';

UPDATE coin_packages SET
    title       = '۳۰۰٬۰۰۰٬۰۰۰ تومان',
    description = 'بهترین ارزش. ۲۰٪ هدیه.',
    coins       = 25000000000,
    bonus_coins = 5000000000
 WHERE code = 'TIER_3';

UPDATE rewards SET cost = cost * 125, min_lifetime_staked = min_lifetime_staked * 125;
-- <<< SEED

COMMIT;
