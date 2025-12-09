from typing import Optional, List
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select, update

from app.crud.base import CRUDBase
from app.models.calendar_account import OfficeCalendarAccount
from app.models.enums import CalendarConnectionStatus
from app.schemas.calendar_account import (
    OfficeCalendarAccountCreate,
    OfficeCalendarAccountUpdate
)


class CRUDOfficeCalendarAccount(CRUDBase[OfficeCalendarAccount, OfficeCalendarAccountCreate, OfficeCalendarAccountUpdate]):

    async def get_by_office_id(
        self,
        db: AsyncSession,
        office_id: UUID
    ) -> Optional[OfficeCalendarAccount]:
        """事業所IDでカレンダーアカウントを取得"""
        result = await db.execute(
            select(self.model)
            .where(self.model.office_id == office_id)
            .options(selectinload(self.model.office))
        )
        return result.scalars().first()

    async def get_connected_accounts(
        self,
        db: AsyncSession
    ) -> List[OfficeCalendarAccount]:
        """連携済みのカレンダーアカウント一覧を取得"""
        result = await db.execute(
            select(self.model)
            .where(self.model.connection_status == CalendarConnectionStatus.connected)
            .options(selectinload(self.model.office))
        )
        return list(result.scalars().all())

    async def update_connection_status(
        self,
        db: AsyncSession,
        account_id: UUID,
        status: CalendarConnectionStatus,
        error_message: Optional[str] = None
    ) -> Optional[OfficeCalendarAccount]:
        """連携状態を更新"""
        update_data = {
            "connection_status": status,
            "last_error_message": error_message  # Noneの場合はNULLに更新される
        }

        await db.execute(
            update(self.model)
            .where(self.model.id == account_id)
            .values(**update_data)
        )
        # SQLAlchemyのライフサイクルに従い、CRUDレイヤーではcommitせずflushのみ実行
        # commitはエンドポイント層で実行される
        await db.flush()

        return await self.get(db, account_id)

    async def create_with_encryption(
        self,
        db: AsyncSession,
        *,
        obj_in: OfficeCalendarAccountCreate
    ) -> OfficeCalendarAccount:
        """暗号化してカレンダーアカウントを作成"""
        # スキーマをdictに変換
        obj_data = obj_in.model_dump()
        service_account_key = obj_data.pop('service_account_key', None)

        # モデルインスタンス作成
        db_obj = self.model(**obj_data)

        # サービスアカウントキーを暗号化して保存
        if service_account_key:
            db_obj.encrypt_service_account_key(service_account_key)

        db.add(db_obj)
        await db.flush()
        await db.refresh(db_obj)
        return db_obj

    async def update_with_encryption(
        self,
        db: AsyncSession,
        *,
        db_obj: OfficeCalendarAccount,
        obj_in: OfficeCalendarAccountUpdate
    ) -> OfficeCalendarAccount:
        """暗号化してカレンダーアカウントを更新"""
        update_data = obj_in.model_dump(exclude_unset=True)
        service_account_key = update_data.pop('service_account_key', None)

        # 通常の更新処理
        for field, value in update_data.items():
            setattr(db_obj, field, value)

        # サービスアカウントキーが含まれている場合は暗号化
        if service_account_key:
            db_obj.encrypt_service_account_key(service_account_key)

        db.add(db_obj)
        await db.flush()
        await db.refresh(db_obj)
        return db_obj


# インスタンス化
crud_office_calendar_account = CRUDOfficeCalendarAccount(OfficeCalendarAccount)
