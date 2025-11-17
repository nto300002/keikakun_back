# tests/api/test_deps_permissions.py

import pytest
import uuid
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_manager_or_owner, require_owner, check_employee_restriction
from app.models.staff import Staff
from app.models.office import OfficeStaff
from app.models.enums import StaffRole, ResourceType, ActionType

# Pytestに非同期テストであることを認識させる
pytestmark = pytest.mark.asyncio


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
    """正常系: Employee権限のスタッフはEmployeeActionRequestを作成"""
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
    assert result.resource_type == ResourceType.welfare_recipient
    assert result.action_type == ActionType.create
    assert result.request_data == request_data
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
    assert result.resource_id == resource_id
    assert result.resource_type == ResourceType.support_plan_cycle
    assert result.action_type == ActionType.update


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
    assert result.resource_id == resource_id
    assert result.resource_type == ResourceType.support_plan_status
    assert result.action_type == ActionType.delete
    assert result.request_data is None  # 削除時はrequest_dataなし
