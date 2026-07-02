# tests/api/test_deps_permissions.py

import inspect
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.api import deps
from app.api.deps import require_manager_or_owner, require_owner, check_employee_restriction
from app.core.security import create_access_token
from app.models.staff import Staff
from app.models.office import OfficeStaff
from app.models.enums import StaffRole, ResourceType, ActionType

# Pytestに非同期テストであることを認識させる
pytestmark = pytest.mark.asyncio


def _dependency_default(function, parameter_name):
    parameter = inspect.signature(function).parameters[parameter_name]
    return parameter.default.dependency


async def test_current_user_dependency_variants_are_available():
    """用途別の認証依存を公開し、endpoint側で必要量を選べるようにする。"""
    assert deps.get_current_user_minimal is not deps.get_current_user_with_office
    assert deps.get_current_user is deps.get_current_user_with_office


async def test_role_dependencies_use_minimal_current_user():
    """role判定だけの依存はoffice associationを要求しない。"""
    assert _dependency_default(deps.require_manager_or_owner, "current_staff") is deps.get_current_user_minimal
    assert _dependency_default(deps.require_owner, "current_staff") is deps.get_current_user_minimal
    assert _dependency_default(deps.require_app_admin, "current_staff") is deps.get_current_user_minimal


async def test_billing_dependency_requires_current_user_with_office():
    """課金チェックはoffice associationが必要なため、office付き依存を明示する。"""
    assert _dependency_default(deps.require_active_billing, "current_staff") is deps.get_current_user_with_office


async def test_get_current_user_minimal_does_not_eager_load_office(
    db_session: AsyncSession,
    service_admin_user_factory,
    office_factory,
):
    """軽量依存はStaff本体だけを取得し、office associationをeager loadしない。"""
    staff = await service_admin_user_factory(
        email="minimal-current-user@example.com",
        role=StaffRole.employee,
    )
    office = await office_factory(creator=staff)
    await associate_staff_with_office(db_session, staff, office.id)
    staff_id = staff.id
    db_session.expire_all()

    request = Request({"type": "http", "headers": []})
    token = create_access_token(str(staff_id))

    current_user = await deps.get_current_user_minimal(request=request, db=db_session, token=token)

    assert current_user.id == staff_id
    assert "office_associations" in sa_inspect(current_user).unloaded


async def test_get_current_user_with_office_eager_loads_office(
    db_session: AsyncSession,
    service_admin_user_factory,
    office_factory,
):
    """office付き依存はoffice associationとofficeをeager loadする。"""
    staff = await service_admin_user_factory(
        email="office-current-user@example.com",
        role=StaffRole.employee,
    )
    office = await office_factory(creator=staff)
    await associate_staff_with_office(db_session, staff, office.id)
    staff_id = staff.id
    db_session.expire_all()

    request = Request({"type": "http", "headers": []})
    token = create_access_token(str(staff_id))

    current_user = await deps.get_current_user_with_office(request=request, db=db_session, token=token)

    assert current_user.id == staff_id
    assert "office_associations" not in sa_inspect(current_user).unloaded
    assert current_user.office_associations
    assert "office" not in sa_inspect(current_user.office_associations[0]).unloaded


async def associate_staff_with_office(
    db_session: AsyncSession,
    staff: Staff,
    office_id: uuid.UUID,
    is_primary: bool = True
):
    """スタッフを事業所に関連付けるヘルパー関数"""
    association = OfficeStaff(
        staff_id=staff.id,
        office_id=office_id,
        is_primary=is_primary
    )
    db_session.add(association)
    await db_session.flush()

    # リレーションシップを再ロード
    await db_session.refresh(staff, ["office_associations"])
    return staff


# --- require_manager_or_owner のテスト ---

async def test_require_manager_or_owner_with_manager(service_admin_user_factory):
    """正常系: Manager権限のスタッフがアクセス可能"""
    # Arrange
    manager = await service_admin_user_factory(
        email="manager@example.com",
        role=StaffRole.manager
    )

    # Act
    result = await require_manager_or_owner(current_staff=manager)

    # Assert
    assert result == manager
    assert result.role == StaffRole.manager


async def test_require_manager_or_owner_with_owner(service_admin_user_factory):
    """正常系: Owner権限のスタッフがアクセス可能"""
    # Arrange
    owner = await service_admin_user_factory(
        email="owner@example.com",
        role=StaffRole.owner
    )

    # Act
    result = await require_manager_or_owner(current_staff=owner)

    # Assert
    assert result == owner
    assert result.role == StaffRole.owner


async def test_require_manager_or_owner_with_employee(service_admin_user_factory):
    """異常系: Employee権限のスタッフはアクセス拒否"""
    # Arrange
    employee = await service_admin_user_factory(
        email="employee@example.com",
        role=StaffRole.employee
    )

    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        await require_manager_or_owner(current_staff=employee)

    assert exc_info.value.status_code == 403
    assert "管理者または事業所管理者の権限が必要です" in exc_info.value.detail


# --- require_owner のテスト ---

async def test_require_owner_with_owner(service_admin_user_factory):
    """正常系: Owner権限のスタッフがアクセス可能"""
    # Arrange
    owner = await service_admin_user_factory(
        email="owner2@example.com",
        role=StaffRole.owner
    )

    # Act
    result = await require_owner(current_staff=owner)

    # Assert
    assert result == owner
    assert result.role == StaffRole.owner


async def test_require_owner_with_manager(service_admin_user_factory):
    """異常系: Manager権限のスタッフはアクセス拒否"""
    # Arrange
    manager = await service_admin_user_factory(
        email="manager2@example.com",
        role=StaffRole.manager
    )

    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        await require_owner(current_staff=manager)

    assert exc_info.value.status_code == 403
    assert "事業所管理者の権限が必要です" in exc_info.value.detail


async def test_require_owner_with_employee(service_admin_user_factory):
    """異常系: Employee権限のスタッフはアクセス拒否"""
    # Arrange
    employee = await service_admin_user_factory(
        email="employee2@example.com",
        role=StaffRole.employee
    )

    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        await require_owner(current_staff=employee)

    assert exc_info.value.status_code == 403
    assert "事業所管理者の権限が必要です" in exc_info.value.detail


# --- check_employee_restriction のテスト ---

async def test_check_employee_restriction_manager_returns_none(
    db_session: AsyncSession,
    service_admin_user_factory,
    office_factory
):
    """正常系: Manager権限のスタッフは制限なし（Noneを返す）"""
    # Arrange
    manager = await service_admin_user_factory(
        email="manager3@example.com",
        role=StaffRole.manager
    )
    office = await office_factory(creator=manager)

    # Act
    result = await check_employee_restriction(
        db=db_session,
        current_staff=manager,
        resource_type=ResourceType.welfare_recipient,
        action_type=ActionType.create,
        request_data={"name": "テスト利用者"}
    )

    # Assert
    assert result is None


async def test_check_employee_restriction_owner_returns_none(
    db_session: AsyncSession,
    service_admin_user_factory,
    office_factory
):
    """正常系: Owner権限のスタッフは制限なし（Noneを返す）"""
    # Arrange
    owner = await service_admin_user_factory(
        email="owner3@example.com",
        role=StaffRole.owner
    )
    office = await office_factory(creator=owner)

    # Act
    result = await check_employee_restriction(
        db=db_session,
        current_staff=owner,
        resource_type=ResourceType.welfare_recipient,
        action_type=ActionType.update,
        resource_id=uuid.uuid4(),
        request_data={"name": "更新された利用者"}
    )

    # Assert
    assert result is None


async def test_check_employee_restriction_employee_creates_request(
    db_session: AsyncSession,
    service_admin_user_factory,
    office_factory
):
    """正常系: Employee権限のスタッフはApprovalRequest（employee_action）を作成"""
    # Arrange
    employee = await service_admin_user_factory(
        email="employee3@example.com",
        role=StaffRole.employee
    )
    office = await office_factory(creator=employee)

    # スタッフを事業所に関連付け
    employee = await associate_staff_with_office(db_session, employee, office.id)

    request_data = {"name": "新規利用者", "age": 30}

    # Act
    result = await check_employee_restriction(
        db=db_session,
        current_staff=employee,
        resource_type=ResourceType.welfare_recipient,
        action_type=ActionType.create,
        request_data=request_data
    )

    # Assert
    assert result is not None
    assert result.requester_staff_id == employee.id
    # ApprovalRequestのrequest_dataフィールドに詳細が格納されている
    assert result.request_data is not None
    assert result.request_data["resource_type"] == ResourceType.welfare_recipient.value
    assert result.request_data["action_type"] == ActionType.create.value
    assert result.request_data["original_request_data"] == request_data
    assert result.status.value == "pending"


async def test_check_employee_restriction_employee_update_request(
    db_session: AsyncSession,
    service_admin_user_factory,
    office_factory
):
    """正常系: Employeeの更新リクエストも正しく作成される"""
    # Arrange
    employee = await service_admin_user_factory(
        email="employee4@example.com",
        role=StaffRole.employee
    )
    office = await office_factory(creator=employee)

    # スタッフを事業所に関連付け
    employee = await associate_staff_with_office(db_session, employee, office.id)

    resource_id = uuid.uuid4()
    request_data = {"name": "更新された利用者"}

    # Act
    result = await check_employee_restriction(
        db=db_session,
        current_staff=employee,
        resource_type=ResourceType.support_plan_cycle,
        action_type=ActionType.update,
        resource_id=resource_id,
        request_data=request_data
    )

    # Assert
    assert result is not None
    assert result.request_data is not None
    assert result.request_data["resource_id"] == str(resource_id)
    assert result.request_data["resource_type"] == ResourceType.support_plan_cycle.value
    assert result.request_data["action_type"] == ActionType.update.value


async def test_check_employee_restriction_employee_delete_request(
    db_session: AsyncSession,
    service_admin_user_factory,
    office_factory
):
    """正常系: Employeeの削除リクエストも正しく作成される"""
    # Arrange
    employee = await service_admin_user_factory(
        email="employee5@example.com",
        role=StaffRole.employee
    )
    office = await office_factory(creator=employee)

    # スタッフを事業所に関連付け
    employee = await associate_staff_with_office(db_session, employee, office.id)

    resource_id = uuid.uuid4()

    # Act
    result = await check_employee_restriction(
        db=db_session,
        current_staff=employee,
        resource_type=ResourceType.support_plan_status,
        action_type=ActionType.delete,
        resource_id=resource_id
    )

    # Assert
    assert result is not None
    assert result.request_data is not None
    assert result.request_data["resource_id"] == str(resource_id)
    assert result.request_data["resource_type"] == ResourceType.support_plan_status.value
    assert result.request_data["action_type"] == ActionType.delete.value
    # 削除時はoriginal_request_dataなし
    assert "original_request_data" not in result.request_data
