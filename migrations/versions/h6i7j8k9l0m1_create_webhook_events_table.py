"""create webhook_events table

Revision ID: h6i7j8k9l0m1
Revises: g5h6i7j8k9l0
Create Date: 2025-12-12 14:00:00.000000

Webhook冪等性実装のためのテーブル
Stripeから送信されるWebhookイベントの重複処理を防止するために使用
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'h6i7j8k9l0m1'
down_revision = 'g5h6i7j8k9l0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    webhook_eventsテーブルを作成

    目的:
    - Stripe Webhookイベントの重複処理を防止（冪等性担保）
    - 処理済みイベントの記録と監査

    使用方法:
    1. Webhook受信時にevent_idの存在確認
    2. 既に存在する場合は200 OKを返して処理スキップ
    3. 新規イベントの場合は処理を実行してテーブルに記録
    """
    op.create_table(
        'webhook_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('event_id', sa.String(length=255), nullable=False, comment='Stripe Event ID (例: evt_1234567890)'),
        sa.Column('event_type', sa.String(length=100), nullable=False, comment='イベントタイプ (例: invoice.payment_succeeded)'),
        sa.Column('source', sa.String(length=50), nullable=False, server_default='stripe', comment='Webhook送信元 (stripe, etc.)'),
        sa.Column('billing_id', postgresql.UUID(as_uuid=True), nullable=True, comment='関連するBilling ID'),
        sa.Column('office_id', postgresql.UUID(as_uuid=True), nullable=True, comment='関連するOffice ID'),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='Webhookペイロード（デバッグ用）'),
        sa.Column('processed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='処理日時'),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='success', comment='処理ステータス (success, failed, skipped)'),
        sa.Column('error_message', sa.Text(), nullable=True, comment='エラーメッセージ（処理失敗時）'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('event_id', name='uq_webhook_events_event_id'),
        sa.ForeignKeyConstraint(['billing_id'], ['billings.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['office_id'], ['offices.id'], ondelete='SET NULL')
    )

    # インデックス作成
    op.create_index('idx_webhook_events_event_id', 'webhook_events', ['event_id'])
    op.create_index('idx_webhook_events_event_type', 'webhook_events', ['event_type'])
    op.create_index('idx_webhook_events_processed_at', 'webhook_events', ['processed_at'])
    op.create_index('idx_webhook_events_billing_id', 'webhook_events', ['billing_id'])
    op.create_index('idx_webhook_events_office_id', 'webhook_events', ['office_id'])
    op.create_index('idx_webhook_events_status', 'webhook_events', ['status'])


def downgrade() -> None:
    """
    webhook_eventsテーブルを削除
    """
    op.drop_index('idx_webhook_events_status', table_name='webhook_events')
    op.drop_index('idx_webhook_events_office_id', table_name='webhook_events')
    op.drop_index('idx_webhook_events_billing_id', table_name='webhook_events')
    op.drop_index('idx_webhook_events_processed_at', table_name='webhook_events')
    op.drop_index('idx_webhook_events_event_type', table_name='webhook_events')
    op.drop_index('idx_webhook_events_event_id', table_name='webhook_events')
    op.drop_table('webhook_events')
