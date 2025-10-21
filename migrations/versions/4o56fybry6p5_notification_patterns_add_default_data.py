"""notification_patterns_add_default_data

Revision ID: 4o56fybry6p5
Revises: 33eogsb9q8aj
Create Date: 2025-10-21 00:00:24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4o56fybry6p5'
down_revision: Union[str, None] = '33eogsb9q8aj'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 通知パターンのデフォルトデータ
    op.execute("""
        INSERT INTO notification_patterns (
            pattern_name,
            pattern_description,
            event_type,
            reminder_days_before,
            title_template,
            description_template,
            is_system_default
        ) VALUES
        (
            '更新期限_標準',
            '更新期限の標準的な通知パターン（30日前、7日前、1日前）',
            'renewal_deadline',
            ARRAY[30, 25, 20, 15, 10, 5, 1],
            '{recipient_name} 更新期限',
            '{recipient_name}さんの個別支援計画の更新期限（{deadline_date}）まで{days_before}日です。',
            TRUE
        ),
        (
            '更新期限_詳細',
            '更新期限の詳細な通知パターン（30日前、14日前、7日前、3日前、1日前）',
            'renewal_deadline',
            ARRAY[30, 25, 20, 15, 10, 5, 1],
            '{recipient_name} 更新期限',
            '{recipient_name}さんの個別支援計画の更新期限（{deadline_date}）まで{days_before}日です。',
            FALSE
        ),
        (
            'モニタリング_標準',
            'モニタリング期限の標準的な通知パターン（7日前、1日前）',
            'monitoring_deadline',
            ARRAY[7, 6, 5, 4, 3, 2, 1],
            '{recipient_name} モニタリング期限',
            '{recipient_name}さんのモニタリング期限（{deadline_date}）まで{days_before}日です。',
            TRUE
        ),
        (
            'モニタリング_詳細',
            'モニタリング期限の詳細な通知パターン（14日前、7日前、3日前、1日前）',
            'monitoring_deadline',
            ARRAY[14, 7, 3, 1],
            '{recipient_name} モニタリング期限',
            '{recipient_name}さんのモニタリング期限（{deadline_date}）まで{days_before}日です。',
            FALSE
        ),
        (
            '更新期限_最小限',
            '更新期限の最小限の通知パターン（7日前、1日前）',
            'renewal_deadline',
            ARRAY[7, 6, 5, 4, 3, 2, 1],
            '{recipient_name} 更新期限',
            '{recipient_name}さんの個別支援計画の更新期限（{deadline_date}）まで{days_before}日です。',
            FALSE
        )
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM notification_patterns
        WHERE pattern_name IN (
            '更新期限_標準',
            '更新期限_詳細',
            'モニタリング_標準',
            'モニタリング_詳細',
            '更新期限_最小限'
        )
    """)
