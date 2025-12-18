"""make audit_log staff_id nullable

Revision ID: n3o4p5q6r7s8
Revises: m2n3o4p5q6r7
Create Date: 2025-12-15 12:00:00.000000

Phase 8: システムアクター問題解決

問題:
- Webhook等の自動処理では、実行者となるStaffが存在しない
- audit_logsテーブルのstaff_idがNOT NULL制約のため、監査ログを記録できない

解決策:
- staff_idをNULLABLEに変更
- 自動処理の場合はstaff_id=NULLで記録
- actor_typeフィールドで「system」を判別可能
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'n3o4p5q6r7s8'
down_revision: Union[str, None] = 'm2n3o4p5q6r7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    audit_logsテーブルのstaff_idをNULLABLEに変更

    これにより、Webhook等のシステムによる自動処理の監査ログを記録可能にする。
    - staff_id=NULL: システムによる自動処理
    - staff_id=UUID: スタッフによる手動操作
    """

    # staff_idカラムをNULLABLEに変更
    op.alter_column(
        'audit_logs',
        'staff_id',
        existing_type=sa.UUID(),
        nullable=True
    )

    # カラムコメントを更新
    op.execute("""
        COMMENT ON COLUMN audit_logs.staff_id IS
        'Staff ID (NULL for system-initiated actions)'
    """)


def downgrade() -> None:
    """
    ロールバック: staff_idをNOT NULL制約に戻す

    注意:
    - staff_id=NULLのレコードが存在する場合、downgradeは失敗する
    - 手動でstaff_idを設定するか、該当レコードを削除する必要がある
    """

    # staff_id=NULLのレコードが存在するか確認
    op.execute("""
        DO $$
        DECLARE
            null_count INT;
        BEGIN
            SELECT COUNT(*) INTO null_count
            FROM audit_logs
            WHERE staff_id IS NULL;

            IF null_count > 0 THEN
                RAISE WARNING 'Found % records with staff_id=NULL. These records must be updated or deleted before downgrade.', null_count;
            END IF;
        END $$;
    """)

    # staff_idカラムをNOT NULLに戻す
    op.alter_column(
        'audit_logs',
        'staff_id',
        existing_type=sa.UUID(),
        nullable=False
    )

    # カラムコメントを元に戻す
    op.execute("""
        COMMENT ON COLUMN audit_logs.staff_id IS
        'Staff ID who performed the action'
    """)
