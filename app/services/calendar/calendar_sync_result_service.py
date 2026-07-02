"""Calendar sync result persistence."""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.crud_calendar_event import crud_calendar_event
from app.models.enums import CalendarSyncStatus
from app.schemas.calendar_event import CalendarEventUpdate


class CalendarSyncResultService:
    """Google同期結果をDBイベントへ反映するサービス。"""

    async def mark_synced(self, db: AsyncSession, event, google_event_id: str) -> None:
        update_data = CalendarEventUpdate(
            google_event_id=google_event_id,
            sync_status=CalendarSyncStatus.synced,
            last_sync_at=datetime.now(),
            last_error_message=None,
        )
        await crud_calendar_event.update(db=db, db_obj=event, obj_in=update_data)

    async def mark_failed(self, db: AsyncSession, event, message: str) -> None:
        update_data = CalendarEventUpdate(
            sync_status=CalendarSyncStatus.failed,
            last_error_message=message,
            last_sync_at=datetime.now(),
        )
        await crud_calendar_event.update(db=db, db_obj=event, obj_in=update_data)

    async def mark_many_failed(self, db: AsyncSession, events: list, message: str) -> int:
        for event in events:
            await self.mark_failed(db=db, event=event, message=message)
        return len(events)
