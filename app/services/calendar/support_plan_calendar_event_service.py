"""Support plan calendar event hooks.

支援計画作成/完了処理からGoogle Calendar連携を直接見せないための境界。
"""

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import CalendarEventType, SupportPlanStep

logger = logging.getLogger(__name__)


class SupportPlanCalendarEventService:
    """支援計画の状態変化に伴うカレンダーイベント操作をまとめる。"""

    def __init__(self, calendar_service=None):
        if calendar_service is None:
            from app.services.calendar_service import calendar_service as default_calendar_service

            calendar_service = default_calendar_service
        self.calendar_service = calendar_service

    async def create_cycle_events(
        self,
        *,
        db: AsyncSession,
        cycle,
        monitoring_status: Optional[object] = None,
    ) -> dict:
        renewal_event_ids = await self.calendar_service.create_renewal_deadline_events(
            db=db,
            office_id=cycle.office_id,
            welfare_recipient_id=cycle.welfare_recipient_id,
            cycle_id=cycle.id,
            next_renewal_deadline=cycle.next_renewal_deadline,
        )
        monitoring_event_ids = await self.calendar_service.create_next_plan_start_date_events(
            db=db,
            office_id=cycle.office_id,
            welfare_recipient_id=cycle.welfare_recipient_id,
            cycle_id=cycle.id,
            cycle_start_date=cycle.plan_cycle_start_date,
            cycle_number=cycle.cycle_number,
            status_id=monitoring_status.id if monitoring_status else None,
        )
        return {
            "renewal_event_ids": renewal_event_ids,
            "monitoring_event_ids": monitoring_event_ids,
        }

    async def delete_completion_event(
        self,
        *,
        db: AsyncSession,
        step_type: SupportPlanStep,
        cycle_id: int,
        status_id: int,
    ) -> bool:
        if step_type == SupportPlanStep.final_plan_signed:
            return await self.calendar_service.delete_event_by_cycle(
                db=db,
                cycle_id=cycle_id,
                event_type=CalendarEventType.renewal_deadline,
            )

        if step_type == SupportPlanStep.monitoring:
            return await self.calendar_service.delete_event_by_status(
                db=db,
                status_id=status_id,
                event_type=CalendarEventType.next_plan_start_date,
            )

        return False


support_plan_calendar_event_service = SupportPlanCalendarEventService()
