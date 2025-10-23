"""
福祉サービス利用歴のCRUD操作
"""

from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import UUID, desc

from app.models.assessment import WelfareServicesUsed
from app.schemas.assessment import ServiceHistoryCreate, ServiceHistoryUpdate
from fastapi.encoders import jsonable_encoder


class CRUDServiceHistory:
    """福祉サービス利用歴のCRUD操作クラス"""

    async def get_service_history(
        self,
        db: AsyncSession,
        *,
        recipient_id: UUID
    ) -> List[WelfareServicesUsed]:
        """
        指定された利用者IDの福祉サービス利用歴を全て取得
        利用開始日の降順（新しい順）でソート

        Args:
            db: データベースセッション
            recipient_id: 利用者ID

        Returns:
            福祉サービス利用歴のリスト
        """
        stmt = select(WelfareServicesUsed).where(
            WelfareServicesUsed.welfare_recipient_id == recipient_id
        ).order_by(desc(WelfareServicesUsed.starting_day))

        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def create(
        self,
        db: AsyncSession,
        *,
        recipient_id: UUID,
        obj_in: ServiceHistoryCreate
    ) -> WelfareServicesUsed:
        """
        新しいサービス利用歴を追加

        Args:
            db: データベースセッション
            recipient_id: 利用者ID
            obj_in: 作成データ

        Returns:
            作成されたサービス利用歴
        """
        obj_in_data = jsonable_encoder(obj_in)
        db_obj = WelfareServicesUsed(
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
        history_id: int,
        obj_in: ServiceHistoryUpdate
    ) -> Optional[WelfareServicesUsed]:
        """
        指定されたIDのサービス利用歴を更新

        Args:
            db: データベースセッション
            history_id: サービス利用歴ID
            obj_in: 更新データ

        Returns:
            更新されたサービス利用歴、存在しない場合はNone
        """
        stmt = select(WelfareServicesUsed).where(
            WelfareServicesUsed.id == history_id
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

    async def delete(
        self,
        db: AsyncSession,
        *,
        history_id: int
    ) -> bool:
        """
        指定されたIDのサービス利用歴を削除

        Args:
            db: データベースセッション
            history_id: サービス利用歴ID

        Returns:
            削除成功ならTrue、失敗ならFalse
        """
        stmt = select(WelfareServicesUsed).where(
            WelfareServicesUsed.id == history_id
        )
        result = await db.execute(stmt)
        db_obj = result.scalars().first()

        if not db_obj:
            return False

        await db.delete(db_obj)
        await db.commit()
        return True


crud_service_history = CRUDServiceHistory()
