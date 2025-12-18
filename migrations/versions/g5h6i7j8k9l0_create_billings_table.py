"""create billings table

Revision ID: g5h6i7j8k9l0
Revises: f4g5h6i7j8k9
Create Date: 2025-12-11 00:00:00.000000

Phase 0: Billingテーブル移行（課金機能の前提作業）
- OfficeテーブルからBillingテーブルへの1:1分離
- Stripe連携情報と課金ステータスの管理
- 無料期間（180日）の自動計算
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'g5h6i7j8k9l0'
down_revision: Union[str, None] = 'f4g5h6i7j8k9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Billingテーブルを作成し、Officeテーブルからデータを移行"""

    # 1. billingsテーブルを作成
    op.create_table(
        'billings',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('office_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('stripe_customer_id', sa.String(length=255), nullable=True),
        sa.Column('stripe_subscription_id', sa.String(length=255), nullable=True),
        sa.Column('billing_status', sa.String(length=20), nullable=False, server_default='free'),
        sa.Column('trial_start_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('trial_end_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('subscription_start_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_billing_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('current_plan_amount', sa.Integer(), nullable=False, server_default='6000'),
        sa.Column('last_payment_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # 2. インデックスと制約を作成
    op.create_unique_constraint('uq_billings_office_id', 'billings', ['office_id'])
    op.create_unique_constraint('uq_billings_stripe_customer_id', 'billings', ['stripe_customer_id'])
    op.create_unique_constraint('uq_billings_stripe_subscription_id', 'billings', ['stripe_subscription_id'])
    op.create_index('idx_billings_billing_status', 'billings', ['billing_status'])

    # 外部キー制約（CASCADE DELETE）
    op.create_foreign_key(
        'fk_billings_office_id',
        'billings',
        'offices',
        ['office_id'],
        ['id'],
        ondelete='CASCADE'
    )

    # 3. Officeテーブルからデータを移行
    op.execute("""
        INSERT INTO billings (
            office_id,
            stripe_customer_id,
            stripe_subscription_id,
            billing_status,
            trial_start_date,
            trial_end_date,
            current_plan_amount,
            created_at,
            updated_at
        )
        SELECT
            id AS office_id,
            stripe_customer_id,
            stripe_subscription_id,
            billing_status,
            created_at AS trial_start_date,
            created_at + INTERVAL '180 days' AS trial_end_date,
            6000 AS current_plan_amount,
            now() AS created_at,
            now() AS updated_at
        FROM offices
    """)

    # 4. Officeテーブルから課金関連カラムを削除
    op.drop_column('offices', 'stripe_subscription_id')
    op.drop_column('offices', 'stripe_customer_id')
    op.drop_column('offices', 'billing_status')

    # テーブルコメント
    op.execute("""
        COMMENT ON TABLE billings IS
        '事業所の課金情報（Officeと1:1リレーション）'
    """)


def downgrade() -> None:
    """ロールバック: Billingテーブルを削除し、Officeテーブルに戻す"""

    # 1. Officeテーブルに課金関連カラムを追加
    op.add_column('offices', sa.Column('billing_status', sa.String(length=20), nullable=False, server_default='free'))
    op.add_column('offices', sa.Column('stripe_customer_id', sa.String(length=255), nullable=True))
    op.add_column('offices', sa.Column('stripe_subscription_id', sa.String(length=255), nullable=True))

    # 2. Billingテーブルからデータを戻す
    op.execute("""
        UPDATE offices
        SET
            billing_status = billings.billing_status,
            stripe_customer_id = billings.stripe_customer_id,
            stripe_subscription_id = billings.stripe_subscription_id
        FROM billings
        WHERE offices.id = billings.office_id
    """)

    # 3. Billingテーブルを削除
    op.drop_constraint('fk_billings_office_id', 'billings', type_='foreignkey')
    op.drop_index('idx_billings_billing_status', table_name='billings')
    op.drop_constraint('uq_billings_stripe_subscription_id', 'billings', type_='unique')
    op.drop_constraint('uq_billings_stripe_customer_id', 'billings', type_='unique')
    op.drop_constraint('uq_billings_office_id', 'billings', type_='unique')
    op.drop_table('billings')
