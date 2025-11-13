"""
Role変更リクエストAPIのテスト

TDD (Test-Driven Development) によるテスト実装
"""

import pytest
import uuid
from datetime import timedelta
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import StaffRole, RequestStatus
from app.models.role_change_request import RoleChangeRequest
from app.crud.crud_role_change_request import crud_role_change_request
from app.core.security import create_access_token
from app.core.config import settings

pytestmark = pytest.mark.asyncio


# ========================================
# POST /api/v1/role-change-requests
# ========================================

async def test_create_role_change_request_employee_to_manager(
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory
):
    """正常系: employeeがmanagerへの変更リクエストを作成"""
    # Arrange
    employee = await employee_user_factory(role=StaffRole.employee)

    # Cookieを設定（認証）
    access_token = create_access_token(str(employee.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    payload = {
        "requested_role": "manager",
        "request_notes": "管理業務を担当したいため"
    }

    # Act
    response = await async_client.post("/api/v1/role-change-requests", json=payload)

    # Assert
    assert response.status_code == 201
    data = response.json()
    assert data["requester_staff_id"] == str(employee.id)
    office_id = employee.office_associations[0].office_id
    assert data["office_id"] == str(office_id)
    assert data["from_role"] == "employee"
    assert data["requested_role"] == "manager"
    assert data["status"] == "pending"
    assert data["request_notes"] == payload["request_notes"]

    # DB確認
    request = await crud_role_change_request.get(db_session, id=uuid.UUID(data["id"]))
    assert request is not None
    assert request.requester_staff_id == employee.id


async def test_create_role_change_request_employee_to_owner(
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory
):
    """正常系: employeeがownerへの変更リクエストを作成"""
    # Arrange
    employee = await employee_user_factory(role=StaffRole.employee)

    access_token = create_access_token(str(employee.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    payload = {
        "requested_role": "owner",
        "request_notes": "事業所の運営を担当したい"
    }

    # Act
    response = await async_client.post("/api/v1/role-change-requests", json=payload)

    # Assert
    assert response.status_code == 201
    data = response.json()
    assert data["requested_role"] == "owner"


async def test_create_role_change_request_manager_to_owner(
    async_client: AsyncClient,
    db_session: AsyncSession,
    manager_user_factory
):
    """正常系: managerがownerへの変更リクエストを作成"""
    # Arrange
    manager = await manager_user_factory(role=StaffRole.manager)

    access_token = create_access_token(str(manager.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    payload = {
        "requested_role": "owner",
        "request_notes": "事業所の運営責任を担いたい"
    }

    # Act
    response = await async_client.post("/api/v1/role-change-requests", json=payload)

    # Assert
    assert response.status_code == 201
    data = response.json()
    assert data["from_role"] == "manager"
    assert data["requested_role"] == "owner"


async def test_create_role_change_request_unauthenticated(
    async_client: AsyncClient
):
    """異常系: 未認証ユーザーはリクエスト作成不可"""
    # Arrange
    payload = {
        "requested_role": "manager",
        "request_notes": "テスト"
    }

    # Act
    response = await async_client.post("/api/v1/role-change-requests", json=payload)

    # Assert
    assert response.status_code == 401


async def test_create_role_change_request_same_role(
    async_client: AsyncClient,
    employee_user_factory
):
    """異常系: 自分と同じroleへの変更リクエストは作成不可"""
    # Arrange
    employee = await employee_user_factory(role=StaffRole.employee)

    access_token = create_access_token(str(employee.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    payload = {
        "requested_role": "employee",  # 既にemployee
        "request_notes": "テスト"
    }

    # Act
    response = await async_client.post("/api/v1/role-change-requests", json=payload)

    # Assert
    assert response.status_code == 400


# ========================================
# GET /api/v1/role-change-requests
# ========================================

async def test_get_my_role_change_requests(
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory
):
    """正常系: 自分が作成したリクエスト一覧を取得"""
    # Arrange
    employee = await employee_user_factory(role=StaffRole.employee)
    office_id = employee.office_associations[0].office_id

    # リクエストを2つ作成
    from app.schemas.role_change_request import RoleChangeRequestCreate
    request1 = await crud_role_change_request.create(
        db=db_session,
        obj_in=RoleChangeRequestCreate(requested_role=StaffRole.manager, request_notes="リクエスト1"),
        requester_staff_id=employee.id,
        office_id=office_id,
        from_role=StaffRole.employee
    )
    request2 = await crud_role_change_request.create(
        db=db_session,
        obj_in=RoleChangeRequestCreate(requested_role=StaffRole.owner, request_notes="リクエスト2"),
        requester_staff_id=employee.id,
        office_id=office_id,
        from_role=StaffRole.employee
    )
    await db_session.commit()

    access_token = create_access_token(str(employee.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    # Act
    response = await async_client.get("/api/v1/role-change-requests")

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
    manager_user_factory,
    office_factory
):
    """正常系: managerは承認可能なpendingリクエストを取得できる"""
    # Arrange
    # 同じ事業所にemployeeとmanagerを作成
    manager = await manager_user_factory(role=StaffRole.manager)
    office = manager.office_associations[0].office
    employee = await employee_user_factory(office=office, role=StaffRole.employee)

    # employeeからのリクエスト作成
    from app.schemas.role_change_request import RoleChangeRequestCreate
    request = await crud_role_change_request.create(
        db=db_session,
        obj_in=RoleChangeRequestCreate(requested_role=StaffRole.manager),
        requester_staff_id=employee.id,
        office_id=office.id,
        from_role=StaffRole.employee
    )
    await db_session.commit()

    access_token = create_access_token(str(manager.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    # Act
    response = await async_client.get("/api/v1/role-change-requests?status=pending")

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert any(item["id"] == str(request.id) for item in data)


# ========================================
# PATCH /api/v1/role-change-requests/{id}/approve
# ========================================

async def test_approve_role_change_request_as_manager(
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory,
    manager_user_factory
):
    """正常系: managerがemployee→managerリクエストを承認"""
    # Arrange
    manager = await manager_user_factory(role=StaffRole.manager)
    office = manager.office_associations[0].office
    employee = await employee_user_factory(office=office, role=StaffRole.employee)

    # リクエスト作成
    from app.schemas.role_change_request import RoleChangeRequestCreate
    request = await crud_role_change_request.create(
        db=db_session,
        obj_in=RoleChangeRequestCreate(requested_role=StaffRole.manager),
        requester_staff_id=employee.id,
        office_id=office.id,
        from_role=StaffRole.employee
    )
    await db_session.commit()

    access_token = create_access_token(str(manager.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    payload = {
        "reviewer_notes": "承認します"
    }

    # Act
    response = await async_client.patch(
        f"/api/v1/role-change-requests/{request.id}/approve",
        json=payload
    )

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "approved"
    assert data["reviewed_by_staff_id"] == str(manager.id)
    assert data["reviewer_notes"] == "承認します"

    # employeeのroleがmanagerに変更されたことを確認
    await db_session.refresh(employee)
    assert employee.role == StaffRole.manager


async def test_approve_role_change_request_as_owner(
    async_client: AsyncClient,
    db_session: AsyncSession,
    manager_user_factory,
    owner_user_factory
):
    """正常系: ownerがmanager→ownerリクエストを承認"""
    # Arrange
    owner = await owner_user_factory(role=StaffRole.owner)
    office = owner.office_associations[0].office
    manager = await manager_user_factory(office=office, role=StaffRole.manager)

    # リクエスト作成
    from app.schemas.role_change_request import RoleChangeRequestCreate
    request = await crud_role_change_request.create(
        db=db_session,
        obj_in=RoleChangeRequestCreate(requested_role=StaffRole.owner),
        requester_staff_id=manager.id,
        office_id=office.id,
        from_role=StaffRole.manager
    )
    await db_session.commit()

    access_token = create_access_token(str(owner.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    payload = {
        "reviewer_notes": "権限を承認します"
    }

    # Act
    response = await async_client.patch(
        f"/api/v1/role-change-requests/{request.id}/approve",
        json=payload
    )

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "approved"

    # managerのroleがownerに変更されたことを確認
    await db_session.refresh(manager)
    assert manager.role == StaffRole.owner


async def test_approve_role_change_request_insufficient_permission(
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
    from app.schemas.role_change_request import RoleChangeRequestCreate
    request = await crud_role_change_request.create(
        db=db_session,
        obj_in=RoleChangeRequestCreate(requested_role=StaffRole.manager),
        requester_staff_id=requester.id,
        office_id=office.id,
        from_role=StaffRole.employee
    )
    await db_session.commit()

    access_token = create_access_token(str(approver_employee.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    payload = {
        "reviewer_notes": "承認します"
    }

    # Act
    response = await async_client.patch(
        f"/api/v1/role-change-requests/{request.id}/approve",
        json=payload
    )

    # Assert
    assert response.status_code == 403


async def test_approve_role_change_request_manager_cannot_approve_manager_to_owner(
    async_client: AsyncClient,
    db_session: AsyncSession,
    manager_user_factory
):
    """異常系: managerはmanager→ownerリクエストを承認できない"""
    # Arrange
    approver_manager = await manager_user_factory(role=StaffRole.manager)
    office = approver_manager.office_associations[0].office
    requester_manager = await manager_user_factory(office=office, role=StaffRole.manager)

    # リクエスト作成
    from app.schemas.role_change_request import RoleChangeRequestCreate
    request = await crud_role_change_request.create(
        db=db_session,
        obj_in=RoleChangeRequestCreate(requested_role=StaffRole.owner),
        requester_staff_id=requester_manager.id,
        office_id=office.id,
        from_role=StaffRole.manager
    )
    await db_session.commit()

    access_token = create_access_token(str(approver_manager.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    payload = {
        "reviewer_notes": "承認します"
    }

    # Act
    response = await async_client.patch(
        f"/api/v1/role-change-requests/{request.id}/approve",
        json=payload
    )

    # Assert
    assert response.status_code == 403


async def test_approve_role_change_request_already_approved(
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
    from app.schemas.role_change_request import RoleChangeRequestCreate
    request = await crud_role_change_request.create(
        db=db_session,
        obj_in=RoleChangeRequestCreate(requested_role=StaffRole.manager),
        requester_staff_id=employee.id,
        office_id=office.id,
        from_role=StaffRole.employee
    )
    await crud_role_change_request.approve(
        db=db_session,
        request_id=request.id,
        reviewer_staff_id=manager.id,
        reviewer_notes="承認済み"
    )
    await db_session.commit()

    access_token = create_access_token(str(manager.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    payload = {
        "reviewer_notes": "再承認"
    }

    # Act
    response = await async_client.patch(
        f"/api/v1/role-change-requests/{request.id}/approve",
        json=payload
    )

    # Assert
    assert response.status_code == 400


# ========================================
# PATCH /api/v1/role-change-requests/{id}/reject
# ========================================

async def test_reject_role_change_request(
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
    from app.schemas.role_change_request import RoleChangeRequestCreate
    request = await crud_role_change_request.create(
        db=db_session,
        obj_in=RoleChangeRequestCreate(requested_role=StaffRole.manager),
        requester_staff_id=employee.id,
        office_id=office.id,
        from_role=StaffRole.employee
    )
    await db_session.commit()

    access_token = create_access_token(str(manager.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    payload = {
        "reviewer_notes": "今回は見送ります"
    }

    # Act
    response = await async_client.patch(
        f"/api/v1/role-change-requests/{request.id}/reject",
        json=payload
    )

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "rejected"
    assert data["reviewed_by_staff_id"] == str(manager.id)
    assert data["reviewer_notes"] == "今回は見送ります"

    # employeeのroleは変更されていないことを確認
    await db_session.refresh(employee)
    assert employee.role == StaffRole.employee


# ========================================
# DELETE /api/v1/role-change-requests/{id}
# ========================================

async def test_delete_pending_role_change_request(
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory
):
    """正常系: pending状態のリクエストを削除"""
    # Arrange
    employee = await employee_user_factory(role=StaffRole.employee)
    office_id = employee.office_associations[0].office_id

    # リクエスト作成
    from app.schemas.role_change_request import RoleChangeRequestCreate
    request = await crud_role_change_request.create(
        db=db_session,
        obj_in=RoleChangeRequestCreate(requested_role=StaffRole.manager),
        requester_staff_id=employee.id,
        office_id=office_id,
        from_role=StaffRole.employee
    )
    await db_session.commit()

    access_token = create_access_token(str(employee.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    # Act
    response = await async_client.delete(f"/api/v1/role-change-requests/{request.id}")

    # Assert
    assert response.status_code == 204

    # DBから削除されていることを確認
    deleted_request = await crud_role_change_request.get(db_session, id=request.id)
    assert deleted_request is None


async def test_delete_approved_role_change_request_fails(
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
    from app.schemas.role_change_request import RoleChangeRequestCreate
    request = await crud_role_change_request.create(
        db=db_session,
        obj_in=RoleChangeRequestCreate(requested_role=StaffRole.manager),
        requester_staff_id=employee.id,
        office_id=office.id,
        from_role=StaffRole.employee
    )
    await crud_role_change_request.approve(
        db=db_session,
        request_id=request.id,
        reviewer_staff_id=manager.id
    )
    await db_session.commit()

    access_token = create_access_token(str(employee.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    # Act
    response = await async_client.delete(f"/api/v1/role-change-requests/{request.id}")

    # Assert
    assert response.status_code == 400


async def test_delete_others_role_change_request_fails(
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
    from app.schemas.role_change_request import RoleChangeRequestCreate
    request = await crud_role_change_request.create(
        db=db_session,
        obj_in=RoleChangeRequestCreate(requested_role=StaffRole.manager),
        requester_staff_id=employee1.id,
        office_id=office.id,
        from_role=StaffRole.employee
    )
    await db_session.commit()

    # employee2がログイン
    access_token = create_access_token(str(employee2.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    # Act
    response = await async_client.delete(f"/api/v1/role-change-requests/{request.id}")

    # Assert
    assert response.status_code == 403
