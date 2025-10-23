"""
医療基本情報のCRUD操作
"""

from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import UUID

from app.models.assessment import MedicalMatters
from app.schemas.assessment import MedicalInfoCreate, MedicalInfoUpdate
from fastapi.encoders import jsonable_encoder


class CRUDMedicalInfo:
    """医療基本情報のCRUD操作クラス"""

    async def get_medical_info(
        self,
        db: AsyncSession,
        *,
        recipient_id: UUID
    ) -> Optional[MedicalMatters]:
        """
        指定された利用者IDの医療基本情報を取得（1対1の関係）

        Args:
            db: データベースセッション
            recipient_id: 利用者ID

        Returns:
            医療情報、存在しない場合はNone
        """
        stmt = select(MedicalMatters).where(
            MedicalMatters.welfare_recipient_id == recipient_id
        )
        result = await db.execute(stmt)
        return result.scalars().first()

    async def create(
        self,
        db: AsyncSession,
        *,
        recipient_id: UUID,
        obj_in: MedicalInfoCreate
    ) -> MedicalMatters:
        """
        新しい医療基本情報を作成

        Args:
            db: データベースセッション
            recipient_id: 利用者ID
            obj_in: 作成データ

        Returns:
            作成された医療情報

        Note:
            同じrecipient_idのレコードが既に存在する場合、unique制約エラーが発生
        """
        obj_in_data = jsonable_encoder(obj_in)
        db_obj = MedicalMatters(
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
        recipient_id: UUID,
        obj_in: MedicalInfoUpdate
    ) -> Optional[MedicalMatters]:
        """
        既存の医療基本情報を更新

        Args:
            db: データベースセッション
            recipient_id: 利用者ID
            obj_in: 更新データ

        Returns:
            更新された医療情報、存在しない場合はNone
        """
        stmt = select(MedicalMatters).where(
            MedicalMatters.welfare_recipient_id == recipient_id
        )
        result = await db.execute(stmt)
        db_obj = result.scalars().first()

        if not db_obj:
            return None

        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)

        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def upsert(
        self,
        db: AsyncSession,
        *,
        recipient_id: UUID,
        obj_in: MedicalInfoCreate
    ) -> MedicalMatters:
        """
        存在すれば更新、存在しなければ作成（PUT操作用）

        Args:
            db: データベースセッション
            recipient_id: 利用者ID
            obj_in: 作成/更新データ

        Returns:
            作成または更新された医療情報
        """
        # 既存レコードを検索
        existing = await self.get_medical_info(db=db, recipient_id=recipient_id)

        if existing:
            # 存在する場合: 更新
            obj_in_data = jsonable_encoder(obj_in)
            for field, value in obj_in_data.items():
                setattr(existing, field, value)

            db.add(existing)
            await db.commit()
            await db.refresh(existing)
            return existing
        else:
            # 存在しない場合: 作成
            return await self.create(db=db, recipient_id=recipient_id, obj_in=obj_in)


crud_medical_info = CRUDMedicalInfo()
