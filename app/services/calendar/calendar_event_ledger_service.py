"""Calendar event ledger operations.

Google Calendarとの同期成否に関係なく、DB上の期限イベント台帳を扱う境界。
"""

import logging
from datetime import date, datetime, time, timedelta
from typing import Optional
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.crud_office_calendar_account import crud_office_calendar_account
from app.models.calendar_events import CalendarEvent
from app.models.enums import (
    CalendarConnectionStatus,
    CalendarEventType,
    CalendarSyncStatus,
)
from app.models.welfare_recipient import WelfareRecipient

logger = logging.getLogger(__name__)


class CalendarEventLedgerService:
    """DB上の期限イベント台帳を作成・検索・削除するサービス。"""

    async def create_renewal_deadline_events(
        self,
        db: AsyncSession,
        office_id: UUID,
        welfare_recipient_id: UUID,
        cycle_id: int,
        next_renewal_deadline: date,
    ) -> list[UUID]:
        existing_event = await self.get_event_by_cycle(
            db=db,
            cycle_id=cycle_id,
            event_type=CalendarEventType.renewal_deadline,
        )
        if existing_event:
            logger.info(
                "Renewal deadline event already exists. Skipping creation."
            )
            return []

        account = await crud_office_calendar_account.get_by_office_id(
            db=db,
            office_id=office_id,
        )
        if not account:
            logger.warning("Calendar account not found. Skipping event creation.")
            return []

        account_calendar_id = account.google_calendar_id
        if account.connection_status != CalendarConnectionStatus.connected:
            logger.warning("Calendar account not connected. Skipping event creation.")
            return []

        result = await db.execute(
            select(WelfareRecipient).where(WelfareRecipient.id == welfare_recipient_id)
        )
        recipient = result.scalar_one_or_none()
        if not recipient:
            logger.error("Welfare recipient not found")
            return []

        from app.models.support_plan_cycle import SupportPlanCycle

        cycle_result = await db.execute(
            select(SupportPlanCycle).where(SupportPlanCycle.id == cycle_id)
        )
        cycle = cycle_result.scalar_one_or_none()
        if not cycle:
            logger.error("Support plan cycle not found")
            return []

        jst = ZoneInfo("Asia/Tokyo")
        event_start_date = date.today() + timedelta(days=150)
        event = CalendarEvent(
            office_id=office_id,
            welfare_recipient_id=welfare_recipient_id,
            support_plan_cycle_id=cycle_id,
            event_type=CalendarEventType.renewal_deadline,
            google_calendar_id=account_calendar_id,
            event_title=f"{recipient.last_name} {recipient.first_name} 更新期限まで残り1ヶ月",
            event_description=f"個別支援計画の更新期限です（{cycle.cycle_number}回目）。\n期限: {next_renewal_deadline}",
            event_start_datetime=datetime.combine(event_start_date, time(9, 0), tzinfo=jst),
            event_end_datetime=datetime.combine(next_renewal_deadline, time(18, 0), tzinfo=jst),
            created_by_system=True,
            sync_status=CalendarSyncStatus.pending,
        )
        db.add(event)
        await db.flush()

        return [event.id]

    async def create_next_plan_start_date_events(
        self,
        db: AsyncSession,
        office_id: UUID,
        welfare_recipient_id: UUID,
        cycle_id: int,
        cycle_start_date: date,
        cycle_number: int,
        status_id: Optional[UUID] = None,
    ) -> list[UUID]:
        if not status_id:
            logger.warning("status_id is None. Cannot create monitoring event without status_id.")
            return []

        existing_event = await self.get_event_by_status(
            db=db,
            status_id=status_id,
            event_type=CalendarEventType.next_plan_start_date,
        )
        if existing_event:
            logger.info(
                "Monitoring deadline event already exists. Skipping creation."
            )
            return []

        account = await crud_office_calendar_account.get_by_office_id(
            db=db,
            office_id=office_id,
        )
        if not account:
            logger.warning("Calendar account not found. Skipping event creation.")
            return []

        account_calendar_id = account.google_calendar_id
        if account.connection_status != CalendarConnectionStatus.connected:
            logger.warning("Calendar account not connected. Skipping event creation.")
            return []

        result = await db.execute(
            select(WelfareRecipient).where(WelfareRecipient.id == welfare_recipient_id)
        )
        recipient = result.scalar_one_or_none()
        if not recipient:
            logger.error("Welfare recipient not found")
            return []

        jst = ZoneInfo("Asia/Tokyo")
        event = CalendarEvent(
            office_id=office_id,
            welfare_recipient_id=welfare_recipient_id,
            support_plan_status_id=status_id,
            event_type=CalendarEventType.next_plan_start_date,
            google_calendar_id=account_calendar_id,
            event_title=f"{recipient.last_name} {recipient.first_name} 次の個別支援計画の開始期限",
            event_description=f"次の個別支援計画の開始期限です（{cycle_number}回目）。",
            event_start_datetime=datetime.combine(cycle_start_date, time(9, 0), tzinfo=jst),
            event_end_datetime=datetime.combine(cycle_start_date + timedelta(days=7), time(18, 0), tzinfo=jst),
            created_by_system=True,
            sync_status=CalendarSyncStatus.pending,
        )
        db.add(event)
        await db.flush()

        return [event.id]

    async def get_event_by_cycle(
        self,
        db: AsyncSession,
        cycle_id: int,
        event_type: CalendarEventType,
    ) -> Optional[CalendarEvent]:
        result = await db.execute(
            select(CalendarEvent).where(
                CalendarEvent.support_plan_cycle_id == cycle_id,
                CalendarEvent.event_type == event_type,
            )
        )
        return result.scalar_one_or_none()

    async def get_event_by_status(
        self,
        db: AsyncSession,
        status_id: int | UUID,
        event_type: CalendarEventType,
    ) -> Optional[CalendarEvent]:
        result = await db.execute(
            select(CalendarEvent).where(
                CalendarEvent.support_plan_status_id == status_id,
                CalendarEvent.event_type == event_type,
            )
        )
        return result.scalar_one_or_none()

    async def get_events_by_recipient(
        self,
        db: AsyncSession,
        recipient_id: UUID,
    ) -> list[CalendarEvent]:
        result = await db.execute(
            select(CalendarEvent).where(
                CalendarEvent.welfare_recipient_id == recipient_id,
            )
        )
        return list(result.scalars().all())

    async def delete_event(self, db: AsyncSession, event: CalendarEvent) -> None:
        await db.delete(event)
        await db.flush()
