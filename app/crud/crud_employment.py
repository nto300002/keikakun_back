"""
就労関係のCRUD操作
"""

from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import UUID

from app.models.assessment import EmploymentRelated
from app.schemas.assessment import EmploymentCreate, EmploymentUpdate
from fastapi.encoders import jsonable_encoder


class CRUDEmployment:
    """就労関係のCRUD操作クラス"""

    async def get_employment(
        self,
        db: AsyncSession,
        *,
        recipient_id: UUID
    ) -> Optional[EmploymentRelated]:
        """
        指定された利用者IDの就労関係情報を取得（1対1の関係）

        Args:
            db: データベースセッション
            recipient_id: 利用者ID

        Returns:
            就労関係情報、存在しない場合はNone
        """
        stmt = select(EmploymentRelated).where(
            EmploymentRelated.welfare_recipient_id == recipient_id
        )
        result = await db.execute(stmt)
        return result.scalars().first()

    async def upsert(
        self,
        db: AsyncSession,
        *,
        recipient_id: UUID,
        staff_id: UUID,
        obj_in: EmploymentCreate
    ) -> EmploymentRelated:
        """
        存在すれば更新、存在しなければ作成（PUT操作用）

        Args:
            db: データベースセッション
            recipient_id: 利用者ID
            staff_id: スタッフID（作成者）
            obj_in: 作成/更新データ

        Returns:
            作成または更新された就労関係情報

        Note:
            - 新規作成時: created_by_staff_idを設定
            - 更新時: created_by_staff_idは変更しない
        """
        # 既存レコードを検索
        existing = await self.get_employment(db=db, recipient_id=recipient_id)

        if existing:
            # 存在する場合: 更新（created_by_staff_idは変更しない）
            obj_in_data = jsonable_encoder(obj_in)
            for field, value in obj_in_data.items():
                setattr(existing, field, value)

            db.add(existing)
            await db.commit()
            await db.refresh(existing)
            return existing
        else:
            # 存在しない場合: 作成（created_by_staff_idを設定）
            obj_in_data = jsonable_encoder(obj_in)
            db_obj = EmploymentRelated(
                **obj_in_data,
                welfare_recipient_id=recipient_id,
                created_by_staff_id=staff_id
            )
            db.add(db_obj)
            await db.commit()
            await db.refresh(db_obj)
            return db_obj


crud_employment = CRUDEmployment()
