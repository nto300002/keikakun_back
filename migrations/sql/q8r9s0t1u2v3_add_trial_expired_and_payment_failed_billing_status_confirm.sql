-- =====================================================
-- Confirm billing_status enum and CHECK constraint
-- =====================================================
-- Revision ID: q8r9s0t1u2v3
-- Purpose:
--   q8r9s0t1u2v3 の実行前後に、billingstatus enum値、
--   ck_billings_billing_status、既存データ件数を確認する。
-- =====================================================

-- 1. 現在のbillingstatus enum値を確認する。
SELECT enumlabel
FROM pg_enum
WHERE enumtypid = 'billingstatus'::regtype
ORDER BY enumsortorder;

-- 2. 現在のbilling_status件数を確認する。
SELECT billing_status::text AS billing_status, COUNT(*) AS count
FROM billings
GROUP BY billing_status::text
ORDER BY billing_status::text;

-- 3. 現在のCHECK制約を確認する。
-- upgrade前の想定:
--   free / early_payment / active / past_due / canceling / canceled
-- upgrade後の想定:
--   free / early_payment / active / past_due / trial_expired /
--   payment_failed / canceling / canceled
SELECT conname, pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'billings'::regclass
  AND conname = 'ck_billings_billing_status';

-- 4. 新statusの件数を個別確認する。
-- upgrade前はこのSELECTが enum input error になる場合があるため、
-- upgrade後確認として実行する。
SELECT billing_status::text AS billing_status, COUNT(*) AS count
FROM billings
WHERE billing_status::text IN ('trial_expired', 'payment_failed')
GROUP BY billing_status::text
ORDER BY billing_status::text;
