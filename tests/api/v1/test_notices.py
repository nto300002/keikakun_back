"""
通知APIのテスト

TDD (Test-Driven Development) によるテスト実装
"""

import pytest
import uuid
from datetime import timedelta
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notice import Notice
from app.crud.crud_notice import crud_notice
from app.schemas.notice import NoticeCreate
from app.core.security import create_access_token
from app.core.config import settings

pytestmark = pytest.mark.asyncio


# ========================================
# GET /api/v1/notices
# ========================================

async def test_get_all_notices(
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory
):
    """正常系: 自分宛の通知一覧を取得"""
    # Arrange
    employee = await employee_user_factory()
    office_id = employee.office_associations[0].office_id

    # 通知を3つ作成
    for i in range(3):
        notice = await crud_notice.create(
            db=db_session,
            obj_in=NoticeCreate(
                recipient_staff_id=employee.id,
                office_id=office_id,
                type="role_change_request",
                title=f"通知{i+1}",
                content=f"テスト通知{i+1}です"
            )
        )
    await db_session.commit()

    access_token = create_access_token(str(employee.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    # Act
    response = await async_client.get("/api/v1/notices")

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert len(data["notices"]) == 3
    assert data["total"] == 3
    assert data["unread_count"] == 3


async def test_get_unread_notices_only(
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory
):
    """正常系: 未読通知のみをフィルタリング"""
    # Arrange
    employee = await employee_user_factory()
    office_id = employee.office_associations[0].office_id

    # 未読2つ、既読1つを作成
    for i in range(2):
        await crud_notice.create(
            db=db_session,
            obj_in=NoticeCreate(
                recipient_staff_id=employee.id,
                office_id=office_id,
                type="role_change_request",
                title=f"未読通知{i+1}",
                content=f"未読{i+1}"
            )
        )

    read_notice = await crud_notice.create(
        db=db_session,
        obj_in=NoticeCreate(
            recipient_staff_id=employee.id,
            office_id=office_id,
            type="role_change_approved",
            title="既読通知",
            content="既読"
        )
    )
    await db_session.commit()

    # 1つを既読にする
    await crud_notice.mark_as_read(db=db_session, notice_id=read_notice.id)

    access_token = create_access_token(str(employee.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    # Act
    response = await async_client.get("/api/v1/notices?is_read=false")

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert len(data["notices"]) == 2
    assert data["unread_count"] == 2


async def test_get_notices_by_type(
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory
):
    """正常系: タイプでフィルタリング"""
    # Arrange
    employee = await employee_user_factory()
    office_id = employee.office_associations[0].office_id

    # 異なるタイプの通知を作成
    await crud_notice.create(
        db=db_session,
        obj_in=NoticeCreate(
            recipient_staff_id=employee.id,
            office_id=office_id,
            type="role_change_request",
            title="Role変更リクエスト",
            content="テスト"
        )
    )
    await crud_notice.create(
        db=db_session,
        obj_in=NoticeCreate(
            recipient_staff_id=employee.id,
            office_id=office_id,
            type="employee_action_request",
            title="アクションリクエスト",
            content="テスト"
        )
    )
    await db_session.commit()

    access_token = create_access_token(str(employee.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    # Act
    response = await async_client.get("/api/v1/notices?type=role_change_request")

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert len(data["notices"]) == 1
    assert data["notices"][0]["type"] == "role_change_request"


async def test_get_notices_unauthenticated(
    async_client: AsyncClient
):
    """異常系: 未認証ユーザーは通知を取得できない"""
    # Act
    response = await async_client.get("/api/v1/notices")

    # Assert
    assert response.status_code == 401


async def test_cannot_get_others_notices(
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory
):
    """異常系: 他人の通知は取得できない"""
    # Arrange
    employee1 = await employee_user_factory()
    employee2 = await employee_user_factory()
    office_id = employee1.office_associations[0].office_id

    # employee1宛の通知を作成
    await crud_notice.create(
        db=db_session,
        obj_in=NoticeCreate(
            recipient_staff_id=employee1.id,
            office_id=office_id,
            type="role_change_request",
            title="employee1の通知",
            content="テスト"
        )
    )
    await db_session.commit()

    # employee2でログイン
    access_token = create_access_token(str(employee2.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    # Act
    response = await async_client.get("/api/v1/notices")

    # Assert
    assert response.status_code == 200
    data = response.json()
    # employee2の通知はない
    assert len(data["notices"]) == 0


# ========================================
# GET /api/v1/notices/unread-count
# ========================================

async def test_get_unread_count(
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory
):
    """正常系: 未読通知の件数を取得"""
    # Arrange
    employee = await employee_user_factory()
    office_id = employee.office_associations[0].office_id

    # 未読3つ、既読1つを作成
    for i in range(3):
        await crud_notice.create(
            db=db_session,
            obj_in=NoticeCreate(
                recipient_staff_id=employee.id,
                office_id=office_id,
                type="role_change_request",
                title=f"未読通知{i+1}",
                content=f"未読{i+1}"
            )
        )

    read_notice = await crud_notice.create(
        db=db_session,
        obj_in=NoticeCreate(
            recipient_staff_id=employee.id,
            office_id=office_id,
            type="role_change_approved",
            title="既読通知",
            content="既読"
        )
    )
    await db_session.commit()
    await crud_notice.mark_as_read(db=db_session, notice_id=read_notice.id)

    access_token = create_access_token(str(employee.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    # Act
    response = await async_client.get("/api/v1/notices/unread-count")

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["unread_count"] == 3


# ========================================
# PATCH /api/v1/notices/{id}/read
# ========================================

async def test_mark_notice_as_read(
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory
):
    """正常系: 通知を既読にする"""
    # Arrange
    employee = await employee_user_factory()
    office_id = employee.office_associations[0].office_id

    notice = await crud_notice.create(
        db=db_session,
        obj_in=NoticeCreate(
            recipient_staff_id=employee.id,
            office_id=office_id,
            type="role_change_request",
            title="テスト通知",
            content="テスト"
        )
    )
    await db_session.commit()

    access_token = create_access_token(str(employee.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    # Act
    response = await async_client.patch(f"/api/v1/notices/{notice.id}/read")

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["is_read"] is True

    # DB確認
    await db_session.refresh(notice)
    assert notice.is_read is True


async def test_mark_others_notice_as_read_fails(
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory
):
    """異常系: 他人の通知は既読にできない"""
    # Arrange
    employee1 = await employee_user_factory()
    employee2 = await employee_user_factory()
    office_id = employee1.office_associations[0].office_id

    # employee1宛の通知を作成
    notice = await crud_notice.create(
        db=db_session,
        obj_in=NoticeCreate(
            recipient_staff_id=employee1.id,
            office_id=office_id,
            type="role_change_request",
            title="employee1の通知",
            content="テスト"
        )
    )
    await db_session.commit()

    # employee2でログイン
    access_token = create_access_token(str(employee2.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    # Act
    response = await async_client.patch(f"/api/v1/notices/{notice.id}/read")

    # Assert
    assert response.status_code == 403


# ========================================
# PATCH /api/v1/notices/read-all
# ========================================

async def test_mark_all_notices_as_read(
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory
):
    """正常系: 全通知を既読にする"""
    # Arrange
    employee = await employee_user_factory()
    office_id = employee.office_associations[0].office_id

    # 未読通知を3つ作成
    notices = []
    for i in range(3):
        notice = await crud_notice.create(
            db=db_session,
            obj_in=NoticeCreate(
                recipient_staff_id=employee.id,
                office_id=office_id,
                type="role_change_request",
                title=f"未読通知{i+1}",
                content=f"未読{i+1}"
            )
        )
        notices.append(notice)
    await db_session.commit()

    access_token = create_access_token(str(employee.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    # Act
    response = await async_client.patch("/api/v1/notices/read-all")

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["marked_count"] == 3

    # DB確認：全て既読になっている
    for notice in notices:
        await db_session.refresh(notice)
        assert notice.is_read is True


# ========================================
# DELETE /api/v1/notices/{id}
# ========================================

async def test_delete_notice(
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory
):
    """正常系: 通知を削除"""
    # Arrange
    employee = await employee_user_factory()
    office_id = employee.office_associations[0].office_id

    notice = await crud_notice.create(
        db=db_session,
        obj_in=NoticeCreate(
            recipient_staff_id=employee.id,
            office_id=office_id,
            type="role_change_request",
            title="削除する通知",
            content="テスト"
        )
    )
    await db_session.commit()

    access_token = create_access_token(str(employee.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    # Act
    response = await async_client.delete(f"/api/v1/notices/{notice.id}")

    # Assert
    assert response.status_code == 204

    # DB確認：削除されている
    deleted_notice = await crud_notice.get(db=db_session, id=notice.id)
    assert deleted_notice is None


async def test_delete_others_notice_fails(
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory
):
    """異常系: 他人の通知は削除できない"""
    # Arrange
    employee1 = await employee_user_factory()
    employee2 = await employee_user_factory()
    office_id = employee1.office_associations[0].office_id

    # employee1宛の通知を作成
    notice = await crud_notice.create(
        db=db_session,
        obj_in=NoticeCreate(
            recipient_staff_id=employee1.id,
            office_id=office_id,
            type="role_change_request",
            title="employee1の通知",
            content="テスト"
        )
    )
    await db_session.commit()

    # employee2でログイン
    access_token = create_access_token(str(employee2.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    async_client.cookies.set("access_token", access_token)

    # Act
    response = await async_client.delete(f"/api/v1/notices/{notice.id}")

    # Assert
    assert response.status_code == 403

    # DB確認：削除されていない
    existing_notice = await crud_notice.get(db=db_session, id=notice.id)
    assert existing_notice is not None
