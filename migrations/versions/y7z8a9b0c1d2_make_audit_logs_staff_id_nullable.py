"""Make audit_logs.staff_id nullable with SET NULL

Revision ID: y7z8a9b0c1d2
Revises: x6y7z8a9b0c1
Create Date: 2026-01-12

Task: audit_logs.staff_idをNULL許可にし、外部キー制約をSET NULLに変更
- staff_idカラムをNOT NULL → NULL許可に変更
- 外部キー制約をCASCADE → SET NULLに変更
- これにより、スタッフ削除後も監査ログが保持される
- システム処理による操作も記録可能になる
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'y7z8a9b0c1d2'
down_revision: Union[str, None] = 'x6y7z8a9b0c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Make audit_logs.staff_id nullable and change FK to SET NULL"""

    # 1. 既存の外部キー制約を削除
    op.drop_constraint(
        'audit_logs_staff_id_fkey',
        'audit_logs',
        type_='foreignkey'
    )

    # 2. staff_idカラムをNULL許可に変更
    op.alter_column(
        'audit_logs',
        'staff_id',
        existing_type=postgresql.UUID(),
        nullable=True
    )

    # 3. 新しい外部キー制約を追加（SET NULL）
    op.create_foreign_key(
        'audit_logs_staff_id_fkey',
        'audit_logs',
        'staffs',
        ['staff_id'],
        ['id'],
        ondelete='SET NULL'
    )

    # 4. カラムのコメントを更新
    op.execute(
        """
        COMMENT ON COLUMN audit_logs.staff_id IS
        '操作実行者のスタッフID（システム処理の場合はNULL、削除されたスタッフの場合もNULL）'
        """
    )


def downgrade() -> None:
    """Revert audit_logs.staff_id to NOT NULL with CASCADE

    WARNING: This will fail if there are audit_logs records with NULL staff_id.
    You must handle those records before downgrading:
    - DELETE FROM audit_logs WHERE staff_id IS NULL; OR
    - UPDATE audit_logs SET staff_id = 'SYSTEM_USER_UUID' WHERE staff_id IS NULL;
    """

    # 1. 既存の外部キー制約を削除
    op.drop_constraint(
        'audit_logs_staff_id_fkey',
        'audit_logs',
        type_='foreignkey'
    )

    # 2. NULL値を持つレコードをチェック（存在する場合はエラー）
    # Note: 実際のダウングレード前に手動でNULL値を処理する必要がある

    # 3. staff_idカラムをNOT NULL制約に戻す
    op.alter_column(
        'audit_logs',
        'staff_id',
        existing_type=postgresql.UUID(),
        nullable=False
    )

    # 4. 元の外部キー制約を追加（CASCADE）
    op.create_foreign_key(
        'audit_logs_staff_id_fkey',
        'audit_logs',
        'staffs',
        ['staff_id'],
        ['id'],
        ondelete='CASCADE'
    )

    # 5. カラムのコメントを元に戻す
    op.execute(
        """
        COMMENT ON COLUMN audit_logs.staff_id IS
        '操作実行者のスタッフID（旧: actor_id）'
        """
    )
