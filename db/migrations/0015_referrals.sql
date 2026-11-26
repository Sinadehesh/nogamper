
BEGIN;

ALTER TYPE ledger_ref_type ADD VALUE 'REFERRAL';
ALTER TYPE ledger_entry_type ADD VALUE 'REFERRAL_BONUS_CREDIT';

CREATE INDEX idx_users_referred_by ON users (referred_by) WHERE referred_by IS NOT NULL;

COMMIT;
