import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import func, String, DateTime, UUID, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.staff import Staff


class TermsAgreement(Base):
    """利用規約・プライバシーポリシーの同意履歴"""
    __tablename__ = 'terms_agreements'

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid()
    )
    staff_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('staffs.id', ondelete="CASCADE"),
        nullable=False,
        unique=True,  # 1:1関係を保証
        index=True
    )
    terms_of_service_agreed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True
    )
    privacy_policy_agreed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True
    )
    terms_version: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True
    )
    privacy_version: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True
    )
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45),  # IPv6対応（最大45文字）
        nullable=True
    )
    user_agent: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    # リレーション（1:1）
    staff: Mapped["Staff"] = relationship(
        "Staff",
        back_populates="terms_agreement"
    )

    def has_agreed_to_current_terms(self, current_version: str) -> bool:
        """
        現在のバージョンの利用規約に同意しているかチェック

        Args:
            current_version: 現在の利用規約バージョン

        Returns:
            同意している場合True
        """
        return (
            self.terms_of_service_agreed_at is not None
            and self.terms_version == current_version
        )

    def has_agreed_to_current_privacy(self, current_version: str) -> bool:
        """
        現在のバージョンのプライバシーポリシーに同意しているかチェック

        Args:
            current_version: 現在のプライバシーポリシーバージョン

        Returns:
            同意している場合True
        """
        return (
            self.privacy_policy_agreed_at is not None
            and self.privacy_version == current_version
        )

    def has_agreed_to_all_current(
        self,
        terms_version: str,
        privacy_version: str
    ) -> bool:
        """
        現在のバージョンの両方に同意しているかチェック

        Args:
            terms_version: 現在の利用規約バージョン
            privacy_version: 現在のプライバシーポリシーバージョン

        Returns:
            両方に同意している場合True
        """
        return (
            self.has_agreed_to_current_terms(terms_version)
            and self.has_agreed_to_current_privacy(privacy_version)
        )
