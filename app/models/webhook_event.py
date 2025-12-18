"""
WebhookEventモデル: Stripe Webhookイベントの冪等性管理
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import ForeignKey, String, Text, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class WebhookEvent(Base):
    """
    Webhook冪等性管理テーブル

    Stripeから送信されるWebhookイベントの重複処理を防止するために使用。
    各Webhookイベントは一度だけ処理されることを保証する。

    使用方法:
    1. Webhook受信時にevent_idの存在確認
    2. 既に存在する場合は200 OKを返して処理スキップ
    3. 新規イベントの場合は処理を実行してテーブルに記録
    """
    __tablename__ = "webhook_events"

    # 主キー
    id: Mapped[UUID] = mapped_column(primary_key=True, server_default="gen_random_uuid()")

    # Stripe Event情報
    event_id: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
        comment="Stripe Event ID (例: evt_1234567890)"
    )
    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="イベントタイプ (例: invoice.payment_succeeded)"
    )
    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="stripe",
        server_default="stripe",
        comment="Webhook送信元 (stripe, etc.)"
    )

    # 関連リソース
    billing_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("billings.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="関連するBilling ID"
    )
    office_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("offices.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="関連するOffice ID"
    )

    # ペイロード（デバッグ用）
    payload: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Webhookペイロード（デバッグ用）"
    )

    # 処理情報
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default="now()",
        nullable=False,
        index=True,
        comment="処理日時"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="success",
        server_default="success",
        index=True,
        comment="処理ステータス (success, failed, skipped)"
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="エラーメッセージ（処理失敗時）"
    )

    # タイムスタンプ
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default="now()",
        nullable=False
    )

    # リレーションシップ
    billing: Mapped[Optional["Billing"]] = relationship(
        "Billing",
        foreign_keys=[billing_id],
        uselist=False
    )
    office: Mapped[Optional["Office"]] = relationship(
        "Office",
        foreign_keys=[office_id],
        uselist=False
    )

    def __repr__(self) -> str:
        return f"<WebhookEvent(id={self.id}, event_id={self.event_id}, event_type={self.event_type}, status={self.status})>"
