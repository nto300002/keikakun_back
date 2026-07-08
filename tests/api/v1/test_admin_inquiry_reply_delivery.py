from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.enums import InquiryStatus, MessageType
from app.models.message import MessageRecipient


def _auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


@pytest.mark.asyncio
async def test_reply_to_logged_in_inquiry_creates_app_notification_and_sends_email(
    async_client: AsyncClient,
    db_session: AsyncSession,
    app_admin_user_factory,
    employee_user_factory,
    inquiry_detail_factory,
    mocker,
):
    app_admin = await app_admin_user_factory()
    sender = await employee_user_factory(email="inquiry.sender@example.com")
    inquiry = await inquiry_detail_factory(
        sender_staff_id=sender.id,
        sender_name=sender.full_name,
        sender_email=sender.email,
        title="ログイン済み問い合わせ",
    )
    send_email = mocker.patch(
        "app.core.mail.send_inquiry_reply_email",
        new_callable=mocker.AsyncMock,
    )
    access_token = create_access_token(str(app_admin.id), timedelta(minutes=30))

    response = await async_client.post(
        f"/api/v1/admin/inquiries/{inquiry.id}/reply",
        json={"body": "返信本文", "send_email": False},
        headers=_auth_headers(access_token),
    )

    assert response.status_code == 200
    data = response.json()
    assert "メール" in data["message"]
    send_email.assert_awaited_once()
    assert send_email.await_args.kwargs["recipient_email"] == sender.email

    await db_session.refresh(inquiry)
    assert inquiry.status == InquiryStatus.answered
    assert inquiry.delivery_log
    assert inquiry.delivery_log[-1]["action"] == "reply_email_queued"

    recipients = await db_session.execute(
        select(MessageRecipient)
        .join(MessageRecipient.message)
        .where(
            MessageRecipient.recipient_staff_id == sender.id,
            MessageRecipient.message.has(message_type=MessageType.inquiry_reply),
        )
    )
    assert recipients.scalars().first() is not None


@pytest.mark.asyncio
async def test_reply_to_external_inquiry_sends_email_without_app_recipient(
    async_client: AsyncClient,
    db_session: AsyncSession,
    app_admin_user_factory,
    inquiry_detail_factory,
    mocker,
):
    app_admin = await app_admin_user_factory()
    inquiry = await inquiry_detail_factory(
        sender_staff_id=None,
        sender_name="外部 送信者",
        sender_email="guest.reply@example.com",
        title="外部問い合わせ",
    )
    send_email = mocker.patch(
        "app.core.mail.send_inquiry_reply_email",
        new_callable=mocker.AsyncMock,
    )
    access_token = create_access_token(str(app_admin.id), timedelta(minutes=30))

    response = await async_client.post(
        f"/api/v1/admin/inquiries/{inquiry.id}/reply",
        json={"body": "外部返信", "send_email": False},
        headers=_auth_headers(access_token),
    )

    assert response.status_code == 200
    send_email.assert_awaited_once()

    reply_recipients = await db_session.execute(
        select(MessageRecipient)
        .join(MessageRecipient.message)
        .where(MessageRecipient.message.has(message_type=MessageType.inquiry_reply))
    )
    assert reply_recipients.scalars().all() == []


@pytest.mark.asyncio
async def test_reply_to_inquiry_without_email_uses_app_notification_only(
    async_client: AsyncClient,
    db_session: AsyncSession,
    app_admin_user_factory,
    employee_user_factory,
    inquiry_detail_factory,
    mocker,
):
    app_admin = await app_admin_user_factory()
    sender = await employee_user_factory()
    inquiry = await inquiry_detail_factory(
        sender_staff_id=sender.id,
        sender_name=sender.full_name,
        title="メールなし問い合わせ",
    )
    inquiry.sender_email = None
    await db_session.flush()
    send_email = mocker.patch(
        "app.core.mail.send_inquiry_reply_email",
        new_callable=mocker.AsyncMock,
    )
    access_token = create_access_token(str(app_admin.id), timedelta(minutes=30))

    response = await async_client.post(
        f"/api/v1/admin/inquiries/{inquiry.id}/reply",
        json={"body": "アプリ通知のみ", "send_email": True},
        headers=_auth_headers(access_token),
    )

    assert response.status_code == 200
    assert "アプリ内通知のみ" in response.json()["message"]
    send_email.assert_not_awaited()

    reply_recipients = await db_session.execute(
        select(MessageRecipient)
        .join(MessageRecipient.message)
        .where(
            MessageRecipient.recipient_staff_id == sender.id,
            MessageRecipient.message.has(message_type=MessageType.inquiry_reply),
        )
    )
    assert reply_recipients.scalars().first() is not None
