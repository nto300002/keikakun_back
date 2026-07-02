from types import SimpleNamespace

from app.models.enums import ActionType, ResourceType
from app.services.approval.employee_action_notice_service import (
    EmployeeActionNoticeService,
)
from app.services.employee_action_service import EmployeeActionService


def _request(*, resource_type, action_type, request_data):
    return SimpleNamespace(
        request_data={
            "resource_type": resource_type.value,
            "action_type": action_type.value,
            "original_request_data": request_data,
        }
    )


def test_employee_action_service_uses_notice_service():
    service = EmployeeActionService()

    assert isinstance(service.notice_service, EmployeeActionNoticeService)


def test_extract_detail_for_welfare_recipient_full_name():
    service = EmployeeActionNoticeService()
    request = _request(
        resource_type=ResourceType.welfare_recipient,
        action_type=ActionType.create,
        request_data={"full_name": "山田 太郎"},
    )

    assert (
        service.extract_detail_from_request_data(request)
        == "利用者山田 太郎さんの作成を"
    )


def test_extract_detail_for_support_plan_status_step_name():
    service = EmployeeActionNoticeService()
    request = _request(
        resource_type=ResourceType.support_plan_status,
        action_type=ActionType.update,
        request_data={
            "welfare_recipient_full_name": "山田 太郎",
            "step_type": "draft_plan",
        },
    )

    assert (
        service.extract_detail_from_request_data(request)
        == "利用者山田 太郎さんの計画案の更新を"
    )
