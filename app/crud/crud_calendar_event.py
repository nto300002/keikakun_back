from typing import List, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select

from app.crud.base import CRUDBase
from app.models.calendar_events import CalendarEvent
from app.models.enums import CalendarSyncStatus
from app.schemas.calendar_event import CalendarEventCreate, CalendarEventUpdate


class CRUDCalendarEvent(CRUDBase[CalendarEvent, CalendarEventCreate, CalendarEventUpdate]):

    async def get_by_office_id(
        self,
        db: AsyncSession,
        office_id: UUID
    ) -> List[CalendarEvent]:
        """事業所IDでカレンダーイベント一覧を取得"""
        result = await db.execute(
            select(self.model)
            .where(self.model.office_id == office_id)
            .options(
                selectinload(self.model.welfare_recipient),
                selectinload(self.model.support_plan_cycle),
                selectinload(self.model.support_plan_status)
            )
        )
        return list(result.scalars().all())

    async def get_pending_sync_events(
        self,
        db: AsyncSession
    ) -> List[CalendarEvent]:
        """同期待ちのイベント一覧を取得"""
        result = await db.execute(
            select(self.model)
            .where(self.model.sync_status == CalendarSyncStatus.pending)
            .options(
                selectinload(self.model.welfare_recipient),
                selectinload(self.model.support_plan_cycle),
                selectinload(self.model.support_plan_status)
            )
        )
        return list(result.scalars().all())

    async def get_by_cycle_id(
        self,
        db: AsyncSession,
        cycle_id: UUID
    ) -> List[CalendarEvent]:
        """サイクルIDでカレンダーイベント一覧を取得"""
        result = await db.execute(
            select(self.model)
            .where(self.model.support_plan_cycle_id == cycle_id)
        )
        return list(result.scalars().all())

    async def get_by_status_id(
        self,
        db: AsyncSession,
        status_id: UUID
    ) -> List[CalendarEvent]:
        """ステータスIDでカレンダーイベント一覧を取得"""
        result = await db.execute(
            select(self.model)
            .where(self.model.support_plan_status_id == status_id)
        )
        return list(result.scalars().all())


# インスタンス化
crud_calendar_event = CRUDCalendarEvent(CalendarEvent)
