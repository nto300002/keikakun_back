"""Add canceling status to BillingStatus enum

Revision ID: acke3219j1m2
Revises: x1y2z3a4b5c6
Create Date: 2025-12-18

BillingStatus enumに'canceling'を追加
- 期間終了時にキャンセル予定の状態を表す
- cancel_at_period_end=trueの場合に使用
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'acke3219j1m2'
down_revision: Union[str, None] = 'x1y2z3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """BillingStatus enumに'canceling'を追加"""

    # 1. デフォルト値を一時的に削除
    op.execute("ALTER TABLE billings ALTER COLUMN billing_status DROP DEFAULT")

    # 2. 既存のenumを一時的にリネーム
    op.execute("ALTER TYPE billingstatus RENAME TO billingstatus_old")

    # 3. 新しいenumを作成（cancelingを追加）
    op.execute("""
        CREATE TYPE billingstatus AS ENUM(
            'free',
            'early_payment',
            'active',
            'past_due',
            'canceling',
            'canceled'
        )
    """)

    # 4. billingsテーブルのbilling_statusカラムを新しいenum型に変換
    op.execute("""
        ALTER TABLE billings
        ALTER COLUMN billing_status
        TYPE billingstatus
        USING billing_status::text::billingstatus
    """)

    # 5. デフォルト値を再設定
    op.execute("ALTER TABLE billings ALTER COLUMN billing_status SET DEFAULT 'free'::billingstatus")

    # 6. 古いenum型を削除
    op.execute("DROP TYPE billingstatus_old")


def downgrade() -> None:
    """BillingStatus enumから'canceling'を削除"""

    # 1. cancelingステータスのデータをcanceledに変換（データ保護）
    op.execute("""
        UPDATE billings
        SET billing_status = 'canceled'
        WHERE billing_status = 'canceling'
    """)

    # 2. デフォルト値を一時的に削除
    op.execute("ALTER TABLE billings ALTER COLUMN billing_status DROP DEFAULT")

    # 3. 既存のenumを一時的にリネーム
    op.execute("ALTER TYPE billingstatus RENAME TO billingstatus_new")

    # 4. 古いenumを作成（cancelingなし）
    op.execute("""
        CREATE TYPE billingstatus AS ENUM(
            'free',
            'early_payment',
            'active',
            'past_due',
            'canceled'
        )
    """)

    # 5. billingsテーブルのbilling_statusカラムを古いenum型に変換
    op.execute("""
        ALTER TABLE billings
        ALTER COLUMN billing_status
        TYPE billingstatus
        USING billing_status::text::billingstatus
    """)

    # 6. デフォルト値を再設定
    op.execute("ALTER TABLE billings ALTER COLUMN billing_status SET DEFAULT 'free'::billingstatus")

    # 7. 新しいenum型を削除
    op.execute("DROP TYPE billingstatus_new")
