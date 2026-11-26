
BEGIN;

ALTER TABLE predictions
    ALTER COLUMN combined_odds TYPE NUMERIC(20,6);

COMMENT ON COLUMN predictions.combined_odds IS
    'Product of the legs'' locked odds and the parlay bonus. Wide enough for '
    'five legs at the minimum probability, which is the longest slip the '
    'engine can price.';

COMMIT;
