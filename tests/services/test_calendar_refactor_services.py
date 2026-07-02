from datetime import date
from uuid import uuid4

import pytest

from app.models.enums import CalendarEventType
from app.services.calendar.calendar_event_ledger_service import CalendarEventLedgerService
from app.services.calendar.google_calendar_sync_service import GoogleCalendarSyncService
from app.services.calendar_service import CalendarService


class FakeCalendarEventLedgerService:
    def __init__(self):
        self.calls = []

    async def create_renewal_deadline_events(
        self,
        db,
        office_id,
        welfare_recipient_id,
        cycle_id,
        next_renewal_deadline,
    ):
        self.calls.append(
            (
                "create_renewal_deadline_events",
                db,
                office_id,
                welfare_recipient_id,
                cycle_id,
                next_renewal_deadline,
            )
        )
        return ["renewal-event-id"]

    async def create_next_plan_start_date_events(
        self,
        db,
        office_id,
        welfare_recipient_id,
        cycle_id,
        cycle_start_date,
        cycle_number,
        status_id=None,
    ):
        self.calls.append(
            (
                "create_next_plan_start_date_events",
                db,
                office_id,
                welfare_recipient_id,
                cycle_id,
                cycle_start_date,
                cycle_number,
                status_id,
            )
        )
        return ["next-plan-event-id"]


class FakeGoogleCalendarSyncService:
    def __init__(self):
        self.calls = []

    async def sync_pending_events(self, db, office_id=None):
        self.calls.append(("sync_pending_events", db, office_id))
        return {"synced": 1, "failed": 0}

    async def delete_event_by_cycle(self, db, cycle_id, event_type):
        self.calls.append(("delete_event_by_cycle", db, cycle_id, event_type))
        return True

    async def delete_event_by_status(self, db, status_id, event_type):
        self.calls.append(("delete_event_by_status", db, status_id, event_type))
        return True


def test_calendar_service_exposes_refactor_services():
    service = CalendarService()

    assert isinstance(service.event_ledger_service, CalendarEventLedgerService)
    assert isinstance(service.google_sync_service, GoogleCalendarSyncService)


@pytest.mark.asyncio
async def test_calendar_service_delegates_event_ledger_creation_methods():
    ledger_service = FakeCalendarEventLedgerService()
    service = CalendarService(event_ledger_service=ledger_service)
    db = object()
    office_id = uuid4()
    welfare_recipient_id = uuid4()
    status_id = uuid4()

    renewal_result = await service.create_renewal_deadline_events(
        db=db,
        office_id=office_id,
        welfare_recipient_id=welfare_recipient_id,
        cycle_id=10,
        next_renewal_deadline=date(2026, 7, 31),
    )
    next_plan_result = await service.create_next_plan_start_date_events(
        db=db,
        office_id=office_id,
        welfare_recipient_id=welfare_recipient_id,
        cycle_id=11,
        cycle_start_date=date(2026, 7, 1),
        cycle_number=2,
        status_id=status_id,
    )

    assert renewal_result == ["renewal-event-id"]
    assert next_plan_result == ["next-plan-event-id"]
    assert ledger_service.calls == [
        (
            "create_renewal_deadline_events",
            db,
            office_id,
            welfare_recipient_id,
            10,
            date(2026, 7, 31),
        ),
        (
            "create_next_plan_start_date_events",
            db,
            office_id,
            welfare_recipient_id,
            11,
            date(2026, 7, 1),
            2,
            status_id,
        ),
    ]


@pytest.mark.asyncio
async def test_calendar_service_delegates_google_sync_methods():
    sync_service = FakeGoogleCalendarSyncService()
    service = CalendarService(google_sync_service=sync_service)
    db = object()
    office_id = uuid4()

    sync_result = await service.sync_pending_events(db=db, office_id=office_id)
    cycle_deleted = await service.delete_event_by_cycle(
        db=db,
        cycle_id=10,
        event_type=CalendarEventType.renewal_deadline,
    )
    status_deleted = await service.delete_event_by_status(
        db=db,
        status_id=20,
        event_type=CalendarEventType.next_plan_start_date,
    )

    assert sync_result == {"synced": 1, "failed": 0}
    assert cycle_deleted is True
    assert status_deleted is True
    assert sync_service.calls == [
        ("sync_pending_events", db, office_id),
        ("delete_event_by_cycle", db, 10, CalendarEventType.renewal_deadline),
        ("delete_event_by_status", db, 20, CalendarEventType.next_plan_start_date),
    ]
