"""
MessageCard送信者名表示のテスト

バックエンドのMessageInboxItemが送信者情報を
MessageSenderInfoオブジェクトとして返すことを確認
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import timedelta

from app.core.security import create_access_token
from app.crud.crud_message import crud_message


class TestMessageInboxSender:
    """MessageInbox送信者情報のテストクラス"""

    @pytest.mark.asyncio
    async def test_inbox_returns_sender_object(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        owner_user_factory,
        manager_user_factory,
    ):
        """
        受信箱APIがsenderをオブジェクトとして返すことを確認

        フロントエンドの MessageSenderInfo 型定義に合わせて、
        senderをオブジェクト（id, first_name, last_name, email）として返す
        """
        # メッセージ送信者（owner）と受信者（manager）を作成
        owner = await owner_user_factory()
        manager = await manager_user_factory(office=owner.office_associations[0].office)
        office_id = owner.office_associations[0].office_id

        # メッセージを作成
        await crud_message.create_personal_message(
            db=db_session,
            obj_in={
                "sender_staff_id": owner.id,
                "recipient_ids": [manager.id],
                "office_id": office_id,
                "title": "Test Message",
                "content": "Test Body",
                "priority": "normal"
            }
        )
        await db_session.commit()

        # 受信者（manager）としてログイン
        access_token = create_access_token(str(manager.id), timedelta(minutes=30))
        headers = {"Authorization": f"Bearer {access_token}"}

        # 受信箱を取得
        response = await async_client.get(
            "/api/v1/messages/inbox",
            headers=headers
        )

        assert response.status_code == 200
        data = response.json()

        assert "messages" in data
        assert len(data["messages"]) == 1

        inbox_item = data["messages"][0]

        # sender_nameではなくsenderオブジェクトが返される
        assert "sender" in inbox_item
        assert isinstance(inbox_item["sender"], dict)

        # senderオブジェクトの構造を確認
        sender = inbox_item["sender"]
        assert "id" in sender
        assert "first_name" in sender
        assert "last_name" in sender
        assert "email" in sender

        # 送信者の情報が正しいことを確認
        assert sender["id"] == str(owner.id)
        assert sender["first_name"] == owner.first_name
        assert sender["last_name"] == owner.last_name
        assert sender["email"] == owner.email

        # 古いsender_nameフィールドは存在しない
        assert "sender_name" not in inbox_item

    @pytest.mark.asyncio
    async def test_inbox_sender_null_for_system_message(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        manager_user_factory,
    ):
        """
        送信者がいないメッセージ（システムメッセージ）の場合、
        senderがNullになることを確認
        """
        manager = await manager_user_factory()
        office_id = manager.office_associations[0].office_id

        # 送信者なしのメッセージを作成
        from app.models.message import Message, MessageRecipient

        message = Message(
            sender_staff_id=None,  # 送信者なし
            office_id=office_id,
            message_type="announcement",
            priority="normal",
            title="System Message",
            content="This is a system message"
        )
        db_session.add(message)
        await db_session.flush()

        # 受信者レコードを作成
        recipient = MessageRecipient(
            message_id=message.id,
            recipient_staff_id=manager.id,
            is_read=False,
            is_archived=False
        )
        db_session.add(recipient)
        await db_session.commit()

        # 受信者としてログイン
        access_token = create_access_token(str(manager.id), timedelta(minutes=30))
        headers = {"Authorization": f"Bearer {access_token}"}

        # 受信箱を取得
        response = await async_client.get(
            "/api/v1/messages/inbox",
            headers=headers
        )

        assert response.status_code == 200
        data = response.json()

        assert len(data["messages"]) == 1
        inbox_item = data["messages"][0]

        # senderがNullであることを確認
        assert inbox_item["sender"] is None

    @pytest.mark.asyncio
    async def test_inbox_multiple_senders(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        owner_user_factory,
        manager_user_factory,
    ):
        """
        複数の送信者からのメッセージがそれぞれ正しいsender情報を持つことを確認
        """
        # 事務所Aの送信者と受信者
        owner_a = await owner_user_factory()
        manager_a = await manager_user_factory(office=owner_a.office_associations[0].office)
        office_a_id = owner_a.office_associations[0].office_id

        # 同じ事務所の別の送信者
        owner_b = await manager_user_factory(office=owner_a.office_associations[0].office)

        # owner_aからmanager_aへメッセージ
        await crud_message.create_personal_message(
            db=db_session,
            obj_in={
                "sender_staff_id": owner_a.id,
                "recipient_ids": [manager_a.id],
                "office_id": office_a_id,
                "title": "Message from Owner A",
                "content": "Test Body",
                "priority": "normal"
            }
        )

        # owner_bからmanager_aへメッセージ
        await crud_message.create_personal_message(
            db=db_session,
            obj_in={
                "sender_staff_id": owner_b.id,
                "recipient_ids": [manager_a.id],
                "office_id": office_a_id,
                "title": "Message from Owner B",
                "content": "Test Body",
                "priority": "normal"
            }
        )

        await db_session.commit()

        # 受信者としてログイン
        access_token = create_access_token(str(manager_a.id), timedelta(minutes=30))
        headers = {"Authorization": f"Bearer {access_token}"}

        # 受信箱を取得
        response = await async_client.get(
            "/api/v1/messages/inbox",
            headers=headers
        )

        assert response.status_code == 200
        data = response.json()

        assert len(data["messages"]) == 2

        # 各メッセージのsender情報を確認
        messages_by_title = {msg["title"]: msg for msg in data["messages"]}

        msg_a = messages_by_title["Message from Owner A"]
        assert msg_a["sender"]["id"] == str(owner_a.id)
        assert msg_a["sender"]["email"] == owner_a.email

        msg_b = messages_by_title["Message from Owner B"]
        assert msg_b["sender"]["id"] == str(owner_b.id)
        assert msg_b["sender"]["email"] == owner_b.email
