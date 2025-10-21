"""add_calendar_series_functions

Revision ID: qwa542xilkfk
Revises: 4o56fybry6p5
Create Date: 2025-10-21 00:00:25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'qwa542xilkfk'
down_revision: Union[str, None] = '4o56fybry6p5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 期限が近いデータからシリーズ作成候補を検出
    op.execute("""
        CREATE OR REPLACE FUNCTION detect_series_candidates()
        RETURNS TABLE(
            office_id UUID,
            welfare_recipient_id UUID,
            recipient_name TEXT,
            event_type calendar_event_type,
            deadline_date DATE,
            cycle_id INTEGER,
            status_id INTEGER,
            suggested_pattern_id UUID
        ) AS $$
        BEGIN
            RETURN QUERY

            -- 更新期限の候補
            SELECT
                owr.office_id,
                spc.welfare_recipient_id,
                wr.first_name || ' ' || wr.last_name as recipient_name,
                'renewal_deadline'::calendar_event_type,
                spc.next_renewal_deadline,
                spc.id as cycle_id,
                NULL::INTEGER as status_id,
                np.id as suggested_pattern_id
            FROM support_plan_cycles spc
            JOIN welfare_recipients wr ON spc.welfare_recipient_id = wr.id
            JOIN office_welfare_recipients owr ON wr.id = owr.welfare_recipient_id
            CROSS JOIN notification_patterns np
            WHERE spc.next_renewal_deadline IS NOT NULL
              AND spc.next_renewal_deadline > CURRENT_DATE
              AND np.event_type = 'renewal_deadline'
              AND np.is_system_default = TRUE
              AND NOT EXISTS (
                  SELECT 1 FROM calendar_event_series ces
                  WHERE ces.support_plan_cycle_id = spc.id
                    AND ces.event_type = 'renewal_deadline'
              )

            UNION ALL

            -- モニタリング期限の候補
            SELECT
                owr.office_id,
                spc.welfare_recipient_id,
                wr.first_name || ' ' || wr.last_name as recipient_name,
                'monitoring_deadline'::calendar_event_type,
                sps.due_date,
                NULL::INTEGER as cycle_id,
                sps.id as status_id,
                np.id as suggested_pattern_id
            FROM support_plan_statuses sps
            JOIN support_plan_cycles spc ON sps.plan_cycle_id = spc.id
            JOIN welfare_recipients wr ON spc.welfare_recipient_id = wr.id
            JOIN office_welfare_recipients owr ON wr.id = owr.welfare_recipient_id
            CROSS JOIN notification_patterns np
            WHERE sps.due_date IS NOT NULL
              AND sps.due_date > CURRENT_DATE
              AND np.event_type = 'monitoring_deadline'
              AND np.is_system_default = TRUE
              AND NOT EXISTS (
                  SELECT 1 FROM calendar_event_series ces
                  WHERE ces.support_plan_status_id = sps.id
                    AND ces.event_type = 'monitoring_deadline'
              );
        END;
        $$ LANGUAGE plpgsql
    """)

    # シリーズの進捗状況更新
    op.execute("""
        CREATE OR REPLACE FUNCTION update_series_progress(p_series_id UUID)
        RETURNS VOID AS $$
        DECLARE
            v_total INTEGER;
            v_completed INTEGER;
        BEGIN
            -- インスタンス数をカウント
            SELECT
                COUNT(*),
                COUNT(CASE WHEN instance_status = 'completed' THEN 1 END)
            INTO v_total, v_completed
            FROM calendar_event_instances
            WHERE event_series_id = p_series_id;

            -- シリーズの進捗を更新
            UPDATE calendar_event_series
            SET
                total_instances = v_total,
                completed_instances = v_completed,
                updated_at = NOW()
            WHERE id = p_series_id;
        END;
        $$ LANGUAGE plpgsql
    """)


def downgrade() -> None:
    op.execute('DROP FUNCTION IF EXISTS update_series_progress(UUID)')
    op.execute('DROP FUNCTION IF EXISTS detect_series_candidates()')
