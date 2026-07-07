from datetime import date, datetime, time
from typing import List, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select

from app.crud.base import CRUDBase
from app.models.calendar_events import CalendarEvent
from app.models.enums import CalendarEventType, CalendarSyncStatus
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
        cycle_id: int
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
        status_id: int
    ) -> List[CalendarEvent]:
        """ステータスIDでカレンダーイベント一覧を取得"""
        result = await db.execute(
            select(self.model)
            .where(self.model.support_plan_status_id == status_id)
        )
        return list(result.scalars().all())

    async def get_deadline_events(
        self,
        db: AsyncSession,
        *,
        office_id: UUID,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        event_type: Optional[CalendarEventType] = None,
        recipient_id: Optional[UUID] = None,
    ) -> List[CalendarEvent]:
        """期限カレンダー用のイベント一覧を取得する。"""
        stmt = (
            select(self.model)
            .where(self.model.office_id == office_id)
            .options(
                selectinload(self.model.welfare_recipient),
                selectinload(self.model.support_plan_cycle),
                selectinload(self.model.support_plan_status),
            )
            .order_by(self.model.event_start_datetime.asc(), self.model.created_at.asc())
        )

        if from_date is not None:
            start_datetime = datetime.combine(from_date, time.min)
            stmt = stmt.where(self.model.event_end_datetime >= start_datetime)

        if to_date is not None:
            end_datetime = datetime.combine(to_date, time.max)
            stmt = stmt.where(self.model.event_start_datetime <= end_datetime)

        if event_type is not None:
            stmt = stmt.where(self.model.event_type == event_type)

        if recipient_id is not None:
            stmt = stmt.where(self.model.welfare_recipient_id == recipient_id)

        result = await db.execute(stmt)
        return list(result.scalars().all())


# インスタンス化
crud_calendar_event = CRUDCalendarEvent(CalendarEvent)
