"""
家族構成のCRUD操作
"""

from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import UUID

from app.models.assessment import FamilyOfServiceRecipients
from app.schemas.assessment import FamilyMemberCreate, FamilyMemberUpdate
from fastapi.encoders import jsonable_encoder


class CRUDFamilyMember:
    """家族構成のCRUD操作クラス"""

    async def get_family_members(
        self,
        db: AsyncSession,
        *,
        recipient_id: UUID
    ) -> List[FamilyOfServiceRecipients]:
        """
        指定された利用者IDの家族構成を全て取得

        Args:
            db: データベースセッション
            recipient_id: 利用者ID

        Returns:
            家族構成のリスト
        """
        stmt = select(FamilyOfServiceRecipients).where(
            FamilyOfServiceRecipients.welfare_recipient_id == recipient_id
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def create(
        self,
        db: AsyncSession,
        *,
        recipient_id: UUID,
        obj_in: FamilyMemberCreate
    ) -> FamilyOfServiceRecipients:
        """
        新しい家族メンバーをデータベースに追加

        Args:
            db: データベースセッション
            recipient_id: 利用者ID
            obj_in: 作成データ

        Returns:
            作成された家族メンバー
        """
        obj_in_data = jsonable_encoder(obj_in)
        db_obj = FamilyOfServiceRecipients(
            **obj_in_data,
            welfare_recipient_id=recipient_id
        )
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def update(
        self,
        db: AsyncSession,
        *,
        family_member_id: int,
        obj_in: FamilyMemberUpdate
    ) -> Optional[FamilyOfServiceRecipients]:
        """
        指定されたIDの家族メンバー情報を更新

        Args:
            db: データベースセッション
            family_member_id: 家族メンバーID
            obj_in: 更新データ

        Returns:
            更新された家族メンバー、存在しない場合はNone
        """
        # 既存のレコードを取得
        stmt = select(FamilyOfServiceRecipients).where(
            FamilyOfServiceRecipients.id == family_member_id
        )
        result = await db.execute(stmt)
        db_obj = result.scalars().first()

        if not db_obj:
            return None

        # 更新データを適用（exclude_unsetでNoneのフィールドは更新しない）
        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)

        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def delete(
        self,
        db: AsyncSession,
        *,
        family_member_id: int
    ) -> bool:
        """
        指定されたIDの家族メンバーを削除

        Args:
            db: データベースセッション
            family_member_id: 家族メンバーID

        Returns:
            削除成功ならTrue、失敗ならFalse
        """
        stmt = select(FamilyOfServiceRecipients).where(
            FamilyOfServiceRecipients.id == family_member_id
        )
        result = await db.execute(stmt)
        db_obj = result.scalars().first()

        if not db_obj:
            return False

        await db.delete(db_obj)
        await db.commit()
        return True


crud_family_member = CRUDFamilyMember()
