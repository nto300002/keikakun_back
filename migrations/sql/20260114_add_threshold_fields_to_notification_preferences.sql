-- ============================================================================
-- Migration: Add threshold fields to notification_preferences
-- Date: 2026-01-14
-- Revision ID: b0c1d2e3f4g5
-- Revises: a9b0c1d2e3f4
--
-- Purpose:
--   Add email_threshold_days and push_threshold_days fields to existing
--   notification_preferences JSONB column in staffs table
-- ============================================================================

-- ============================================================================
-- UPGRADE
-- ============================================================================

BEGIN;

-- Step 1: Add threshold fields to all existing records
UPDATE staffs
SET notification_preferences = notification_preferences ||
    '{"email_threshold_days": 30, "push_threshold_days": 10}'::jsonb
WHERE notification_preferences IS NOT NULL;

-- Step 2: Update column default value for new records
ALTER TABLE staffs
ALTER COLUMN notification_preferences
SET DEFAULT '{
  "in_app_notification": true,
  "email_notification": true,
  "system_notification": false,
  "email_threshold_days": 30,
  "push_threshold_days": 10
}'::jsonb;

-- Update column comment
COMMENT ON COLUMN staffs.notification_preferences IS 'User notification channel preferences (in_app, email, system) + threshold settings (email_threshold_days: 5/10/20/30, push_threshold_days: 5/10/20/30)';

COMMIT;

-- ============================================================================
-- DOWNGRADE
-- ============================================================================

-- Uncomment below to rollback (restore to previous state)
-- BEGIN;
--
-- -- Step 1: Remove threshold fields from all existing records
-- UPDATE staffs
-- SET notification_preferences = notification_preferences - 'email_threshold_days' - 'push_threshold_days'
-- WHERE notification_preferences IS NOT NULL;
--
-- -- Step 2: Restore original default value
-- ALTER TABLE staffs
-- ALTER COLUMN notification_preferences
-- SET DEFAULT '{
--   "in_app_notification": true,
--   "email_notification": true,
--   "system_notification": false
-- }'::jsonb;
--
-- -- Restore original comment
-- COMMENT ON COLUMN staffs.notification_preferences IS 'User notification channel preferences (in_app, email, system)';
--
-- COMMIT;

-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================

-- 1. Verify threshold fields exist in existing records
SELECT
    id,
    email,
    notification_preferences->>'email_threshold_days' AS email_threshold,
    notification_preferences->>'push_threshold_days' AS push_threshold
FROM staffs
LIMIT 10;

-- Expected output: All records should have email_threshold = '30' and push_threshold = '10'

-- ============================================================================

-- 2. Verify default value updated
SELECT column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'staffs'
  AND column_name = 'notification_preferences';

-- Expected output: Default should include email_threshold_days and push_threshold_days

-- ============================================================================

-- 3. Count records with threshold fields
SELECT
    COUNT(*) AS total_staffs,
    COUNT(CASE WHEN notification_preferences ? 'email_threshold_days' THEN 1 END) AS has_email_threshold,
    COUNT(CASE WHEN notification_preferences ? 'push_threshold_days' THEN 1 END) AS has_push_threshold
FROM staffs;

-- Expected output: all three counts should be equal

-- ============================================================================

-- 4. Verify threshold value distribution
SELECT
    notification_preferences->>'email_threshold_days' AS email_threshold,
    notification_preferences->>'push_threshold_days' AS push_threshold,
    COUNT(*) AS count
FROM staffs
GROUP BY
    notification_preferences->>'email_threshold_days',
    notification_preferences->>'push_threshold_days'
ORDER BY count DESC;

-- Expected output (after migration): Most staffs should have default values (30, 10)

-- ============================================================================

-- 5. Test JSONB merge operation (dry run)
SELECT
    id,
    email,
    notification_preferences AS before,
    notification_preferences || '{"email_threshold_days": 20}'::jsonb AS after_update
FROM staffs
LIMIT 5;

-- This shows how JSONB merge works (|| operator adds/updates keys)

-- ============================================================================

-- 6. Verify JSONB structure consistency
SELECT
    id,
    email,
    jsonb_object_keys(notification_preferences) AS keys
FROM staffs
LIMIT 50;

-- Expected output: All records should have 5 keys (in_app_notification, email_notification, system_notification, email_threshold_days, push_threshold_days)

-- ============================================================================

-- 7. Test query with threshold filtering
SELECT
    id,
    email,
    notification_preferences->>'email_threshold_days' AS email_threshold
FROM staffs
WHERE (notification_preferences->>'email_threshold_days')::int <= 20
LIMIT 10;

-- This tests filtering by threshold value (useful for debugging)

-- ============================================================================

-- 8. Verify no NULL threshold values
SELECT
    id,
    email,
    notification_preferences
FROM staffs
WHERE
    notification_preferences->>'email_threshold_days' IS NULL OR
    notification_preferences->>'push_threshold_days' IS NULL;

-- Expected output: Empty result (all records should have threshold values)

-- ============================================================================
-- NOTES
-- ============================================================================

-- Threshold field details:
--   - email_threshold_days: 5, 10, 20, or 30 (default: 30)
--   - push_threshold_days: 5, 10, 20, or 30 (default: 10)
--
-- Valid threshold values are enforced by application-level validation (Pydantic schema)