-- =====================================================
-- billing_status CHECK制約の修正
-- =====================================================
-- 問題: CHECK制約にcancelingが含まれていない
-- 解決: CHECK制約を削除して再作成
-- =====================================================

BEGIN;

-- 1. 古いCHECK制約を削除
ALTER TABLE billings
DROP CONSTRAINT IF EXISTS ck_billings_billing_status;

-- 2. 新しいCHECK制約を作成（cancelingを含む）
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

COMMIT;
