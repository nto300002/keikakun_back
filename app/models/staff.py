import uuid
import datetime
from typing import List, Optional, TYPE_CHECKING
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, String, DateTime, UUID, ForeignKey, Enum as SQLAlchemyEnum, Boolean, Integer, select, delete
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import StaffRole

if TYPE_CHECKING:
    from app.models.office import Office, OfficeStaff
    from app.models.terms_agreement import TermsAgreement

class Staff(Base):
    """スタッフ"""
    __tablename__ = 'staffs'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    # DEPRECATED: 名前フィールド（後方互換性のため残す。新規コードではfirst_name/last_name/full_nameを使用すること）
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # 新しい名前フィールド
    last_name: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    last_name_furigana: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    first_name_furigana: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)  # 姓名を結合したもの（last_name + スペース + first_name）

    role: Mapped[StaffRole] = mapped_column(SQLAlchemyEnum(StaffRole), nullable=False)
    is_email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # MFA関連フィールド
    is_mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_mfa_verified_by_user: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # ユーザーが実際にTOTPアプリで検証を完了したか
    mfa_secret: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # 暗号化されたTOTPシークレット
    mfa_backup_codes_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 使用済みバックアップコード数

    # パスワード変更関連
    password_changed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_password_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    locked_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    is_test_data: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True, comment="テストデータフラグ。Factory関数で生成されたデータはTrue")

    # Relationships
    office_associations: Mapped[List["OfficeStaff"]] = relationship(
        "OfficeStaff",
        back_populates="staff",
        foreign_keys="[OfficeStaff.staff_id]"
    )
    mfa_backup_codes: Mapped[List["MFABackupCode"]] = relationship(back_populates="staff", cascade="all, delete-orphan")
    mfa_audit_logs: Mapped[List["MFAAuditLog"]] = relationship(back_populates="staff", cascade="all, delete-orphan")

    @property
    def office(self) -> Optional["Office"]:
        """プライマリ事業所を取得する（プロパティ）"""
        if not self.office_associations:
            return None
        # is_primary=Trueのものを優先、なければ最初のものを使用
        for assoc in self.office_associations:
            if assoc.is_primary:
                return assoc.office
        return self.office_associations[0].office if self.office_associations else None

    # Staff -> StaffCalendarAccount (one-to-one)
    calendar_account: Mapped[Optional["StaffCalendarAccount"]] = relationship(
        "StaffCalendarAccount",
        back_populates="staff",
        uselist=False,
        cascade="all, delete-orphan"
    )

    # Staff -> TermsAgreement (one-to-one)
    terms_agreement: Mapped[Optional["TermsAgreement"]] = relationship(
        "TermsAgreement",
        back_populates="staff",
        uselist=False,
        cascade="all, delete-orphan"
    )
    
    # MFA関連メソッド
    def set_mfa_secret(self, secret: str) -> None:
        """MFAシークレットを暗号化して設定"""
        from app.core.security import encrypt_mfa_secret
        self.mfa_secret = encrypt_mfa_secret(secret)
    
    def get_mfa_secret(self) -> Optional[str]:
        """
        復号化されたMFAシークレットを取得

        Returns:
            Optional[str]: 復号化されたシークレット、または存在しない場合はNone

        Raises:
            ValueError: 復号化に失敗した場合（データ破損の可能性）
        """
        import logging
        logger = logging.getLogger(__name__)

        if not self.mfa_secret:
            return None

        try:
            from app.core.security import decrypt_mfa_secret
            logger.info(f"[MFA SECRET] Attempting to decrypt. Encrypted length: {len(self.mfa_secret)}")
            decrypted = decrypt_mfa_secret(self.mfa_secret)
            logger.info(f"[MFA SECRET] Decryption successful. Decrypted length: {len(decrypted)}")
            return decrypted
        except Exception as e:
            # 復号化失敗時は明示的にエラーを発生させる
            logger.error(f"[MFA SECRET] Decryption failed for user {self.email}: {str(e)}")
            raise ValueError(
                f"MFAシークレットの復号化に失敗しました。データが破損している可能性があります。"
            ) from e
    
    async def enable_mfa(self, db: AsyncSession, secret: str, recovery_codes: List[str]) -> None:
        """MFAを有効化"""
        self.set_mfa_secret(secret)
        self.is_mfa_enabled = True
        
        # リカバリーコードを保存
        from app.models.mfa import MFABackupCode
        from app.core.security import hash_recovery_code
        
        for code in recovery_codes:
            backup_code = MFABackupCode(
                staff_id=self.id,
                code_hash=hash_recovery_code(code),
                is_used=False
            )
            db.add(backup_code)
    
    async def disable_mfa(self, db: AsyncSession) -> None:
        """MFAを無効化"""
        self.is_mfa_enabled = False
        self.is_mfa_verified_by_user = False  # ← 追加: ユーザー検証フラグもリセット
        self.mfa_secret = None
        self.mfa_backup_codes_used = 0

        # バックアップコードを削除（明示的なDELETEクエリ）
        from app.models.mfa import MFABackupCode
        stmt = delete(MFABackupCode).where(MFABackupCode.staff_id == self.id)
        await db.execute(stmt)
    
    async def get_backup_codes(self, db: AsyncSession) -> List["MFABackupCode"]:
        """全てのバックアップコードを取得"""
        from app.models.mfa import MFABackupCode
        stmt = select(MFABackupCode).where(MFABackupCode.staff_id == self.id)
        result = await db.execute(stmt)
        return list(result.scalars().all())
    
    async def get_unused_backup_codes(self, db: AsyncSession) -> List["MFABackupCode"]:
        """未使用のバックアップコードを取得"""
        from app.models.mfa import MFABackupCode
        stmt = select(MFABackupCode).where(
            MFABackupCode.staff_id == self.id,
            MFABackupCode.is_used == False
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())
    
    async def has_backup_codes_remaining(self, db: AsyncSession) -> bool:
        """未使用のバックアップコードが残っているかチェック"""
        unused_codes = await self.get_unused_backup_codes(db)
        return len(unused_codes) > 0

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