"""
Billingモデル: 事業所の課金情報（Officeと1:1）
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import ForeignKey, String, Integer, DateTime, Index, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import BillingStatus


class Billing(Base):
    """事業所の課金情報（Officeと1:1リレーション）"""
    __tablename__ = "billings"

    # 主キー
    id: Mapped[UUID] = mapped_column(primary_key=True, server_default="gen_random_uuid()")

    # 外部キー（1:1リレーション）
    office_id: Mapped[UUID] = mapped_column(
        ForeignKey("offices.id", ondelete="CASCADE"),
        unique=True,
        nullable=False
    )

    # Stripe情報
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True)
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True)

    # 課金ステータス
    billing_status: Mapped[BillingStatus] = mapped_column(
        Enum(BillingStatus, name='billingstatus', create_constraint=True, native_enum=True),
        default=BillingStatus.free,
        nullable=False,
        index=True
    )

    # 無料期間
    trial_start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    trial_end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # 課金期間
    subscription_start_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    next_billing_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # 課金額
    current_plan_amount: Mapped[int] = mapped_column(Integer, default=6000, nullable=False)

    # 最終支払い日
    last_payment_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # スケジュールされたキャンセル日時
    scheduled_cancel_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # タイムスタンプ
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default="now()",
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default="now()",
        onupdate=datetime.now,
        nullable=False
    )

    # リレーション
    office: Mapped["Office"] = relationship(
        "Office",
        back_populates="billing",
        uselist=False
    )

    def __repr__(self) -> str:
        return f"<Billing(id={self.id}, office_id={self.office_id}, status={self.billing_status})>"


# インデックス定義
__table_args__ = (
    Index('idx_billings_billing_status', 'billing_status'),
)
