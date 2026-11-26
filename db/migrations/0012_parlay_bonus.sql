
BEGIN;

ALTER TABLE predictions
    ADD COLUMN parlay_bonus NUMERIC(6,3) NOT NULL DEFAULT 1.0
        CHECK (parlay_bonus >= 1.0);

COMMENT ON COLUMN predictions.parlay_bonus IS
    'Slip-wide payout multiplier earned by leg count. Applied by '
    'fn_effective_parlay_odds so settlement agrees with the quote the player saw.';

CREATE OR REPLACE FUNCTION fn_effective_parlay_odds(p_prediction_id UUID)
RETURNS NUMERIC AS $$
DECLARE
    v_odds  NUMERIC := 1.0;
    v_bonus NUMERIC;
    r       RECORD;
BEGIN
    SELECT parlay_bonus INTO v_bonus FROM predictions WHERE id = p_prediction_id;
    IF NOT FOUND THEN
        RETURN NULL;
    END IF;

    FOR r IN
        SELECT status, locked_odds FROM prediction_legs
         WHERE prediction_id = p_prediction_id
    LOOP
        IF r.status = 'PENDING' THEN
            RETURN NULL;
        ELSIF r.status = 'LOST' THEN
            RETURN 0;
        ELSIF r.status = 'WON' THEN
            v_odds := v_odds * r.locked_odds;
        END IF;   -- VOID contributes a factor of 1.0
    END LOOP;

    RETURN v_odds * v_bonus;
END;
$$ LANGUAGE plpgsql STABLE;

COMMIT;
