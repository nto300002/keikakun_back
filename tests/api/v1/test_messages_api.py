"""
メッセージAPI のテスト (TDD)

TDD方式: テストを先に作成し、その後実装する
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from datetime import timedelta

from app.models.enums import MessageType, MessagePriority
from app.core.security import create_access_token
from app.core.config import settings

pytestmark = pytest.mark.asyncio


async def get_csrf_tokens(async_client: AsyncClient) -> tuple[str, str]:
    """
    CSRFトークンを取得するヘルパー関数

    Returns:
        tuple[str, str]: (csrf_token, csrf_cookie)
            - csrf_token: X-CSRF-Tokenヘッダーに設定する値
            - csrf_cookie: fastapi-csrf-token Cookieの値
    """
    csrf_response = await async_client.get("/api/v1/csrf-token")
    csrf_token = csrf_response.json()["csrf_token"]
    csrf_cookie = csrf_response.cookies.get("fastapi-csrf-token")
    return csrf_token, csrf_cookie


class TestPersonalMessageAPI:
    """個別メッセージ送信APIのテスト"""

    async def test_send_personal_message_success(
        self,
        async_client: AsyncClient,
        employee_user_factory,
        db_session: AsyncSession
    ):
        """個別メッセージ送信が成功すること"""
        # テストユーザーを作成
        sender = await employee_user_factory()
        recipient = await employee_user_factory(
            office=sender.office_associations[0].office if sender.office_associations else None
        )

        # リクエストデータ
        payload = {
            "recipient_staff_ids": [str(recipient.id)],
            "title": "テストメッセージ",
            "content": "これはテストメッセージです。",
            "priority": "normal"
        }

        # 認証 + CSRF トークン取得
        access_token = create_access_token(str(sender.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
        csrf_token, csrf_cookie = await get_csrf_tokens(async_client)

        # Cookie とヘッダーを設定
        cookies = {
            "access_token": access_token,
            "fastapi-csrf-token": csrf_cookie
        }
        headers = {"X-CSRF-Token": csrf_token}

        # メッセージ送信
        response = await async_client.post(
            "/api/v1/messages/personal",
            json=payload,
            cookies=cookies,
            headers=headers
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "テストメッセージ"
        assert data["content"] == "これはテストメッセージです。"
        assert data["message_type"] == "personal"
        assert data["priority"] == "normal"
        assert data["recipient_count"] == 1
        assert "id" in data
        assert "created_at" in data

    async def test_send_personal_message_to_multiple_recipients(
        self,
        async_client: AsyncClient,
        employee_user_factory,
        db_session: AsyncSession
    ):
        """複数の受信者にメッセージを送信できること"""
        sender = await employee_user_factory()
        office = sender.office_associations[0].office if sender.office_associations else None
        recipients = [
            await employee_user_factory(office=office),
            await employee_user_factory(office=office),
            await employee_user_factory(office=office)
        ]

        payload = {
            "recipient_staff_ids": [str(r.id) for r in recipients],
            "title": "複数人へのメッセージ",
            "content": "3人に送信します",
            "priority": "high"
        }

        # 認証 + CSRF トークン取得
        access_token = create_access_token(str(sender.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
        csrf_token, csrf_cookie = await get_csrf_tokens(async_client)

        # Cookie とヘッダーを設定
        cookies = {
            "access_token": access_token,
            "fastapi-csrf-token": csrf_cookie
        }
        headers = {"X-CSRF-Token": csrf_token}

        response = await async_client.post(
            "/api/v1/messages/personal",
            json=payload,
            cookies=cookies,
            headers=headers
        )

        assert response.status_code == 201
        data = response.json()
        assert data["recipient_count"] == 3

    async def test_send_personal_message_validation_error(
        self,
        async_client: AsyncClient,
        employee_user_factory
    ):
        """バリデーションエラーが返されること（受信者なし）"""
        sender = await employee_user_factory()

        payload = {
            "recipient_staff_ids": [],  # 受信者なし
            "title": "テスト",
            "content": "本文"
        }

        # 認証 + CSRF トークン取得
        access_token = create_access_token(str(sender.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
        csrf_token, csrf_cookie = await get_csrf_tokens(async_client)

        # Cookie とヘッダーを設定
        cookies = {
            "access_token": access_token,
            "fastapi-csrf-token": csrf_cookie
        }
        headers = {"X-CSRF-Token": csrf_token}

        response = await async_client.post(
            "/api/v1/messages/personal",
            json=payload,
            cookies=cookies,
            headers=headers
        )

        assert response.status_code == 422  # Validation Error

    async def test_send_personal_message_empty_title(
        self,
        async_client: AsyncClient,
        employee_user_factory
    ):
        """バリデーションエラー: タイトルが空の場合"""
        sender = await employee_user_factory()
        recipient = await employee_user_factory(
            office=sender.office_associations[0].office if sender.office_associations else None
        )

        payload = {
            "recipient_staff_ids": [str(recipient.id)],
            "title": "",  # タイトル空
            "content": "本文"
        }

        # 認証 + CSRF トークン取得
        access_token = create_access_token(str(sender.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
        csrf_token, csrf_cookie = await get_csrf_tokens(async_client)

        # Cookie とヘッダーを設定
        cookies = {
            "access_token": access_token,
            "fastapi-csrf-token": csrf_cookie
        }
        headers = {"X-CSRF-Token": csrf_token}

        response = await async_client.post(
            "/api/v1/messages/personal",
            json=payload,
            cookies=cookies,
            headers=headers
        )

        assert response.status_code == 422  # Validation Error

    async def test_send_personal_message_to_different_office(
        self,
        async_client: AsyncClient,
        employee_user_factory,
        office_factory
    ):
        """権限エラー: 異なる事務所のスタッフへの送信"""
        sender = await employee_user_factory()

        # 異なる事務所を作成
        other_office = await office_factory()
        recipient = await employee_user_factory(office=other_office)

        payload = {
            "recipient_staff_ids": [str(recipient.id)],
            "title": "テスト",
            "content": "本文"
        }

        # 認証 + CSRF トークン取得
        access_token = create_access_token(str(sender.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
        csrf_token, csrf_cookie = await get_csrf_tokens(async_client)

        # Cookie とヘッダーを設定
        cookies = {
            "access_token": access_token,
            "fastapi-csrf-token": csrf_cookie
        }
        headers = {"X-CSRF-Token": csrf_token}

        response = await async_client.post(
            "/api/v1/messages/personal",
            json=payload,
            cookies=cookies,
            headers=headers
        )

        assert response.status_code == 403  # Forbidden

    async def test_send_personal_message_to_nonexistent_recipient(
        self,
        async_client: AsyncClient,
        employee_user_factory
    ):
        """Not Found: 存在しない受信者（エラーメッセージにUUIDを含まない）"""
        sender = await employee_user_factory()

        # 存在しないUUID
        nonexistent_uuid = "00000000-0000-0000-0000-000000000000"

        payload = {
            "recipient_staff_ids": [nonexistent_uuid],
            "title": "テスト",
            "content": "本文"
        }

        # 認証 + CSRF トークン取得
        access_token = create_access_token(str(sender.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
        csrf_token, csrf_cookie = await get_csrf_tokens(async_client)

        # Cookie とヘッダーを設定
        cookies = {
            "access_token": access_token,
            "fastapi-csrf-token": csrf_cookie
        }
        headers = {"X-CSRF-Token": csrf_token}

        response = await async_client.post(
            "/api/v1/messages/personal",
            json=payload,
            cookies=cookies,
            headers=headers
        )

        assert response.status_code == 400  # Bad Request（404から400に変更）
        error_detail = response.json()["detail"]
        # エラーメッセージにUUIDが含まれていないことを確認（情報漏洩防止）
        assert nonexistent_uuid not in error_detail
        assert "指定された受信者" in error_detail or "無効" in error_detail

    async def test_send_personal_message_to_locked_account(
        self,
        async_client: AsyncClient,
        employee_user_factory,
        db_session: AsyncSession
    ):
        """ロックされたアカウントにはメッセージを送信できない"""
        sender = await employee_user_factory()
        office = sender.office_associations[0].office if sender.office_associations else None
        locked_recipient = await employee_user_factory(office=office)

        # 受信者をロック
        locked_recipient.is_locked = True
        db_session.add(locked_recipient)
        await db_session.commit()

        payload = {
            "recipient_staff_ids": [str(locked_recipient.id)],
            "title": "テスト",
            "content": "本文"
        }

        # 認証 + CSRF トークン取得
        access_token = create_access_token(str(sender.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
        csrf_token, csrf_cookie = await get_csrf_tokens(async_client)

        # Cookie とヘッダーを設定
        cookies = {
            "access_token": access_token,
            "fastapi-csrf-token": csrf_cookie
        }
        headers = {"X-CSRF-Token": csrf_token}

        response = await async_client.post(
            "/api/v1/messages/personal",
            json=payload,
            cookies=cookies,
            headers=headers
        )

        assert response.status_code == 400  # Bad Request
        assert "無効" in response.json()["detail"] or "ロック" in response.json()["detail"]


class TestInboxAPI:
    """受信箱APIのテスト"""

    async def test_get_inbox_messages(
        self,
        async_client: AsyncClient,
        employee_user_factory,
        db_session: AsyncSession
    ):
        """受信箱のメッセージ一覧を取得できること"""
        sender = await employee_user_factory()
        recipient = await employee_user_factory(
            office=sender.office_associations[0].office if sender.office_associations else None
        )

        # メッセージを送信（CRUD経由で直接作成）
        from app import crud
        message_data = {
            "sender_staff_id": sender.id,
            "office_id": sender.office_associations[0].office.id if sender.office_associations else None,
            "recipient_ids": [recipient.id],
            "message_type": MessageType.personal,
            "priority": MessagePriority.normal,
            "title": "テストメッセージ",
            "content": "受信箱テスト"
        }
        await crud.message.create_personal_message(db=db_session, obj_in=message_data)
        await db_session.commit()

        # 認証 + CSRF トークン取得
        access_token = create_access_token(str(recipient.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
        csrf_token, csrf_cookie = await get_csrf_tokens(async_client)

        # Cookie とヘッダーを設定
        cookies = {
            "access_token": access_token,
            "fastapi-csrf-token": csrf_cookie
        }
        headers = {"X-CSRF-Token": csrf_token}

        # 受信箱を取得
        response = await async_client.get(
            "/api/v1/messages/inbox",
            cookies=cookies,
            headers=headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "messages" in data
        assert "total" in data
        assert "unread_count" in data
        assert len(data["messages"]) > 0

    async def test_get_inbox_with_unread_filter(
        self,
        async_client: AsyncClient,
        employee_user_factory,
        db_session: AsyncSession
    ):
        """未読フィルタが機能すること"""
        sender = await employee_user_factory()
        recipient = await employee_user_factory(
            office=sender.office_associations[0].office if sender.office_associations else None
        )

        # 未読メッセージを作成
        from app import crud
        message_data = {
            "sender_staff_id": sender.id,
            "office_id": sender.office_associations[0].office.id if sender.office_associations else None,
            "recipient_ids": [recipient.id],
            "message_type": MessageType.personal,
            "priority": MessagePriority.normal,
            "title": "未読メッセージ",
            "content": "未読です"
        }
        await crud.message.create_personal_message(db=db_session, obj_in=message_data)
        await db_session.commit()

        # 認証 + CSRF トークン取得
        access_token = create_access_token(str(recipient.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
        csrf_token, csrf_cookie = await get_csrf_tokens(async_client)

        # Cookie とヘッダーを設定
        cookies = {
            "access_token": access_token,
            "fastapi-csrf-token": csrf_cookie
        }
        headers = {"X-CSRF-Token": csrf_token}

        # 未読のみ取得
        response = await async_client.get(
            "/api/v1/messages/inbox?is_read=false",
            cookies=cookies,
            headers=headers
        )

        assert response.status_code == 200
        data = response.json()
        assert all(not msg["is_read"] for msg in data["messages"])

    async def test_get_inbox_with_read_filter(
        self,
        async_client: AsyncClient,
        employee_user_factory,
        db_session: AsyncSession
    ):
        """既読フィルタが機能すること"""
        sender = await employee_user_factory()
        recipient = await employee_user_factory(
            office=sender.office_associations[0].office if sender.office_associations else None
        )

        # メッセージを作成して既読化
        from app import crud
        message_data = {
            "sender_staff_id": sender.id,
            "office_id": sender.office_associations[0].office.id if sender.office_associations else None,
            "recipient_ids": [recipient.id],
            "message_type": MessageType.personal,
            "priority": MessagePriority.normal,
            "title": "既読メッセージ",
            "content": "既読です"
        }
        message = await crud.message.create_personal_message(db=db_session, obj_in=message_data)
        await db_session.commit()

        # 既読化
        await crud.message.mark_as_read(db=db_session, message_id=message.id, recipient_staff_id=recipient.id)
        await db_session.commit()

        # 認証 + CSRF トークン取得
        access_token = create_access_token(str(recipient.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
        csrf_token, csrf_cookie = await get_csrf_tokens(async_client)

        # Cookie とヘッダーを設定
        cookies = {
            "access_token": access_token,
            "fastapi-csrf-token": csrf_cookie
        }
        headers = {"X-CSRF-Token": csrf_token}

        # 既読のみ取得
        response = await async_client.get(
            "/api/v1/messages/inbox?is_read=true",
            cookies=cookies,
            headers=headers
        )

        assert response.status_code == 200
        data = response.json()
        assert all(msg["is_read"] for msg in data["messages"])

    async def test_get_inbox_with_message_type_filter(
        self,
        async_client: AsyncClient,
        owner_user_factory,
        employee_user_factory,
        db_session: AsyncSession
    ):
        """メッセージタイプフィルタが機能すること"""
        owner = await owner_user_factory()
        office = owner.office_associations[0].office if owner.office_associations else None
        recipient = await employee_user_factory(office=office)

        # 一斉通知を作成
        from app import crud
        message_data = {
            "sender_staff_id": owner.id,
            "office_id": office.id if office else None,
            "recipient_ids": [recipient.id],
            "message_type": MessageType.announcement,
            "priority": MessagePriority.high,
            "title": "お知らせ",
            "content": "重要なお知らせです"
        }
        await crud.message.create_announcement(db=db_session, obj_in=message_data)
        await db_session.commit()

        # 認証 + CSRF トークン取得
        access_token = create_access_token(str(recipient.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
        csrf_token, csrf_cookie = await get_csrf_tokens(async_client)

        # Cookie とヘッダーを設定
        cookies = {
            "access_token": access_token,
            "fastapi-csrf-token": csrf_cookie
        }
        headers = {"X-CSRF-Token": csrf_token}

        # 一斉通知のみ取得
        response = await async_client.get(
            "/api/v1/messages/inbox?message_type=announcement",
            cookies=cookies,
            headers=headers
        )

        assert response.status_code == 200
        data = response.json()
        assert all(msg["message_type"] == "announcement" for msg in data["messages"])

    async def test_get_inbox_with_pagination(
        self,
        async_client: AsyncClient,
        employee_user_factory,
        db_session: AsyncSession
    ):
        """ページネーションが機能すること"""
        sender = await employee_user_factory()
        recipient = await employee_user_factory(
            office=sender.office_associations[0].office if sender.office_associations else None
        )

        # 10件のメッセージを作成
        from app import crud
        for i in range(10):
            message_data = {
                "sender_staff_id": sender.id,
                "office_id": sender.office_associations[0].office.id if sender.office_associations else None,
                "recipient_ids": [recipient.id],
                "message_type": MessageType.personal,
                "priority": MessagePriority.normal,
                "title": f"メッセージ{i}",
                "content": f"内容{i}"
            }
            await crud.message.create_personal_message(db=db_session, obj_in=message_data)
        await db_session.commit()

        # 認証 + CSRF トークン取得
        access_token = create_access_token(str(recipient.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
        csrf_token, csrf_cookie = await get_csrf_tokens(async_client)

        # Cookie とヘッダーを設定
        cookies = {
            "access_token": access_token,
            "fastapi-csrf-token": csrf_cookie
        }
        headers = {"X-CSRF-Token": csrf_token}

        # ページネーション: 最初の5件
        response = await async_client.get(
            "/api/v1/messages/inbox?skip=0&limit=5",
            cookies=cookies,
            headers=headers
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["messages"]) == 5


class TestMarkAsReadAPI:
    """既読化APIのテスト"""

    async def test_mark_message_as_read(
        self,
        async_client: AsyncClient,
        employee_user_factory,
        db_session: AsyncSession
    ):
        """メッセージを既読化できること"""
        sender = await employee_user_factory()
        recipient = await employee_user_factory(
            office=sender.office_associations[0].office if sender.office_associations else None
        )

        # メッセージを作成
        from app import crud
        message_data = {
            "sender_staff_id": sender.id,
            "office_id": sender.office_associations[0].office.id if sender.office_associations else None,
            "recipient_ids": [recipient.id],
            "message_type": MessageType.personal,
            "priority": MessagePriority.normal,
            "title": "既読テスト",
            "content": "既読化テスト"
        }
        message = await crud.message.create_personal_message(db=db_session, obj_in=message_data)
        await db_session.commit()

        # 認証 + CSRF トークン取得
        access_token = create_access_token(str(recipient.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
        csrf_token, csrf_cookie = await get_csrf_tokens(async_client)

        # Cookie とヘッダーを設定
        cookies = {
            "access_token": access_token,
            "fastapi-csrf-token": csrf_cookie
        }
        headers = {"X-CSRF-Token": csrf_token}

        # 既読化
        response = await async_client.post(
            f"/api/v1/messages/{message.id}/read",
            cookies=cookies,
            headers=headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_read"] is True
        assert data["read_at"] is not None

    async def test_mark_other_user_message_as_read_forbidden(
        self,
        async_client: AsyncClient,
        employee_user_factory,
        db_session: AsyncSession
    ):
        """他人のメッセージを既読化しようとすると404エラー"""
        sender = await employee_user_factory()
        recipient = await employee_user_factory(
            office=sender.office_associations[0].office if sender.office_associations else None
        )
        other_user = await employee_user_factory(
            office=sender.office_associations[0].office if sender.office_associations else None
        )

        # メッセージを作成
        from app import crud
        message_data = {
            "sender_staff_id": sender.id,
            "office_id": sender.office_associations[0].office.id if sender.office_associations else None,
            "recipient_ids": [recipient.id],
            "message_type": MessageType.personal,
            "priority": MessagePriority.normal,
            "title": "既読テスト",
            "content": "既読化テスト"
        }
        message = await crud.message.create_personal_message(db=db_session, obj_in=message_data)
        await db_session.commit()

        # 認証 + CSRF トークン取得
        access_token = create_access_token(str(other_user.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
        csrf_token, csrf_cookie = await get_csrf_tokens(async_client)

        # Cookie とヘッダーを設定
        cookies = {
            "access_token": access_token,
            "fastapi-csrf-token": csrf_cookie
        }
        headers = {"X-CSRF-Token": csrf_token}

        # 既読化しようとする
        response = await async_client.post(
            f"/api/v1/messages/{message.id}/read",
            cookies=cookies,
            headers=headers
        )

        assert response.status_code == 404  # Not Found

    async def test_mark_nonexistent_message_as_read(
        self,
        async_client: AsyncClient,
        employee_user_factory
    ):
        """存在しないメッセージを既読化しようとすると404エラー"""
        user = await employee_user_factory()

        # 認証 + CSRF トークン取得
        access_token = create_access_token(str(user.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
        csrf_token, csrf_cookie = await get_csrf_tokens(async_client)

        # Cookie とヘッダーを設定
        cookies = {
            "access_token": access_token,
            "fastapi-csrf-token": csrf_cookie
        }
        headers = {"X-CSRF-Token": csrf_token}

        # 存在しないUUID
        nonexistent_uuid = "00000000-0000-0000-0000-000000000000"

        # 既読化しようとする
        response = await async_client.post(
            f"/api/v1/messages/{nonexistent_uuid}/read",
            cookies=cookies,
            headers=headers
        )

        assert response.status_code == 404  # Not Found

    async def test_read_at_has_timezone_info(
        self,
        async_client: AsyncClient,
        employee_user_factory,
        db_session: AsyncSession
    ):
        """既読時刻にタイムゾーン情報が含まれること（UTC）"""
        from datetime import timezone
        from sqlalchemy import select
        from app.models.message import MessageRecipient

        sender = await employee_user_factory()
        recipient = await employee_user_factory(
            office=sender.office_associations[0].office if sender.office_associations else None
        )

        # メッセージを作成
        from app import crud
        message_data = {
            "sender_staff_id": sender.id,
            "office_id": sender.office_associations[0].office.id if sender.office_associations else None,
            "recipient_ids": [recipient.id],
            "message_type": MessageType.personal,
            "priority": MessagePriority.normal,
            "title": "タイムゾーンテスト",
            "content": "タイムゾーンテスト"
        }
        message = await crud.message.create_personal_message(db=db_session, obj_in=message_data)
        await db_session.commit()

        # 認証 + CSRF トークン取得
        access_token = create_access_token(str(recipient.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
        csrf_token, csrf_cookie = await get_csrf_tokens(async_client)

        # Cookie とヘッダーを設定
        cookies = {
            "access_token": access_token,
            "fastapi-csrf-token": csrf_cookie
        }
        headers = {"X-CSRF-Token": csrf_token}

        # 既読化
        response = await async_client.post(
            f"/api/v1/messages/{message.id}/read",
            cookies=cookies,
            headers=headers
        )

        assert response.status_code == 200

        # DBから直接確認
        stmt = select(MessageRecipient).where(
            MessageRecipient.message_id == message.id,
            MessageRecipient.recipient_staff_id == recipient.id
        )
        result = await db_session.execute(stmt)
        recipient_record = result.scalar_one()

        # タイムゾーン情報の確認
        assert recipient_record.read_at is not None
        assert recipient_record.read_at.tzinfo is not None
        # PostgreSQLはGMTとして返すことがあるが、これはUTCと同等
        # タイムゾーン情報が存在し、オフセットが0であることを確認
        import datetime as dt
        assert recipient_record.read_at.utcoffset() == dt.timedelta(0)


class TestUnreadCountAPI:
    """未読件数APIのテスト"""

    async def test_get_unread_count(
        self,
        async_client: AsyncClient,
        employee_user_factory,
        db_session: AsyncSession
    ):
        """未読件数を取得できること"""
        sender = await employee_user_factory()
        recipient = await employee_user_factory(
            office=sender.office_associations[0].office if sender.office_associations else None
        )

        # 未読メッセージを3件作成
        from app import crud
        for i in range(3):
            message_data = {
                "sender_staff_id": sender.id,
                "office_id": sender.office_associations[0].office.id if sender.office_associations else None,
                "recipient_ids": [recipient.id],
                "message_type": MessageType.personal,
                "priority": MessagePriority.normal,
                "title": f"メッセージ{i}",
                "content": f"内容{i}"
            }
            await crud.message.create_personal_message(db=db_session, obj_in=message_data)
        await db_session.commit()

        # 認証 + CSRF トークン取得
        access_token = create_access_token(str(recipient.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
        csrf_token, csrf_cookie = await get_csrf_tokens(async_client)

        # Cookie とヘッダーを設定
        cookies = {
            "access_token": access_token,
            "fastapi-csrf-token": csrf_cookie
        }
        headers = {"X-CSRF-Token": csrf_token}

        # 未読件数を取得
        response = await async_client.get(
            "/api/v1/messages/unread-count",
            cookies=cookies,
            headers=headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["unread_count"] >= 3


class TestAnnouncementAPI:
    """一斉通知APIのテスト"""

    async def test_send_announcement_as_owner(
        self,
        async_client: AsyncClient,
        owner_user_factory,
        employee_user_factory,
        db_session: AsyncSession
    ):
        """オーナーが一斉通知を送信できること"""
        owner = await owner_user_factory()
        office = owner.office_associations[0].office if owner.office_associations else None

        # 受信者を作成
        recipients = [await employee_user_factory(office=office) for _ in range(3)]

        payload = {
            "title": "全員へのお知らせ",
            "content": "重要なお知らせです",
            "priority": "high"
        }

        # 認証 + CSRF トークン取得
        access_token = create_access_token(str(owner.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
        csrf_token, csrf_cookie = await get_csrf_tokens(async_client)

        # Cookie とヘッダーを設定
        cookies = {
            "access_token": access_token,
            "fastapi-csrf-token": csrf_cookie
        }
        headers = {"X-CSRF-Token": csrf_token}

        # 一斉通知を送信
        response = await async_client.post(
            "/api/v1/messages/announcement",
            json=payload,
            cookies=cookies,
            headers=headers
        )

        assert response.status_code == 201
        data = response.json()
        assert data["message_type"] == "announcement"
        assert data["priority"] == "high"
        assert data["recipient_count"] >= 3  # 少なくとも作成した受信者数

    async def test_send_announcement_as_admin(
        self,
        async_client: AsyncClient,
        manager_user_factory,
        employee_user_factory,
        db_session: AsyncSession
    ):
        """管理者が一斉通知を送信できること"""
        admin = await manager_user_factory()
        office = admin.office_associations[0].office if admin.office_associations else None

        # 受信者を作成
        recipients = [await employee_user_factory(office=office) for _ in range(2)]

        payload = {
            "title": "管理者からのお知らせ",
            "content": "重要なお知らせです",
            "priority": "normal"
        }

        # 認証 + CSRF トークン取得
        access_token = create_access_token(str(admin.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
        csrf_token, csrf_cookie = await get_csrf_tokens(async_client)

        # Cookie とヘッダーを設定
        cookies = {
            "access_token": access_token,
            "fastapi-csrf-token": csrf_cookie
        }
        headers = {"X-CSRF-Token": csrf_token}

        # 一斉通知を送信
        response = await async_client.post(
            "/api/v1/messages/announcement",
            json=payload,
            cookies=cookies,
            headers=headers
        )

        assert response.status_code == 201
        data = response.json()
        assert data["message_type"] == "announcement"

    async def test_send_announcement_as_employee_forbidden(
        self,
        async_client: AsyncClient,
        employee_user_factory,
        db_session: AsyncSession
    ):
        """一般スタッフが一斉通知を送信しようとすると403エラー"""
        employee = await employee_user_factory()

        payload = {
            "title": "お知らせ",
            "content": "本文",
            "priority": "normal"
        }

        # 認証 + CSRF トークン取得
        access_token = create_access_token(str(employee.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
        csrf_token, csrf_cookie = await get_csrf_tokens(async_client)

        # Cookie とヘッダーを設定
        cookies = {
            "access_token": access_token,
            "fastapi-csrf-token": csrf_cookie
        }
        headers = {"X-CSRF-Token": csrf_token}

        # 一斉通知を送信しようとする
        response = await async_client.post(
            "/api/v1/messages/announcement",
            json=payload,
            cookies=cookies,
            headers=headers
        )

        assert response.status_code == 403  # Forbidden

    async def test_send_announcement_empty_title(
        self,
        async_client: AsyncClient,
        owner_user_factory
    ):
        """バリデーションエラー: タイトルが空の場合"""
        owner = await owner_user_factory()

        payload = {
            "title": "",  # タイトル空
            "content": "本文",
            "priority": "normal"
        }

        # 認証 + CSRF トークン取得
        access_token = create_access_token(str(owner.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
        csrf_token, csrf_cookie = await get_csrf_tokens(async_client)

        # Cookie とヘッダーを設定
        cookies = {
            "access_token": access_token,
            "fastapi-csrf-token": csrf_cookie
        }
        headers = {"X-CSRF-Token": csrf_token}

        # 一斉通知を送信しようとする
        response = await async_client.post(
            "/api/v1/messages/announcement",
            json=payload,
            cookies=cookies,
            headers=headers
        )

        assert response.status_code == 422  # Validation Error


class TestMessageStatsAPI:
    """統計取得APIのテスト"""

    async def test_get_message_stats_as_sender(
        self,
        async_client: AsyncClient,
        employee_user_factory,
        db_session: AsyncSession
    ):
        """送信者として統計情報を取得できること"""
        sender = await employee_user_factory()
        office = sender.office_associations[0].office if sender.office_associations else None

        # 3人の受信者を作成
        recipients = [await employee_user_factory(office=office) for _ in range(3)]

        # メッセージを作成
        from app import crud
        message_data = {
            "sender_staff_id": sender.id,
            "office_id": office.id if office else None,
            "recipient_ids": [r.id for r in recipients],
            "message_type": MessageType.personal,
            "priority": MessagePriority.normal,
            "title": "統計テスト",
            "content": "統計情報を確認"
        }
        message = await crud.message.create_personal_message(db=db_session, obj_in=message_data)
        await db_session.commit()

        # 1人だけ既読化
        await crud.message.mark_as_read(db=db_session, message_id=message.id, recipient_staff_id=recipients[0].id)
        await db_session.commit()

        # 認証 + CSRF トークン取得
        access_token = create_access_token(str(sender.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
        csrf_token, csrf_cookie = await get_csrf_tokens(async_client)

        # Cookie とヘッダーを設定
        cookies = {
            "access_token": access_token,
            "fastapi-csrf-token": csrf_cookie
        }
        headers = {"X-CSRF-Token": csrf_token}

        # 統計情報を取得
        response = await async_client.get(
            f"/api/v1/messages/{message.id}/stats",
            cookies=cookies,
            headers=headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_recipients"] == 3
        assert data["read_count"] == 1
        assert data["unread_count"] == 2
        assert 0.0 <= data["read_rate"] <= 1.0

    async def test_get_message_stats_as_non_sender_forbidden(
        self,
        async_client: AsyncClient,
        employee_user_factory,
        db_session: AsyncSession
    ):
        """送信者以外が統計情報を取得しようとすると403エラー"""
        sender = await employee_user_factory()
        office = sender.office_associations[0].office if sender.office_associations else None
        recipient = await employee_user_factory(office=office)
        other_user = await employee_user_factory(office=office)

        # メッセージを作成
        from app import crud
        message_data = {
            "sender_staff_id": sender.id,
            "office_id": office.id if office else None,
            "recipient_ids": [recipient.id],
            "message_type": MessageType.personal,
            "priority": MessagePriority.normal,
            "title": "統計テスト",
            "content": "統計情報を確認"
        }
        message = await crud.message.create_personal_message(db=db_session, obj_in=message_data)
        await db_session.commit()

        # 認証 + CSRF トークン取得
        access_token = create_access_token(str(other_user.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
        csrf_token, csrf_cookie = await get_csrf_tokens(async_client)

        # Cookie とヘッダーを設定
        cookies = {
            "access_token": access_token,
            "fastapi-csrf-token": csrf_cookie
        }
        headers = {"X-CSRF-Token": csrf_token}

        # 統計情報を取得しようとする
        response = await async_client.get(
            f"/api/v1/messages/{message.id}/stats",
            cookies=cookies,
            headers=headers
        )

        assert response.status_code == 403  # Forbidden

    async def test_get_stats_for_nonexistent_message(
        self,
        async_client: AsyncClient,
        employee_user_factory
    ):
        """存在しないメッセージの統計情報を取得しようとすると404エラー"""
        user = await employee_user_factory()

        # 認証 + CSRF トークン取得
        access_token = create_access_token(str(user.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
        csrf_token, csrf_cookie = await get_csrf_tokens(async_client)

        # Cookie とヘッダーを設定
        cookies = {
            "access_token": access_token,
            "fastapi-csrf-token": csrf_cookie
        }
        headers = {"X-CSRF-Token": csrf_token}

        # 存在しないUUID
        nonexistent_uuid = "00000000-0000-0000-0000-000000000000"

        # 統計情報を取得しようとする
        response = await async_client.get(
            f"/api/v1/messages/{nonexistent_uuid}/stats",
            cookies=cookies,
            headers=headers
        )

        assert response.status_code == 404  # Not Found


class TestMarkAllAsReadAPI:
    """全既読化APIのテスト"""

    async def test_mark_all_as_read(
        self,
        async_client: AsyncClient,
        employee_user_factory,
        db_session: AsyncSession
    ):
        """全未読メッセージを既読化できること"""
        sender = await employee_user_factory()
        recipient = await employee_user_factory(
            office=sender.office_associations[0].office if sender.office_associations else None
        )

        # 5件の未読メッセージを作成
        from app import crud
        for i in range(5):
            message_data = {
                "sender_staff_id": sender.id,
                "office_id": sender.office_associations[0].office.id if sender.office_associations else None,
                "recipient_ids": [recipient.id],
                "message_type": MessageType.personal,
                "priority": MessagePriority.normal,
                "title": f"メッセージ{i}",
                "content": f"内容{i}"
            }
            await crud.message.create_personal_message(db=db_session, obj_in=message_data)
        await db_session.commit()

        # 認証 + CSRF トークン取得
        access_token = create_access_token(str(recipient.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
        csrf_token, csrf_cookie = await get_csrf_tokens(async_client)

        # Cookie とヘッダーを設定
        cookies = {
            "access_token": access_token,
            "fastapi-csrf-token": csrf_cookie
        }
        headers = {"X-CSRF-Token": csrf_token}

        # 全既読化
        response = await async_client.post(
            "/api/v1/messages/mark-all-read",
            cookies=cookies,
            headers=headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["updated_count"] == 5

    async def test_mark_all_as_read_with_zero_unread(
        self,
        async_client: AsyncClient,
        employee_user_factory
    ):
        """未読メッセージがない場合、更新件数が0であること"""
        user = await employee_user_factory()

        # 認証 + CSRF トークン取得
        access_token = create_access_token(str(user.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
        csrf_token, csrf_cookie = await get_csrf_tokens(async_client)

        # Cookie とヘッダーを設定
        cookies = {
            "access_token": access_token,
            "fastapi-csrf-token": csrf_cookie
        }
        headers = {"X-CSRF-Token": csrf_token}

        # 全既読化
        response = await async_client.post(
            "/api/v1/messages/mark-all-read",
            cookies=cookies,
            headers=headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["updated_count"] == 0


class TestArchiveMessageAPI:
    """アーカイブAPIのテスト"""

    async def test_archive_message(
        self,
        async_client: AsyncClient,
        employee_user_factory,
        db_session: AsyncSession
    ):
        """メッセージをアーカイブできること"""
        sender = await employee_user_factory()
        recipient = await employee_user_factory(
            office=sender.office_associations[0].office if sender.office_associations else None
        )

        # メッセージを作成
        from app import crud
        message_data = {
            "sender_staff_id": sender.id,
            "office_id": sender.office_associations[0].office.id if sender.office_associations else None,
            "recipient_ids": [recipient.id],
            "message_type": MessageType.personal,
            "priority": MessagePriority.normal,
            "title": "アーカイブテスト",
            "content": "アーカイブするメッセージ"
        }
        message = await crud.message.create_personal_message(db=db_session, obj_in=message_data)
        await db_session.commit()

        # 認証 + CSRF トークン取得
        access_token = create_access_token(str(recipient.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
        csrf_token, csrf_cookie = await get_csrf_tokens(async_client)

        # Cookie とヘッダーを設定
        cookies = {
            "access_token": access_token,
            "fastapi-csrf-token": csrf_cookie
        }
        headers = {"X-CSRF-Token": csrf_token}

        # アーカイブ
        response = await async_client.post(
            f"/api/v1/messages/{message.id}/archive",
            json={"is_archived": True},
            cookies=cookies,
            headers=headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_archived"] is True

    async def test_unarchive_message(
        self,
        async_client: AsyncClient,
        employee_user_factory,
        db_session: AsyncSession
    ):
        """メッセージをアーカイブ解除できること"""
        sender = await employee_user_factory()
        recipient = await employee_user_factory(
            office=sender.office_associations[0].office if sender.office_associations else None
        )

        # メッセージを作成してアーカイブ
        from app import crud
        message_data = {
            "sender_staff_id": sender.id,
            "office_id": sender.office_associations[0].office.id if sender.office_associations else None,
            "recipient_ids": [recipient.id],
            "message_type": MessageType.personal,
            "priority": MessagePriority.normal,
            "title": "アーカイブテスト",
            "content": "アーカイブ解除するメッセージ"
        }
        message = await crud.message.create_personal_message(db=db_session, obj_in=message_data)
        await db_session.commit()

        # アーカイブ
        await crud.message.archive_message(db=db_session, message_id=message.id, recipient_staff_id=recipient.id, is_archived=True)
        await db_session.commit()

        # 認証 + CSRF トークン取得
        access_token = create_access_token(str(recipient.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
        csrf_token, csrf_cookie = await get_csrf_tokens(async_client)

        # Cookie とヘッダーを設定
        cookies = {
            "access_token": access_token,
            "fastapi-csrf-token": csrf_cookie
        }
        headers = {"X-CSRF-Token": csrf_token}

        # アーカイブ解除
        response = await async_client.post(
            f"/api/v1/messages/{message.id}/archive",
            json={"is_archived": False},
            cookies=cookies,
            headers=headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_archived"] is False

    async def test_archive_other_user_message_forbidden(
        self,
        async_client: AsyncClient,
        employee_user_factory,
        db_session: AsyncSession
    ):
        """他人のメッセージをアーカイブしようとすると404エラー"""
        sender = await employee_user_factory()
        recipient = await employee_user_factory(
            office=sender.office_associations[0].office if sender.office_associations else None
        )
        other_user = await employee_user_factory(
            office=sender.office_associations[0].office if sender.office_associations else None
        )

        # メッセージを作成
        from app import crud
        message_data = {
            "sender_staff_id": sender.id,
            "office_id": sender.office_associations[0].office.id if sender.office_associations else None,
            "recipient_ids": [recipient.id],
            "message_type": MessageType.personal,
            "priority": MessagePriority.normal,
            "title": "アーカイブテスト",
            "content": "アーカイブするメッセージ"
        }
        message = await crud.message.create_personal_message(db=db_session, obj_in=message_data)
        await db_session.commit()

        # 認証 + CSRF トークン取得
        access_token = create_access_token(str(other_user.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
        csrf_token, csrf_cookie = await get_csrf_tokens(async_client)

        # Cookie とヘッダーを設定
        cookies = {
            "access_token": access_token,
            "fastapi-csrf-token": csrf_cookie
        }
        headers = {"X-CSRF-Token": csrf_token}

        # アーカイブしようとする
        response = await async_client.post(
            f"/api/v1/messages/{message.id}/archive",
            json={"is_archived": True},
            cookies=cookies,
            headers=headers
        )

        assert response.status_code == 404  # Not Found

    async def test_archive_nonexistent_message(
        self,
        async_client: AsyncClient,
        employee_user_factory
    ):
        """存在しないメッセージをアーカイブしようとすると404エラー"""
        user = await employee_user_factory()

        # 認証 + CSRF トークン取得
        access_token = create_access_token(str(user.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
        csrf_token, csrf_cookie = await get_csrf_tokens(async_client)

        # Cookie とヘッダーを設定
        cookies = {
            "access_token": access_token,
            "fastapi-csrf-token": csrf_cookie
        }
        headers = {"X-CSRF-Token": csrf_token}

        # 存在しないUUID
        nonexistent_uuid = "00000000-0000-0000-0000-000000000000"

        # アーカイブしようとする
        response = await async_client.post(
            f"/api/v1/messages/{nonexistent_uuid}/archive",
            json={"is_archived": True},
            cookies=cookies,
            headers=headers
        )

        assert response.status_code == 404  # Not Found
