-- ╔══════════════════════════════════════════════════════════════╗
-- ║  ファクトリ生成テストデータ完全削除スクリプト                ║
-- ║  安全性: ファクトリパターンのデータのみを削除                ║
-- ╚══════════════════════════════════════════════════════════════╝

BEGIN;

DO $$
DECLARE
    -- スタッフ関連
    target_staff_ids UUID[];
    replacement_staff_id UUID;
    v_count INT;

    -- 事業所関連
    target_office_ids UUID[];

    -- 利用者関連
    target_welfare_ids UUID[];

BEGIN

    RAISE NOTICE '';
    RAISE NOTICE '╔══════════════════════════════════════════════════════════════╗';
    RAISE NOTICE '║          ファクトリテストデータ削除プロセス開始              ║';
    RAISE NOTICE '╚══════════════════════════════════════════════════════════════╝';
    RAISE NOTICE '';

    -- ========================================
    -- Phase 1: 削除対象の特定
    -- ========================================

    RAISE NOTICE '[Phase 1] 削除対象の特定...';
    RAISE NOTICE '';

    -- 1-1. ファクトリ生成スタッフの特定
    SELECT ARRAY_AGG(id) INTO target_staff_ids
    FROM staffs
    WHERE email LIKE '%@test.com'
       OR email LIKE '%@example.com'
       OR last_name LIKE '%テスト%'
       OR full_name LIKE '%テスト%';

    IF target_staff_ids IS NULL THEN
        RAISE NOTICE '  ファクトリStaffs: なし';
    ELSE
        RAISE NOTICE '  ファクトリStaffs: % 人', array_length(target_staff_ids, 1);
    END IF;

    -- 1-2. ファクトリ生成事業所の特定
    SELECT ARRAY_AGG(id) INTO target_office_ids
    FROM offices
    WHERE name LIKE '%テスト事業所%'
       OR name LIKE '%test%'
       OR name LIKE '%Test%';

    IF target_office_ids IS NULL THEN
        RAISE NOTICE '  ファクトリOffices: なし';
    ELSE
        RAISE NOTICE '  ファクトリOffices: % 件', array_length(target_office_ids, 1);
    END IF;

    -- 1-3. ファクトリ生成利用者の特定
    SELECT ARRAY_AGG(id) INTO target_welfare_ids
    FROM welfare_recipients
    WHERE first_name LIKE '%テスト%'
       OR last_name LIKE '%テスト%'
       OR first_name LIKE '%test%'
       OR last_name LIKE '%test%';

    IF target_welfare_ids IS NULL THEN
        RAISE NOTICE '  ファクトリWelfareRecipients: なし';
    ELSE
        RAISE NOTICE '  ファクトリWelfareRecipients: % 人', array_length(target_welfare_ids, 1);
    END IF;

    RAISE NOTICE '';

    -- ========================================
    -- Phase 2: 事業所関連データの削除
    -- ========================================

    IF target_office_ids IS NOT NULL THEN
        RAISE NOTICE '[Phase 2] 事業所関連データの削除...';

        -- plan_deliverables
        DELETE FROM plan_deliverables
        WHERE plan_cycle_id IN (
            SELECT id FROM support_plan_cycles
            WHERE office_id = ANY(target_office_ids)
        );
        GET DIAGNOSTICS v_count = ROW_COUNT;
        IF v_count > 0 THEN RAISE NOTICE '  ✓ plan_deliverables: %', v_count; END IF;

        -- support_plan_statuses
        DELETE FROM support_plan_statuses
        WHERE office_id = ANY(target_office_ids);
        GET DIAGNOSTICS v_count = ROW_COUNT;
        IF v_count > 0 THEN RAISE NOTICE '  ✓ support_plan_statuses: %', v_count; END IF;

        -- support_plan_cycles
        DELETE FROM support_plan_cycles
        WHERE office_id = ANY(target_office_ids);
        GET DIAGNOSTICS v_count = ROW_COUNT;
        IF v_count > 0 THEN RAISE NOTICE '  ✓ support_plan_cycles: %', v_count; END IF;

        -- calendar_events
        DELETE FROM calendar_events
        WHERE office_id = ANY(target_office_ids);
        GET DIAGNOSTICS v_count = ROW_COUNT;
        IF v_count > 0 THEN RAISE NOTICE '  ✓ calendar_events: %', v_count; END IF;

        -- office_calendar_accounts
        DELETE FROM office_calendar_accounts
        WHERE office_id = ANY(target_office_ids);
        GET DIAGNOSTICS v_count = ROW_COUNT;
        IF v_count > 0 THEN RAISE NOTICE '  ✓ office_calendar_accounts: %', v_count; END IF;

        -- notices
        DELETE FROM notices
        WHERE office_id = ANY(target_office_ids);
        GET DIAGNOSTICS v_count = ROW_COUNT;
        IF v_count > 0 THEN RAISE NOTICE '  ✓ notices: %', v_count; END IF;

        -- role_change_requests
        DELETE FROM role_change_requests
        WHERE office_id = ANY(target_office_ids);
        GET DIAGNOSTICS v_count = ROW_COUNT;
        IF v_count > 0 THEN RAISE NOTICE '  ✓ role_change_requests: %', v_count; END IF;

        -- employee_action_requests
        DELETE FROM employee_action_requests
        WHERE office_id = ANY(target_office_ids);
        GET DIAGNOSTICS v_count = ROW_COUNT;
        IF v_count > 0 THEN RAISE NOTICE '  ✓ employee_action_requests: %', v_count; END IF;

        -- office_welfare_recipients
        DELETE FROM office_welfare_recipients
        WHERE office_id = ANY(target_office_ids);
        GET DIAGNOSTICS v_count = ROW_COUNT;
        IF v_count > 0 THEN RAISE NOTICE '  ✓ office_welfare_recipients: %', v_count; END IF;

        -- office_staffs
        DELETE FROM office_staffs
        WHERE office_id = ANY(target_office_ids);
        GET DIAGNOSTICS v_count = ROW_COUNT;
        IF v_count > 0 THEN RAISE NOTICE '  ✓ office_staffs: %', v_count; END IF;

        -- offices
        DELETE FROM offices
        WHERE id = ANY(target_office_ids);
        GET DIAGNOSTICS v_count = ROW_COUNT;
        RAISE NOTICE '  ✓ offices: %', v_count;

        RAISE NOTICE '';
    END IF;

    -- ========================================
    -- Phase 3: 利用者関連データの削除
    -- ========================================

    IF target_welfare_ids IS NOT NULL THEN
        RAISE NOTICE '[Phase 3] 利用者関連データの削除...';

        -- plan_deliverables
        DELETE FROM plan_deliverables
        WHERE plan_cycle_id IN (
            SELECT id FROM support_plan_cycles
            WHERE welfare_recipient_id = ANY(target_welfare_ids)
        );
        GET DIAGNOSTICS v_count = ROW_COUNT;
        IF v_count > 0 THEN RAISE NOTICE '  ✓ plan_deliverables: %', v_count; END IF;

        -- support_plan_statuses (plan_cycle経由)
        DELETE FROM support_plan_statuses
        WHERE id IN (
            SELECT sps.id FROM support_plan_statuses sps
            INNER JOIN support_plan_cycles spc ON sps.plan_cycle_id = spc.id
            WHERE spc.welfare_recipient_id = ANY(target_welfare_ids)
        );
        GET DIAGNOSTICS v_count = ROW_COUNT;
        IF v_count > 0 THEN RAISE NOTICE '  ✓ support_plan_statuses: %', v_count; END IF;

        -- support_plan_cycles
        DELETE FROM support_plan_cycles
        WHERE welfare_recipient_id = ANY(target_welfare_ids);
        GET DIAGNOSTICS v_count = ROW_COUNT;
        IF v_count > 0 THEN RAISE NOTICE '  ✓ support_plan_cycles: %', v_count; END IF;

        -- welfare_recipients
        DELETE FROM welfare_recipients
        WHERE id = ANY(target_welfare_ids);
        GET DIAGNOSTICS v_count = ROW_COUNT;
        RAISE NOTICE '  ✓ welfare_recipients: %', v_count;

        RAISE NOTICE '';
    END IF;

    -- ========================================
    -- Phase 4: スタッフデータの削除
    -- ========================================

    IF target_staff_ids IS NOT NULL THEN
        RAISE NOTICE '[Phase 4] スタッフデータの削除...';

        -- 再割当先を探す
        SELECT s.id INTO replacement_staff_id
        FROM staffs s
        INNER JOIN office_staffs os ON s.id = os.staff_id
        WHERE s.role = 'owner'
          AND s.id != ALL(target_staff_ids)
          AND s.email NOT LIKE '%@test.com'
          AND s.email NOT LIKE '%@example.com'
        LIMIT 1;

        IF replacement_staff_id IS NOT NULL THEN
            RAISE NOTICE '  ✓ 再割当先スタッフを発見';

            -- offices.created_by を再割当
            UPDATE offices
            SET created_by = replacement_staff_id
            WHERE created_by = ANY(target_staff_ids);
            GET DIAGNOSTICS v_count = ROW_COUNT;
            IF v_count > 0 THEN RAISE NOTICE '    offices.created_by: %', v_count; END IF;

            -- offices.last_modified_by を再割当
            UPDATE offices
            SET last_modified_by = replacement_staff_id
            WHERE last_modified_by = ANY(target_staff_ids);
            GET DIAGNOSTICS v_count = ROW_COUNT;
            IF v_count > 0 THEN RAISE NOTICE '    offices.last_modified_by: %', v_count; END IF;
        ELSE
            RAISE NOTICE '  ⚠ 再割当先なし（全staffsが削除対象の可能性）';
        END IF;

        -- support_plan_statuses.completed_by を NULL に
        UPDATE support_plan_statuses
        SET completed_by = NULL
        WHERE completed_by = ANY(target_staff_ids);
        GET DIAGNOSTICS v_count = ROW_COUNT;
        IF v_count > 0 THEN RAISE NOTICE '  ✓ support_plan_statuses.completed_by: %', v_count; END IF;

        -- staffs を削除 (CASCADE)
        DELETE FROM staffs
        WHERE id = ANY(target_staff_ids);
        GET DIAGNOSTICS v_count = ROW_COUNT;
        RAISE NOTICE '  ✓ staffs (CASCADE): %', v_count;

        RAISE NOTICE '';
    END IF;

    -- ========================================
    -- 完了
    -- ========================================

    RAISE NOTICE '╔══════════════════════════════════════════════════════════════╗';
    RAISE NOTICE '║            ✅ ファクトリデータの削除完了                     ║';
    RAISE NOTICE '╚══════════════════════════════════════════════════════════════╝';
    RAISE NOTICE '';

END $$;

COMMIT;

-- 削除確認
SELECT
    'ファクトリStaffs (残)' as check_item,
    COUNT(*) as count
FROM staffs
WHERE email LIKE '%@test.com'
   OR email LIKE '%@example.com'
   OR last_name LIKE '%テスト%'
UNION ALL
SELECT
    'ファクトリOffices (残)',
    COUNT(*)
FROM offices
WHERE name LIKE '%テスト%'
   OR name LIKE '%test%';
