-- Migration: w5x6y7z8a9b0
-- Description: Rename monitoring_deadline to next_plan_start_date in support_plan_cycles table
-- Created: 2026-01-11
-- Task: 次回開始期限カラムリネーム

-- =============================================================================
-- UPGRADE
-- =============================================================================

-- Step 1: Rename monitoring_deadline to next_plan_start_date
ALTER TABLE support_plan_cycles
RENAME COLUMN monitoring_deadline TO next_plan_start_date;

-- Update column comment
COMMENT ON COLUMN support_plan_cycles.next_plan_start_date IS
'次回計画開始期限（日数）';

-- Step 2: Update calendar_events event_type values
UPDATE calendar_events
SET event_type = 'next_plan_start_date'
WHERE event_type = 'monitoring_deadline';

-- Verify column was renamed
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'support_plan_cycles'
          AND column_name = 'next_plan_start_date'
    ) THEN
        RAISE EXCEPTION 'Column next_plan_start_date does not exist in support_plan_cycles table';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'support_plan_cycles'
          AND column_name = 'monitoring_deadline'
    ) THEN
        RAISE EXCEPTION 'Column monitoring_deadline still exists in support_plan_cycles table';
    END IF;

    RAISE NOTICE 'Column successfully renamed from monitoring_deadline to next_plan_start_date';
END $$;

-- Verify calendar event types were updated
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM calendar_events
        WHERE event_type = 'monitoring_deadline'
    ) THEN
        RAISE WARNING 'Some calendar events still have event_type = monitoring_deadline';
    END IF;

    RAISE NOTICE 'Calendar event types successfully updated to next_plan_start_date';
END $$;

-- =============================================================================
-- DOWNGRADE
-- =============================================================================

-- Restore calendar event types
-- Uncomment below to execute downgrade:

-- UPDATE calendar_events
-- SET event_type = 'monitoring_deadline'
-- WHERE event_type = 'next_plan_start_date';

-- Rename next_plan_start_date back to monitoring_deadline

-- ALTER TABLE support_plan_cycles
-- RENAME COLUMN next_plan_start_date TO monitoring_deadline;

-- COMMENT ON COLUMN support_plan_cycles.monitoring_deadline IS
-- 'モニタリング期限（日数）';

-- -- Verify column was renamed back
-- DO $$
-- BEGIN
--     IF NOT EXISTS (
--         SELECT 1
--         FROM information_schema.columns
--         WHERE table_name = 'support_plan_cycles'
--           AND column_name = 'monitoring_deadline'
--     ) THEN
--         RAISE EXCEPTION 'Column monitoring_deadline does not exist in support_plan_cycles table';
--     END IF;

--     IF EXISTS (
--         SELECT 1
--         FROM information_schema.columns
--         WHERE table_name = 'support_plan_cycles'
--           AND column_name = 'next_plan_start_date'
--     ) THEN
--         RAISE EXCEPTION 'Column next_plan_start_date still exists in support_plan_cycles table';
--     END IF;

--     RAISE NOTICE 'Column successfully renamed from next_plan_start_date back to monitoring_deadline';
-- END $$;
