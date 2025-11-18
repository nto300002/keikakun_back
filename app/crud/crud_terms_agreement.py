import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.crud.base import CRUDBase
from app.models.terms_agreement import TermsAgreement
from app.schemas.terms_agreement import TermsAgreementCreate, TermsAgreementUpdate


class CRUDTermsAgreement(CRUDBase[TermsAgreement, TermsAgreementCreate, TermsAgreementUpdate]):
    """利用規約同意履歴のCRUD操作"""

    async def get_by_staff_id(
        self,
        db: AsyncSession,
        *,
        staff_id: uuid.UUID
    ) -> Optional[TermsAgreement]:
        """
        スタッフIDで同意履歴を取得（1:1関係）

        Args:
            db: データベースセッション
            staff_id: スタッフID

        Returns:
            同意履歴、または None
        """
        query = select(TermsAgreement).where(TermsAgreement.staff_id == staff_id)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def agree_to_terms(
        self,
        db: AsyncSession,
        *,
        staff_id: uuid.UUID,
        terms_version: str,
        privacy_version: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> TermsAgreement:
        """
        利用規約・プライバシーポリシーに同意

        Args:
            db: データベースセッション
            staff_id: スタッフID
            terms_version: 利用規約バージョン
            privacy_version: プライバシーポリシーバージョン
            ip_address: IPアドレス
            user_agent: ユーザーエージェント

        Returns:
            更新された同意履歴
        """
        now = datetime.now(timezone.utc)

        # 既存の同意履歴を取得
        existing = await self.get_by_staff_id(db, staff_id=staff_id)

        if existing:
            # 既存レコードを更新
            existing.terms_of_service_agreed_at = now
            existing.privacy_policy_agreed_at = now
            existing.terms_version = terms_version
            existing.privacy_version = privacy_version
            existing.ip_address = ip_address
            existing.user_agent = user_agent

            await db.flush()
            await db.refresh(existing)
            return existing
        else:
            # 新規レコードを作成
            db_obj = TermsAgreement(
                staff_id=staff_id,
                terms_of_service_agreed_at=now,
                privacy_policy_agreed_at=now,
                terms_version=terms_version,
                privacy_version=privacy_version,
                ip_address=ip_address,
                user_agent=user_agent
            )
            db.add(db_obj)
            await db.flush()
            await db.refresh(db_obj)
            return db_obj


terms_agreement = CRUDTermsAgreement(TermsAgreement)
