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

-- The Telegram Stars purchases table is retired: nothing in the application
-- writes to it and check 16 asserts none of its packages is on sale. It is
-- still in the schema, with the rows it already holds, so the rule that kept
-- those rows honest is still checked. Points bought through the website live
-- in point_purchases, which check 18 covers.
\echo '12. Retired purchases table: one charge id, one credit'
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

\echo '14. A web account is an email and a password together, or neither'
DO $$
BEGIN
    INSERT INTO users (email, password_hash, first_name)
    VALUES ('ada@example.com', '$argon2id$stub', 'Ada');

    BEGIN
        INSERT INTO users (email, first_name) VALUES ('nopass@example.com', 'NoPass');
        RAISE EXCEPTION 'FAIL: an email without a password was accepted';
    EXCEPTION WHEN check_violation THEN NULL; END;

    BEGIN
        INSERT INTO users (password_hash, first_name, is_guest) VALUES ('$argon2id$stub', 'NoMail', TRUE);
        RAISE EXCEPTION 'FAIL: a password without an email was accepted';
    EXCEPTION WHEN check_violation THEN NULL; END;

    BEGIN
        INSERT INTO users (email, password_hash, first_name)
        VALUES ('Ada@Example.com', '$argon2id$stub', 'Shouting Ada');
        RAISE EXCEPTION 'FAIL: an email that is not lower-cased was accepted';
    EXCEPTION WHEN check_violation THEN NULL; END;

    BEGIN
        INSERT INTO users (email, password_hash, first_name)
        VALUES ('ada@example.com', '$argon2id$stub', 'Second Ada');
        RAISE EXCEPTION 'FAIL: the same email registered twice';
    EXCEPTION WHEN unique_violation THEN NULL; END;
END $$;

\echo '15. A guest has no credentials, and nobody exists without an identity'
DO $$
BEGIN
    INSERT INTO users (first_name, is_guest) VALUES ('Guest', TRUE);
    INSERT INTO users (first_name, is_guest) VALUES ('Guest', TRUE);  -- many guests are fine

    BEGIN
        INSERT INTO users (email, password_hash, first_name, is_guest)
        VALUES ('both@example.com', '$argon2id$stub', 'Both', TRUE);
        RAISE EXCEPTION 'FAIL: a guest with credentials was accepted';
    EXCEPTION WHEN check_violation THEN NULL; END;

    BEGIN
        INSERT INTO users (first_name) VALUES ('Nobody');
        RAISE EXCEPTION 'FAIL: a user with no identity at all was accepted';
    EXCEPTION WHEN check_violation THEN NULL; END;
END $$;

\echo '16. The old store stays closed and nothing is redeemable'
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM coin_packages WHERE is_active) THEN
        RAISE EXCEPTION 'FAIL: a Telegram Stars package is still on sale';
    END IF;
    IF EXISTS (SELECT 1 FROM rewards WHERE is_active) THEN
        RAISE EXCEPTION 'FAIL: a reward is still redeemable';
    END IF;
END $$;

\echo '17. An article is never refused without a reason, published without a date, or given a taken address'
DO $$
DECLARE v_id UUID;
BEGIN
    INSERT INTO articles (author_id, slug, title, summary, body)
    VALUES ('11111111-1111-1111-1111-111111111111', 'an-invariant-check-abcde',
            'An invariant check', repeat('s', 60), repeat('b', 700))
    RETURNING id INTO v_id;

    BEGIN
        UPDATE articles SET status = 'REJECTED' WHERE id = v_id;
        RAISE EXCEPTION 'FAIL: rejected with no reason at all';
    EXCEPTION WHEN check_violation THEN NULL; END;

    BEGIN
        UPDATE articles SET status = 'REMOVED', review_note = '   ' WHERE id = v_id;
        RAISE EXCEPTION 'FAIL: removed with a blank reason';
    EXCEPTION WHEN check_violation THEN NULL; END;

    BEGIN
        UPDATE articles SET status = 'PUBLISHED' WHERE id = v_id;
        RAISE EXCEPTION 'FAIL: published with no date';
    EXCEPTION WHEN check_violation THEN NULL; END;

    BEGIN
        INSERT INTO articles (author_id, slug, title, summary, body)
        VALUES ('11111111-1111-1111-1111-111111111111', 'an-invariant-check-abcde',
                'A second article', repeat('s', 60), repeat('b', 700));
        RAISE EXCEPTION 'FAIL: two articles at one address';
    EXCEPTION WHEN unique_violation THEN NULL; END;

    BEGIN
        UPDATE articles SET body = 'too short' WHERE id = v_id;
        RAISE EXCEPTION 'FAIL: a one-line article accepted';
    EXCEPTION WHEN check_violation THEN NULL; END;
END $$;

\echo '18. A purchase is credited once, dated when paid, and refunded no more than it gave'
DO $$
DECLARE
    v_user UUID := '11111111-1111-1111-1111-111111111111';
    v_id   UUID;
BEGIN
    INSERT INTO point_purchases (user_id, points, amount_cents, currency, expires_at)
    VALUES (v_user, 100000, 200, 'usd', NOW() + INTERVAL '30 minutes')
    RETURNING id INTO v_id;

    BEGIN
        UPDATE point_purchases SET status = 'PAID' WHERE id = v_id;
        RAISE EXCEPTION 'FAIL: marked paid with no date';
    EXCEPTION WHEN check_violation THEN NULL; END;

    BEGIN
        UPDATE point_purchases SET status = 'REFUNDED', paid_at = NOW() WHERE id = v_id;
        RAISE EXCEPTION 'FAIL: marked refunded with no refund date';
    EXCEPTION WHEN check_violation THEN NULL; END;

    BEGIN
        UPDATE point_purchases SET clawed_back = 5 WHERE id = v_id;
        RAISE EXCEPTION 'FAIL: points taken back from a purchase that was never refunded';
    EXCEPTION WHEN check_violation THEN NULL; END;

    UPDATE point_purchases SET status = 'PAID', paid_at = NOW(), stripe_session_id = 'cs_inv_1'
     WHERE id = v_id;

    INSERT INTO ledger_entries (user_id, entry_type, amount, ref_type, ref_id, idempotency_key)
    VALUES (v_user, 'POINTS_PURCHASE_CREDIT', 100000, 'POINT_PURCHASE', v_id, 'purchase:' || v_id);

    BEGIN
        INSERT INTO ledger_entries (user_id, entry_type, amount, ref_type, ref_id, idempotency_key)
        VALUES (v_user, 'POINTS_PURCHASE_CREDIT', 100000, 'POINT_PURCHASE', v_id, 'purchase-again:' || v_id);
        RAISE EXCEPTION 'FAIL: one purchase credited twice';
    EXCEPTION WHEN unique_violation THEN NULL; END;

    BEGIN
        UPDATE point_purchases
           SET status = 'REFUNDED', refunded_at = NOW(), clawed_back = 100001
         WHERE id = v_id;
        RAISE EXCEPTION 'FAIL: a refund took back more points than the purchase gave';
    EXCEPTION WHEN check_violation THEN NULL; END;

    BEGIN
        INSERT INTO point_purchases (user_id, points, amount_cents, currency, expires_at, stripe_session_id)
        VALUES (v_user, 100000, 200, 'usd', NOW() + INTERVAL '30 minutes', 'cs_inv_1');
        RAISE EXCEPTION 'FAIL: one Stripe session recorded as two purchases';
    EXCEPTION WHEN unique_violation THEN NULL; END;

    BEGIN
        INSERT INTO point_purchases (user_id, points, amount_cents, currency, expires_at)
        VALUES (v_user, 100000, 0, 'usd', NOW() + INTERVAL '30 minutes');
        RAISE EXCEPTION 'FAIL: a purchase that cost nothing';
    EXCEPTION WHEN check_violation THEN NULL; END;

    BEGIN
        UPDATE users SET monthly_spend_limit_cents = -1, spend_limit_set_at = NOW() WHERE id = v_user;
        RAISE EXCEPTION 'FAIL: a negative spending limit';
    EXCEPTION WHEN check_violation THEN NULL; END;

    BEGIN
        UPDATE users SET monthly_spend_limit_cents = 500 WHERE id = v_user;
        RAISE EXCEPTION 'FAIL: a spending limit with no record of when it was set';
    EXCEPTION WHEN check_violation THEN NULL; END;
END $$;

\echo '19. A change in a price has something to be measured from, and a page address is shaped like one'
DO $$
DECLARE v_market UUID := 'a0000000-0000-0000-0000-00000000000a';
BEGIN
    -- The plain case has to be allowed, or everything below proves nothing.
    UPDATE markets
       SET slug = 'fed-cuts-25bp', change_24h = 0.25, change_ref_prob = 0.55, changes_at = NOW()
     WHERE id = v_market;

    BEGIN
        UPDATE markets SET changes_at = NULL, change_ref_prob = NULL WHERE id = v_market;
        RAISE EXCEPTION 'FAIL: a change kept with nothing to measure it from';
    EXCEPTION WHEN check_violation THEN NULL; END;

    BEGIN
        UPDATE markets SET change_ref_prob = NULL WHERE id = v_market;
        RAISE EXCEPTION 'FAIL: a change dated but with no reference price';
    EXCEPTION WHEN check_violation THEN NULL; END;

    BEGIN
        UPDATE markets SET change_7d = 1.5 WHERE id = v_market;
        RAISE EXCEPTION 'FAIL: a change of more than the whole range accepted';
    EXCEPTION WHEN check_violation THEN NULL; END;

    BEGIN
        UPDATE markets SET change_ref_prob = 1.2 WHERE id = v_market;
        RAISE EXCEPTION 'FAIL: a reference price that is not a probability accepted';
    EXCEPTION WHEN check_violation THEN NULL; END;

    BEGIN
        UPDATE markets SET slug = 'Fed Cuts 25bp?' WHERE id = v_market;
        RAISE EXCEPTION 'FAIL: an address with spaces and capitals accepted';
    EXCEPTION WHEN check_violation THEN NULL; END;

    BEGIN
        UPDATE markets SET slug = 'trailing-dash-' WHERE id = v_market;
        RAISE EXCEPTION 'FAIL: an address ending in a dash accepted';
    EXCEPTION WHEN check_violation THEN NULL; END;

    -- No figures at all is the ordinary state of a new question.
    UPDATE markets
       SET change_1h = NULL, change_24h = NULL, change_7d = NULL,
           change_ref_prob = NULL, changes_at = NULL
     WHERE id = v_market;
END $$;

\echo ''
\echo 'ALL INVARIANTS HOLD'
ROLLBACK;
