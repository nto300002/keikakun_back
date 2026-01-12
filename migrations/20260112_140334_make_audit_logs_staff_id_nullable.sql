-- ================================================================
-- Migration: Make audit_logs.staff_id nullable with SET NULL
-- Revision ID: y7z8a9b0c1d2
-- Revises: x6y7z8a9b0c1
-- Created: 2026-01-12 14:03:34
-- Description:
--   Change audit_logs.staff_id to allow NULL values and update
--   foreign key constraint from CASCADE to SET NULL.
--   This allows audit logs to persist after staff deletion.
-- ================================================================

-- ================================================================
-- UPGRADE
-- ================================================================

BEGIN;

-- 1. Drop existing foreign key constraint
ALTER TABLE audit_logs
DROP CONSTRAINT IF EXISTS audit_logs_staff_id_fkey;

-- 2. Alter column to allow NULL
ALTER TABLE audit_logs
ALTER COLUMN staff_id DROP NOT NULL;

-- 3. Create new foreign key constraint with SET NULL
ALTER TABLE audit_logs
ADD CONSTRAINT audit_logs_staff_id_fkey
FOREIGN KEY (staff_id)
REFERENCES staffs(id)
ON DELETE SET NULL;

-- 4. Add comment to document the change
COMMENT ON COLUMN audit_logs.staff_id IS '操作実行者のスタッフID（システム処理の場合はNULL、削除されたスタッフの場合もNULL）';

COMMIT;

-- ================================================================
-- DOWNGRADE (Rollback)
-- ================================================================
--
-- WARNING: This rollback will FAIL if there are any audit_logs
-- records with NULL staff_id. You must handle those records first.
--
-- To execute rollback, uncomment and run the following:
--
-- BEGIN;
--
-- -- 1. Drop the SET NULL foreign key constraint
-- ALTER TABLE audit_logs
-- DROP CONSTRAINT IF EXISTS audit_logs_staff_id_fkey;
--
-- -- 2. Delete or update records with NULL staff_id
-- -- OPTION A: Delete records with NULL staff_id (loses audit trail)
-- -- DELETE FROM audit_logs WHERE staff_id IS NULL;
-- --
-- -- OPTION B: Set to a system user ID (preserves audit trail)
-- -- UPDATE audit_logs SET staff_id = 'SYSTEM_USER_UUID' WHERE staff_id IS NULL;
--
-- -- 3. Alter column to NOT NULL
-- ALTER TABLE audit_logs
-- ALTER COLUMN staff_id SET NOT NULL;
--
-- -- 4. Create original foreign key constraint with CASCADE
-- ALTER TABLE audit_logs
-- ADD CONSTRAINT audit_logs_staff_id_fkey
-- FOREIGN KEY (staff_id)
-- REFERENCES staffs(id)
-- ON DELETE CASCADE;
--
-- -- 5. Restore original comment
-- COMMENT ON COLUMN audit_logs.staff_id IS '操作実行者のスタッフID（旧: actor_id）';
--
-- COMMIT;

-- ================================================================
-- Verification Queries
-- ================================================================
--
-- After running UPGRADE, verify the changes:
--
-- 1. Check constraint details:
-- SELECT
--     conname AS constraint_name,
--     contype AS constraint_type,
--     confdeltype AS on_delete_action,
--     pg_get_constraintdef(oid) AS constraint_definition
-- FROM pg_constraint
-- WHERE conrelid = 'audit_logs'::regclass
--   AND conname = 'audit_logs_staff_id_fkey';
--
-- Expected: confdeltype should be 'n' (SET NULL)
--
-- 2. Check column nullable status:
-- SELECT
--     column_name,
--     data_type,
--     is_nullable,
--     column_default
-- FROM information_schema.columns
-- WHERE table_name = 'audit_logs'
--   AND column_name = 'staff_id';
--
-- Expected: is_nullable should be 'YES'
--
-- 3. Test: Create audit log with NULL staff_id (system operation)
-- INSERT INTO audit_logs (
--     staff_id,
--     action,
--     target_type,
--     target_id,
--     office_id,
--     actor_role,
--     details,
--     is_test_data
-- ) VALUES (
--     NULL,  -- System operation
--     'system.test',
--     'test',
--     gen_random_uuid(),
--     NULL,
--     'system',
--     '{"test": true}'::jsonb,
--     true
-- );
--
-- 4. Check existing NULL records:
-- SELECT COUNT(*) FROM audit_logs WHERE staff_id IS NULL;
--
-- ================================================================
