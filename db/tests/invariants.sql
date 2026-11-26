\set ON_ERROR_STOP on
BEGIN;

INSERT INTO users (id, telegram_id, first_name)
VALUES ('11111111-1111-1111-1111-111111111111', 900001, 'Alice');

INSERT INTO ledger_entries (user_id, entry_type, amount, idempotency_key)
VALUES ('11111111-1111-1111-1111-111111111111', 'SIGNUP_BONUS_CREDIT', 100000, 'signup:900001');

INSERT INTO market_events (id, polymarket_event_id, title, category) VALUES
  ('e0000000-0000-0000-0000-00000000000a', 'evt-a', 'Fed September decision', 'Macro'),
  ('e0000000-0000-0000-0000-00000000000b', 'evt-b', 'BTC year-end level',      'Crypto'),
  ('e0000000-0000-0000-0000-00000000000c', 'evt-c', 'US CPI print',            'Macro');

INSERT INTO markets (id, event_id, polymarket_market_id, condition_id, question, category,
                     yes_token_id, no_token_id, raw_yes_prob, lock_at, end_date, status) VALUES
  ('a0000000-0000-0000-0000-00000000000a','e0000000-0000-0000-0000-00000000000a','pm-a1','c-a1','Fed cuts 25bp?','Macro','y-a1','n-a1',0.50, NOW()+INTERVAL '2 days', NOW()+INTERVAL '3 days','ACTIVE'),
  ('a0000000-0000-0000-0000-00000000000d','e0000000-0000-0000-0000-00000000000a','pm-a2','c-a2','Fed cuts 50bp?','Macro','y-a2','n-a2',0.10, NOW()+INTERVAL '2 days', NOW()+INTERVAL '3 days','ACTIVE'),
  ('a0000000-0000-0000-0000-00000000000b','e0000000-0000-0000-0000-00000000000b','pm-b1','c-b1','BTC above 150k?','Crypto','y-b1','n-b1',0.35, NOW()+INTERVAL '2 days', NOW()+INTERVAL '3 days','ACTIVE'),
  ('a0000000-0000-0000-0000-00000000000c','e0000000-0000-0000-0000-00000000000c','pm-c1','c-c1','CPI above 3%?','Macro','y-c1','n-c1',0.60, NOW()+INTERVAL '2 days', NOW()+INTERVAL '3 days','ACTIVE');

\echo '1. Ledger drives the cached balance'
DO $$
DECLARE v BIGINT;
BEGIN
    SELECT coin_balance INTO v FROM users WHERE telegram_id = 900001;
    IF v <> 100000 THEN RAISE EXCEPTION 'FAIL: balance % <> 100000', v; END IF;
    IF EXISTS (SELECT 1 FROM v_balance_reconciliation) THEN
        RAISE EXCEPTION 'FAIL: reconciliation drift after signup';
    END IF;
END $$;

\echo '2. Overdraft is refused with SQLSTATE PT001'
DO $$
BEGIN
    BEGIN
        INSERT INTO ledger_entries (user_id, entry_type, amount, idempotency_key)
        VALUES ('11111111-1111-1111-1111-111111111111', 'STAKE_DEBIT', -100001, 'overdraft-probe');
        RAISE EXCEPTION 'FAIL: overdraft was accepted';
    EXCEPTION WHEN SQLSTATE 'PT001' THEN
        NULL;  -- expected
    END;
END $$;

\echo '3. Replayed ledger idempotency key is rejected'
DO $$
BEGIN
    BEGIN
        INSERT INTO ledger_entries (user_id, entry_type, amount, idempotency_key)
        VALUES ('11111111-1111-1111-1111-111111111111', 'SIGNUP_BONUS_CREDIT', 100000, 'signup:900001');
        RAISE EXCEPTION 'FAIL: duplicate idempotency key accepted';
    EXCEPTION WHEN unique_violation THEN
        NULL;  -- expected
    END;
END $$;

\echo '4. The ledger is append-only'
DO $$
BEGIN
    BEGIN
        UPDATE ledger_entries SET amount = 999999 WHERE idempotency_key = 'signup:900001';
        RAISE EXCEPTION 'FAIL: ledger row was mutable';
    EXCEPTION WHEN SQLSTATE 'PT003' THEN
        NULL;  -- expected
    END;
    BEGIN
        DELETE FROM ledger_entries WHERE idempotency_key = 'signup:900001';
        RAISE EXCEPTION 'FAIL: ledger row was deletable';
    EXCEPTION WHEN SQLSTATE 'PT003' THEN
        NULL;  -- expected
    END;
END $$;

\echo '5. A winning 2-leg parlay settles once, at capped odds'
INSERT INTO predictions (id, user_id, idempotency_key, request_fingerprint, type, leg_count,
                         stake, combined_odds, gross_potential_payout, payout_cap, potential_payout,
                         house_edge_bps)
VALUES ('d0000000-0000-0000-0000-000000000001','11111111-1111-1111-1111-111111111111',
        'slip-win-1','fp1','PARLAY',2, 10000, 3.61, 36100, 500000000, 36100, 975);

INSERT INTO ledger_entries (user_id, entry_type, amount, ref_type, ref_id, idempotency_key)
VALUES ('11111111-1111-1111-1111-111111111111','STAKE_DEBIT',-10000,'PREDICTION',
        'd0000000-0000-0000-0000-000000000001','stake:d0000000-0000-0000-0000-000000000001');

INSERT INTO prediction_legs (prediction_id, leg_index, market_id, event_id, side, raw_prob, vig_rate, locked_odds) VALUES
  ('d0000000-0000-0000-0000-000000000001',1,'a0000000-0000-0000-0000-00000000000a','e0000000-0000-0000-0000-00000000000a','YES',0.50,0.05,1.90),
  ('d0000000-0000-0000-0000-000000000001',2,'a0000000-0000-0000-0000-00000000000b','e0000000-0000-0000-0000-00000000000b','NO', 0.65,0.05,1.90);

DO $$
DECLARE v_status slip_status; v_bal BIGINT; v_entries INT;
BEGIN
    IF fn_settle_prediction('d0000000-0000-0000-0000-000000000001') <> 'PENDING' THEN
        RAISE EXCEPTION 'FAIL: settled a slip with open legs';
    END IF;

    UPDATE prediction_legs SET status = 'WON', settled_at = NOW()
     WHERE prediction_id = 'd0000000-0000-0000-0000-000000000001';

    v_status := fn_settle_prediction('d0000000-0000-0000-0000-000000000001');
    IF v_status <> 'WON' THEN RAISE EXCEPTION 'FAIL: status % <> WON', v_status; END IF;

    SELECT coin_balance INTO v_bal FROM users WHERE telegram_id = 900001;
    IF v_bal <> 126100 THEN RAISE EXCEPTION 'FAIL: balance % <> 126100', v_bal; END IF;

    PERFORM fn_settle_prediction('d0000000-0000-0000-0000-000000000001');
    PERFORM fn_settle_prediction('d0000000-0000-0000-0000-000000000001');
    SELECT coin_balance INTO v_bal FROM users WHERE telegram_id = 900001;
    IF v_bal <> 126100 THEN RAISE EXCEPTION 'FAIL: double payout, balance %', v_bal; END IF;

    SELECT COUNT(*) INTO v_entries FROM ledger_entries
     WHERE ref_id = 'd0000000-0000-0000-0000-000000000001' AND entry_type = 'PAYOUT_CREDIT';
    IF v_entries <> 1 THEN RAISE EXCEPTION 'FAIL: % payout entries', v_entries; END IF;
END $$;

\echo '6. Correlated legs from one event are impossible'
INSERT INTO predictions (id, user_id, idempotency_key, request_fingerprint, type, leg_count,
                         stake, combined_odds, gross_potential_payout, payout_cap, potential_payout)
VALUES ('d0000000-0000-0000-0000-000000000002','11111111-1111-1111-1111-111111111111',
        'slip-corr','fp2','PARLAY',2, 10000, 3.61, 36100, 500000000, 36100);

INSERT INTO prediction_legs (prediction_id, leg_index, market_id, event_id, side, raw_prob, vig_rate, locked_odds)
VALUES ('d0000000-0000-0000-0000-000000000002',1,'a0000000-0000-0000-0000-00000000000a','e0000000-0000-0000-0000-00000000000a','YES',0.50,0.05,1.90);

DO $$
BEGIN
    BEGIN
        INSERT INTO prediction_legs (prediction_id, leg_index, market_id, event_id, side, raw_prob, vig_rate, locked_odds)
        VALUES ('d0000000-0000-0000-0000-000000000002',2,'a0000000-0000-0000-0000-00000000000d','e0000000-0000-0000-0000-00000000000a','YES',0.10,0.05,9.50);
        RAISE EXCEPTION 'FAIL: correlated same-event leg accepted';
    EXCEPTION WHEN unique_violation THEN NULL; END;

    BEGIN
        INSERT INTO prediction_legs (prediction_id, leg_index, market_id, event_id, side, raw_prob, vig_rate, locked_odds)
        VALUES ('d0000000-0000-0000-0000-000000000002',2,'a0000000-0000-0000-0000-00000000000a','e0000000-0000-0000-0000-00000000000a','NO',0.50,0.05,1.90);
        RAISE EXCEPTION 'FAIL: duplicate market leg accepted';
    EXCEPTION WHEN unique_violation THEN NULL; END;

    BEGIN
        INSERT INTO prediction_legs (prediction_id, leg_index, market_id, event_id, side, raw_prob, vig_rate, locked_odds)
        VALUES ('d0000000-0000-0000-0000-000000000002',3,'a0000000-0000-0000-0000-00000000000b','e0000000-0000-0000-0000-00000000000c','YES',0.35,0.05,2.71);
        RAISE EXCEPTION 'FAIL: mismatched market/event pair accepted';
    EXCEPTION WHEN foreign_key_violation THEN NULL; END;
END $$;

\echo '7. Insurance pays the stake back on a covered near-miss'
INSERT INTO predictions (id, user_id, idempotency_key, request_fingerprint, type, leg_count,
                         stake, combined_odds, gross_potential_payout, payout_cap, potential_payout,
                         has_insurance, insurance_premium, insurance_rate, insurance_min_legs, insurance_max_failed)
VALUES ('d0000000-0000-0000-0000-000000000003','11111111-1111-1111-1111-111111111111',
        'slip-ins','fp3','PARLAY',3, 10000, 6.86, 68600, 500000000, 68600,
        TRUE, 2110, 0.211, 3, 1);

INSERT INTO ledger_entries (user_id, entry_type, amount, ref_type, ref_id, idempotency_key) VALUES
  ('11111111-1111-1111-1111-111111111111','STAKE_DEBIT',-10000,'PREDICTION','d0000000-0000-0000-0000-000000000003','stake:d3'),
  ('11111111-1111-1111-1111-111111111111','INSURANCE_PREMIUM_DEBIT',-2110,'PREDICTION','d0000000-0000-0000-0000-000000000003','prem:d3');

INSERT INTO prediction_legs (prediction_id, leg_index, market_id, event_id, side, raw_prob, vig_rate, locked_odds, status, settled_at) VALUES
  ('d0000000-0000-0000-0000-000000000003',1,'a0000000-0000-0000-0000-00000000000a','e0000000-0000-0000-0000-00000000000a','YES',0.50,0.05,1.90,'WON', NOW()),
  ('d0000000-0000-0000-0000-000000000003',2,'a0000000-0000-0000-0000-00000000000b','e0000000-0000-0000-0000-00000000000b','YES',0.35,0.05,2.71,'WON', NOW()),
  ('d0000000-0000-0000-0000-000000000003',3,'a0000000-0000-0000-0000-00000000000c','e0000000-0000-0000-0000-00000000000c','NO', 0.60,0.05,2.37,'LOST',NOW());

DO $$
DECLARE v_status slip_status; v_paid BIGINT;
BEGIN
    v_status := fn_settle_prediction('d0000000-0000-0000-0000-000000000003');
    IF v_status <> 'INSURED' THEN RAISE EXCEPTION 'FAIL: status % <> INSURED', v_status; END IF;
    SELECT settled_payout INTO v_paid FROM predictions WHERE id = 'd0000000-0000-0000-0000-000000000003';
    IF v_paid <> 10000 THEN RAISE EXCEPTION 'FAIL: insured payout % <> 10000', v_paid; END IF;
END $$;

\echo '8. A voided leg neither pays nor kills the slip'
INSERT INTO predictions (id, user_id, idempotency_key, request_fingerprint, type, leg_count,
                         stake, combined_odds, gross_potential_payout, payout_cap, potential_payout)
VALUES ('d0000000-0000-0000-0000-000000000004','11111111-1111-1111-1111-111111111111',
        'slip-void','fp4','PARLAY',2, 10000, 3.61, 36100, 500000000, 36100);

INSERT INTO ledger_entries (user_id, entry_type, amount, ref_type, ref_id, idempotency_key)
VALUES ('11111111-1111-1111-1111-111111111111','STAKE_DEBIT',-10000,'PREDICTION','d0000000-0000-0000-0000-000000000004','stake:d4');

INSERT INTO prediction_legs (prediction_id, leg_index, market_id, event_id, side, raw_prob, vig_rate, locked_odds, status, settled_at) VALUES
  ('d0000000-0000-0000-0000-000000000004',1,'a0000000-0000-0000-0000-00000000000a','e0000000-0000-0000-0000-00000000000a','YES',0.50,0.05,1.90,'WON', NOW()),
  ('d0000000-0000-0000-0000-000000000004',2,'a0000000-0000-0000-0000-00000000000b','e0000000-0000-0000-0000-00000000000b','YES',0.35,0.05,2.71,'VOID',NOW());

DO $$
DECLARE v_status slip_status; v_paid BIGINT;
BEGIN
    v_status := fn_settle_prediction('d0000000-0000-0000-0000-000000000004');
    IF v_status <> 'WON' THEN RAISE EXCEPTION 'FAIL: status % <> WON', v_status; END IF;
    SELECT settled_payout INTO v_paid FROM predictions WHERE id = 'd0000000-0000-0000-0000-000000000004';
    IF v_paid <> 19000 THEN RAISE EXCEPTION 'FAIL: void-adjusted payout % <> 19000', v_paid; END IF;
END $$;

\echo '9. The payout cap is what we actually owe'
INSERT INTO predictions (id, user_id, idempotency_key, request_fingerprint, type, leg_count,
                         stake, combined_odds, gross_potential_payout, payout_cap, potential_payout)
VALUES ('d0000000-0000-0000-0000-000000000005','11111111-1111-1111-1111-111111111111',
        'slip-cap','fp5','SINGLE',1, 10000, 9500.0, 95000000, 50000, 50000);

INSERT INTO ledger_entries (user_id, entry_type, amount, ref_type, ref_id, idempotency_key)
VALUES ('11111111-1111-1111-1111-111111111111','STAKE_DEBIT',-10000,'PREDICTION','d0000000-0000-0000-0000-000000000005','stake:d5');

INSERT INTO prediction_legs (prediction_id, leg_index, market_id, event_id, side, raw_prob, vig_rate, locked_odds, status, settled_at)
VALUES ('d0000000-0000-0000-0000-000000000005',1,'a0000000-0000-0000-0000-00000000000c','e0000000-0000-0000-0000-00000000000c','YES',0.0001,0.05,9500.0,'WON',NOW());

DO $$
DECLARE v_paid BIGINT; v_capped BOOLEAN;
BEGIN
    PERFORM fn_settle_prediction('d0000000-0000-0000-0000-000000000005');
    SELECT settled_payout INTO v_paid FROM predictions WHERE id = 'd0000000-0000-0000-0000-000000000005';
    IF v_paid <> 50000 THEN RAISE EXCEPTION 'FAIL: payout % ignored the cap', v_paid; END IF;
    SELECT (metadata->>'capped')::BOOLEAN INTO v_capped FROM ledger_entries
     WHERE ref_id = 'd0000000-0000-0000-0000-000000000005' AND entry_type = 'PAYOUT_CREDIT';
    IF NOT v_capped THEN RAISE EXCEPTION 'FAIL: capping was not recorded'; END IF;
END $$;

\echo '10. Overlapping boosts on one market/side cannot coexist'
DO $$
BEGIN
    INSERT INTO odds_boosts (market_id, side, boost_multiplier, ends_at, max_total_stake, max_stake_per_user)
    VALUES ('a0000000-0000-0000-0000-00000000000c','YES',1.4, NOW()+INTERVAL '6 hours', 10000000, 100000);
    INSERT INTO odds_boosts (market_id, side, boost_multiplier, ends_at, max_total_stake, max_stake_per_user)
    VALUES ('a0000000-0000-0000-0000-00000000000c','NO', 1.4, NOW()+INTERVAL '6 hours', 10000000, 100000);
    BEGIN
        INSERT INTO odds_boosts (market_id, side, boost_multiplier, starts_at, ends_at, max_total_stake, max_stake_per_user)
        VALUES ('a0000000-0000-0000-0000-00000000000c','YES',1.5, NOW()+INTERVAL '1 hour', NOW()+INTERVAL '9 hours', 10000000, 100000);
        RAISE EXCEPTION 'FAIL: overlapping boost accepted';
    EXCEPTION WHEN exclusion_violation THEN NULL; END;
END $$;

\echo '11. Daily drip and inactivity decay are once-per-day by construction'
INSERT INTO daily_claims (user_id, claim_date, base_amount, streak_bonus, streak_after)
VALUES ('11111111-1111-1111-1111-111111111111', CURRENT_DATE, 25000, 5000, 2);
DO $$
BEGIN
    BEGIN
        INSERT INTO daily_claims (user_id, claim_date, base_amount, streak_bonus, streak_after)
        VALUES ('11111111-1111-1111-1111-111111111111', CURRENT_DATE, 25000, 5000, 3);
        RAISE EXCEPTION 'FAIL: double claim accepted';
    EXCEPTION WHEN unique_violation THEN NULL; END;

    INSERT INTO decay_events (user_id, run_date, days_inactive, decay_rate, amount, balance_before, balance_after)
    VALUES ('11111111-1111-1111-1111-111111111111', CURRENT_DATE, 3, 0.05, 1000, 20000, 19000);
    BEGIN
        INSERT INTO decay_events (user_id, run_date, days_inactive, decay_rate, amount, balance_before, balance_after)
        VALUES ('11111111-1111-1111-1111-111111111111', CURRENT_DATE, 3, 0.05, 1000, 19000, 18000);
        RAISE EXCEPTION 'FAIL: double decay accepted';
    EXCEPTION WHEN unique_violation THEN NULL; END;
END $$;

\echo '12. Stars: one charge id, one credit'
INSERT INTO star_purchases (id, user_id, package_code, invoice_payload, stars_amount, coins_amount)
VALUES ('f0000000-0000-0000-0000-000000000001','11111111-1111-1111-1111-111111111111','TIER_1','nonce-abc123',50,500000);

DO $$
BEGIN
    UPDATE star_purchases SET status='PAID', telegram_payment_charge_id='tg-charge-1',
           provider_payment_charge_id='pp-1', paid_at=NOW()
     WHERE id='f0000000-0000-0000-0000-000000000001';

    INSERT INTO ledger_entries (user_id, entry_type, amount, ref_type, ref_id, idempotency_key, metadata)
    VALUES ('11111111-1111-1111-1111-111111111111','STAR_PURCHASE_CREDIT',500000,'STAR_PURCHASE',
            'f0000000-0000-0000-0000-000000000001','stars:tg-charge-1','{"stars":50}');

    BEGIN
        INSERT INTO ledger_entries (user_id, entry_type, amount, ref_type, ref_id, idempotency_key, metadata)
        VALUES ('11111111-1111-1111-1111-111111111111','STAR_PURCHASE_CREDIT',500000,'STAR_PURCHASE',
                'f0000000-0000-0000-0000-000000000001','stars:tg-charge-1','{"stars":50}');
        RAISE EXCEPTION 'FAIL: replayed payment credited twice';
    EXCEPTION WHEN unique_violation THEN NULL; END;

    BEGIN
        INSERT INTO ledger_entries (user_id, entry_type, amount, ref_type, ref_id, idempotency_key, metadata)
        VALUES ('11111111-1111-1111-1111-111111111111','STAR_PURCHASE_CREDIT',500000,'STAR_PURCHASE',
                'f0000000-0000-0000-0000-000000000001','stars:tg-charge-2','{"stars":50}');
        RAISE EXCEPTION 'FAIL: second credit against one purchase';
    EXCEPTION WHEN unique_violation THEN NULL; END;
END $$;

\echo '13. Lifetime counters and reconciliation agree at the end'
DO $$
DECLARE u users%ROWTYPE; v_drift INT;
BEGIN
    SELECT * INTO u FROM users WHERE telegram_id = 900001;
    IF u.lifetime_staked <> 42110 THEN RAISE EXCEPTION 'FAIL: lifetime_staked %', u.lifetime_staked; END IF;
    IF u.lifetime_returned <> 115100 THEN RAISE EXCEPTION 'FAIL: lifetime_returned %', u.lifetime_returned; END IF;
    IF u.lifetime_stars <> 50 THEN RAISE EXCEPTION 'FAIL: lifetime_stars %', u.lifetime_stars; END IF;

    SELECT COUNT(*) INTO v_drift FROM v_balance_reconciliation;
    IF v_drift <> 0 THEN RAISE EXCEPTION 'FAIL: % account(s) drifted', v_drift; END IF;
END $$;

\echo ''
\echo 'ALL INVARIANTS HOLD'
ROLLBACK;
