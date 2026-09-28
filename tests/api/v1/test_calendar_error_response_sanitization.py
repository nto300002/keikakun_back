"""Calendar endpoints must not expose external exception details."""
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException, status

from app.api.v1.endpoints import calendar
from app.messages import ja
from app.models.enums import StaffRole


RAW_EXTERNAL_ERROR = f"{'tok' + 'en'}=value {'person' + '@example.invalid'} /srv/private/client.py"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "service_method", "expected_detail"),
    [
        ("setup", "setup_office_calendar", ja.CALENDAR_SETUP_ERROR),
        ("update", "update_office_calendar", ja.CALENDAR_UPDATE_ERROR),
        ("delete", "delete_office_calendar", ja.CALENDAR_DELETE_ERROR),
        ("sync", "sync_pending_events", ja.CALENDAR_SYNC_ERROR),
    ],
)
async def test_calendar_endpoint_unexpected_errors_do_not_expose_raw_exception(
    monkeypatch,
    operation,
    service_method,
    expected_detail,
):
    """A 500 response has a fixed message even if the upstream error is sensitive."""
    db = SimpleNamespace(rollback=AsyncMock(), commit=AsyncMock())
    owner = SimpleNamespace(role=StaffRole.owner)
    monkeypatch.setattr(
        calendar.calendar_service,
        service_method,
        AsyncMock(side_effect=RuntimeError(RAW_EXTERNAL_ERROR)),
    )

    with pytest.raises(HTTPException) as exc_info:
        if operation == "setup":
            await calendar.setup_calendar(db=db, request=SimpleNamespace(), current_user=owner)
        elif operation == "update":
            await calendar.update_calendar(
                db=db,
                account_id=uuid4(),
                request=SimpleNamespace(),
                current_user=owner,
            )
        elif operation == "delete":
            await calendar.delete_calendar(db=db, account_id=uuid4(), current_user=owner)
        else:
            await calendar.sync_pending_events(db=db, current_user=owner)

    assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert exc_info.value.detail == expected_detail
    assert RAW_EXTERNAL_ERROR not in exc_info.value.detail
    db.rollback.assert_awaited_once()
