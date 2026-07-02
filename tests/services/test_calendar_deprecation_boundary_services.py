from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.enums import CalendarEventType, CalendarSyncStatus, SupportPlanStep
from app.services.calendar.calendar_sync_result_service import CalendarSyncResultService
from app.services.calendar.google_calendar_account_service import GoogleCalendarAccountService
from app.services.calendar.google_calendar_sync_service import GoogleCalendarSyncService
from app.services.calendar.support_plan_calendar_event_service import (
    SupportPlanCalendarEventService,
)


class FakeAccountService:
    def __init__(self):
        self.calls = []

    async def get_connected_service_account_json(self, db, office_id):
        self.calls.append((db, office_id))
        return "service-account-json"


class FakeSyncResultService:
    def __init__(self):
        self.calls = []

    async def mark_synced(self, db, event, google_event_id):
        self.calls.append(("synced", db, event, google_event_id))

    async def mark_failed(self, db, event, message):
        self.calls.append(("failed", db, event, message))


class FakeGateway:
    def __init__(self):
        self.calls = []

    def create_event(
        self,
        *,
        service_account_json,
        calendar_id,
        title,
        description,
        start_datetime,
        end_datetime,
    ):
        self.calls.append(
            (
                service_account_json,
                calendar_id,
                title,
                description,
                start_datetime,
                end_datetime,
            )
        )
        return "google-event-id"

    def delete_event(self, *, service_account_json, calendar_id, event_id):
        self.calls.append(("delete", service_account_json, calendar_id, event_id))


@pytest.mark.asyncio
async def test_google_sync_service_separates_account_resolution_and_result_updates():
    account_service = FakeAccountService()
    result_service = FakeSyncResultService()
    gateway = FakeGateway()
    service = GoogleCalendarSyncService(
        gateway=gateway,
        account_service=account_service,
        sync_result_service=result_service,
    )
    db = object()
    office_id = uuid4()
    event = SimpleNamespace(
        office_id=office_id,
        google_calendar_id="calendar-id",
        event_title="title",
        event_description="description",
        event_start_datetime="start",
        event_end_datetime="end",
    )

    result = await service.sync_event_group(db=db, office_id=office_id, events=[event])

    assert result == {"synced": 1, "failed": 0}
    assert account_service.calls == [(db, office_id)]
    assert gateway.calls == [
        ("service-account-json", "calendar-id", "title", "description", "start", "end")
    ]
    assert result_service.calls == [("synced", db, event, "google-event-id")]


def test_google_sync_service_exposes_boundary_services():
    service = GoogleCalendarSyncService()

    assert isinstance(service.account_service, GoogleCalendarAccountService)
    assert isinstance(service.sync_result_service, CalendarSyncResultService)


class FakeRecipientLedgerService:
    def __init__(self, events):
        self.events = events
        self.calls = []

    async def get_events_by_recipient(self, db, recipient_id):
        self.calls.append((db, recipient_id))
        return self.events


@pytest.mark.asyncio
async def test_google_sync_service_deletes_recipient_events_without_db_delete():
    office_id = uuid4()
    recipient_id = uuid4()
    event = SimpleNamespace(
        office_id=office_id,
        google_calendar_id="calendar-id",
        google_event_id="google-event-id",
    )
    ledger_service = FakeRecipientLedgerService(events=[event])
    account_service = FakeAccountService()
    gateway = FakeGateway()
    service = GoogleCalendarSyncService(
        gateway=gateway,
        event_ledger_service=ledger_service,
        account_service=account_service,
    )
    db = object()

    deleted_count = await service.delete_google_events_for_recipient(
        db=db,
        recipient_id=recipient_id,
    )

    assert deleted_count == 1
    assert ledger_service.calls == [(db, recipient_id)]
    assert account_service.calls == [(db, office_id)]
    assert gateway.calls == [("delete", "service-account-json", "calendar-id", "google-event-id")]


class FakeCalendarService:
    def __init__(self):
        self.calls = []

    async def create_renewal_deadline_events(self, **kwargs):
        self.calls.append(("create_renewal_deadline_events", kwargs))
        return ["renewal"]

    async def create_next_plan_start_date_events(self, **kwargs):
        self.calls.append(("create_next_plan_start_date_events", kwargs))
        return ["monitoring"]

    async def delete_event_by_cycle(self, **kwargs):
        self.calls.append(("delete_event_by_cycle", kwargs))
        return True

    async def delete_event_by_status(self, **kwargs):
        self.calls.append(("delete_event_by_status", kwargs))
        return True


@pytest.mark.asyncio
async def test_support_plan_calendar_event_service_hides_calendar_facade_calls():
    calendar_service = FakeCalendarService()
    service = SupportPlanCalendarEventService(calendar_service=calendar_service)
    db = object()
    cycle = SimpleNamespace(
        id=10,
        office_id=uuid4(),
        welfare_recipient_id=uuid4(),
        next_renewal_deadline="deadline",
        plan_cycle_start_date="start-date",
        cycle_number=2,
    )
    monitoring_status = SimpleNamespace(id=20)

    created = await service.create_cycle_events(
        db=db,
        cycle=cycle,
        monitoring_status=monitoring_status,
    )
    renewal_deleted = await service.delete_completion_event(
        db=db,
        step_type=SupportPlanStep.final_plan_signed,
        cycle_id=cycle.id,
        status_id=monitoring_status.id,
    )
    monitoring_deleted = await service.delete_completion_event(
        db=db,
        step_type=SupportPlanStep.monitoring,
        cycle_id=cycle.id,
        status_id=monitoring_status.id,
    )

    assert created == {"renewal_event_ids": ["renewal"], "monitoring_event_ids": ["monitoring"]}
    assert renewal_deleted is True
    assert monitoring_deleted is True
    assert calendar_service.calls[0][0] == "create_renewal_deadline_events"
    assert calendar_service.calls[1][0] == "create_next_plan_start_date_events"
    assert calendar_service.calls[2] == (
        "delete_event_by_cycle",
        {
            "db": db,
            "cycle_id": cycle.id,
            "event_type": CalendarEventType.renewal_deadline,
        },
    )
    assert calendar_service.calls[3] == (
        "delete_event_by_status",
        {
            "db": db,
            "status_id": monitoring_status.id,
            "event_type": CalendarEventType.next_plan_start_date,
        },
    )
