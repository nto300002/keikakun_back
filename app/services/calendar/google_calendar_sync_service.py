"""Google Calendar sync orchestration."""

from typing import Dict, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.crud_calendar_event import crud_calendar_event
from app.models.enums import CalendarEventType
from app.services.calendar.calendar_event_ledger_service import CalendarEventLedgerService
from app.services.calendar.calendar_sync_result_service import CalendarSyncResultService
from app.services.calendar.google_calendar_account_service import GoogleCalendarAccountService
from app.services.calendar.google_calendar_gateway import GoogleCalendarGateway


class GoogleCalendarSyncService:
    """Google Calendarへの同期と削除を隔離する互換サービス。"""

    def __init__(
        self,
        *,
        gateway: Optional[GoogleCalendarGateway] = None,
        event_ledger_service: Optional[CalendarEventLedgerService] = None,
        account_service: Optional[GoogleCalendarAccountService] = None,
        sync_result_service: Optional[CalendarSyncResultService] = None,
    ):
        if gateway is None:
            from app.services import google_calendar_client as google_calendar_client_module

            gateway = GoogleCalendarGateway(
                client_class=google_calendar_client_module.GoogleCalendarClient,
            )
        self.gateway = gateway
        self.event_ledger_service = event_ledger_service or CalendarEventLedgerService()
        self.account_service = account_service or GoogleCalendarAccountService()
        self.sync_result_service = sync_result_service or CalendarSyncResultService()

    async def sync_pending_events(
        self,
        db: AsyncSession,
        office_id: Optional[UUID] = None,
    ) -> Dict[str, int]:
        synced_count = 0
        failed_count = 0

        pending_events = await crud_calendar_event.get_pending_sync_events(db=db)
        if office_id:
            pending_events = [event for event in pending_events if event.office_id == office_id]

        if not pending_events:
            return {"synced": 0, "failed": 0}

        events_by_office: Dict[UUID, list] = {}
        for event in pending_events:
            events_by_office.setdefault(event.office_id, []).append(event)

        for current_office_id, events in events_by_office.items():
            result = await self.sync_event_group(
                db=db,
                office_id=current_office_id,
                events=events,
            )
            synced_count += result["synced"]
            failed_count += result["failed"]

        return {"synced": synced_count, "failed": failed_count}

    async def sync_event_group(
        self,
        db: AsyncSession,
        office_id: UUID,
        events: list,
    ) -> Dict[str, int]:
        synced_count = 0
        failed_count = 0

        try:
            service_account_json = await self.account_service.get_connected_service_account_json(
                db=db,
                office_id=office_id,
            )
        except ValueError as exc:
            failed_count += await self.sync_result_service.mark_many_failed(
                db=db,
                events=events,
                message=str(exc),
            )
            return {"synced": synced_count, "failed": failed_count}
        except Exception as exc:
            failed_count += await self.sync_result_service.mark_many_failed(
                db=db,
                events=events,
                message=f"Authentication failed: {str(exc)}",
            )
            return {"synced": synced_count, "failed": failed_count}

        for event in events:
            try:
                google_event_id = self.gateway.create_event(
                    service_account_json=service_account_json,
                    calendar_id=event.google_calendar_id,
                    title=event.event_title,
                    description=event.event_description,
                    start_datetime=event.event_start_datetime,
                    end_datetime=event.event_end_datetime,
                )
                await self.sync_result_service.mark_synced(
                    db=db,
                    event=event,
                    google_event_id=google_event_id,
                )
                synced_count += 1
            except Exception as exc:
                await self.sync_result_service.mark_failed(
                    db=db,
                    event=event,
                    message=str(exc),
                )
                failed_count += 1

        return {"synced": synced_count, "failed": failed_count}

    async def delete_event_by_cycle(
        self,
        db: AsyncSession,
        cycle_id: int,
        event_type: CalendarEventType,
    ) -> bool:
        event = await self.event_ledger_service.get_event_by_cycle(
            db=db,
            cycle_id=cycle_id,
            event_type=event_type,
        )
        if not event:
            return False

        await self._delete_google_event_if_needed(db=db, event=event)
        await self.event_ledger_service.delete_event(db=db, event=event)
        return True

    async def delete_event_by_status(
        self,
        db: AsyncSession,
        status_id: int,
        event_type: CalendarEventType,
    ) -> bool:
        event = await self.event_ledger_service.get_event_by_status(
            db=db,
            status_id=status_id,
            event_type=event_type,
        )
        if not event:
            return False

        await self._delete_google_event_if_needed(db=db, event=event)
        await self.event_ledger_service.delete_event(db=db, event=event)
        return True

    async def delete_google_events_for_recipient(
        self,
        db: AsyncSession,
        recipient_id: UUID,
    ) -> int:
        events = await self.event_ledger_service.get_events_by_recipient(
            db=db,
            recipient_id=recipient_id,
        )
        deleted_count = 0
        for event in events:
            if not event.google_event_id:
                continue
            await self._delete_google_event_if_needed(db=db, event=event)
            deleted_count += 1
        return deleted_count

    async def _delete_google_event_if_needed(self, db: AsyncSession, event) -> None:
        if not event.google_event_id:
            return

        try:
            service_account_json = await self.account_service.get_connected_service_account_json(
                db=db,
                office_id=event.office_id,
            )
            self.gateway.delete_event(
                service_account_json=service_account_json,
                calendar_id=event.google_calendar_id,
                event_id=event.google_event_id,
            )
        except Exception:
            # Google側削除に失敗しても、既存仕様どおりDB上の台帳削除は継続する。
            return
