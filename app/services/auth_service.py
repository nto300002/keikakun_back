import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud

logger = logging.getLogger(__name__)


class AuthService:
    """認証関連のビジネスロジックを提供するサービス"""

    async def register_admin(
        self,
        db: AsyncSession,
        *,
        staff_in,
    ):
        """
        管理者スタッフを新規作成してコミットする

        Args:
            db: データベースセッション
            staff_in: 管理者作成データ (AdminCreate)

        Returns:
            作成されたスタッフ（リレーションシップ読み込み済み）
        """
        from app.models.staff import Staff
        from app.models.office import OfficeStaff

        user = await crud.staff.create_admin(db=db, obj_in=staff_in)
        user_id = user.id
        try:
            await db.commit()
        except Exception:
            await db.rollback()
            raise

        # リレーションシップを含めて再取得
        stmt = (
            select(Staff)
            .options(selectinload(Staff.office_associations).selectinload(OfficeStaff.office))
            .where(Staff.id == user_id)
        )
        result = await db.execute(stmt)
        return result.scalar_one()

    async def register_staff(
        self,
        db: AsyncSession,
        *,
        staff_in,
    ):
        """
        一般スタッフを新規作成してコミットする

        Args:
            db: データベースセッション
            staff_in: スタッフ作成データ (StaffCreate)

        Returns:
            作成されたスタッフ（リレーションシップ読み込み済み）
        """
        from app.models.staff import Staff
        from app.models.office import OfficeStaff

        user = await crud.staff.create_staff(db=db, obj_in=staff_in)
        user_id = user.id
        try:
            await db.commit()
        except Exception:
            await db.rollback()
            raise

        # リレーションシップを含めて再取得
        stmt = (
            select(Staff)
            .options(selectinload(Staff.office_associations).selectinload(OfficeStaff.office))
            .where(Staff.id == user_id)
        )
        result = await db.execute(stmt)
        return result.scalar_one()

    async def verify_email(
        self,
        db: AsyncSession,
        *,
        user,
    ) -> str:
        """
        メールアドレス確認済みにしてコミットする

        Args:
            db: データベースセッション
            user: 確認対象スタッフ (Staff)

        Returns:
            スタッフのロール文字列
        """
        user_role = user.role
        user.is_email_verified = True
        db.add(user)
        try:
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        return user_role

    async def use_recovery_code(
        self,
        db: AsyncSession,
        *,
        user_id,
        recovery_code: str,
    ) -> bool:
        """
        リカバリーコードを使用済みとしてマークしてコミットする

        Args:
            db: データベースセッション
            user_id: スタッフID
            recovery_code: 平文のリカバリーコード

        Returns:
            コードが有効で使用済みにできた場合はTrue、それ以外はFalse
        """
        from app.models.mfa import MFABackupCode
        from app.core.security import verify_recovery_code

        stmt = select(MFABackupCode).where(
            MFABackupCode.staff_id == user_id,
            MFABackupCode.is_used == False,
        )
        result = await db.execute(stmt)
        backup_codes = result.scalars().all()

        for backup_code in backup_codes:
            if verify_recovery_code(recovery_code, backup_code.code_hash):
                backup_code.mark_as_used()
                try:
                    await db.commit()
                except Exception:
                    await db.rollback()
                    raise
                return True
        return False

    async def set_mfa_verified_by_user(
        self,
        db: AsyncSession,
        *,
        user,
    ):
        """
        MFA初回検証済みフラグをセットしてコミットする

        Args:
            db: データベースセッション
            user: 対象スタッフ (Staff)

        Returns:
            更新されたスタッフ
        """
        user.is_mfa_verified_by_user = True
        try:
            await db.commit()
            await db.refresh(user)
        except Exception:
            await db.rollback()
            raise
        return user

    async def create_password_reset_token(
        self,
        db: AsyncSession,
        *,
        staff_id,
        email: str,
        ip_address,
        user_agent,
    ) -> str:
        """
        パスワードリセットトークンを作成してコミットする

        Args:
            db: データベースセッション
            staff_id: スタッフID
            email: スタッフのメールアドレス
            ip_address: リクエスト元IPアドレス
            user_agent: リクエスト元User-Agent

        Returns:
            生成されたトークン文字列
        """
        from app.crud import password_reset as crud_password_reset

        try:
            # 既存の未使用トークンを無効化
            await crud_password_reset.invalidate_existing_tokens(db, staff_id=staff_id)

            # 新しいトークンを生成
            token = str(uuid.uuid4())
            await crud_password_reset.create_token(db, staff_id=staff_id, token=token)

            # 監査ログを記録（同一トランザクション内）
            await crud_password_reset.create_audit_log(
                db,
                staff_id=staff_id,
                action='requested',
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                success=True,
            )

            await db.commit()
            return token
        except Exception:
            await db.rollback()
            raise

    async def reset_password(
        self,
        db: AsyncSession,
        *,
        token_id,
        staff,
        new_password: str,
        email: str,
    ) -> None:
        """
        パスワードをリセットしてコミットする

        Args:
            db: データベースセッション
            token_id: パスワードリセットトークンID
            staff: 対象スタッフ (Staff)
            new_password: 新しいパスワード（平文）
            email: スタッフのメールアドレス

        Raises:
            HTTPException: トークンが既に使用済みの場合
        """
        from app.crud import password_reset as crud_password_reset
        from app.core.security import get_password_hash
        from datetime import datetime, timezone
        from fastapi import HTTPException
        from app.messages import ja

        try:
            # トークンを使用済みにマーク（楽観的ロック）
            marked_token = await crud_password_reset.mark_as_used(db, token_id=token_id)
            if not marked_token:
                raise HTTPException(
                    status_code=400,
                    detail=ja.AUTH_RESET_TOKEN_ALREADY_USED,
                )

            # パスワードを更新
            staff.hashed_password = get_password_hash(new_password)
            staff.password_changed_at = datetime.now(timezone.utc)

            # 監査ログを記録（同一トランザクション内）
            await crud_password_reset.create_audit_log(
                db,
                staff_id=staff.id,
                action='completed',
                email=email,
                success=True,
            )

            await db.commit()
        except HTTPException:
            await db.rollback()
            raise
        except Exception:
            await db.rollback()
            raise


auth_service = AuthService()
