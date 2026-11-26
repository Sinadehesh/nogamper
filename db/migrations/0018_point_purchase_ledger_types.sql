BEGIN;

-- ---------------------------------------------------------------------------
-- Ledger vocabulary for points bought with money.
--
-- On its own in this file because of a rule of the database's: a value added
-- to an enum cannot be used until the transaction that added it has committed.
-- The table that uses these arrives in the next migration.
--
-- The old STAR_PURCHASE_* values are not reused. They describe purchases made
-- with Telegram Stars in a product that no longer exists, and a ledger that
-- used one word for two different things would be harder to audit than one
-- with two words.
-- ---------------------------------------------------------------------------

ALTER TYPE ledger_ref_type ADD VALUE 'POINT_PURCHASE';

ALTER TYPE ledger_entry_type ADD VALUE 'POINTS_PURCHASE_CREDIT';

ALTER TYPE ledger_entry_type ADD VALUE 'POINTS_REFUND_DEBIT';

COMMIT;
