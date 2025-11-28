"""
Employee制限リクエストAPIのテスト（統合テーブル版）

TDD (Test-Driven Development) によるテスト実装

注意: 統合approval_requestsテーブルを使用しています
"""

import pytest
import uuid
from datetime import timedelta, date
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import StaffRole, RequestStatus, ActionType, ResourceType, GenderType, ApprovalResourceType
from app.models.approval_request import ApprovalRequest
from app.crud.crud_approval_request import approval_request
from app.schemas.employee_action_request import EmployeeActionRequestCreate
from app.core.security import create_access_token
from app.core.config import settings

pytestmark = pytest.mark.asyncio


# ========================================
# POST /api/v1/employee-action-requests
# ========================================

async def test_create_employee_action_request(
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory
):
    """正常系: employeeがアクションリクエストを作成"""
    # Arrange
    employee = await employee_user_factory(role=StaffRole.employee)
    office_id = employee.office_associations[0].office_id

    access_token = create_access_token(str(employee.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    payload = {
        "resource_type": "welfare_recipient",
        "action_type": "create",
        "request_data": {
            "last_name": "テスト",
            "first_name": "太郎",
            "last_name_furigana": "テスト",
            "first_name_furigana": "タロウ",
            "birth_day": "1990-01-01",
            "gender": "male"
        }
    }

    # Act
    response = await async_client.post("/api/v1/employee-action-requests", json=payload)

    # Assert
    assert response.status_code == 201
    data = response.json()
    assert data["requester_staff_id"] == str(employee.id)
    assert data["office_id"] == str(office_id)
    assert data["resource_type"] == "welfare_recipient"
    assert data["action_type"] == "create"
    assert data["status"] == "pending"
    assert data["request_data"]["last_name"] == "テスト"


async def test_create_employee_action_request_update(
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory
):
    """正常系: employeeが更新リクエストを作成"""
    # Arrange
    employee = await employee_user_factory(role=StaffRole.employee)

    access_token = create_access_token(str(employee.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    resource_id = uuid.uuid4()
    payload = {
        "resource_type": "welfare_recipient",
        "action_type": "update",
        "resource_id": str(resource_id),
        "request_data": {
            "first_name": "花子"
        }
    }

    # Act
    response = await async_client.post("/api/v1/employee-action-requests", json=payload)

    # Assert
    assert response.status_code == 201
    data = response.json()
    assert data["action_type"] == "update"
    assert data["resource_id"] == str(resource_id)


async def test_create_employee_action_request_delete(
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory
):
    """正常系: employeeが削除リクエストを作成"""
    # Arrange
    employee = await employee_user_factory(role=StaffRole.employee)

    access_token = create_access_token(str(employee.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    resource_id = uuid.uuid4()
    payload = {
        "resource_type": "welfare_recipient",
        "action_type": "delete",
        "resource_id": str(resource_id)
    }

    # Act
    response = await async_client.post("/api/v1/employee-action-requests", json=payload)

    # Assert
    assert response.status_code == 201
    data = response.json()
    assert data["action_type"] == "delete"
    assert data["resource_id"] == str(resource_id)


async def test_create_employee_action_request_unauthenticated(
    async_client: AsyncClient
):
    """異常系: 未認証ユーザーはリクエスト作成不可"""
    # Arrange
    payload = {
        "resource_type": "welfare_recipient",
        "action_type": "create",
        "request_data": {}
    }

    # Act
    response = await async_client.post("/api/v1/employee-action-requests", json=payload)

    # Assert
    assert response.status_code == 401


# ========================================
# GET /api/v1/employee-action-requests
# ========================================

async def test_get_my_employee_action_requests(
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory
):
    """正常系: 自分が作成したリクエスト一覧を取得"""
    # Arrange
    employee = await employee_user_factory(role=StaffRole.employee)
    office_id = employee.office_associations[0].office_id

    # リクエストを2つ作成
    request1 = await crud_employee_action_request.create(
        db=db_session,
        obj_in=EmployeeActionRequestCreate(
            resource_type=ResourceType.welfare_recipient,
            action_type=ActionType.create,
            request_data={"test": "data1"}
        ),
        requester_staff_id=employee.id,
        office_id=office_id
    )
    request2 = await crud_employee_action_request.create(
        db=db_session,
        obj_in=EmployeeActionRequestCreate(
            resource_type=ResourceType.welfare_recipient,
            action_type=ActionType.update,
            resource_id=uuid.uuid4(),
            request_data={"test": "data2"}
        ),
        requester_staff_id=employee.id,
        office_id=office_id
    )
    await db_session.commit()

    access_token = create_access_token(str(employee.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    # Act
    response = await async_client.get("/api/v1/employee-action-requests")

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 2
    request_ids = [item["id"] for item in data]
    assert str(request1.id) in request_ids
    assert str(request2.id) in request_ids


async def test_get_pending_requests_for_approval_as_manager(
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory,
    manager_user_factory
):
    """正常系: managerは承認可能なpendingリクエストを取得できる"""
    # Arrange
    manager = await manager_user_factory(role=StaffRole.manager)
    office = manager.office_associations[0].office
    employee = await employee_user_factory(office=office, role=StaffRole.employee)

    # employeeからのリクエスト作成
    request = await crud_employee_action_request.create(
        db=db_session,
        obj_in=EmployeeActionRequestCreate(
            resource_type=ResourceType.welfare_recipient,
            action_type=ActionType.create,
            request_data={"test": "data"}
        ),
        requester_staff_id=employee.id,
        office_id=office.id
    )
    await db_session.commit()

    access_token = create_access_token(str(manager.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    # Act
    response = await async_client.get("/api/v1/employee-action-requests?status=pending")

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert any(item["id"] == str(request.id) for item in data)


# ========================================
# PATCH /api/v1/employee-action-requests/{id}/approve
# ========================================

async def test_approve_employee_action_request_as_manager(
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory,
    manager_user_factory
):
    """正常系: managerがemployeeのリクエストを承認"""
    # Arrange
    manager = await manager_user_factory(role=StaffRole.manager)
    office = manager.office_associations[0].office
    employee = await employee_user_factory(office=office, role=StaffRole.employee)

    # リクエスト作成
    request = await crud_employee_action_request.create(
        db=db_session,
        obj_in=EmployeeActionRequestCreate(
            resource_type=ResourceType.welfare_recipient,
            action_type=ActionType.create,
            request_data={
                "last_name": "テスト",
                "first_name": "太郎",
                "last_name_furigana": "テスト",
                "first_name_furigana": "タロウ",
                "birth_day": "1990-01-01",
                "gender": "male"
            }
        ),
        requester_staff_id=employee.id,
        office_id=office.id
    )
    await db_session.commit()

    access_token = create_access_token(str(manager.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    payload = {
        "approver_notes": "承認します"
    }

    # Act
    response = await async_client.patch(
        f"/api/v1/employee-action-requests/{request.id}/approve",
        json=payload
    )

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "approved"
    assert data["approved_by_staff_id"] == str(manager.id)
    assert data["approver_notes"] == "承認します"
    assert data["execution_result"] is not None


async def test_approve_employee_action_request_as_owner(
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory,
    owner_user_factory
):
    """正常系: ownerがリクエストを承認"""
    # Arrange
    owner = await owner_user_factory(role=StaffRole.owner)
    office = owner.office_associations[0].office
    employee = await employee_user_factory(office=office, role=StaffRole.employee)

    # リクエスト作成
    request = await crud_employee_action_request.create(
        db=db_session,
        obj_in=EmployeeActionRequestCreate(
            resource_type=ResourceType.welfare_recipient,
            action_type=ActionType.create,
            request_data={
                "last_name": "テスト",
                "first_name": "花子",
                "last_name_furigana": "テスト",
                "first_name_furigana": "ハナコ",
                "birth_day": "1995-05-05",
                "gender": "female"
            }
        ),
        requester_staff_id=employee.id,
        office_id=office.id
    )
    await db_session.commit()

    access_token = create_access_token(str(owner.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    payload = {
        "approver_notes": "承認します"
    }

    # Act
    response = await async_client.patch(
        f"/api/v1/employee-action-requests/{request.id}/approve",
        json=payload
    )

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "approved"


async def test_approve_employee_action_request_insufficient_permission(
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory
):
    """異常系: employeeは承認できない"""
    # Arrange
    approver_employee = await employee_user_factory(role=StaffRole.employee)
    office = approver_employee.office_associations[0].office
    requester = await employee_user_factory(office=office, role=StaffRole.employee)

    # リクエスト作成
    request = await crud_employee_action_request.create(
        db=db_session,
        obj_in=EmployeeActionRequestCreate(
            resource_type=ResourceType.welfare_recipient,
            action_type=ActionType.create,
            request_data={"test": "data"}
        ),
        requester_staff_id=requester.id,
        office_id=office.id
    )
    await db_session.commit()

    access_token = create_access_token(str(approver_employee.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    payload = {
        "approver_notes": "承認します"
    }

    # Act
    response = await async_client.patch(
        f"/api/v1/employee-action-requests/{request.id}/approve",
        json=payload
    )

    # Assert
    assert response.status_code == 403


async def test_approve_employee_action_request_already_approved(
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory,
    manager_user_factory
):
    """異常系: 既に承認済みのリクエストは再承認できない"""
    # Arrange
    manager = await manager_user_factory(role=StaffRole.manager)
    office = manager.office_associations[0].office
    employee = await employee_user_factory(office=office, role=StaffRole.employee)

    # リクエスト作成と承認
    request = await crud_employee_action_request.create(
        db=db_session,
        obj_in=EmployeeActionRequestCreate(
            resource_type=ResourceType.welfare_recipient,
            action_type=ActionType.create,
            request_data={"test": "data"}
        ),
        requester_staff_id=employee.id,
        office_id=office.id
    )
    await crud_employee_action_request.approve(
        db=db_session,
        request_id=request.id,
        approver_staff_id=manager.id,
        approver_notes="承認済み"
    )
    await db_session.commit()

    access_token = create_access_token(str(manager.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    payload = {
        "approver_notes": "再承認"
    }

    # Act
    response = await async_client.patch(
        f"/api/v1/employee-action-requests/{request.id}/approve",
        json=payload
    )

    # Assert
    assert response.status_code == 400


# ========================================
# PATCH /api/v1/employee-action-requests/{id}/reject
# ========================================

async def test_reject_employee_action_request(
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory,
    manager_user_factory
):
    """正常系: managerがリクエストを却下"""
    # Arrange
    manager = await manager_user_factory(role=StaffRole.manager)
    office = manager.office_associations[0].office
    employee = await employee_user_factory(office=office, role=StaffRole.employee)

    # リクエスト作成
    request = await crud_employee_action_request.create(
        db=db_session,
        obj_in=EmployeeActionRequestCreate(
            resource_type=ResourceType.welfare_recipient,
            action_type=ActionType.create,
            request_data={"test": "data"}
        ),
        requester_staff_id=employee.id,
        office_id=office.id
    )
    await db_session.commit()

    access_token = create_access_token(str(manager.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    payload = {
        "approver_notes": "今回は見送ります"
    }

    # Act
    response = await async_client.patch(
        f"/api/v1/employee-action-requests/{request.id}/reject",
        json=payload
    )

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "rejected"
    assert data["approved_by_staff_id"] == str(manager.id)
    assert data["approver_notes"] == "今回は見送ります"


# ========================================
# DELETE /api/v1/employee-action-requests/{id}
# ========================================

async def test_delete_pending_employee_action_request(
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory
):
    """正常系: pending状態のリクエストを削除"""
    # Arrange
    employee = await employee_user_factory(role=StaffRole.employee)
    office_id = employee.office_associations[0].office_id

    # リクエスト作成
    request = await crud_employee_action_request.create(
        db=db_session,
        obj_in=EmployeeActionRequestCreate(
            resource_type=ResourceType.welfare_recipient,
            action_type=ActionType.create,
            request_data={"test": "data"}
        ),
        requester_staff_id=employee.id,
        office_id=office_id
    )
    await db_session.commit()

    access_token = create_access_token(str(employee.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    # Act
    response = await async_client.delete(f"/api/v1/employee-action-requests/{request.id}")

    # Assert
    assert response.status_code == 204

    # DBから削除されていることを確認
    deleted_request = await crud_employee_action_request.get(db_session, id=request.id)
    assert deleted_request is None


async def test_delete_approved_employee_action_request_fails(
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory,
    manager_user_factory
):
    """異常系: 承認済みリクエストは削除できない"""
    # Arrange
    manager = await manager_user_factory(role=StaffRole.manager)
    office = manager.office_associations[0].office
    employee = await employee_user_factory(office=office, role=StaffRole.employee)

    # リクエスト作成と承認
    request = await crud_employee_action_request.create(
        db=db_session,
        obj_in=EmployeeActionRequestCreate(
            resource_type=ResourceType.welfare_recipient,
            action_type=ActionType.create,
            request_data={"test": "data"}
        ),
        requester_staff_id=employee.id,
        office_id=office.id
    )
    await crud_employee_action_request.approve(
        db=db_session,
        request_id=request.id,
        approver_staff_id=manager.id
    )
    await db_session.commit()

    access_token = create_access_token(str(employee.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    # Act
    response = await async_client.delete(f"/api/v1/employee-action-requests/{request.id}")

    # Assert
    assert response.status_code == 400


async def test_delete_others_employee_action_request_fails(
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory
):
    """異常系: 他人のリクエストは削除できない"""
    # Arrange
    employee1 = await employee_user_factory(role=StaffRole.employee)
    office = employee1.office_associations[0].office
    employee2 = await employee_user_factory(office=office, role=StaffRole.employee)

    # employee1がリクエスト作成
    request = await crud_employee_action_request.create(
        db=db_session,
        obj_in=EmployeeActionRequestCreate(
            resource_type=ResourceType.welfare_recipient,
            action_type=ActionType.create,
            request_data={"test": "data"}
        ),
        requester_staff_id=employee1.id,
        office_id=office.id
    )
    await db_session.commit()

    # employee2がログイン
    access_token = create_access_token(str(employee2.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    # Act
    response = await async_client.delete(f"/api/v1/employee-action-requests/{request.id}")

    # Assert
    assert response.status_code == 403
