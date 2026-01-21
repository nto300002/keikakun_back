-- ============================================================================
-- Migration: Add notification_preferences to staffs table
-- Date: 2026-01-14
-- Revision ID: a9b0c1d2e3f4
-- Revises: z8a9b0c1d2e3
--
-- Purpose:
--   Add notification_preferences JSONB column to staffs table for managing
--   user notification channel preferences (in_app, email, system/web push)
--
-- Usage:
--   - Upgrade:   Execute UPGRADE section
--   - Downgrade: Execute DOWNGRADE section
--   - Verify:    Execute VERIFICATION QUERIES section
-- ============================================================================

-- ============================================================================
-- UPGRADE
-- ============================================================================

BEGIN;

-- Add notification_preferences column to staffs table
ALTER TABLE staffs ADD COLUMN notification_preferences JSONB DEFAULT '{
  "in_app_notification": true,
  "email_notification": true,
  "system_notification": false
}'::jsonb NOT NULL;

COMMENT ON COLUMN staffs.notification_preferences IS 'User notification channel preferences (in_app, email, system)';

-- Create index for JSONB queries (optional, for performance if needed later)
-- CREATE INDEX idx_staffs_notification_preferences ON staffs USING GIN (notification_preferences);

COMMIT;

-- ============================================================================
-- DOWNGRADE
-- ============================================================================

-- Uncomment below to rollback (restore to previous state)
-- BEGIN;
--
-- -- Remove notification_preferences column
-- ALTER TABLE staffs DROP COLUMN notification_preferences;
--
-- COMMIT;

-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================

-- 1. Verify column exists
SELECT column_name, data_type, column_default, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'staffs'
  AND column_name = 'notification_preferences';

-- Expected output:
-- column_name              | data_type | column_default                                                                                      | is_nullable
-- -------------------------+-----------+-----------------------------------------------------------------------------------------------------+-------------
-- notification_preferences | jsonb     | '{"in_app_notification": true, "email_notification": true, "system_notification": false}'::jsonb  | NO

-- ============================================================================

-- 2. Verify default value applied to existing records
SELECT
    id,
    email,
    notification_preferences
FROM staffs
LIMIT 5;

-- Expected output: All existing staffs should have default notification_preferences

-- ============================================================================

-- 3. Test JSONB query - Get staffs with system_notification enabled
SELECT
    id,
    email,
    notification_preferences->>'system_notification' AS system_notification
FROM staffs
WHERE notification_preferences->>'system_notification' = 'true';

-- Expected output: Empty result (default is false)

-- ============================================================================

-- 4. Test JSONB update - Enable system_notification for a specific staff
-- DO $$
-- DECLARE
--     test_staff_id UUID;
-- BEGIN
--     -- Get first staff ID
--     SELECT id INTO test_staff_id FROM staffs LIMIT 1;
--
--     -- Update notification_preferences
--     UPDATE staffs
--     SET notification_preferences = jsonb_set(
--         notification_preferences,
--         '{system_notification}',
--         'true'::jsonb
--     )
--     WHERE id = test_staff_id;
--
--     -- Verify update
--     RAISE NOTICE 'Updated staff: %', test_staff_id;
--
--     SELECT
--         id,
--         email,
--         notification_preferences
--     FROM staffs
--     WHERE id = test_staff_id;
--
--     -- Rollback test changes
--     ROLLBACK;
-- END $$;

-- ============================================================================

-- 5. Test all notification channels disabled (should not be allowed by app logic)
-- This is a data integrity check - application should prevent this
SELECT
    id,
    email,
    notification_preferences
FROM staffs
WHERE
    notification_preferences->>'in_app_notification' = 'false' AND
    notification_preferences->>'email_notification' = 'false' AND
    notification_preferences->>'system_notification' = 'false';

-- Expected output: Empty result (app validation prevents all channels OFF)

-- ============================================================================

-- 6. Count staffs by notification preference combination
SELECT
    notification_preferences->>'in_app_notification' AS in_app,
    notification_preferences->>'email_notification' AS email,
    notification_preferences->>'system_notification' AS system,
    COUNT(*) AS count
FROM staffs
GROUP BY
    notification_preferences->>'in_app_notification',
    notification_preferences->>'email_notification',
    notification_preferences->>'system_notification'
ORDER BY count DESC;

-- Expected output (after migration):
-- in_app | email | system | count
-- -------+-------+--------+-------
-- true   | true  | false  | <all existing staffs>

-- ============================================================================

-- 7. Test JSONB structure validation
SELECT
    id,
    email,
    notification_preferences ? 'in_app_notification' AS has_in_app,
    notification_preferences ? 'email_notification' AS has_email,
    notification_preferences ? 'system_notification' AS has_system
FROM staffs
LIMIT 5;

-- Expected output: All should return true for all three keys

-- ============================================================================

-- 8. Test JSONB partial update (modify single key)
-- DO $$
-- DECLARE
--     test_staff_id UUID;
-- BEGIN
--     -- Get first staff ID
--     SELECT id INTO test_staff_id FROM staffs LIMIT 1;
--
--     -- Enable email notification only
--     UPDATE staffs
--     SET notification_preferences = jsonb_set(
--         notification_preferences,
--         '{email_notification}',
--         'false'::jsonb
--     )
--     WHERE id = test_staff_id;
--
--     -- Verify other keys remain unchanged
--     SELECT
--         id,
--         email,
--         notification_preferences
--     FROM staffs
--     WHERE id = test_staff_id;
--
--     RAISE NOTICE 'Partial update test completed for staff: %', test_staff_id;
--
--     -- Rollback test changes
--     ROLLBACK;
-- END $$;

-- ============================================================================
-- NOTES
-- ============================================================================

-- Default values:
--   - in_app_notification: true  (Existing behavior - toast/popover notifications)
--   - email_notification: true   (Existing behavior - daily batch emails)
--   - system_notification: false (New feature - requires explicit opt-in)

-- Rationale for defaults:
--   1. Preserve existing notification behavior (in_app & email = true)
--   2. System notification requires browser permission, so default to false
--   3. Users must explicitly enable Web Push in profile settings

-- Future considerations:
--   - Add GIN index if JSONB query performance becomes an issue
--   - Consider CHECK constraint to prevent all channels = false (currently handled by app logic)
--   - Monitor notification_preferences query patterns for optimization

-- ============================================================================
-- END OF MIGRATION
-- ============================================================================
