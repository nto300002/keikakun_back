"""
問い合わせAPIエンドポイントのテスト

エンドポイントレベルでのHTTP APIテスト:
- POST /api/v1/inquiries (公開)
- GET /api/v1/admin/inquiries (app_admin専用)
- GET /api/v1/admin/inquiries/{id} (app_admin専用)
- PATCH /api/v1/admin/inquiries/{id} (app_admin専用)
- DELETE /api/v1/admin/inquiries/{id} (app_admin専用)
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import timedelta
from uuid import uuid4

from app.core.security import create_access_token
from app.core.config import settings
from app.models.enums import StaffRole, InquiryStatus, InquiryPriority

pytestmark = pytest.mark.asyncio


class TestInquiryPublicEndpoint:
    """公開問い合わせエンドポイントのテスト"""

    async def test_create_inquiry_from_logged_in_user(
        self,
        async_client: AsyncClient,
        employee_user_factory,
        app_admin_user_factory,
        db_session: AsyncSession
    ):
        """
        ログイン済みユーザーからの問い合わせ送信

        POST /api/v1/inquiries
        - 認証あり
        - sender_staff_id が設定される
        """
        # Setup
        sender = await employee_user_factory()
        app_admin = await app_admin_user_factory()

        # 認証トークン
        access_token = create_access_token(
            str(sender.id),
            timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        )

        # リクエストデータ
        payload = {
            "title": "機能について質問",
            "content": "サービスの使い方を教えてください。",
            "category": "質問"
        }

        # Execute
        response = await async_client.post(
            "/api/v1/inquiries",
            json=payload,
            cookies={"access_token": access_token}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["message"] == "問い合わせを受け付けました"

    async def test_create_inquiry_from_guest_user(
        self,
        async_client: AsyncClient,
        app_admin_user_factory,
        db_session: AsyncSession
    ):
        """
        未ログインユーザーからの問い合わせ送信

        POST /api/v1/inquiries
        - 認証なし
        - sender_name, sender_email が必須
        """
        # Setup: app_adminを事務所に所属させる
        from app.models.office import Office, OfficeStaff
        from uuid import uuid4
        from app.models.enums import OfficeType

        app_admin = await app_admin_user_factory()

        # app_admin用の事務所を作成
        admin_office = Office(
            id=uuid4(),
            name="システム事務所",
            type=OfficeType.type_A_office,
            created_by=app_admin.id,
            last_modified_by=app_admin.id,
            is_test_data=True
        )
        db_session.add(admin_office)
        await db_session.flush()

        # app_adminを事務所に所属させる
        office_staff = OfficeStaff(
            office_id=admin_office.id,
            staff_id=app_admin.id,
            is_primary=True,
            is_test_data=True
        )
        db_session.add(office_staff)
        await db_session.flush()

        # リクエストデータ（未ログイン）
        payload = {
            "title": "利用方法について",
            "content": "このアプリの使い方を教えてください。",
            "sender_name": "ゲストユーザー",
            "sender_email": "guest@example.com",
            "category": "質問"
        }

        # Execute（認証なし）
        response = await async_client.post(
            "/api/v1/inquiries",
            json=payload
        )

        # Assert
        if response.status_code != 200:
            print(f"Error response: {response.json()}")
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["message"] == "問い合わせを受け付けました"

    async def test_create_inquiry_guest_without_email_fails(
        self,
        async_client: AsyncClient,
        app_admin_user_factory
    ):
        """
        未ログインでメールアドレスなしの場合、400エラー

        POST /api/v1/inquiries
        - sender_email が必須
        """
        # Setup
        await app_admin_user_factory()

        # リクエストデータ（sender_email なし）
        payload = {
            "title": "質問",
            "content": "内容",
            "sender_name": "ゲスト"
            # sender_email がない
        }

        # Execute
        response = await async_client.post(
            "/api/v1/inquiries",
            json=payload
        )

        # Assert
        assert response.status_code == 400
        assert "送信者メールアドレスは必須です" in response.json()["detail"]


class TestAdminInquiryListEndpoint:
    """管理者用問い合わせ一覧エンドポイントのテスト"""

    async def test_get_inquiries_as_app_admin(
        self,
        async_client: AsyncClient,
        app_admin_user_factory,
        employee_user_factory,
        db_session: AsyncSession
    ):
        """
        app_adminが問い合わせ一覧を取得

        GET /api/v1/admin/inquiries
        - app_admin専用
        - ページネーション対応
        """
        # Setup
        app_admin = await app_admin_user_factory()
        sender = await employee_user_factory()

        # 問い合わせを作成
        from app import crud

        office_id = sender.office_associations[0].office.id if sender.office_associations else None
        await crud.inquiry.create_inquiry(
            db=db_session,
            sender_staff_id=sender.id,
            office_id=office_id,
            title="テスト問い合わせ",
            content="テスト内容",
            priority=InquiryPriority.normal,
            admin_recipient_ids=[app_admin.id],
            is_test_data=True
        )
        await db_session.commit()

        # 認証トークン
        access_token = create_access_token(
            str(app_admin.id),
            timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        )

        # Execute (include_test_data=trueを指定)
        response = await async_client.get(
            "/api/v1/admin/inquiries?include_test_data=true",
            cookies={"access_token": access_token}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "inquiries" in data
        assert "total" in data
        assert isinstance(data["inquiries"], list)
        assert data["total"] >= 1

    async def test_get_inquiries_as_employee_fails(
        self,
        async_client: AsyncClient,
        employee_user_factory
    ):
        """
        Employeeは問い合わせ一覧を取得できない

        GET /api/v1/admin/inquiries
        - 403 Forbidden
        """
        # Setup
        employee = await employee_user_factory()

        # 認証トークン（Employee）
        access_token = create_access_token(
            str(employee.id),
            timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        )

        # Execute
        response = await async_client.get(
            "/api/v1/admin/inquiries",
            cookies={"access_token": access_token}
        )

        # Assert
        assert response.status_code == 403
        assert "権限がありません" in response.json()["detail"]

    async def test_get_inquiries_with_filters(
        self,
        async_client: AsyncClient,
        app_admin_user_factory,
        employee_user_factory,
        db_session: AsyncSession
    ):
        """
        フィルタ付き問い合わせ一覧取得

        GET /api/v1/admin/inquiries?status=new&priority=high
        """
        # Setup
        app_admin = await app_admin_user_factory()
        sender = await employee_user_factory()
        from app import crud

        office_id = sender.office_associations[0].office.id if sender.office_associations else None

        # 高優先度の問い合わせを作成
        await crud.inquiry.create_inquiry(
            db=db_session,
            sender_staff_id=sender.id,
            office_id=office_id,
            title="緊急問い合わせ",
            content="緊急の内容",
            priority=InquiryPriority.high,
            admin_recipient_ids=[app_admin.id],
            is_test_data=True
        )
        await db_session.commit()

        # 認証トークン
        access_token = create_access_token(
            str(app_admin.id),
            timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        )

        # Execute
        response = await async_client.get(
            "/api/v1/admin/inquiries?status=new&priority=high&include_test_data=true",
            cookies={"access_token": access_token}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        # すべての問い合わせが高優先度
        for inquiry in data["inquiries"]:
            assert inquiry["priority"] == "high"


class TestAdminInquiryDetailEndpoint:
    """管理者用問い合わせ詳細エンドポイントのテスト"""

    async def test_get_inquiry_detail_as_app_admin(
        self,
        async_client: AsyncClient,
        app_admin_user_factory,
        employee_user_factory,
        db_session: AsyncSession
    ):
        """
        app_adminが問い合わせ詳細を取得

        GET /api/v1/admin/inquiries/{inquiry_id}
        """
        # Setup
        app_admin = await app_admin_user_factory()
        sender = await employee_user_factory()
        from app import crud

        office_id = sender.office_associations[0].office.id if sender.office_associations else None
        inquiry = await crud.inquiry.create_inquiry(
            db=db_session,
            sender_staff_id=sender.id,
            office_id=office_id,
            title="詳細テスト",
            content="詳細テスト内容",
            priority=InquiryPriority.normal,
            admin_recipient_ids=[app_admin.id],
            is_test_data=True
        )
        await db_session.commit()

        # 認証トークン
        access_token = create_access_token(
            str(app_admin.id),
            timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        )

        # Execute
        response = await async_client.get(
            f"/api/v1/admin/inquiries/{inquiry.id}",
            cookies={"access_token": access_token}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(inquiry.id)
        assert data["message"]["title"] == "詳細テスト"
        assert data["inquiry_detail"]["status"] == "new"

    async def test_get_inquiry_detail_not_found(
        self,
        async_client: AsyncClient,
        app_admin_user_factory
    ):
        """
        存在しない問い合わせID

        GET /api/v1/admin/inquiries/{inquiry_id}
        - 404 Not Found
        """
        # Setup
        app_admin = await app_admin_user_factory()

        # 認証トークン
        access_token = create_access_token(
            str(app_admin.id),
            timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        )

        # Execute（存在しないID）
        fake_id = uuid4()
        response = await async_client.get(
            f"/api/v1/admin/inquiries/{fake_id}",
            cookies={"access_token": access_token}
        )

        # Assert
        assert response.status_code == 404
        assert "見つかりません" in response.json()["detail"]


class TestAdminInquiryUpdateEndpoint:
    """管理者用問い合わせ更新エンドポイントのテスト"""

    async def test_update_inquiry_as_app_admin(
        self,
        async_client: AsyncClient,
        app_admin_user_factory,
        employee_user_factory,
        db_session: AsyncSession
    ):
        """
        app_adminが問い合わせを更新

        PATCH /api/v1/admin/inquiries/{inquiry_id}
        """
        # Setup
        app_admin = await app_admin_user_factory()
        sender = await employee_user_factory()
        from app import crud

        office_id = sender.office_associations[0].office.id if sender.office_associations else None
        inquiry = await crud.inquiry.create_inquiry(
            db=db_session,
            sender_staff_id=sender.id,
            office_id=office_id,
            title="更新テスト",
            content="更新テスト内容",
            priority=InquiryPriority.normal,
            admin_recipient_ids=[app_admin.id],
            is_test_data=True
        )
        await db_session.commit()

        # 認証トークン
        access_token = create_access_token(
            str(app_admin.id),
            timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        )

        # リクエストデータ
        update_payload = {
            "status": "in_progress",
            "priority": "high",
            "admin_notes": "対応中です"
        }

        # Execute
        response = await async_client.patch(
            f"/api/v1/admin/inquiries/{inquiry.id}",
            json=update_payload,
            cookies={"access_token": access_token}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(inquiry.id)
        assert data["message"] == "更新しました"

        # データベースで確認
        updated = await crud.inquiry.get_inquiry_by_id(db=db_session, inquiry_id=inquiry.id)
        assert updated.status == InquiryStatus.in_progress
        assert updated.priority == InquiryPriority.high
        assert updated.admin_notes == "対応中です"


class TestAdminInquiryReplyEndpoint:
    """管理者用問い合わせ返信エンドポイントのテスト"""

    async def test_reply_to_inquiry_from_logged_in_sender(
        self,
        async_client: AsyncClient,
        app_admin_user_factory,
        employee_user_factory,
        db_session: AsyncSession
    ):
        """
        ログイン済み送信者への返信（内部通知）

        POST /api/v1/admin/inquiries/{inquiry_id}/reply
        - 送信者がログイン済み
        - 内部通知として配信
        - ステータスが「answered」に更新
        """
        # Setup
        app_admin = await app_admin_user_factory()
        sender = await employee_user_factory()
        from app import crud

        office_id = sender.office_associations[0].office.id if sender.office_associations else None
        inquiry = await crud.inquiry.create_inquiry(
            db=db_session,
            sender_staff_id=sender.id,
            office_id=office_id,
            title="返信テスト",
            content="返信テスト内容",
            priority=InquiryPriority.normal,
            admin_recipient_ids=[app_admin.id],
            is_test_data=True
        )
        await db_session.commit()

        # 認証トークン
        access_token = create_access_token(
            str(app_admin.id),
            timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        )

        # リクエストデータ
        reply_payload = {
            "body": "お問い合わせありがとうございます。確認いたしました。",
            "send_email": False
        }

        # Execute
        response = await async_client.post(
            f"/api/v1/admin/inquiries/{inquiry.id}/reply",
            json=reply_payload,
            cookies={"access_token": access_token}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert "返信を送信しました" in data["message"]

        # データベースで確認
        await db_session.refresh(inquiry)
        assert inquiry.status == InquiryStatus.answered

        # 返信メッセージが作成されていることを確認
        from app.models.message import Message
        from sqlalchemy import select
        query = select(Message).where(
            Message.sender_staff_id == app_admin.id,
            Message.content.contains("確認いたしました")
        )
        result = await db_session.execute(query)
        reply_message = result.scalar_one_or_none()
        assert reply_message is not None
        assert reply_message.message_type.value == "inquiry_reply"

    async def test_reply_to_inquiry_with_email(
        self,
        async_client: AsyncClient,
        app_admin_user_factory,
        employee_user_factory,
        db_session: AsyncSession
    ):
        """
        メール送信フラグ付き返信

        POST /api/v1/admin/inquiries/{inquiry_id}/reply
        - send_email=true
        - delivery_logに記録される
        """
        # Setup
        app_admin = await app_admin_user_factory()
        sender = await employee_user_factory()
        from app import crud

        office_id = sender.office_associations[0].office.id if sender.office_associations else None

        # sender_emailを設定した問い合わせを作成
        inquiry = await crud.inquiry.create_inquiry(
            db=db_session,
            sender_staff_id=sender.id,
            office_id=office_id,
            title="メール返信テスト",
            content="メール返信テスト内容",
            priority=InquiryPriority.normal,
            admin_recipient_ids=[app_admin.id],
            sender_email="sender@example.com",
            is_test_data=True
        )
        await db_session.commit()

        # 認証トークン
        access_token = create_access_token(
            str(app_admin.id),
            timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        )

        # リクエストデータ（メール送信フラグON）
        reply_payload = {
            "body": "メールでの返信内容です。",
            "send_email": True
        }

        # Execute
        response = await async_client.post(
            f"/api/v1/admin/inquiries/{inquiry.id}/reply",
            json=reply_payload,
            cookies={"access_token": access_token}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "メール送信を含む" in data["message"]

        # delivery_logに記録されていることを確認
        await db_session.refresh(inquiry)
        assert inquiry.delivery_log is not None
        assert len(inquiry.delivery_log) > 0
        assert inquiry.delivery_log[0]["action"] == "reply_email_queued"
        assert inquiry.delivery_log[0]["recipient"] == "sender@example.com"

    async def test_reply_to_inquiry_not_found(
        self,
        async_client: AsyncClient,
        app_admin_user_factory
    ):
        """
        存在しない問い合わせへの返信

        POST /api/v1/admin/inquiries/{inquiry_id}/reply
        - 404 Not Found
        """
        # Setup
        app_admin = await app_admin_user_factory()

        # 認証トークン
        access_token = create_access_token(
            str(app_admin.id),
            timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        )

        # リクエストデータ
        reply_payload = {
            "body": "返信内容",
            "send_email": False
        }

        # Execute（存在しないID）
        fake_id = uuid4()
        response = await async_client.post(
            f"/api/v1/admin/inquiries/{fake_id}/reply",
            json=reply_payload,
            cookies={"access_token": access_token}
        )

        # Assert
        assert response.status_code == 404
        assert "見つかりません" in response.json()["detail"]

    async def test_reply_to_inquiry_empty_body_fails(
        self,
        async_client: AsyncClient,
        app_admin_user_factory,
        employee_user_factory,
        db_session: AsyncSession
    ):
        """
        返信内容が空の場合はバリデーションエラー

        POST /api/v1/admin/inquiries/{inquiry_id}/reply
        - 422 Validation Error
        """
        # Setup
        app_admin = await app_admin_user_factory()
        sender = await employee_user_factory()
        from app import crud

        office_id = sender.office_associations[0].office.id if sender.office_associations else None
        inquiry = await crud.inquiry.create_inquiry(
            db=db_session,
            sender_staff_id=sender.id,
            office_id=office_id,
            title="バリデーションテスト",
            content="バリデーションテスト内容",
            priority=InquiryPriority.normal,
            admin_recipient_ids=[app_admin.id],
            is_test_data=True
        )
        await db_session.commit()

        # 認証トークン
        access_token = create_access_token(
            str(app_admin.id),
            timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        )

        # リクエストデータ（空の本文）
        reply_payload = {
            "body": "   ",  # 空白のみ
            "send_email": False
        }

        # Execute
        response = await async_client.post(
            f"/api/v1/admin/inquiries/{inquiry.id}/reply",
            json=reply_payload,
            cookies={"access_token": access_token}
        )

        # Assert
        assert response.status_code == 422
        assert "返信内容は空にできません" in str(response.json())

    async def test_reply_as_non_admin_fails(
        self,
        async_client: AsyncClient,
        employee_user_factory,
        app_admin_user_factory,
        db_session: AsyncSession
    ):
        """
        非app_adminは返信できない

        POST /api/v1/admin/inquiries/{inquiry_id}/reply
        - 403 Forbidden
        """
        # Setup
        sender = await employee_user_factory()
        from app import crud

        # app_adminユーザーを作成
        app_admin = await app_admin_user_factory()

        office_id = sender.office_associations[0].office.id if sender.office_associations else None
        inquiry = await crud.inquiry.create_inquiry(
            db=db_session,
            sender_staff_id=sender.id,
            office_id=office_id,
            title="権限テスト",
            content="権限テスト内容",
            priority=InquiryPriority.normal,
            admin_recipient_ids=[app_admin.id],
            is_test_data=True
        )
        await db_session.commit()

        # 認証トークン（Employee）
        access_token = create_access_token(
            str(sender.id),
            timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        )

        # リクエストデータ
        reply_payload = {
            "body": "返信内容",
            "send_email": False
        }

        # Execute
        response = await async_client.post(
            f"/api/v1/admin/inquiries/{inquiry.id}/reply",
            json=reply_payload,
            cookies={"access_token": access_token}
        )

        # Assert
        assert response.status_code == 403
        assert "権限がありません" in response.json()["detail"]


class TestAdminInquiryDeleteEndpoint:
    """管理者用問い合わせ削除エンドポイントのテスト"""

    async def test_delete_inquiry_as_app_admin(
        self,
        async_client: AsyncClient,
        app_admin_user_factory,
        employee_user_factory,
        db_session: AsyncSession
    ):
        """
        app_adminが問い合わせを削除

        DELETE /api/v1/admin/inquiries/{inquiry_id}
        """
        # Setup
        app_admin = await app_admin_user_factory()
        sender = await employee_user_factory()
        from app import crud

        office_id = sender.office_associations[0].office.id if sender.office_associations else None
        inquiry = await crud.inquiry.create_inquiry(
            db=db_session,
            sender_staff_id=sender.id,
            office_id=office_id,
            title="削除テスト",
            content="削除テスト内容",
            priority=InquiryPriority.normal,
            admin_recipient_ids=[app_admin.id],
            is_test_data=True
        )
        await db_session.commit()

        inquiry_id = inquiry.id

        # 認証トークン
        access_token = create_access_token(
            str(app_admin.id),
            timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        )

        # Execute
        response = await async_client.delete(
            f"/api/v1/admin/inquiries/{inquiry_id}",
            cookies={"access_token": access_token}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "削除しました"

        # データベースで確認（削除されている）
        deleted = await crud.inquiry.get_inquiry_by_id(db=db_session, inquiry_id=inquiry_id)
        assert deleted is None

    async def test_delete_inquiry_not_found(
        self,
        async_client: AsyncClient,
        app_admin_user_factory
    ):
        """
        存在しない問い合わせの削除

        DELETE /api/v1/admin/inquiries/{inquiry_id}
        - 404 Not Found
        """
        # Setup
        app_admin = await app_admin_user_factory()

        # 認証トークン
        access_token = create_access_token(
            str(app_admin.id),
            timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        )

        # Execute（存在しないID）
        fake_id = uuid4()
        response = await async_client.delete(
            f"/api/v1/admin/inquiries/{fake_id}",
            cookies={"access_token": access_token}
        )

        # Assert
        assert response.status_code == 404
        assert "見つかりません" in response.json()["detail"]
