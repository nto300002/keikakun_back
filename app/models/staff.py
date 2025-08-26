import uuid
import datetime
from typing import List

from sqlalchemy import func, String, DateTime, UUID, ForeignKey, Enum as SQLAlchemyEnum, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import StaffRole

class Staff(Base):
    """スタッフ"""
    __tablename__ = 'staffs'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[StaffRole] = mapped_column(SQLAlchemyEnum(StaffRole), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Staff -> OfficeStaff (one-to-many)
    office_associations: Mapped[List["OfficeStaff"]] = relationship(back_populates="staff")

# パスワードリセット機能 
# class PasswordResetToken(Base):
#     """パスワードリセットトークン"""
#     __tablename__ = 'password_reset_tokens'
#     id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
#     staff_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('staffs.id', ondelete="CASCADE"), nullable=False)
#     token: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
#     expires_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
#     created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

#     staff: Mapped["Staff"] = relationship("Staff")