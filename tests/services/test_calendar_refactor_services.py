from datetime import date, datetime
from uuid import uuid4

import pytest

from app.models.calendar_events import CalendarEvent
from app.models.enums import CalendarEventType, CalendarSyncStatus
from app.models.support_plan_cycle import SupportPlanCycle, SupportPlanStatus
from app.models.enums import SupportPlanStep
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


@pytest.mark.asyncio
async def test_ledger_creates_local_only_renewal_event_without_google_account(
    db_session,
    office_factory,
    employee_user_factory,
    welfare_recipient_factory,
):
    staff = await employee_user_factory(with_office=False)
    office = await office_factory(creator=staff)
    recipient = await welfare_recipient_factory(office_id=office.id)
    cycle = SupportPlanCycle(
        office_id=office.id,
        welfare_recipient_id=recipient.id,
        cycle_number=1,
        next_renewal_deadline=date(2026, 12, 31),
    )
    db_session.add(cycle)
    await db_session.flush()

    event_ids = await CalendarEventLedgerService().create_renewal_deadline_events(
        db=db_session,
        office_id=office.id,
        welfare_recipient_id=recipient.id,
        cycle_id=cycle.id,
        next_renewal_deadline=cycle.next_renewal_deadline,
    )

    assert len(event_ids) == 1
    event = await db_session.get(CalendarEvent, event_ids[0])
    assert event.google_calendar_id is None
    assert event.sync_status == CalendarSyncStatus.local_only
    assert event.event_type == CalendarEventType.renewal_deadline


@pytest.mark.asyncio
async def test_ledger_creates_local_only_next_plan_event_without_google_account(
    db_session,
    office_factory,
    employee_user_factory,
    welfare_recipient_factory,
):
    staff = await employee_user_factory(with_office=False)
    office = await office_factory(creator=staff)
    recipient = await welfare_recipient_factory(office_id=office.id)
    cycle = SupportPlanCycle(
        office_id=office.id,
        welfare_recipient_id=recipient.id,
        cycle_number=2,
    )
    db_session.add(cycle)
    await db_session.flush()
    status = SupportPlanStatus(
        plan_cycle_id=cycle.id,
        office_id=office.id,
        welfare_recipient_id=recipient.id,
        step_type=SupportPlanStep.monitoring,
    )
    db_session.add(status)
    await db_session.flush()

    event_ids = await CalendarEventLedgerService().create_next_plan_start_date_events(
        db=db_session,
        office_id=office.id,
        welfare_recipient_id=recipient.id,
        cycle_id=cycle.id,
        cycle_start_date=date(2026, 8, 1),
        cycle_number=cycle.cycle_number,
        status_id=status.id,
    )

    assert len(event_ids) == 1
    event = await db_session.get(CalendarEvent, event_ids[0])
    assert event.google_calendar_id is None
    assert event.sync_status == CalendarSyncStatus.local_only
    assert event.event_type == CalendarEventType.next_plan_start_date


@pytest.mark.asyncio
async def test_google_sync_ignores_local_only_events(
    db_session,
    office_factory,
    employee_user_factory,
    welfare_recipient_factory,
):
    staff = await employee_user_factory(with_office=False)
    office = await office_factory(creator=staff)
    recipient = await welfare_recipient_factory(office_id=office.id)
    cycle = SupportPlanCycle(
        office_id=office.id,
        welfare_recipient_id=recipient.id,
        cycle_number=1,
    )
    db_session.add(cycle)
    await db_session.flush()
    event = CalendarEvent(
        office_id=office.id,
        welfare_recipient_id=recipient.id,
        support_plan_cycle_id=cycle.id,
        event_type=CalendarEventType.renewal_deadline,
        google_calendar_id=None,
        event_title="ローカル期限",
        event_start_datetime=datetime.fromisoformat("2026-08-01T09:00:00+09:00"),
        event_end_datetime=datetime.fromisoformat("2026-08-01T18:00:00+09:00"),
        sync_status=CalendarSyncStatus.local_only,
    )
    db_session.add(event)
    await db_session.flush()

    result = await GoogleCalendarSyncService().sync_pending_events(db=db_session)

    assert result == {"synced": 0, "failed": 0}
    await db_session.refresh(event)
    assert event.sync_status == CalendarSyncStatus.local_only
