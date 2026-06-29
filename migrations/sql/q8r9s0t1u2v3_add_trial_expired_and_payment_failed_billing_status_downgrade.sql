-- =====================================================
-- Downgrade: remove trial_expired/payment_failed billing statuses
-- =====================================================
-- Revision ID: q8r9s0t1u2v3
-- Alembic file:
--   migrations/versions/q8r9s0t1u2v3_add_trial_expired_and_payment_failed_billing_status.py
--
-- Rollback policy:
--   trial_expired/payment_failed は後方互換用の past_due へ戻す。
--
-- Change:
--   1. Convert trial_expired/payment_failed records to past_due.
--   2. Drop current 8-value CHECK constraint.
--   3. Recreate billingstatus enum with the previous 6 values.
--   4. Recreate ck_billings_billing_status with the previous 6 values.
-- =====================================================

BEGIN;

UPDATE billings
SET billing_status = 'past_due'
WHERE billing_status IN ('trial_expired', 'payment_failed');

ALTER TABLE billings
DROP CONSTRAINT IF EXISTS ck_billings_billing_status;

ALTER TABLE billings
ALTER COLUMN billing_status DROP DEFAULT;

ALTER TYPE billingstatus RENAME TO billingstatus_new;

CREATE TYPE billingstatus AS ENUM(
    'free',
    'early_payment',
    'active',
    'past_due',
    'canceling',
    'canceled'
);

ALTER TABLE billings
ALTER COLUMN billing_status
TYPE billingstatus
USING billing_status::text::billingstatus;

ALTER TABLE billings
ALTER COLUMN billing_status SET DEFAULT 'free'::billingstatus;

DROP TYPE billingstatus_new;

ALTER TABLE billings
ADD CONSTRAINT ck_billings_billing_status
CHECK (billing_status::text = ANY (ARRAY[
    'free'::character varying::text,
    'early_payment'::character varying::text,
    'active'::character varying::text,
    'past_due'::character varying::text,
    'canceling'::character varying::text,
    'canceled'::character varying::text
]));

COMMENT ON COLUMN billings.billing_status IS
'Billing status: free (無料トライアル), early_payment (早期支払い完了・無料期間中), active (課金中), past_due (支払い遅延), canceling (キャンセル予定), canceled (キャンセル済み)';

COMMIT;
