"""add_function_create_calendar

Revision ID: k6bsnmc8hdki
Revises: si3z83ycga3r
Create Date: 2025-10-21 00:00:17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'k6bsnmc8hdki'
down_revision: Union[str, None] = 'si3z83ycga3r'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 期限が近いイベントを検出する関数
    op.execute("""
        CREATE OR REPLACE FUNCTION detect_upcoming_deadlines()
        RETURNS TABLE(
            office_id UUID,
            welfare_recipient_id UUID,
            recipient_name TEXT,
            event_type calendar_event_type,
            deadline_date DATE,
            cycle_id INTEGER,
            status_id INTEGER,
            days_until_deadline INTEGER
        ) AS $$
        BEGIN
            RETURN QUERY

            -- 更新期限（30日以内）
            SELECT
                owr.office_id,
                spc.welfare_recipient_id,
                wr.first_name || ' ' || wr.last_name as recipient_name,
                'renewal_deadline'::calendar_event_type as event_type,
                spc.next_renewal_deadline as deadline_date,
                spc.id as cycle_id,
                NULL::INTEGER as status_id,
                (spc.next_renewal_deadline - CURRENT_DATE)::INTEGER as days_until_deadline
            FROM support_plan_cycles spc
            JOIN welfare_recipients wr ON spc.welfare_recipient_id = wr.id
            JOIN office_welfare_recipients owr ON wr.id = owr.welfare_recipient_id
            WHERE spc.next_renewal_deadline IS NOT NULL
              AND spc.next_renewal_deadline BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '30 days'
              AND NOT EXISTS (
                  SELECT 1 FROM calendar_events ce
                  WHERE ce.support_plan_cycle_id = spc.id
                    AND ce.event_type = 'renewal_deadline'
                    AND ce.sync_status IN ('pending', 'synced')
              )

            UNION ALL

            -- モニタリング期限（7日以内）
            SELECT
                owr.office_id,
                spc.welfare_recipient_id,
                wr.first_name || ' ' || wr.last_name as recipient_name,
                'monitoring_deadline'::calendar_event_type as event_type,
                sps.due_date as deadline_date,
                NULL::INTEGER as cycle_id,
                sps.id as status_id,
                (sps.due_date - CURRENT_DATE)::INTEGER as days_until_deadline
            FROM support_plan_statuses sps
            JOIN support_plan_cycles spc ON sps.plan_cycle_id = spc.id
            JOIN welfare_recipients wr ON spc.welfare_recipient_id = wr.id
            JOIN office_welfare_recipients owr ON wr.id = owr.welfare_recipient_id
            WHERE sps.due_date IS NOT NULL
              AND sps.due_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '7 days'
              AND NOT EXISTS (
                  SELECT 1 FROM calendar_events ce
                  WHERE ce.support_plan_status_id = sps.id
                    AND ce.event_type = 'monitoring_deadline'
                    AND ce.sync_status IN ('pending', 'synced')
              );
        END;
        $$ LANGUAGE plpgsql
    """)

    # カレンダーイベント作成関数
    op.execute("""
        CREATE OR REPLACE FUNCTION create_calendar_event(
            p_office_id UUID,
            p_welfare_recipient_id UUID,
            p_event_type calendar_event_type,
            p_event_date DATE,
            p_cycle_id INTEGER DEFAULT NULL,
            p_status_id INTEGER DEFAULT NULL
        )
        RETURNS UUID AS $$
        DECLARE
            v_event_id UUID;
            v_recipient_name TEXT;
            v_event_title TEXT;
            v_event_description TEXT;
            v_calendar_id TEXT;
            v_event_start TIMESTAMP WITH TIME ZONE;
            v_event_end TIMESTAMP WITH TIME ZONE;
        BEGIN
            -- 利用者名取得
            SELECT first_name || ' ' || last_name INTO v_recipient_name
            FROM welfare_recipients
            WHERE id = p_welfare_recipient_id;

            IF v_recipient_name IS NULL THEN
                RAISE EXCEPTION 'Welfare recipient not found: %', p_welfare_recipient_id;
            END IF;

            -- カレンダーID取得
            SELECT google_calendar_id INTO v_calendar_id
            FROM office_calendar_accounts
            WHERE office_id = p_office_id
              AND connection_status = 'connected'
              AND google_calendar_id IS NOT NULL;

            IF v_calendar_id IS NULL THEN
                RAISE EXCEPTION 'Office calendar not connected for office_id: %', p_office_id;
            END IF;

            -- イベントタイトル・説明生成
            CASE p_event_type
                WHEN 'renewal_deadline' THEN
                    v_event_title := v_recipient_name || ' 更新期限';
                    v_event_description := v_recipient_name || 'さんの個別支援計画の更新期限です。';
                WHEN 'monitoring_deadline' THEN
                    v_event_title := v_recipient_name || ' モニタリング期限';
                    v_event_description := v_recipient_name || 'さんのモニタリング期限です。';
                ELSE
                    v_event_title := v_recipient_name || ' カレンダーイベント';
                    v_event_description := v_recipient_name || 'さんに関するイベントです。';
            END CASE;

            -- イベント時刻設定（9:00-10:00）
            v_event_start := p_event_date::TIMESTAMP WITH TIME ZONE + INTERVAL '9 hours';
            v_event_end := p_event_date::TIMESTAMP WITH TIME ZONE + INTERVAL '10 hours';

            -- カレンダーイベントレコード作成
            INSERT INTO calendar_events (
                office_id,
                welfare_recipient_id,
                support_plan_cycle_id,
                support_plan_status_id,
                event_type,
                google_calendar_id,
                event_title,
                event_description,
                event_start_datetime,
                event_end_datetime,
                sync_status
            ) VALUES (
                p_office_id,
                p_welfare_recipient_id,
                p_cycle_id,
                p_status_id,
                p_event_type,
                v_calendar_id,
                v_event_title,
                v_event_description,
                v_event_start,
                v_event_end,
                'pending'
            ) RETURNING id INTO v_event_id;

            RETURN v_event_id;
        END;
        $$ LANGUAGE plpgsql
    """)

    # 自動イベント作成バッチ関数
    op.execute("""
        CREATE OR REPLACE FUNCTION create_calendar_events_batch()
        RETURNS TABLE(
            created_event_id UUID,
            office_id UUID,
            recipient_name TEXT,
            event_type calendar_event_type,
            deadline_date DATE,
            success BOOLEAN,
            error_message TEXT
        ) AS $$
        DECLARE
            deadline_record RECORD;
            v_event_id UUID;
            v_error_msg TEXT;
        BEGIN
            FOR deadline_record IN
                SELECT * FROM detect_upcoming_deadlines()
            LOOP
                BEGIN
                    SELECT create_calendar_event(
                        deadline_record.office_id,
                        deadline_record.welfare_recipient_id,
                        deadline_record.event_type,
                        deadline_record.deadline_date,
                        deadline_record.cycle_id,
                        deadline_record.status_id
                    ) INTO v_event_id;

                    RETURN QUERY SELECT
                        v_event_id,
                        deadline_record.office_id,
                        deadline_record.recipient_name,
                        deadline_record.event_type,
                        deadline_record.deadline_date,
                        TRUE,
                        NULL::TEXT;

                EXCEPTION WHEN OTHERS THEN
                    v_error_msg := SQLERRM;

                    RETURN QUERY SELECT
                        NULL::UUID,
                        deadline_record.office_id,
                        deadline_record.recipient_name,
                        deadline_record.event_type,
                        deadline_record.deadline_date,
                        FALSE,
                        v_error_msg;
                END;
            END LOOP;
        END;
        $$ LANGUAGE plpgsql
    """)


def downgrade() -> None:
    op.execute('DROP FUNCTION IF EXISTS create_calendar_events_batch()')
    op.execute('DROP FUNCTION IF EXISTS create_calendar_event(UUID, UUID, calendar_event_type, DATE, INTEGER, INTEGER)')
    op.execute('DROP FUNCTION IF EXISTS detect_upcoming_deadlines()')
