-- =====================================================
-- Upgrade: add trial_expired/payment_failed billing statuses
-- =====================================================
-- Revision ID: q8r9s0t1u2v3
-- Alembic file:
--   migrations/versions/q8r9s0t1u2v3_add_trial_expired_and_payment_failed_billing_status.py
--
-- Current DB premise:
--   ck_billings_billing_status currently allows:
--   free / early_payment / active / past_due / canceling / canceled
--
-- Change:
--   1. Drop current 6-value CHECK constraint.
--   2. Recreate billingstatus enum with:
--      free / early_payment / active / past_due / trial_expired /
--      payment_failed / canceling / canceled
--   3. Recreate ck_billings_billing_status with the same 8 values.
-- =====================================================

BEGIN;

ALTER TABLE billings
DROP CONSTRAINT IF EXISTS ck_billings_billing_status;

ALTER TABLE billings
ALTER COLUMN billing_status DROP DEFAULT;

ALTER TYPE billingstatus RENAME TO billingstatus_old;

CREATE TYPE billingstatus AS ENUM(
    'free',
    'early_payment',
    'active',
    'past_due',
    'trial_expired',
    'payment_failed',
    'canceling',
    'canceled'
);

ALTER TABLE billings
ALTER COLUMN billing_status
TYPE billingstatus
USING billing_status::text::billingstatus;

ALTER TABLE billings
ALTER COLUMN billing_status SET DEFAULT 'free'::billingstatus;

DROP TYPE billingstatus_old;

ALTER TABLE billings
ADD CONSTRAINT ck_billings_billing_status
CHECK (billing_status::text = ANY (ARRAY[
    'free'::character varying::text,
    'early_payment'::character varying::text,
    'active'::character varying::text,
    'past_due'::character varying::text,
    'trial_expired'::character varying::text,
    'payment_failed'::character varying::text,
    'canceling'::character varying::text,
    'canceled'::character varying::text
]));

COMMENT ON COLUMN billings.billing_status IS
'Billing status: free (無料トライアル), early_payment (早期支払い完了・無料期間中), active (課金中), past_due (互換用の支払い対応必要状態), trial_expired (無料期間終了・未課金), payment_failed (支払い失敗), canceling (キャンセル予定), canceled (キャンセル済み)';

COMMIT;

-- =====================================================
-- Downgrade: remove trial_expired/payment_failed billing statuses
-- =====================================================

-- BEGIN;

-- UPDATE billings
-- SET billing_status = 'past_due'
-- WHERE billing_status IN ('trial_expired', 'payment_failed');

-- ALTER TABLE billings
-- DROP CONSTRAINT IF EXISTS ck_billings_billing_status;

-- ALTER TABLE billings
-- ALTER COLUMN billing_status DROP DEFAULT;

-- ALTER TYPE billingstatus RENAME TO billingstatus_new;

-- CREATE TYPE billingstatus AS ENUM(
--     'free',
--     'early_payment',
--     'active',
--     'past_due',
--     'canceling',
--     'canceled'
-- );

-- ALTER TABLE billings
-- ALTER COLUMN billing_status
-- TYPE billingstatus
-- USING billing_status::text::billingstatus;

-- ALTER TABLE billings
-- ALTER COLUMN billing_status SET DEFAULT 'free'::billingstatus;

-- DROP TYPE billingstatus_new;

-- ALTER TABLE billings
-- ADD CONSTRAINT ck_billings_billing_status
-- CHECK (billing_status::text = ANY (ARRAY[
--     'free'::character varying::text,
--     'early_payment'::character varying::text,
--     'active'::character varying::text,
--     'past_due'::character varying::text,
--     'canceling'::character varying::text,
--     'canceled'::character varying::text
-- ]));

-- COMMENT ON COLUMN billings.billing_status IS
-- 'Billing status: free (無料トライアル), early_payment (早期支払い完了・無料期間中), active (課金中), past_due (支払い遅延), canceling (キャンセル予定), canceled (キャンセル済み)';

-- COMMIT;
