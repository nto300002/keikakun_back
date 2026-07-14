from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.enums import StaffRole
from app.models.message import Message, MessageRecipient
from app.models.office import OfficeStaff
from app.models.staff import Staff


def _auth_cookies(access_token: str, csrf_cookie: str | None = None) -> dict[str, str]:
    cookies = {"access_token": access_token}
    if csrf_cookie is not None:
        cookies["fastapi-csrf-token"] = csrf_cookie
    return cookies


async def _csrf(async_client: AsyncClient) -> tuple[dict[str, str], str]:
    csrf_response = await async_client.get("/api/v1/csrf-token")
    csrf_response.raise_for_status()
    return (
        {"X-CSRF-Token": csrf_response.json()["csrf_token"]},
        csrf_response.cookies.get("fastapi-csrf-token"),
    )


@pytest.mark.asyncio
async def test_app_admin_send_announcement_with_valid_csrf_returns_created(
    async_client: AsyncClient,
    db_session: AsyncSession,
    app_admin_user_factory,
    office_factory,
    staff_factory,
):
    app_admin = await app_admin_user_factory()
    another_app_admin = await app_admin_user_factory()
    office = await office_factory()
    recipient = await staff_factory(office_id=office.id, role=StaffRole.employee)
    deleted_recipient = await staff_factory(office_id=office.id, role=StaffRole.employee)
    deleted_recipient.is_deleted = True
    await db_session.flush()
    headers, csrf_cookie = await _csrf(async_client)
    access_token = create_access_token(str(app_admin.id), timedelta(minutes=30))

    response = await async_client.post(
        "/api/v1/admin/announcements",
        json={"title": "全体通知", "content": "本文です"},
        cookies=_auth_cookies(access_token, csrf_cookie),
        headers=headers,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "全体通知"
    assert data["content"] == "本文です"
    assert data["recipient_count"] >= 1
    assert data["office_id"] is not None

    message = await db_session.get(Message, data["id"])
    assert message is not None
    recipients_result = await db_session.execute(
        select(MessageRecipient).where(MessageRecipient.message_id == message.id)
    )
    recipient_ids = {
        message_recipient.recipient_staff_id
        for message_recipient in recipients_result.scalars().all()
    }
    assert recipient.id in recipient_ids
    assert another_app_admin.id in recipient_ids
    assert app_admin.id not in recipient_ids
    assert deleted_recipient.id not in recipient_ids


@pytest.mark.asyncio
async def test_app_admin_send_announcement_excludes_unverified_and_office_less_non_admin_staff(
    async_client: AsyncClient,
    db_session: AsyncSession,
    app_admin_user_factory,
    employee_user_factory,
    office_factory,
    staff_factory,
):
    app_admin = await app_admin_user_factory()
    other_app_admin = await app_admin_user_factory()
    office = await office_factory()
    verified_recipient = await staff_factory(
        office_id=office.id,
        role=StaffRole.employee,
        is_email_verified=True,
    )
    unverified_recipient = await staff_factory(
        office_id=office.id,
        role=StaffRole.employee,
        is_email_verified=False,
    )
    office_less_owner = await employee_user_factory(
        role=StaffRole.owner,
        with_office=False,
        is_email_verified=True,
    )
    await db_session.flush()
    headers, csrf_cookie = await _csrf(async_client)
    access_token = create_access_token(str(app_admin.id), timedelta(minutes=30))

    response = await async_client.post(
        "/api/v1/admin/announcements",
        json={"title": "対象ルール", "content": "本文です"},
        cookies=_auth_cookies(access_token, csrf_cookie),
        headers=headers,
    )

    assert response.status_code == 201
    recipients_result = await db_session.execute(
        select(MessageRecipient).where(MessageRecipient.message_id == response.json()["id"])
    )
    recipient_ids = {
        message_recipient.recipient_staff_id
        for message_recipient in recipients_result.scalars().all()
    }
    assert verified_recipient.id in recipient_ids
    assert other_app_admin.id in recipient_ids
    assert unverified_recipient.id not in recipient_ids
    assert office_less_owner.id not in recipient_ids


@pytest.mark.asyncio
@pytest.mark.performance
async def test_app_admin_send_announcement_handles_more_than_1000_recipients(
    async_client: AsyncClient,
    db_session: AsyncSession,
    app_admin_user_factory,
    office_factory,
):
    app_admin = await app_admin_user_factory()
    office = await office_factory()
    recipients = [
        Staff(
            first_name="大量",
            last_name=f"送信{i}",
            full_name=f"送信{i} 大量",
            email=f"bulk-announcement-{i}@example.com",
            hashed_password="test-password-hash",
            role=StaffRole.employee,
            is_email_verified=True,
            is_test_data=True,
        )
        for i in range(1001)
    ]
    db_session.add_all(recipients)
    await db_session.flush()
    db_session.add_all(
        [
            OfficeStaff(
                staff_id=recipient.id,
                office_id=office.id,
                is_primary=True,
                is_test_data=True,
            )
            for recipient in recipients
        ]
    )
    await db_session.flush()
    headers, csrf_cookie = await _csrf(async_client)
    access_token = create_access_token(str(app_admin.id), timedelta(minutes=30))

    response = await async_client.post(
        "/api/v1/admin/announcements",
        json={"title": "大量送信", "content": "本文です"},
        cookies=_auth_cookies(access_token, csrf_cookie),
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["recipient_count"] >= 1001


@pytest.mark.asyncio
async def test_app_admin_send_announcement_does_not_lazy_load_staff_office(
    async_client: AsyncClient,
    app_admin_user_factory,
    office_factory,
    staff_factory,
):
    app_admin = await app_admin_user_factory()
    office = await office_factory()
    await staff_factory(office_id=office.id, role=StaffRole.employee)
    headers, csrf_cookie = await _csrf(async_client)
    access_token = create_access_token(str(app_admin.id), timedelta(minutes=30))

    response = await async_client.post(
        "/api/v1/admin/announcements",
        json={"title": "遅延ロード回避", "content": "本文です"},
        cookies=_auth_cookies(access_token, csrf_cookie),
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["office_id"] is not None


@pytest.mark.asyncio
async def test_app_admin_send_announcement_without_recipients_returns_400(
    async_client: AsyncClient,
    db_session: AsyncSession,
    app_admin_user_factory,
):
    app_admin = await app_admin_user_factory()
    await db_session.execute(
        update(Staff)
        .where(Staff.id != app_admin.id)
        .values(is_deleted=True)
    )
    await db_session.flush()
    headers, csrf_cookie = await _csrf(async_client)
    access_token = create_access_token(str(app_admin.id), timedelta(minutes=30))

    response = await async_client.post(
        "/api/v1/admin/announcements",
        json={"title": "送信先なし", "content": "本文です"},
        cookies=_auth_cookies(access_token, csrf_cookie),
        headers=headers,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "送信先のスタッフが存在しません"


@pytest.mark.asyncio
async def test_app_admin_send_announcement_requires_csrf_for_cookie_auth(
    async_client: AsyncClient,
    app_admin_user_factory,
    office_factory,
    staff_factory,
):
    app_admin = await app_admin_user_factory()
    office = await office_factory()
    await staff_factory(office_id=office.id, role=StaffRole.employee)
    access_token = create_access_token(str(app_admin.id), timedelta(minutes=30))

    response = await async_client.post(
        "/api/v1/admin/announcements",
        json={"title": "CSRFなし", "content": "本文です"},
        cookies=_auth_cookies(access_token),
    )

    assert response.status_code == 403
    assert "画面の有効期限" in response.json()["detail"]
