"""
統合型承認リクエストモデル

役割変更、Employee操作、退会の各種承認リクエストを統合管理
"""
import uuid
import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import func, DateTime, UUID, ForeignKey, Text, Boolean, Enum as SQLAlchemyEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import RequestStatus, ApprovalResourceType

if TYPE_CHECKING:
    from .staff import Staff
    from .office import Office


class ApprovalRequest(Base):
    """
    統合型承認リクエスト

    以下のリクエストタイプを統合:
    - role_change: 役割変更リクエスト（employee → manager昇格申請など）
    - employee_action: Employee操作リクエスト（CRUD許可申請）
    - withdrawal: 退会リクエスト（スタッフ/事務所の退会申請）

    request_dataにはリクエストタイプ固有のデータを格納:
    - role_change: {"from_role": "employee", "requested_role": "manager", "request_notes": "..."}
    - employee_action: {"resource_type": "...", "action_type": "...", "resource_id": "...", "original_request_data": {...}}
    - withdrawal: {"withdrawal_type": "staff|office", "reason": "...", "affected_staff_ids": [...]}
    """
    __tablename__ = 'approval_requests'

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid()
    )
    requester_staff_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('staffs.id', ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="リクエスト作成者のスタッフID"
    )
    office_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('offices.id', ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="対象事務所ID"
    )
    resource_type: Mapped[ApprovalResourceType] = mapped_column(
        SQLAlchemyEnum(ApprovalResourceType),
        nullable=False,
        index=True,
        comment="リクエスト種別: role_change, employee_action, withdrawal"
    )
    status: Mapped[RequestStatus] = mapped_column(
        SQLAlchemyEnum(RequestStatus),
        default=RequestStatus.pending,
        nullable=False,
        index=True,
        comment="ステータス: pending, approved, rejected"
    )
    request_data: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="リクエスト固有のデータ（JSON形式）"
    )
    reviewed_by_staff_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('staffs.id', ondelete="SET NULL"),
        nullable=True,
        comment="承認/却下したスタッフID"
    )
    reviewed_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="承認/却下日時"
    )
    reviewer_notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="承認者のメモ"
    )
    execution_result: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="実行結果（成功/失敗、エラーメッセージなど）"
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
    is_test_data: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
        comment="テストデータフラグ"
    )

    # Relationships
    requester: Mapped["Staff"] = relationship(
        "Staff",
        foreign_keys=[requester_staff_id],
        backref="approval_requests"
    )
    reviewer: Mapped[Optional["Staff"]] = relationship(
        "Staff",
        foreign_keys=[reviewed_by_staff_id]
    )
    office: Mapped["Office"] = relationship(
        "Office",
        foreign_keys=[office_id]
    )

    # ヘルパープロパティ
    @property
    def is_pending(self) -> bool:
        """承認待ちかどうか"""
        return self.status == RequestStatus.pending

    @property
    def is_approved(self) -> bool:
        """承認済みかどうか"""
        return self.status == RequestStatus.approved

    @property
    def is_rejected(self) -> bool:
        """却下されたかどうか"""
        return self.status == RequestStatus.rejected
