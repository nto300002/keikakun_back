from uuid import uuid4

import pytest

from app.services.welfare_recipient.deadline_alert_service import DeadlineAlertService
from app.services.welfare_recipient.support_plan_integrity_service import (
    SupportPlanIntegrityService,
)
from app.services.welfare_recipient_service import WelfareRecipientService


class SpyDeadlineAlertService:
    def __init__(self):
        self.calls = []

    async def get_deadline_alerts(self, **kwargs):
        self.calls.append(("single", kwargs))
        return "single-result"

    async def get_deadline_alerts_batch(self, **kwargs):
        self.calls.append(("batch", kwargs))
        return "batch-result"


class SpySupportPlanIntegrityService:
    def __init__(self):
        self.calls = []

    async def repair_recipient_support_plan(self, **kwargs):
        self.calls.append(("repair", kwargs))
        return True, "delegated"


def test_welfare_recipient_service_has_split_services():
    service = WelfareRecipientService()

    assert isinstance(service.deadline_alert_service, DeadlineAlertService)
    assert isinstance(
        service.support_plan_integrity_service,
        SupportPlanIntegrityService,
    )


@pytest.mark.asyncio
async def test_get_deadline_alerts_delegates_to_deadline_alert_service():
    original_service = WelfareRecipientService.deadline_alert_service
    spy = SpyDeadlineAlertService()
    WelfareRecipientService.deadline_alert_service = spy
    office_id = uuid4()

    try:
        result = await WelfareRecipientService.get_deadline_alerts(
            db="db",
            office_id=office_id,
            threshold_days=45,
            limit=10,
            offset=5,
        )
    finally:
        WelfareRecipientService.deadline_alert_service = original_service

    assert result == "single-result"
    assert spy.calls == [
        (
            "single",
            {
                "db": "db",
                "office_id": office_id,
                "threshold_days": 45,
                "limit": 10,
                "offset": 5,
            },
        )
    ]


@pytest.mark.asyncio
async def test_get_deadline_alerts_batch_delegates_to_deadline_alert_service():
    original_service = WelfareRecipientService.deadline_alert_service
    spy = SpyDeadlineAlertService()
    WelfareRecipientService.deadline_alert_service = spy
    office_ids = [uuid4(), uuid4()]

    try:
        result = await WelfareRecipientService.get_deadline_alerts_batch(
            db="db",
            office_ids=office_ids,
            threshold_days=60,
        )
    finally:
        WelfareRecipientService.deadline_alert_service = original_service

    assert result == "batch-result"
    assert spy.calls == [
        (
            "batch",
            {
                "db": "db",
                "office_ids": office_ids,
                "threshold_days": 60,
            },
        )
    ]


@pytest.mark.asyncio
async def test_repair_recipient_support_plan_delegates_to_integrity_service():
    service = WelfareRecipientService()
    original_service = service.support_plan_integrity_service
    spy = SpySupportPlanIntegrityService()
    service.support_plan_integrity_service = spy
    recipient_id = uuid4()
    staff_id = uuid4()

    try:
        result = await service.repair_recipient_support_plan(
            db="db",
            welfare_recipient_id=recipient_id,
            performed_by=staff_id,
        )
    finally:
        service.support_plan_integrity_service = original_service

    assert result == (True, "delegated")
    assert spy.calls == [
        (
            "repair",
            {
                "db": "db",
                "welfare_recipient_id": recipient_id,
                "performed_by": staff_id,
            },
        )
    ]
