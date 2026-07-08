from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.crud.crud_message import crud_message
from app.models.enums import MessagePriority, MessageType


@pytest.mark.asyncio
async def test_inbox_filters_by_multiple_message_types(
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory,
):
    sender = await employee_user_factory()
    office = sender.office_associations[0].office
    recipient = await employee_user_factory(office=office)

    for message_type in [MessageType.announcement, MessageType.inquiry_reply, MessageType.personal]:
        await crud_message.create_personal_message(
            db=db_session,
            obj_in={
                "sender_staff_id": sender.id,
                "office_id": office.id,
                "recipient_ids": [recipient.id],
                "message_type": message_type,
                "priority": MessagePriority.normal,
                "title": f"{message_type.value} title",
                "content": "本文",
            },
        )
    await db_session.commit()

    access_token = create_access_token(str(recipient.id), timedelta(minutes=30))
    response = await async_client.get(
        "/api/v1/messages/inbox",
        params=[
            ("message_types", "announcement"),
            ("message_types", "inquiry_reply"),
            ("limit", "20"),
        ],
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    message_types = {item["message_type"] for item in response.json()["messages"]}
    assert message_types == {"announcement", "inquiry_reply"}
