"""Add is_test_data flag to all test-related tables

Revision ID: a1b2c3d4e5f6
Revises: t5u6v7w8x9y0
Create Date: 2025-11-19 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 't5u6v7w8x9y0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """すべての対象テーブルに is_test_data カラムとインデックスを追加"""

    # 必須テーブル群 (19テーブル)
    tables = [
        'offices',
        'staffs',
        'office_staffs',
        'welfare_recipients',
        'office_welfare_recipients',
        'support_plan_cycles',
        'support_plan_statuses',
        'calendar_event_series',
        'calendar_event_instances',
        'notices',
        'role_change_requests',
        'employee_action_requests',
        'service_recipient_details',
        'disability_statuses',
        'disability_details',
        'family_of_service_recipients',
        'medical_matters',
        'employment_related',
        'issue_analyses',
    ]

    # オプションテーブル群 (5テーブル)
    optional_tables = [
        'calendar_events',
        'plan_deliverables',
        'emergency_contacts',
        'welfare_services_used',
        'history_of_hospital_visits',
    ]

    # 全テーブルに対して is_test_data カラムとインデックスを追加
    all_tables = tables + optional_tables

    for table_name in all_tables:
        # is_test_data カラムを追加
        op.add_column(
            table_name,
            sa.Column('is_test_data', sa.Boolean(),
                     nullable=False, server_default='false',
                     comment='テストデータフラグ。Factory関数で生成されたデータはTrue')
        )

        # インデックスを作成
        op.create_index(
            f'idx_{table_name}_is_test_data',
            table_name,
            ['is_test_data']
        )


def downgrade() -> None:
    """すべてのインデックスとカラムを削除"""

    all_tables = [
        'offices', 'staffs', 'office_staffs', 'welfare_recipients',
        'office_welfare_recipients', 'support_plan_cycles',
        'support_plan_statuses', 'calendar_event_series',
        'calendar_event_instances', 'notices', 'role_change_requests',
        'employee_action_requests', 'service_recipient_details',
        'disability_statuses', 'disability_details',
        'family_of_service_recipients', 'medical_matters',
        'employment_related', 'issue_analyses', 'calendar_events',
        'plan_deliverables', 'emergency_contacts',
        'welfare_services_used', 'history_of_hospital_visits',
    ]

    for table_name in all_tables:
        # インデックスを削除
        op.drop_index(f'idx_{table_name}_is_test_data', table_name=table_name)

        # カラムを削除
        op.drop_column(table_name, 'is_test_data')
