-- E2E test staff and office cleanup.
--
-- Targets:
--   - staffs.email contains both "e2e_staff" and "@example.com"
--   - offices.name contains "E2Eテスト事務所"
--   - offices directly tied to target staffs through created_by/last_modified_by/deleted_by/office_staffs
--
-- Run with:
--   psql "$TEST_DATABASE_URL" -f k_back/scripts/cleanup_e2e_staffs_and_offices.sql

BEGIN;

DO $$
DECLARE
    v_count integer;
BEGIN
    CREATE TEMP TABLE _e2e_staff_ids ON COMMIT DROP AS
    SELECT DISTINCT s.id
    FROM staffs s
    WHERE s.email ILIKE '%e2e_staff%'
      AND s.email ILIKE '%@example.com%';

    CREATE TEMP TABLE _e2e_office_ids ON COMMIT DROP AS
    SELECT DISTINCT o.id
    FROM offices o
    WHERE o.name LIKE '%E2Eテスト事務所%'
       OR o.created_by IN (SELECT id FROM _e2e_staff_ids)
       OR o.last_modified_by IN (SELECT id FROM _e2e_staff_ids)
       OR o.deleted_by IN (SELECT id FROM _e2e_staff_ids)
       OR EXISTS (
            SELECT 1
            FROM office_staffs os
            WHERE os.office_id = o.id
              AND os.staff_id IN (SELECT id FROM _e2e_staff_ids)
       );

    CREATE TEMP TABLE _e2e_welfare_recipient_ids ON COMMIT DROP AS
    SELECT DISTINCT owr.welfare_recipient_id AS id
    FROM office_welfare_recipients owr
    WHERE owr.office_id IN (SELECT id FROM _e2e_office_ids)
      AND NOT EXISTS (
          SELECT 1
          FROM office_welfare_recipients other_owr
          WHERE other_owr.welfare_recipient_id = owr.welfare_recipient_id
            AND other_owr.office_id NOT IN (SELECT id FROM _e2e_office_ids)
      );

    CREATE TEMP TABLE _e2e_support_plan_cycle_ids ON COMMIT DROP AS
    SELECT DISTINCT spc.id
    FROM support_plan_cycles spc
    WHERE spc.office_id IN (SELECT id FROM _e2e_office_ids)
       OR spc.welfare_recipient_id IN (SELECT id FROM _e2e_welfare_recipient_ids);

    CREATE TEMP TABLE _e2e_support_plan_status_ids ON COMMIT DROP AS
    SELECT DISTINCT sps.id
    FROM support_plan_statuses sps
    WHERE sps.office_id IN (SELECT id FROM _e2e_office_ids)
       OR sps.welfare_recipient_id IN (SELECT id FROM _e2e_welfare_recipient_ids)
       OR sps.plan_cycle_id IN (SELECT id FROM _e2e_support_plan_cycle_ids);

    CREATE TEMP TABLE _e2e_message_ids ON COMMIT DROP AS
    SELECT DISTINCT m.id
    FROM messages m
    WHERE m.office_id IN (SELECT id FROM _e2e_office_ids)
       OR m.sender_staff_id IN (SELECT id FROM _e2e_staff_ids);

    CREATE TEMP TABLE _e2e_calendar_event_series_ids ON COMMIT DROP AS
    SELECT DISTINCT ces.id
    FROM calendar_event_series ces
    WHERE ces.office_id IN (SELECT id FROM _e2e_office_ids)
       OR ces.welfare_recipient_id IN (SELECT id FROM _e2e_welfare_recipient_ids)
       OR ces.support_plan_cycle_id IN (SELECT id FROM _e2e_support_plan_cycle_ids)
       OR ces.support_plan_status_id IN (SELECT id FROM _e2e_support_plan_status_ids);

    CREATE TEMP TABLE _e2e_billing_ids ON COMMIT DROP AS
    SELECT DISTINCT b.id
    FROM billings b
    WHERE b.office_id IN (SELECT id FROM _e2e_office_ids);

    RAISE NOTICE 'E2E cleanup targets: staffs=%, offices=%, welfare_recipients=%, support_plan_cycles=%',
        (SELECT count(*) FROM _e2e_staff_ids),
        (SELECT count(*) FROM _e2e_office_ids),
        (SELECT count(*) FROM _e2e_welfare_recipient_ids),
        (SELECT count(*) FROM _e2e_support_plan_cycle_ids);

    UPDATE webhook_events
    SET billing_id = NULL
    WHERE billing_id IN (SELECT id FROM _e2e_billing_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'webhook_events.billing_id nulled: %', v_count;

    UPDATE webhook_events
    SET office_id = NULL
    WHERE office_id IN (SELECT id FROM _e2e_office_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'webhook_events.office_id nulled: %', v_count;

    UPDATE audit_logs
    SET staff_id = NULL
    WHERE staff_id IN (SELECT id FROM _e2e_staff_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'audit_logs.staff_id nulled: %', v_count;

    UPDATE audit_logs
    SET office_id = NULL
    WHERE office_id IN (SELECT id FROM _e2e_office_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'audit_logs.office_id nulled: %', v_count;

    UPDATE message_audit_logs
    SET staff_id = NULL
    WHERE staff_id IN (SELECT id FROM _e2e_staff_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'message_audit_logs.staff_id nulled: %', v_count;

    UPDATE message_audit_logs
    SET message_id = NULL
    WHERE message_id IN (SELECT id FROM _e2e_message_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'message_audit_logs.message_id nulled: %', v_count;

    UPDATE password_reset_audit_logs
    SET staff_id = NULL
    WHERE staff_id IN (SELECT id FROM _e2e_staff_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'password_reset_audit_logs.staff_id nulled: %', v_count;

    UPDATE office_audit_logs
    SET staff_id = NULL
    WHERE staff_id IN (SELECT id FROM _e2e_staff_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'office_audit_logs.staff_id nulled: %', v_count;

    UPDATE inquiry_details
    SET assigned_staff_id = NULL
    WHERE assigned_staff_id IN (SELECT id FROM _e2e_staff_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'inquiry_details.assigned_staff_id nulled: %', v_count;

    UPDATE staffs
    SET deleted_by = NULL
    WHERE deleted_by IN (SELECT id FROM _e2e_staff_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'staffs.deleted_by nulled: %', v_count;

    UPDATE offices
    SET deleted_by = NULL
    WHERE deleted_by IN (SELECT id FROM _e2e_staff_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'offices.deleted_by nulled: %', v_count;

    DELETE FROM calendar_event_instances
    WHERE event_series_id IN (SELECT id FROM _e2e_calendar_event_series_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'calendar_event_instances deleted: %', v_count;

    DELETE FROM calendar_events
    WHERE office_id IN (SELECT id FROM _e2e_office_ids)
       OR welfare_recipient_id IN (SELECT id FROM _e2e_welfare_recipient_ids)
       OR support_plan_cycle_id IN (SELECT id FROM _e2e_support_plan_cycle_ids)
       OR support_plan_status_id IN (SELECT id FROM _e2e_support_plan_status_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'calendar_events deleted: %', v_count;

    DELETE FROM calendar_event_series
    WHERE id IN (SELECT id FROM _e2e_calendar_event_series_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'calendar_event_series deleted: %', v_count;

    DELETE FROM inquiry_details
    WHERE message_id IN (SELECT id FROM _e2e_message_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'inquiry_details deleted: %', v_count;

    DELETE FROM message_recipients
    WHERE message_id IN (SELECT id FROM _e2e_message_ids)
       OR recipient_staff_id IN (SELECT id FROM _e2e_staff_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'message_recipients deleted: %', v_count;

    DELETE FROM messages
    WHERE id IN (SELECT id FROM _e2e_message_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'messages deleted: %', v_count;

    DELETE FROM notices
    WHERE office_id IN (SELECT id FROM _e2e_office_ids)
       OR recipient_staff_id IN (SELECT id FROM _e2e_staff_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'notices deleted: %', v_count;

    DELETE FROM approval_requests
    WHERE office_id IN (SELECT id FROM _e2e_office_ids)
       OR requester_staff_id IN (SELECT id FROM _e2e_staff_ids)
       OR reviewed_by_staff_id IN (SELECT id FROM _e2e_staff_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'approval_requests deleted: %', v_count;

    DELETE FROM employee_action_requests
    WHERE office_id IN (SELECT id FROM _e2e_office_ids)
       OR requester_staff_id IN (SELECT id FROM _e2e_staff_ids)
       OR approved_by_staff_id IN (SELECT id FROM _e2e_staff_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'employee_action_requests deleted: %', v_count;

    DELETE FROM role_change_requests
    WHERE office_id IN (SELECT id FROM _e2e_office_ids)
       OR requester_staff_id IN (SELECT id FROM _e2e_staff_ids)
       OR reviewed_by_staff_id IN (SELECT id FROM _e2e_staff_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'role_change_requests deleted: %', v_count;

    DELETE FROM push_subscriptions
    WHERE staff_id IN (SELECT id FROM _e2e_staff_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'push_subscriptions deleted: %', v_count;

    DELETE FROM terms_agreements
    WHERE staff_id IN (SELECT id FROM _e2e_staff_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'terms_agreements deleted: %', v_count;

    DELETE FROM email_change_requests
    WHERE staff_id IN (SELECT id FROM _e2e_staff_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'email_change_requests deleted: %', v_count;

    DELETE FROM password_histories
    WHERE staff_id IN (SELECT id FROM _e2e_staff_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'password_histories deleted: %', v_count;

    DELETE FROM password_reset_tokens
    WHERE staff_id IN (SELECT id FROM _e2e_staff_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'password_reset_tokens deleted: %', v_count;

    DELETE FROM refresh_token_blacklist
    WHERE staff_id IN (SELECT id FROM _e2e_staff_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'refresh_token_blacklist deleted: %', v_count;

    DELETE FROM mfa_backup_codes
    WHERE staff_id IN (SELECT id FROM _e2e_staff_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'mfa_backup_codes deleted: %', v_count;

    DELETE FROM mfa_audit_logs
    WHERE staff_id IN (SELECT id FROM _e2e_staff_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'mfa_audit_logs deleted: %', v_count;

    DELETE FROM staff_calendar_accounts
    WHERE staff_id IN (SELECT id FROM _e2e_staff_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'staff_calendar_accounts deleted: %', v_count;

    DELETE FROM plan_deliverables
    WHERE plan_cycle_id IN (SELECT id FROM _e2e_support_plan_cycle_ids)
       OR uploaded_by IN (SELECT id FROM _e2e_staff_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'plan_deliverables deleted: %', v_count;

    DELETE FROM support_plan_statuses
    WHERE id IN (SELECT id FROM _e2e_support_plan_status_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'support_plan_statuses deleted: %', v_count;

    DELETE FROM support_plan_cycles
    WHERE id IN (SELECT id FROM _e2e_support_plan_cycle_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'support_plan_cycles deleted: %', v_count;

    DELETE FROM history_of_hospital_visits
    WHERE medical_matters_id IN (
        SELECT id FROM medical_matters
        WHERE welfare_recipient_id IN (SELECT id FROM _e2e_welfare_recipient_ids)
    );
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'history_of_hospital_visits deleted: %', v_count;

    DELETE FROM family_of_service_recipients
    WHERE welfare_recipient_id IN (SELECT id FROM _e2e_welfare_recipient_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'family_of_service_recipients deleted: %', v_count;

    DELETE FROM welfare_services_used
    WHERE welfare_recipient_id IN (SELECT id FROM _e2e_welfare_recipient_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'welfare_services_used deleted: %', v_count;

    DELETE FROM employment_related
    WHERE welfare_recipient_id IN (SELECT id FROM _e2e_welfare_recipient_ids)
       OR created_by_staff_id IN (SELECT id FROM _e2e_staff_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'employment_related deleted: %', v_count;

    DELETE FROM issue_analyses
    WHERE welfare_recipient_id IN (SELECT id FROM _e2e_welfare_recipient_ids)
       OR created_by_staff_id IN (SELECT id FROM _e2e_staff_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'issue_analyses deleted: %', v_count;

    DELETE FROM medical_matters
    WHERE welfare_recipient_id IN (SELECT id FROM _e2e_welfare_recipient_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'medical_matters deleted: %', v_count;

    DELETE FROM disability_details
    WHERE disability_status_id IN (
        SELECT id FROM disability_statuses
        WHERE welfare_recipient_id IN (SELECT id FROM _e2e_welfare_recipient_ids)
    );
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'disability_details deleted: %', v_count;

    DELETE FROM disability_statuses
    WHERE welfare_recipient_id IN (SELECT id FROM _e2e_welfare_recipient_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'disability_statuses deleted: %', v_count;

    DELETE FROM emergency_contacts
    WHERE service_recipient_detail_id IN (
        SELECT id FROM service_recipient_details
        WHERE welfare_recipient_id IN (SELECT id FROM _e2e_welfare_recipient_ids)
    );
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'emergency_contacts deleted: %', v_count;

    DELETE FROM service_recipient_details
    WHERE welfare_recipient_id IN (SELECT id FROM _e2e_welfare_recipient_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'service_recipient_details deleted: %', v_count;

    DELETE FROM office_welfare_recipients
    WHERE office_id IN (SELECT id FROM _e2e_office_ids)
       OR welfare_recipient_id IN (SELECT id FROM _e2e_welfare_recipient_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'office_welfare_recipients deleted: %', v_count;

    DELETE FROM welfare_recipients
    WHERE id IN (SELECT id FROM _e2e_welfare_recipient_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'welfare_recipients deleted: %', v_count;

    DELETE FROM office_calendar_accounts
    WHERE office_id IN (SELECT id FROM _e2e_office_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'office_calendar_accounts deleted: %', v_count;

    DELETE FROM billings
    WHERE id IN (SELECT id FROM _e2e_billing_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'billings deleted: %', v_count;

    DELETE FROM office_audit_logs
    WHERE office_id IN (SELECT id FROM _e2e_office_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'office_audit_logs deleted: %', v_count;

    DELETE FROM office_staffs
    WHERE office_id IN (SELECT id FROM _e2e_office_ids)
       OR staff_id IN (SELECT id FROM _e2e_staff_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'office_staffs deleted: %', v_count;

    DELETE FROM offices
    WHERE id IN (SELECT id FROM _e2e_office_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'offices deleted: %', v_count;

    DELETE FROM staffs
    WHERE id IN (SELECT id FROM _e2e_staff_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'staffs deleted: %', v_count;
END $$;

COMMIT;
