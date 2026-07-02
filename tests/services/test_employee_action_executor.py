from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.enums import ActionType, ResourceType
from app.services.approval.employee_action_executor import EmployeeActionExecutor
from app.services.employee_action_service import EmployeeActionService


def _request(*, resource_type, action_type, request_data=None, resource_id=None):
    data = {
        "resource_type": resource_type.value if hasattr(resource_type, "value") else resource_type,
        "action_type": action_type.value if hasattr(action_type, "value") else action_type,
        "original_request_data": request_data or {},
    }
    if resource_id:
        data["resource_id"] = str(resource_id)
    return SimpleNamespace(request_data=data, office_id="office-id")


class SpyExecutor:
    def __init__(self):
        self.calls = []

    async def execute_action(self, db, request):
        self.calls.append((db, request))
        return {"success": True, "action": "spy"}


def test_employee_action_service_uses_executor_by_default():
    service = EmployeeActionService()

    assert isinstance(service.executor, EmployeeActionExecutor)


@pytest.mark.asyncio
async def test_employee_action_service_delegates_execute_action():
    executor = SpyExecutor()
    service = EmployeeActionService(executor=executor)
    request = _request(
        resource_type=ResourceType.support_plan_cycle,
        action_type=ActionType.update,
    )

    result = await service._execute_action("db", request)

    assert result == {"success": True, "action": "spy"}
    assert executor.calls == [("db", request)]


@pytest.mark.asyncio
async def test_executor_keeps_support_plan_cycle_placeholder_behavior():
    executor = EmployeeActionExecutor()
    request = _request(
        resource_type=ResourceType.support_plan_cycle,
        action_type=ActionType.update,
    )

    result = await executor.execute_action("db", request)

    assert result == {
        "success": True,
        "action": str(ActionType.update),
        "message": "SupportPlanCycle actions not yet implemented",
    }


@pytest.mark.asyncio
async def test_executor_rejects_unsupported_resource_type():
    executor = EmployeeActionExecutor()
    request = _request(
        resource_type="unsupported_resource",
        action_type=ActionType.update,
    )

    with pytest.raises(HTTPException) as exc_info:
        await executor.execute_action("db", request)

    assert exc_info.value.status_code == 400
