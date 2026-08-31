"""WebAuthn credentialと単回使用challengeの永続化モデル。"""

import datetime
import uuid
from enum import Enum
from typing import Optional, TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    LargeBinary,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.staff import Staff


class WebAuthnCeremony(str, Enum):
    """WebAuthnで許可するchallengeの用途。"""

    registration = "registration"
    authentication = "authentication"


class WebAuthnCredential(Base):
    """Serverが保持する公開鍵credential。秘密鍵や生体情報は保持しない。"""

    __tablename__ = "webauthn_credentials"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    staff_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("staffs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    credential_id: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, unique=True)
    public_key: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    sign_count: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    transports: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    aaguid: Mapped[Optional[uuid.UUID]] = mapped_column(nullable=True)
    backup_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    backup_state: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_used_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    staff: Mapped["Staff"] = relationship(back_populates="webauthn_credentials")


class WebAuthnChallenge(Base):
    """ceremony・利用者・短命sessionに束縛するchallenge hash。"""

    __tablename__ = "webauthn_challenges"
    __table_args__ = (
        UniqueConstraint("challenge_hash", name="uq_webauthn_challenges_challenge_hash"),
        CheckConstraint(
            "ceremony IN ('registration', 'authentication')",
            name="ck_webauthn_challenges_ceremony",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    staff_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("staffs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ceremony: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    challenge_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    session_id_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    expires_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    used_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    staff: Mapped["Staff"] = relationship(back_populates="webauthn_challenges")
