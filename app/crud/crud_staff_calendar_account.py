from typing import Optional, List
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy import select

from app.crud.base import CRUDBase
from app.models.calendar_account import StaffCalendarAccount
from app.models.office import OfficeStaff
from app.schemas.calendar_account import (
    StaffCalendarAccountCreate,
    StaffCalendarAccountUpdate
)


class CRUDStaffCalendarAccount(CRUDBase[StaffCalendarAccount, StaffCalendarAccountCreate, StaffCalendarAccountUpdate]):

    async def get_by_staff_id(
        self,
        db: AsyncSession,
        staff_id: UUID
    ) -> Optional[StaffCalendarAccount]:
        """スタッフIDでカレンダーアカウントを取得"""
        result = await db.execute(
            select(self.model)
            .where(self.model.staff_id == staff_id)
            .options(selectinload(self.model.staff))
        )
        return result.scalars().first()

    async def get_notification_enabled_by_office(
        self,
        db: AsyncSession,
        office_id: UUID
    ) -> List[StaffCalendarAccount]:
        """事業所の通知有効スタッフのカレンダーアカウント一覧を取得"""
        result = await db.execute(
            select(self.model)
            .join(self.model.staff)
            .join(OfficeStaff, OfficeStaff.staff_id == self.model.staff_id)
            .where(
                self.model.calendar_notifications_enabled == True,
                OfficeStaff.office_id == office_id
            )
            .options(
                selectinload(self.model.staff)
            )
        )
        return list(result.scalars().all())

    async def create_for_staff(
        self,
        db: AsyncSession,
        staff_id: UUID,
        **kwargs
    ) -> StaffCalendarAccount:
        """スタッフ用のカレンダーアカウントを作成（デフォルト設定付き）"""
        create_data = StaffCalendarAccountCreate(
            staff_id=staff_id,
            calendar_notifications_enabled=kwargs.get('calendar_notifications_enabled', True),
            email_notifications_enabled=kwargs.get('email_notifications_enabled', True),
            in_app_notifications_enabled=kwargs.get('in_app_notifications_enabled', True),
            **{k: v for k, v in kwargs.items() if k not in ['calendar_notifications_enabled', 'email_notifications_enabled', 'in_app_notifications_enabled']}
        )
        return await self.create(db, obj_in=create_data)

    async def get_all_with_notifications_enabled(
        self,
        db: AsyncSession
    ) -> List[StaffCalendarAccount]:
        """全ての通知有効スタッフを取得"""
        result = await db.execute(
            select(self.model)
            .where(
                (self.model.calendar_notifications_enabled == True) |
                (self.model.email_notifications_enabled == True) |
                (self.model.in_app_notifications_enabled == True)
            )
            .options(selectinload(self.model.staff))
        )
        return list(result.scalars().all())


# インスタンス化
crud_staff_calendar_account = CRUDStaffCalendarAccount(StaffCalendarAccount)
