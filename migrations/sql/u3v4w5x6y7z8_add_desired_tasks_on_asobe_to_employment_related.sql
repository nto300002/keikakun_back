-- Migration: u3v4w5x6y7z8
-- Description: Add desired_tasks_on_asobe column to employment_related table
-- Created: 2026-01-08
-- Task: Task 2 - asoBeで希望する作業フィールドの追加

-- =============================================================================
-- UPGRADE
-- =============================================================================

-- Add desired_tasks_on_asobe column to employment_related table
ALTER TABLE employment_related
ADD COLUMN desired_tasks_on_asobe TEXT NULL;

-- Add column comment
COMMENT ON COLUMN employment_related.desired_tasks_on_asobe IS
'asoBeで希望する作業内容（最大1000文字、Pydanticでバリデーション）';

-- Verify column was added
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'employment_related'
          AND column_name = 'desired_tasks_on_asobe'
    ) THEN
        RAISE EXCEPTION 'Column desired_tasks_on_asobe was not added to employment_related table';
    END IF;
    RAISE NOTICE 'Column desired_tasks_on_asobe successfully added to employment_related table';
END $$;

-- =============================================================================
-- DOWNGRADE
-- =============================================================================

-- Remove desired_tasks_on_asobe column from employment_related table
-- Uncomment below to execute downgrade:

-- ALTER TABLE employment_related
-- DROP COLUMN IF EXISTS desired_tasks_on_asobe;

-- COMMENT ON COLUMN employment_related.desired_tasks_on_asobe IS NULL;

-- -- Verify column was removed
-- DO $$
-- BEGIN
--     IF EXISTS (
--         SELECT 1
--         FROM information_schema.columns
--         WHERE table_name = 'employment_related'
--           AND column_name = 'desired_tasks_on_asobe'
--     ) THEN
--         RAISE EXCEPTION 'Column desired_tasks_on_asobe was not removed from employment_related table';
--     END IF;
--     RAISE NOTICE 'Column desired_tasks_on_asobe successfully removed from employment_related table';
-- END $$;
