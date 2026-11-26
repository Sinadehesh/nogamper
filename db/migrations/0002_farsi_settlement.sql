
BEGIN;

CREATE OR REPLACE FUNCTION fn_settle_prediction(p_prediction_id UUID)
RETURNS slip_status AS $$
DECLARE
    p        predictions%ROWTYPE;
    v_odds   NUMERIC;
    v_lost   INTEGER;
    v_void   INTEGER;
    v_payout BIGINT;
    v_status slip_status;
    v_entry  ledger_entry_type;
    v_note   TEXT;
BEGIN
    SELECT * INTO p FROM predictions WHERE id = p_prediction_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'PREDICTION_NOT_FOUND: %', p_prediction_id USING ERRCODE = 'PT004';
    END IF;

    IF p.status <> 'PENDING' THEN
        RETURN p.status;   -- already settled; idempotent no-op
    END IF;

    v_odds := fn_effective_parlay_odds(p_prediction_id);
    IF v_odds IS NULL THEN
        RETURN 'PENDING';  -- legs outstanding
    END IF;

    SELECT COUNT(*) FILTER (WHERE status = 'LOST'),
           COUNT(*) FILTER (WHERE status = 'VOID')
      INTO v_lost, v_void
      FROM prediction_legs WHERE prediction_id = p_prediction_id;

    IF v_odds > 0 AND v_void = p.leg_count THEN
        v_status := 'VOID';
        v_entry  := 'VOID_REFUND_CREDIT';
        v_payout := p.total_cost;
        v_note   := 'همهٔ انتخاب‌ها در مرجع باطل شدند؛ مبلغ و حق بیمه بازگشت.';

    ELSIF v_odds > 0 THEN
        v_status := 'WON';
        v_entry  := 'PAYOUT_CREDIT';
        v_payout := LEAST(ROUND(p.stake * v_odds)::BIGINT, p.payout_cap);
        v_note   := CASE WHEN v_void > 0
                         THEN format('%s انتخاب باطل شد؛ ضریب دوباره روی %s حساب شد.', v_void, v_odds)
                         ELSE NULL END;

    ELSIF p.has_insurance AND v_lost <= p.insurance_max_failed AND v_lost > 0 THEN
        v_status := 'INSURED';
        v_entry  := 'INSURANCE_CREDIT';
        v_payout := p.stake;   -- premium is retained; that is the product
        v_note   := format('بیمه پرداخت شد: %s انتخاب بازنده، درون سقف پوشش.', v_lost);

    ELSE
        v_status := 'LOST';
        v_payout := 0;
    END IF;

    UPDATE predictions SET
        status          = v_status,
        settled_payout  = v_payout,
        settlement_note = v_note,
        settled_at      = NOW()
     WHERE id = p_prediction_id;

    IF v_payout > 0 THEN
        INSERT INTO ledger_entries (user_id, entry_type, amount, ref_type, ref_id,
                                    idempotency_key, metadata)
        VALUES (
            p.user_id, v_entry, v_payout, 'PREDICTION', p_prediction_id,
            'settle:' || p_prediction_id::TEXT,
            jsonb_build_object(
                'effective_odds', v_odds,
                'lost_legs',      v_lost,
                'void_legs',      v_void,
                'capped',         (ROUND(p.stake * v_odds)::BIGINT > p.payout_cap)
            )
        );
    END IF;

    RETURN v_status;
END;
$$ LANGUAGE plpgsql;

COMMIT;
