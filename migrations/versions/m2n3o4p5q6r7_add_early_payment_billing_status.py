"""add early_payment billing status

Revision ID: m2n3o4p5q6r7
Revises: h6i7j8k9l0m1
Create Date: 2025-12-15 09:00:00.000000

早期支払い機能の追加
- billing_status に 'early_payment' を追加
- 無料トライアル中に課金設定を完了した場合のステータス
- CHECK制約を追加して有効な値のみを許可
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'm2n3o4p5q6r7'
down_revision: Union[str, None] = 'h6i7j8k9l0m1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    billing_status に early_payment を追加し、CHECK制約を設定

    early_payment:
    - 無料トライアル中に課金設定を完了した状態
    - trial_end_date まで無料で利用可能
    - trial_end_date 経過後、自動的に 'active' に変更される
    """

    # CHECK制約を追加（既存の値 + early_payment）
    op.execute("""
        ALTER TABLE billings
        ADD CONSTRAINT ck_billings_billing_status
        CHECK (billing_status IN ('free', 'early_payment', 'active', 'past_due', 'canceled'))
    """)

    # テーブルコメントを更新
    op.execute("""
        COMMENT ON COLUMN billings.billing_status IS
        'Billing status: free (無料トライアル), early_payment (早期支払い完了), active (課金中), past_due (支払い遅延), canceled (キャンセル済み)'
    """)


def downgrade() -> None:
    """
    ロールバック: CHECK制約を削除

    注意: early_payment 状態のレコードがある場合、
    downgrade前に手動で別のステータスに変更する必要があります
    """

    # early_payment 状態のレコードがないか確認
    # もしあれば警告を出力（実際には downgrade が失敗する可能性がある）
    op.execute("""
        DO $$
        DECLARE
            early_payment_count INT;
        BEGIN
            SELECT COUNT(*) INTO early_payment_count
            FROM billings
            WHERE billing_status = 'early_payment';

            IF early_payment_count > 0 THEN
                RAISE WARNING 'Found % records with billing_status = early_payment. These records should be updated before downgrade.', early_payment_count;
            END IF;
        END $$;
    """)

    # CHECK制約を削除
    op.execute("""
        ALTER TABLE billings
        DROP CONSTRAINT IF EXISTS ck_billings_billing_status
    """)

    # テーブルコメントを元に戻す
    op.execute("""
        COMMENT ON COLUMN billings.billing_status IS
        'Billing status: free (無料トライアル), active (課金中), past_due (支払い遅延), canceled (キャンセル済み)'
    """)
