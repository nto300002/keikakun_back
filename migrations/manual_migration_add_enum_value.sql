-- =====================================================
-- Revision ID: x6y7z8a9b0c1
-- Revises: w5x6y7z8a9b0
-- Create Date: 2026-01-12
-- calendar_event_type enumに次回計画開始期限の値を追加
-- =====================================================

-- 1. 現在のenum値を確認
SELECT e.enumlabel
FROM pg_enum e
JOIN pg_type t ON e.enumtypid = t.oid
WHERE t.typname = 'calendar_event_type'
ORDER BY e.enumsortorder;

-- 期待される結果:
-- enumlabel
-- -----------------
-- renewal_deadline
-- monitoring_deadline
-- custom

-- 2. 新しいenum値を追加
ALTER TYPE calendar_event_type ADD VALUE IF NOT EXISTS 'next_plan_start_date';

-- 3. 追加後の値を確認
SELECT e.enumlabel
FROM pg_enum e
JOIN pg_type t ON e.enumtypid = t.oid
WHERE t.typname = 'calendar_event_type'
ORDER BY e.enumsortorder;

-- 期待される結果:
-- enumlabel
-- -----------------
-- renewal_deadline
-- monitoring_deadline
-- custom
-- next_plan_start_date

-- 4. 既存のmonitoring_deadlineイベントをnext_plan_start_dateに更新
UPDATE calendar_events
SET event_type = 'next_plan_start_date'
WHERE event_type = 'monitoring_deadline';

-- 5. 更新結果を確認
SELECT event_type, COUNT(*) as count
FROM calendar_events
GROUP BY event_type
ORDER BY event_type;


