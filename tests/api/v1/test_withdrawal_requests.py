"""
退会リクエストAPIのテスト

TDD (Test-Driven Development) によるテスト実装
"""

import pytest
import uuid
from datetime import timedelta
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import StaffRole, RequestStatus, ApprovalResourceType
from app.models.approval_request import ApprovalRequest
from app.core.security import create_access_token
from app.core.config import settings

pytestmark = pytest.mark.asyncio


# ========================================
# POST /api/v1/withdrawal-requests
# ========================================

async def test_create_withdrawal_request_as_owner(
    async_client: AsyncClient,
    db_session: AsyncSession,
    owner_user_factory
):
    """正常系: ownerが退会リクエストを作成"""
    # Arrange
    owner = await owner_user_factory(role=StaffRole.owner)

    # Cookieを設定（認証）
    access_token = create_access_token(str(owner.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    payload = {
        "title": "事業所退会申請",
        "reason": "事業所を閉鎖するため退会を希望します。"
    }

    # Act
    response = await async_client.post("/api/v1/withdrawal-requests", json=payload)

    # Assert
    assert response.status_code == 201
    data = response.json()
    assert data["requester_staff_id"] == str(owner.id)
    office_id = owner.office_associations[0].office_id
    assert data["office_id"] == str(office_id)
    assert data["status"] == "pending"
    assert data["title"] == payload["title"]
    assert data["reason"] == payload["reason"]

    # DB確認
    result = await db_session.execute(
        ApprovalRequest.__table__.select().where(
            ApprovalRequest.id == uuid.UUID(data["id"])
        )
    )
    request = result.first()
    assert request is not None
    assert str(request.requester_staff_id) == str(owner.id)
    assert request.resource_type == ApprovalResourceType.withdrawal


async def test_create_withdrawal_request_employee_forbidden(
    async_client: AsyncClient,
    employee_user_factory
):
    """異常系: employeeは退会リクエストを作成できない (403)"""
    # Arrange
    employee = await employee_user_factory(role=StaffRole.employee)

    access_token = create_access_token(str(employee.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    payload = {
        "title": "事業所退会申請",
        "reason": "退会希望"
    }

    # Act
    response = await async_client.post("/api/v1/withdrawal-requests", json=payload)

    # Assert
    assert response.status_code == 403


async def test_create_withdrawal_request_manager_forbidden(
    async_client: AsyncClient,
    manager_user_factory
):
    """異常系: managerは退会リクエストを作成できない (403)"""
    # Arrange
    manager = await manager_user_factory(role=StaffRole.manager)

    access_token = create_access_token(str(manager.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    payload = {
        "title": "事業所退会申請",
        "reason": "退会希望"
    }

    # Act
    response = await async_client.post("/api/v1/withdrawal-requests", json=payload)

    # Assert
    assert response.status_code == 403


async def test_create_withdrawal_request_empty_title(
    async_client: AsyncClient,
    owner_user_factory
):
    """異常系: タイトルが空 (422)"""
    # Arrange
    owner = await owner_user_factory(role=StaffRole.owner)

    access_token = create_access_token(str(owner.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    payload = {
        "title": "",
        "reason": "退会希望"
    }

    # Act
    response = await async_client.post("/api/v1/withdrawal-requests", json=payload)

    # Assert
    assert response.status_code == 422


async def test_create_withdrawal_request_empty_reason(
    async_client: AsyncClient,
    owner_user_factory
):
    """異常系: 申請内容が空 (422)"""
    # Arrange
    owner = await owner_user_factory(role=StaffRole.owner)

    access_token = create_access_token(str(owner.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    payload = {
        "title": "事業所退会申請",
        "reason": ""
    }

    # Act
    response = await async_client.post("/api/v1/withdrawal-requests", json=payload)

    # Assert
    assert response.status_code == 422


async def test_create_withdrawal_request_unauthenticated(
    async_client: AsyncClient
):
    """異常系: 未認証ユーザーはリクエスト作成不可 (401)"""
    # Arrange
    payload = {
        "title": "事業所退会申請",
        "reason": "退会希望"
    }

    # Act
    response = await async_client.post("/api/v1/withdrawal-requests", json=payload)

    # Assert
    assert response.status_code == 401


# ========================================
# GET /api/v1/withdrawal-requests
# ========================================

async def test_get_withdrawal_requests_as_app_admin(
    async_client: AsyncClient,
    db_session: AsyncSession,
    app_admin_user_factory,
    owner_user_factory
):
    """正常系: app_adminは全件取得できる"""
    # Arrange
    app_admin = await app_admin_user_factory()
    owner = await owner_user_factory(role=StaffRole.owner)
    office_id = owner.office_associations[0].office_id

    # 退会リクエストを作成
    request = ApprovalRequest(
        requester_staff_id=owner.id,
        office_id=office_id,
        resource_type=ApprovalResourceType.withdrawal,
        status=RequestStatus.pending,
        request_data={
            "title": "退会申請",
            "reason": "退会希望"
        },
        is_test_data=True
    )
    db_session.add(request)
    await db_session.flush()

    access_token = create_access_token(str(app_admin.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    # Act
    response = await async_client.get("/api/v1/withdrawal-requests")

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert "requests" in data
    assert len(data["requests"]) >= 1
    assert any(item["id"] == str(request.id) for item in data["requests"])


async def test_get_withdrawal_requests_as_owner(
    async_client: AsyncClient,
    db_session: AsyncSession,
    owner_user_factory
):
    """正常系: ownerは自事務所のリクエストのみ取得"""
    # Arrange
    owner = await owner_user_factory(role=StaffRole.owner)
    office_id = owner.office_associations[0].office_id

    # 自事務所の退会リクエストを作成
    request = ApprovalRequest(
        requester_staff_id=owner.id,
        office_id=office_id,
        resource_type=ApprovalResourceType.withdrawal,
        status=RequestStatus.pending,
        request_data={
            "title": "退会申請",
            "reason": "退会希望"
        },
        is_test_data=True
    )
    db_session.add(request)
    await db_session.flush()

    access_token = create_access_token(str(owner.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    # Act
    response = await async_client.get("/api/v1/withdrawal-requests")

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert "requests" in data
    # 自事務所のリクエストのみ返される
    for item in data["requests"]:
        assert item["office_id"] == str(office_id)


async def test_get_withdrawal_requests_employee_forbidden(
    async_client: AsyncClient,
    employee_user_factory
):
    """異常系: employeeはアクセスできない (403)"""
    # Arrange
    employee = await employee_user_factory(role=StaffRole.employee)

    access_token = create_access_token(str(employee.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    # Act
    response = await async_client.get("/api/v1/withdrawal-requests")

    # Assert
    assert response.status_code == 403


async def test_get_withdrawal_requests_manager_forbidden(
    async_client: AsyncClient,
    manager_user_factory
):
    """異常系: managerはアクセスできない (403)"""
    # Arrange
    manager = await manager_user_factory(role=StaffRole.manager)

    access_token = create_access_token(str(manager.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    # Act
    response = await async_client.get("/api/v1/withdrawal-requests")

    # Assert
    assert response.status_code == 403


# ========================================
# PATCH /api/v1/withdrawal-requests/{id}/approve
# ========================================

async def test_approve_withdrawal_request_as_app_admin(
    async_client: AsyncClient,
    db_session: AsyncSession,
    app_admin_user_factory,
    owner_user_factory
):
    """正常系: app_adminがリクエストを承認"""
    # Arrange
    app_admin = await app_admin_user_factory()
    owner = await owner_user_factory(role=StaffRole.owner)
    office_id = owner.office_associations[0].office_id

    # 退会リクエストを作成
    request = ApprovalRequest(
        requester_staff_id=owner.id,
        office_id=office_id,
        resource_type=ApprovalResourceType.withdrawal,
        status=RequestStatus.pending,
        request_data={
            "title": "退会申請",
            "reason": "退会希望"
        },
        is_test_data=True
    )
    db_session.add(request)
    await db_session.flush()

    access_token = create_access_token(str(app_admin.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    payload = {
        "reviewer_notes": "退会を承認します"
    }

    # Act
    response = await async_client.patch(
        f"/api/v1/withdrawal-requests/{request.id}/approve",
        json=payload
    )

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "approved"
    assert data["reviewed_by_staff_id"] == str(app_admin.id)
    assert data["reviewer_notes"] == "退会を承認します"


async def test_approve_withdrawal_request_owner_forbidden(
    async_client: AsyncClient,
    db_session: AsyncSession,
    owner_user_factory
):
    """異常系: ownerは承認できない (403)"""
    # Arrange
    owner = await owner_user_factory(role=StaffRole.owner)
    office_id = owner.office_associations[0].office_id

    # 別のオーナーが作成した退会リクエスト
    request = ApprovalRequest(
        requester_staff_id=owner.id,
        office_id=office_id,
        resource_type=ApprovalResourceType.withdrawal,
        status=RequestStatus.pending,
        request_data={
            "title": "退会申請",
            "reason": "退会希望"
        },
        is_test_data=True
    )
    db_session.add(request)
    await db_session.flush()

    access_token = create_access_token(str(owner.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    payload = {
        "reviewer_notes": "承認"
    }

    # Act
    response = await async_client.patch(
        f"/api/v1/withdrawal-requests/{request.id}/approve",
        json=payload
    )

    # Assert
    assert response.status_code == 403


async def test_approve_withdrawal_request_not_found(
    async_client: AsyncClient,
    app_admin_user_factory
):
    """異常系: 存在しないリクエスト (404)"""
    # Arrange
    app_admin = await app_admin_user_factory()

    access_token = create_access_token(str(app_admin.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    non_existent_id = uuid.uuid4()
    payload = {
        "reviewer_notes": "承認"
    }

    # Act
    response = await async_client.patch(
        f"/api/v1/withdrawal-requests/{non_existent_id}/approve",
        json=payload
    )

    # Assert
    assert response.status_code == 404


async def test_approve_withdrawal_request_already_processed(
    async_client: AsyncClient,
    db_session: AsyncSession,
    app_admin_user_factory,
    owner_user_factory
):
    """異常系: 既に処理済みのリクエスト (400)"""
    # Arrange
    app_admin = await app_admin_user_factory()
    owner = await owner_user_factory(role=StaffRole.owner)
    office_id = owner.office_associations[0].office_id

    # 既に承認済みの退会リクエストを作成
    request = ApprovalRequest(
        requester_staff_id=owner.id,
        office_id=office_id,
        resource_type=ApprovalResourceType.withdrawal,
        status=RequestStatus.approved,  # 既に承認済み
        request_data={
            "title": "退会申請",
            "reason": "退会希望"
        },
        reviewed_by_staff_id=app_admin.id,
        is_test_data=True
    )
    db_session.add(request)
    await db_session.flush()

    access_token = create_access_token(str(app_admin.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    payload = {
        "reviewer_notes": "再承認"
    }

    # Act
    response = await async_client.patch(
        f"/api/v1/withdrawal-requests/{request.id}/approve",
        json=payload
    )

    # Assert
    assert response.status_code == 400


# ========================================
# PATCH /api/v1/withdrawal-requests/{id}/reject
# ========================================

async def test_reject_withdrawal_request_as_app_admin(
    async_client: AsyncClient,
    db_session: AsyncSession,
    app_admin_user_factory,
    owner_user_factory
):
    """正常系: app_adminがリクエストを却下"""
    # Arrange
    app_admin = await app_admin_user_factory()
    owner = await owner_user_factory(role=StaffRole.owner)
    office_id = owner.office_associations[0].office_id

    # 退会リクエストを作成
    request = ApprovalRequest(
        requester_staff_id=owner.id,
        office_id=office_id,
        resource_type=ApprovalResourceType.withdrawal,
        status=RequestStatus.pending,
        request_data={
            "title": "退会申請",
            "reason": "退会希望"
        },
        is_test_data=True
    )
    db_session.add(request)
    await db_session.flush()

    access_token = create_access_token(str(app_admin.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    payload = {
        "reviewer_notes": "契約期間が残っているため却下します"
    }

    # Act
    response = await async_client.patch(
        f"/api/v1/withdrawal-requests/{request.id}/reject",
        json=payload
    )

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "rejected"
    assert data["reviewed_by_staff_id"] == str(app_admin.id)
    assert data["reviewer_notes"] == "契約期間が残っているため却下します"


async def test_reject_withdrawal_request_owner_forbidden(
    async_client: AsyncClient,
    db_session: AsyncSession,
    owner_user_factory
):
    """異常系: ownerは却下できない (403)"""
    # Arrange
    owner = await owner_user_factory(role=StaffRole.owner)
    office_id = owner.office_associations[0].office_id

    # 退会リクエストを作成
    request = ApprovalRequest(
        requester_staff_id=owner.id,
        office_id=office_id,
        resource_type=ApprovalResourceType.withdrawal,
        status=RequestStatus.pending,
        request_data={
            "title": "退会申請",
            "reason": "退会希望"
        },
        is_test_data=True
    )
    db_session.add(request)
    await db_session.flush()

    access_token = create_access_token(str(owner.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    payload = {
        "reviewer_notes": "却下"
    }

    # Act
    response = await async_client.patch(
        f"/api/v1/withdrawal-requests/{request.id}/reject",
        json=payload
    )

    # Assert
    assert response.status_code == 403


async def test_reject_withdrawal_request_not_found(
    async_client: AsyncClient,
    app_admin_user_factory
):
    """異常系: 存在しないリクエスト (404)"""
    # Arrange
    app_admin = await app_admin_user_factory()

    access_token = create_access_token(str(app_admin.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    non_existent_id = uuid.uuid4()
    payload = {
        "reviewer_notes": "却下"
    }

    # Act
    response = await async_client.patch(
        f"/api/v1/withdrawal-requests/{non_existent_id}/reject",
        json=payload
    )

    # Assert
    assert response.status_code == 404
