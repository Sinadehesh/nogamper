
BEGIN;

DO $$
DECLARE
    open_slips INT;
    topped_up  INT;
BEGIN
    SELECT count(*) INTO open_slips FROM predictions WHERE status = 'PENDING';
    IF open_slips > 0 THEN
        RAISE NOTICE
            '% prediction(s) are still open and carry a pre-redenomination payout. '
            'They settle at the amount the player was shown, which is correct, but '
            'it is small against the new prices.', open_slips;
    END IF;

    WITH credited AS (
        INSERT INTO ledger_entries (user_id, entry_type, amount, idempotency_key, metadata)
        SELECT id,
               'ADMIN_ADJUSTMENT',
               coin_balance * 39,
               'redenomination:0009:' || id::TEXT,
               jsonb_build_object(
                   'reason', 'toman redenomination: balances rescaled x40 to match 0008 prices',
                   'factor', 40,
                   'balance_before', coin_balance
               )
          FROM users
         WHERE coin_balance > 0
        ON CONFLICT (user_id, idempotency_key) DO NOTHING
        RETURNING 1
    )
    SELECT count(*) INTO topped_up FROM credited;

    RAISE NOTICE 'redenomination top-up posted for % player(s)', topped_up;
END
$$;

UPDATE users
   SET daily_stake_limit = daily_stake_limit * 40
 WHERE daily_stake_limit IS NOT NULL;

UPDATE odds_boosts
   SET max_total_stake    = max_total_stake * 40,
       max_stake_per_user = max_stake_per_user * 40,
       consumed_stake     = consumed_stake * 40
 WHERE ends_at > NOW();

COMMIT;
