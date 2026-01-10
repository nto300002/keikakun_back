-- Migration: v4w5x6y7z8a9
-- Description: Add no_employment_experience fields to employment_related table
-- Created: 2026-01-08
-- Task: Task 1 - 就労経験なしチェックボックス追加

-- =============================================================================
-- UPGRADE
-- =============================================================================

-- Add no_employment_experience (親チェックボックス)
ALTER TABLE employment_related
ADD COLUMN no_employment_experience BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN employment_related.no_employment_experience IS
'就労経験なし（親チェックボックス）';

-- Add attended_job_selection_office (子チェックボックス)
ALTER TABLE employment_related
ADD COLUMN attended_job_selection_office BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN employment_related.attended_job_selection_office IS
'就職選択事務所を利用したことがある';

-- Add received_employment_assessment (子チェックボックス)
ALTER TABLE employment_related
ADD COLUMN received_employment_assessment BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN employment_related.received_employment_assessment IS
'就労アセスメントを受けたことがある';

-- Add employment_other_experience (子チェックボックス - その他)
ALTER TABLE employment_related
ADD COLUMN employment_other_experience BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN employment_related.employment_other_experience IS
'その他の就労関連経験がある';

-- Add employment_other_text (その他の詳細)
ALTER TABLE employment_related
ADD COLUMN employment_other_text TEXT NULL;

COMMENT ON COLUMN employment_related.employment_other_text IS
'その他の就労関連経験の詳細';

-- Verify columns were added
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'employment_related'
          AND column_name = 'no_employment_experience'
    ) THEN
        RAISE EXCEPTION 'Column no_employment_experience was not added to employment_related table';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'employment_related'
          AND column_name = 'attended_job_selection_office'
    ) THEN
        RAISE EXCEPTION 'Column attended_job_selection_office was not added to employment_related table';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'employment_related'
          AND column_name = 'received_employment_assessment'
    ) THEN
        RAISE EXCEPTION 'Column received_employment_assessment was not added to employment_related table';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'employment_related'
          AND column_name = 'employment_other_experience'
    ) THEN
        RAISE EXCEPTION 'Column employment_other_experience was not added to employment_related table';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'employment_related'
          AND column_name = 'employment_other_text'
    ) THEN
        RAISE EXCEPTION 'Column employment_other_text was not added to employment_related table';
    END IF;

    RAISE NOTICE 'All 5 columns successfully added to employment_related table';
END $$;

-- =============================================================================
-- DOWNGRADE
-- =============================================================================

-- Remove all no_employment_experience fields from employment_related table
-- Uncomment below to execute downgrade:

-- ALTER TABLE employment_related
-- DROP COLUMN IF EXISTS employment_other_text;

-- ALTER TABLE employment_related
-- DROP COLUMN IF EXISTS employment_other_experience;

-- ALTER TABLE employment_related
-- DROP COLUMN IF EXISTS received_employment_assessment;

-- ALTER TABLE employment_related
-- DROP COLUMN IF EXISTS attended_job_selection_office;

-- ALTER TABLE employment_related
-- DROP COLUMN IF EXISTS no_employment_experience;

-- -- Verify columns were removed
-- DO $$
-- BEGIN
--     IF EXISTS (
--         SELECT 1
--         FROM information_schema.columns
--         WHERE table_name = 'employment_related'
--           AND column_name IN ('no_employment_experience', 'attended_job_selection_office',
--                               'received_employment_assessment', 'employment_other_experience',
--                               'employment_other_text')
--     ) THEN
--         RAISE EXCEPTION 'Not all columns were removed from employment_related table';
--     END IF;
--     RAISE NOTICE 'All 5 columns successfully removed from employment_related table';
-- END $$;
