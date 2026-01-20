-- ================================================================
-- Migration: Add push_subscriptions table for Web Push notifications
-- Revision ID: z8a9b0c1d2e3
-- Revises: y7z8a9b0c1d2
-- Created: 2026-01-13
-- Description:
--   Create push_subscriptions table to store Web Push notification
--   subscription information for each staff member's device.
--   Supports multiple devices per staff (PC, smartphone, etc.).
-- ================================================================

-- ================================================================
-- UPGRADE
-- ================================================================

BEGIN;

-- 1. Create push_subscriptions table
CREATE TABLE push_subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    staff_id UUID NOT NULL,
    endpoint TEXT NOT NULL,
    p256dh_key TEXT NOT NULL,
    auth_key TEXT NOT NULL,
    user_agent TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,

    -- Foreign key constraint (CASCADE delete when staff is deleted)
    CONSTRAINT push_subscriptions_staff_id_fkey
        FOREIGN KEY (staff_id)
        REFERENCES staffs(id)
        ON DELETE CASCADE,

    -- Unique constraint (one subscription per endpoint)
    CONSTRAINT push_subscriptions_endpoint_key
        UNIQUE (endpoint)
);

-- 2. Create indexes for performance
-- Index on staff_id for fast retrieval of all devices per staff
CREATE INDEX idx_push_subscriptions_staff_id
ON push_subscriptions(staff_id);

-- Hash index on endpoint for fast duplicate checks
CREATE INDEX idx_push_subscriptions_endpoint_hash
ON push_subscriptions USING HASH (endpoint);

-- 3. Add table comment
COMMENT ON TABLE push_subscriptions IS 'Web Push通知の購読情報（スタッフのデバイス登録）';

-- 4. Add column comments
COMMENT ON COLUMN push_subscriptions.id IS '購読ID（UUID）';
COMMENT ON COLUMN push_subscriptions.staff_id IS 'スタッフID（削除時はCASCADE）';
COMMENT ON COLUMN push_subscriptions.endpoint IS 'Push Service提供のエンドポイントURL（UNIQUE）';
COMMENT ON COLUMN push_subscriptions.p256dh_key IS 'P-256公開鍵（暗号化用、Base64エンコード）';
COMMENT ON COLUMN push_subscriptions.auth_key IS '認証シークレット（Base64エンコード）';
COMMENT ON COLUMN push_subscriptions.user_agent IS 'デバイス/ブラウザ情報（任意）';
COMMENT ON COLUMN push_subscriptions.created_at IS '購読登録日時';
COMMENT ON COLUMN push_subscriptions.updated_at IS '最終更新日時';

-- 5. Create trigger function for updated_at auto-update
CREATE OR REPLACE FUNCTION update_push_subscriptions_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 6. Create trigger
CREATE TRIGGER trigger_update_push_subscriptions_updated_at
BEFORE UPDATE ON push_subscriptions
FOR EACH ROW
EXECUTE FUNCTION update_push_subscriptions_updated_at();

COMMIT;

-- ================================================================
-- DOWNGRADE (Rollback)
-- ================================================================
--
-- WARNING: This rollback will PERMANENTLY DELETE all push subscription data.
-- Users will need to re-enable push notifications after upgrading again.
--
-- To execute rollback, uncomment and run the following:
--
-- BEGIN;
--
-- -- 1. Drop trigger
-- DROP TRIGGER IF EXISTS trigger_update_push_subscriptions_updated_at ON push_subscriptions;
--
-- -- 2. Drop trigger function
-- DROP FUNCTION IF EXISTS update_push_subscriptions_updated_at();
--
-- -- 3. Drop indexes
-- DROP INDEX IF EXISTS idx_push_subscriptions_endpoint_hash;
-- DROP INDEX IF EXISTS idx_push_subscriptions_staff_id;
--
-- -- 4. Drop table (cascades all constraints)
-- DROP TABLE IF EXISTS push_subscriptions;
--
-- COMMIT;

-- ================================================================
-- Verification Queries
-- ================================================================
--
-- After running UPGRADE, verify the changes:
--
-- 1. Check table structure:
-- \d push_subscriptions
--
-- 2. Verify table exists:
-- SELECT
--     table_name,
--     table_type
-- FROM information_schema.tables
-- WHERE table_schema = 'public'
--   AND table_name = 'push_subscriptions';
--
-- Expected: 1 row with table_type = 'BASE TABLE'
--
-- 3. Check foreign key constraint:
-- SELECT
--     conname AS constraint_name,
--     contype AS constraint_type,
--     confdeltype AS on_delete_action,
--     pg_get_constraintdef(oid) AS constraint_definition
-- FROM pg_constraint
-- WHERE conrelid = 'push_subscriptions'::regclass
--   AND conname = 'push_subscriptions_staff_id_fkey';
--
-- Expected: confdeltype should be 'c' (CASCADE)
--
-- 4. Check unique constraint on endpoint:
-- SELECT
--     conname AS constraint_name,
--     contype AS constraint_type,
--     pg_get_constraintdef(oid) AS constraint_definition
-- FROM pg_constraint
-- WHERE conrelid = 'push_subscriptions'::regclass
--   AND conname = 'push_subscriptions_endpoint_key';
--
-- Expected: 1 row with contype = 'u' (UNIQUE)
--
-- 5. Check indexes:
-- SELECT
--     indexname,
--     indexdef
-- FROM pg_indexes
-- WHERE tablename = 'push_subscriptions'
-- ORDER BY indexname;
--
-- Expected: 3 indexes (primary key, staff_id, endpoint_hash)
--
-- 6. Check trigger exists:
-- SELECT
--     trigger_name,
--     event_manipulation,
--     action_statement
-- FROM information_schema.triggers
-- WHERE event_object_table = 'push_subscriptions';
--
-- Expected: trigger_update_push_subscriptions_updated_at
--
-- 7. Test: Insert a sample subscription (rollback after test)
-- BEGIN;
-- INSERT INTO push_subscriptions (
--     staff_id,
--     endpoint,
--     p256dh_key,
--     auth_key,
--     user_agent
-- ) VALUES (
--     (SELECT id FROM staffs LIMIT 1),  -- Use existing staff
--     'https://fcm.googleapis.com/fcm/send/TEST_ENDPOINT',
--     'BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUK',
--     'tBHItJI5svbpez7KI4CCXg',
--     'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'
-- );
--
-- -- Verify insertion
-- SELECT * FROM push_subscriptions;
--
-- -- Test updated_at trigger
-- UPDATE push_subscriptions
-- SET user_agent = 'Updated User Agent'
-- WHERE endpoint = 'https://fcm.googleapis.com/fcm/send/TEST_ENDPOINT';
--
-- -- Verify updated_at changed
-- SELECT id, created_at, updated_at FROM push_subscriptions;
--
-- -- Rollback test data
-- ROLLBACK;
--
-- 8. Test CASCADE delete (rollback after test)
-- BEGIN;
--
-- -- Create test staff
-- INSERT INTO staffs (id, email, last_name, first_name, hashed_password)
-- VALUES (
--     gen_random_uuid(),
--     'test_push@example.com',
--     'Test',
--     'Push',
--     'dummy_hash'
-- );
--
-- -- Create subscription for test staff
-- INSERT INTO push_subscriptions (staff_id, endpoint, p256dh_key, auth_key)
-- SELECT id, 'https://test.endpoint', 'test_p256dh', 'test_auth'
-- FROM staffs WHERE email = 'test_push@example.com';
--
-- -- Verify subscription exists
-- SELECT COUNT(*) FROM push_subscriptions
-- WHERE staff_id IN (SELECT id FROM staffs WHERE email = 'test_push@example.com');
-- -- Expected: 1
--
-- -- Delete staff (should cascade to push_subscriptions)
-- DELETE FROM staffs WHERE email = 'test_push@example.com';
--
-- -- Verify subscription was deleted (CASCADE)
-- SELECT COUNT(*) FROM push_subscriptions
-- WHERE endpoint = 'https://test.endpoint';
-- -- Expected: 0
--
-- ROLLBACK;
--
-- ================================================================
