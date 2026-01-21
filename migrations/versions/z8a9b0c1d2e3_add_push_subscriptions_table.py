"""Add push_subscriptions table for Web Push notifications

Revision ID: z8a9b0c1d2e3
Revises: y7z8a9b0c1d2
Create Date: 2026-01-13

Task: Web Push通知のためのpush_subscriptionsテーブル作成
- staff_id: スタッフID（外部キー、CASCADE削除）
- endpoint: Push Service提供のエンドポイントURL（UNIQUE制約）
- p256dh_key: 公開鍵（暗号化用）
- auth_key: 認証キー
- user_agent: デバイス情報（任意）
- created_at/updated_at: タイムスタンプ
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'z8a9b0c1d2e3'
down_revision: Union[str, None] = 'y7z8a9b0c1d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add push_subscriptions table for Web Push notifications"""

    # 1. push_subscriptionsテーブル作成
    op.create_table(
        'push_subscriptions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('staff_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('endpoint', sa.Text(), nullable=False),
        sa.Column('p256dh_key', sa.Text(), nullable=False),
        sa.Column('auth_key', sa.Text(), nullable=False),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),

        # 外部キー制約
        sa.ForeignKeyConstraint(
            ['staff_id'],
            ['staffs.id'],
            name='push_subscriptions_staff_id_fkey',
            ondelete='CASCADE'
        ),

        # UNIQUE制約（同一エンドポイントは1つのみ）
        sa.UniqueConstraint('endpoint', name='push_subscriptions_endpoint_key')
    )

    # 2. インデックス作成
    # staff_idでの検索を高速化（スタッフの全デバイス取得時）
    op.create_index(
        'idx_push_subscriptions_staff_id',
        'push_subscriptions',
        ['staff_id']
    )

    # endpointのハッシュインデックス（重複チェック高速化）
    op.execute(
        """
        CREATE INDEX idx_push_subscriptions_endpoint_hash
        ON push_subscriptions USING HASH (endpoint)
        """
    )

    # 3. テーブルコメント
    op.execute(
        """
        COMMENT ON TABLE push_subscriptions IS
        'Web Push通知の購読情報（スタッフのデバイス登録）'
        """
    )

    # 4. カラムコメント
    op.execute(
        """
        COMMENT ON COLUMN push_subscriptions.id IS '購読ID（UUID）';
        COMMENT ON COLUMN push_subscriptions.staff_id IS 'スタッフID（削除時はCASCADE）';
        COMMENT ON COLUMN push_subscriptions.endpoint IS 'Push Service提供のエンドポイントURL（UNIQUE）';
        COMMENT ON COLUMN push_subscriptions.p256dh_key IS 'P-256公開鍵（暗号化用、Base64エンコード）';
        COMMENT ON COLUMN push_subscriptions.auth_key IS '認証シークレット（Base64エンコード）';
        COMMENT ON COLUMN push_subscriptions.user_agent IS 'デバイス/ブラウザ情報（任意）';
        COMMENT ON COLUMN push_subscriptions.created_at IS '購読登録日時';
        COMMENT ON COLUMN push_subscriptions.updated_at IS '最終更新日時';
        """
    )

    # 5. updated_atの自動更新トリガー作成
    op.execute(
        """
        CREATE OR REPLACE FUNCTION update_push_subscriptions_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trigger_update_push_subscriptions_updated_at
        BEFORE UPDATE ON push_subscriptions
        FOR EACH ROW
        EXECUTE FUNCTION update_push_subscriptions_updated_at();
        """
    )


def downgrade() -> None:
    """Remove push_subscriptions table

    WARNING: This will permanently delete all push subscription data.
    Users will need to re-enable push notifications after upgrading again.
    """

    # 1. トリガー削除
    op.execute('DROP TRIGGER IF EXISTS trigger_update_push_subscriptions_updated_at ON push_subscriptions')
    op.execute('DROP FUNCTION IF EXISTS update_push_subscriptions_updated_at()')

    # 2. インデックス削除
    op.execute('DROP INDEX IF EXISTS idx_push_subscriptions_endpoint_hash')
    op.drop_index('idx_push_subscriptions_staff_id', table_name='push_subscriptions')

    # 3. テーブル削除
    op.drop_table('push_subscriptions')
