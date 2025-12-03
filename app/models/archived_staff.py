"""
法定保存義務に基づくスタッフアーカイブモデル

労働基準法第109条、障害者総合支援法に基づき、
退職・削除されたスタッフの法定保存データを5年間保持する。
"""

import uuid
from datetime import datetime, timedelta, timezone
from dateutil.relativedelta import relativedelta
from typing import Optional
from sqlalchemy import String, DateTime, Boolean, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class ArchivedStaff(Base):
    """
    法定保存義務に基づくスタッフアーカイブ

    労働基準法、障害者総合支援法の要件を満たすため、
    退職・削除されたスタッフの法定保存データを5年間保持する。

    個人識別情報は匿名化され、法定保存が必要な情報のみを含む。
    """
    __tablename__ = 'archived_staffs'

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid()
    )
    original_staff_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="元のスタッフID（参照整合性なし）"
    )
    anonymized_full_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="匿名化された氏名（例: スタッフ-ABC123）"
    )
    anonymized_email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="匿名化されたメール（例: archived-ABC123@deleted.local）"
    )
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="役職（owner/manager/employee）"
    )
    office_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
        comment="所属していた事務所ID（参照整合性なし）"
    )
    office_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="事務所名（スナップショット）"
    )
    hired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="雇入れ日（元のcreated_at）"
    )
    terminated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="退職日（deleted_at）"
    )
    archived_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
        comment="アーカイブ作成日時"
    )
    archive_reason: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="アーカイブ理由（staff_deletion/staff_withdrawal/office_withdrawal）"
    )
    legal_retention_until: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="法定保存期限（terminated_at + 5年）"
    )
    metadata_: Mapped[Optional[dict]] = mapped_column(
        "metadata",  # DBのカラム名
        JSONB,
        nullable=True,
        comment="その他の法定保存が必要なメタデータ"
    )
    is_test_data: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
        comment="テストデータフラグ"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now()
    )

    __table_args__ = (
        Index('idx_archived_staffs_retention_until', 'legal_retention_until'),
        Index('idx_archived_staffs_office_id', 'office_id'),
    )

    @classmethod
    def calculate_retention_until(cls, terminated_at: datetime, years: int = 5) -> datetime:
        """
        法定保存期限を計算（退職日 + 5年）

        Args:
            terminated_at: 退職日
            years: 保存年数（デフォルト5年）

        Returns:
            保存期限日時
        """
        return terminated_at + relativedelta(years=years)

    def is_retention_expired(self) -> bool:
        """
        法定保存期限が過ぎているかチェック

        Returns:
            期限切れの場合True
        """
        return datetime.now(timezone.utc) >= self.legal_retention_until
