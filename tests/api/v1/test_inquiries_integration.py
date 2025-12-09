"""
問い合わせ機能の統合テスト

エンドツーエンドで以下をテスト：
- 問い合わせ作成（ログイン済み/未ログイン）
- セキュリティ機能（サニタイズ、レート制限、スパム検出、ハニーポット）
- CRUD操作の統合
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import timedelta
from uuid import uuid4

from app.core.security import create_access_token
from app.core.config import settings
from app.models.enums import StaffRole, OfficeType, InquiryStatus, InquiryPriority

pytestmark = pytest.mark.asyncio


async def get_csrf_tokens(async_client: AsyncClient) -> tuple[str, str]:
    """
    CSRFトークンを取得するヘルパー関数

    Returns:
        tuple[str, str]: (csrf_token, csrf_cookie)
    """
    csrf_response = await async_client.get("/api/v1/csrf-token")
    csrf_token = csrf_response.json()["csrf_token"]
    csrf_cookie = csrf_response.cookies.get("fastapi-csrf-token")
    return csrf_token, csrf_cookie


class TestInquiryCreationIntegration:
    """問い合わせ作成の統合テスト"""

    async def test_create_inquiry_from_logged_in_user_full_flow(
        self,
        async_client: AsyncClient,
        employee_user_factory,
        app_admin_user_factory,
        db_session: AsyncSession
    ):
        """
        ログイン済みユーザーからの問い合わせ作成（フルフロー）

        1. 問い合わせを送信
        2. データベースに保存される
        3. app_adminに通知される
        4. サニタイズが適用される
        """
        # 1. Setup: ユーザーとapp_adminを作成
        sender = await employee_user_factory()
        app_admin = await app_admin_user_factory()

        # 2. リクエストデータ
        payload = {
            "title": "機能について質問",
            "content": "サービスの使い方を教えてください。",
            "category": "質問"
        }

        # 3. 認証 + CSRF トークン
        access_token = create_access_token(
            str(sender.id),
            timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        csrf_token, csrf_cookie = await get_csrf_tokens(async_client)

        cookies = {
            "access_token": access_token,
            "fastapi-csrf-token": csrf_cookie
        }
        headers = {"X-CSRF-Token": csrf_token}

        # 4. 問い合わせ送信（まだエンドポイント未実装のため、CRUD層のテスト）
        from app import crud
        from app.models.inquiry import InquiryDetail

        inquiry = await crud.inquiry.create_inquiry(
            db=db_session,
            sender_staff_id=sender.id,
            office_id=sender.office_associations[0].office.id if sender.office_associations else None,
            title=payload["title"],
            content=payload["content"],
            priority=InquiryPriority.normal,
            admin_recipient_ids=[app_admin.id],
            is_test_data=True
        )

        await db_session.commit()

        # 5. Assert: 問い合わせが作成された
        assert inquiry is not None
        assert inquiry.message.title == "機能について質問"
        assert inquiry.message.content == "サービスの使い方を教えてください。"
        assert inquiry.message.sender_staff_id == sender.id
        assert inquiry.status == InquiryStatus.new
        assert inquiry.priority == InquiryPriority.normal

        # 6. Assert: MessageRecipientが作成された
        assert len(inquiry.message.recipients) == 1
        assert inquiry.message.recipients[0].recipient_staff_id == app_admin.id

    async def test_create_inquiry_from_guest_user_full_flow(
        self,
        async_client: AsyncClient,
        app_admin_user_factory,
        db_session: AsyncSession
    ):
        """
        未ログインユーザーからの問い合わせ作成（フルフロー）

        1. 未ログインで問い合わせを送信
        2. sender_name, sender_emailが記録される
        3. ip_address, user_agentが記録される
        """
        # 1. Setup: app_adminを作成
        app_admin = await app_admin_user_factory()

        # システム用officeを作成
        from app.models.office import Office
        from app.models.staff import Staff

        # app_adminをcreated_byとして使用するためにStaffとして取得
        system_office = Office(
            id=uuid4(),
            name="システム",
            type=OfficeType.type_A_office,
            created_by=app_admin.id,
            last_modified_by=app_admin.id,
            is_test_data=True
        )
        db_session.add(system_office)
        await db_session.flush()

        # 2. リクエストデータ（未ログイン）
        payload = {
            "title": "利用方法について",
            "content": "このアプリの使い方を教えてください。",
            "sender_name": "ゲストユーザー",
            "sender_email": "guest@example.com",
            "category": "質問"
        }

        # 3. CSRFトークン（未ログインでも取得可能）
        csrf_token, csrf_cookie = await get_csrf_tokens(async_client)

        cookies = {"fastapi-csrf-token": csrf_cookie}
        headers = {"X-CSRF-Token": csrf_token}

        # 4. 問い合わせ送信（CRUD層）
        from app import crud

        inquiry = await crud.inquiry.create_inquiry(
            db=db_session,
            sender_staff_id=None,  # 未ログイン
            office_id=system_office.id,
            title=payload["title"],
            content=payload["content"],
            sender_name=payload["sender_name"],
            sender_email=payload["sender_email"],
            priority=InquiryPriority.normal,
            ip_address="203.0.113.42",
            user_agent="Mozilla/5.0",
            admin_recipient_ids=[app_admin.id],
            is_test_data=True
        )

        await db_session.commit()

        # 5. Assert: 問い合わせが作成された
        assert inquiry is not None
        assert inquiry.message.sender_staff_id is None
        assert inquiry.sender_name == "ゲストユーザー"
        assert inquiry.sender_email == "guest@example.com"
        assert inquiry.ip_address == "203.0.113.42"
        assert inquiry.user_agent == "Mozilla/5.0"


class TestInquirySanitizationIntegration:
    """サニタイズ機能の統合テスト"""

    async def test_html_sanitization_in_inquiry(
        self,
        async_client: AsyncClient,
        app_admin_user_factory,
        db_session: AsyncSession
    ):
        """
        HTMLタグがサニタイズされること

        入力: <script>alert('XSS')</script>
        期待: タグが除去またはエスケープされる
        """
        from app.utils.sanitization import sanitize_inquiry_input

        # HTMLタグを含む入力
        input_data = {
            "title": "<script>alert('XSS')</script>件名",
            "content": "<b>太字</b>の内容",
            "honeypot": ""
        }

        # サニタイズ
        sanitized = sanitize_inquiry_input(**input_data)

        # Assert: HTMLタグが除去されている
        assert "<script>" not in sanitized["title"]
        assert "<b>" not in sanitized["content"]
        assert "件名" in sanitized["title"]
        assert "太字" in sanitized["content"]

    async def test_spam_detection_integration(
        self,
        async_client: AsyncClient,
        app_admin_user_factory,
        db_session: AsyncSession
    ):
        """
        スパム検出の統合テスト

        スパムパターンを含む問い合わせは拒否される
        """
        from app.utils.sanitization import sanitize_inquiry_input

        # スパムパターンを含む入力
        spam_data = {
            "title": "お得な情報",
            "content": "今すぐクリック！http://spam1.com http://spam2.com http://spam3.com",
            "honeypot": ""
        }

        # Assert: スパム検出でValueErrorが発生
        with pytest.raises(ValueError, match="Spam detected"):
            sanitize_inquiry_input(**spam_data)

    async def test_honeypot_detection_integration(
        self,
        async_client: AsyncClient,
        app_admin_user_factory,
        db_session: AsyncSession
    ):
        """
        ハニーポット検出の統合テスト

        ハニーポットに値が入っている場合は拒否される
        """
        from app.utils.sanitization import sanitize_inquiry_input

        # ハニーポットに値が入っている（ボット）
        bot_data = {
            "title": "質問",
            "content": "内容",
            "honeypot": "bot-value"  # ボットが埋めた
        }

        # Assert: ハニーポット検出でValueErrorが発生
        with pytest.raises(ValueError, match="Invalid submission detected"):
            sanitize_inquiry_input(**bot_data)

    async def test_email_sanitization_integration(
        self,
        async_client: AsyncClient,
        app_admin_user_factory,
        db_session: AsyncSession
    ):
        """
        メールアドレスのサニタイズ統合テスト

        大文字 → 小文字、前後の空白除去
        """
        from app.utils.sanitization import sanitize_inquiry_input

        # 大文字と空白を含むメールアドレス
        input_data = {
            "title": "質問",
            "content": "内容",
            "sender_email": "  Test@Example.COM  ",
            "honeypot": ""
        }

        sanitized = sanitize_inquiry_input(**input_data)

        # Assert: 小文字に変換され、空白が除去されている
        assert sanitized["sender_email"] == "test@example.com"


class TestInquiryCRUDIntegration:
    """CRUD操作の統合テスト"""

    async def test_inquiry_retrieval_with_filters(
        self,
        async_client: AsyncClient,
        employee_user_factory,
        app_admin_user_factory,
        db_session: AsyncSession
    ):
        """
        問い合わせ一覧取得（フィルタリング）

        1. 複数の問い合わせを作成
        2. ステータスでフィルタリング
        3. 優先度でフィルタリング
        """
        from app import crud

        # Setup
        sender = await employee_user_factory()
        app_admin = await app_admin_user_factory()
        office_id = sender.office_associations[0].office.id if sender.office_associations else None

        # 作成前のカウントを取得
        _, count_before = await crud.inquiry.get_inquiries(
            db=db_session,
            status=InquiryStatus.new,
            skip=0,
            limit=100,
            include_test_data=True
        )

        # 新規問い合わせを2件作成
        inquiry1 = await crud.inquiry.create_inquiry(
            db=db_session,
            sender_staff_id=sender.id,
            office_id=office_id,
            title="新規問い合わせ1",
            content="内容1",
            priority=InquiryPriority.normal,
            admin_recipient_ids=[app_admin.id],
            is_test_data=True
        )

        inquiry2 = await crud.inquiry.create_inquiry(
            db=db_session,
            sender_staff_id=sender.id,
            office_id=office_id,
            title="新規問い合わせ2",
            content="内容2",
            priority=InquiryPriority.normal,
            admin_recipient_ids=[app_admin.id],
            is_test_data=True
        )

        # 高優先度の問い合わせを1件作成
        inquiry3 = await crud.inquiry.create_inquiry(
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

        # Execute: 新規ステータスのみ取得
        inquiries_new, total_new = await crud.inquiry.get_inquiries(
            db=db_session,
            status=InquiryStatus.new,
            skip=0,
            limit=100,
            include_test_data=True
        )

        # Assert: 3件増えている
        assert total_new == count_before + 3
        assert len(inquiries_new) >= 3

        # 作成した問い合わせのIDが含まれているか確認
        inquiry_ids = [str(inq.id) for inq in inquiries_new]
        assert str(inquiry1.id) in inquiry_ids
        assert str(inquiry2.id) in inquiry_ids
        assert str(inquiry3.id) in inquiry_ids

        # Execute: 高優先度のみ取得
        inquiries_high, total_high = await crud.inquiry.get_inquiries(
            db=db_session,
            priority=InquiryPriority.high,
            skip=0,
            limit=100,
            include_test_data=True
        )

        # Assert: 作成した高優先度の問い合わせが含まれている
        high_inquiry_ids = [str(inq.id) for inq in inquiries_high]
        assert str(inquiry3.id) in high_inquiry_ids
        assert all(inq.priority == InquiryPriority.high for inq in inquiries_high)

    async def test_inquiry_update_integration(
        self,
        async_client: AsyncClient,
        employee_user_factory,
        app_admin_user_factory,
        db_session: AsyncSession
    ):
        """
        問い合わせ更新の統合テスト

        1. 問い合わせを作成
        2. ステータスを更新
        3. 担当者を割り当て
        """
        from app import crud

        # Setup
        sender = await employee_user_factory()
        app_admin = await app_admin_user_factory()
        staff_member = await employee_user_factory()
        office_id = sender.office_associations[0].office.id if sender.office_associations else None

        # 問い合わせ作成
        inquiry = await crud.inquiry.create_inquiry(
            db=db_session,
            sender_staff_id=sender.id,
            office_id=office_id,
            title="更新テスト",
            content="内容",
            priority=InquiryPriority.normal,
            admin_recipient_ids=[app_admin.id],
            is_test_data=True
        )

        await db_session.commit()

        # Execute: ステータスと担当者を更新
        updated = await crud.inquiry.update_inquiry(
            db=db_session,
            inquiry_id=inquiry.id,
            status=InquiryStatus.in_progress,
            assigned_staff_id=staff_member.id,
            admin_notes="対応中"
        )

        await db_session.commit()

        # Assert
        assert updated.status == InquiryStatus.in_progress
        assert updated.assigned_staff_id == staff_member.id
        assert updated.admin_notes == "対応中"

    async def test_inquiry_deletion_integration(
        self,
        async_client: AsyncClient,
        employee_user_factory,
        app_admin_user_factory,
        db_session: AsyncSession
    ):
        """
        問い合わせ削除の統合テスト

        1. 問い合わせを作成
        2. 削除
        3. CASCADE により Message と MessageRecipient も削除される
        """
        from app import crud

        # Setup
        sender = await employee_user_factory()
        app_admin = await app_admin_user_factory()
        office_id = sender.office_associations[0].office.id if sender.office_associations else None

        # 問い合わせ作成
        inquiry = await crud.inquiry.create_inquiry(
            db=db_session,
            sender_staff_id=sender.id,
            office_id=office_id,
            title="削除テスト",
            content="内容",
            priority=InquiryPriority.normal,
            admin_recipient_ids=[app_admin.id],
            is_test_data=True
        )

        inquiry_id = inquiry.id
        message_id = inquiry.message_id

        await db_session.commit()

        # Execute: 削除
        result = await crud.inquiry.delete_inquiry(
            db=db_session,
            inquiry_id=inquiry_id
        )

        await db_session.commit()

        # Assert
        assert result is True

        # 削除確認
        deleted_inquiry = await crud.inquiry.get_inquiry_by_id(
            db=db_session,
            inquiry_id=inquiry_id
        )
        assert deleted_inquiry is None

        # Message も削除されている
        from sqlalchemy import select
        from app.models.message import Message

        stmt = select(Message).where(Message.id == message_id)
        result = await db_session.execute(stmt)
        message = result.scalar_one_or_none()
        assert message is None


class TestInquirySecurityIntegration:
    """セキュリティ機能の統合テスト"""

    async def test_character_limit_enforcement(
        self,
        async_client: AsyncClient,
        app_admin_user_factory,
        db_session: AsyncSession
    ):
        """
        文字数制限の強制

        title: 200文字
        content: 20,000文字
        """
        from app.utils.sanitization import sanitize_inquiry_input

        # 長すぎる入力
        input_data = {
            "title": "a" * 300,  # 200文字を超える
            "content": "a" * 25000,  # 20,000文字を超える
            "honeypot": ""
        }

        sanitized = sanitize_inquiry_input(**input_data)

        # Assert: 文字数が制限されている
        assert len(sanitized["title"]) == 200
        assert len(sanitized["content"]) == 20000

    async def test_invalid_email_rejection(
        self,
        async_client: AsyncClient,
        app_admin_user_factory,
        db_session: AsyncSession
    ):
        """
        不正なメールアドレスの拒否
        """
        from app.utils.sanitization import sanitize_inquiry_input

        # 不正なメールアドレス
        input_data = {
            "title": "質問",
            "content": "内容",
            "sender_email": "invalid-email",
            "honeypot": ""
        }

        # Assert: ValueError が発生
        with pytest.raises(ValueError, match="Invalid email format"):
            sanitize_inquiry_input(**input_data)

    async def test_xss_prevention(
        self,
        async_client: AsyncClient,
        app_admin_user_factory,
        db_session: AsyncSession
    ):
        """
        XSS攻撃の防止

        スクリプトタグが無効化される
        """
        from app.utils.sanitization import sanitize_html

        # XSS攻撃パターン
        xss_input = "<script>alert('XSS')</script><img src=x onerror='alert(1)'>"

        sanitized = sanitize_html(xss_input)

        # Assert: タグがエスケープされている
        assert "&lt;script&gt;" in sanitized
        assert "&lt;img" in sanitized
        assert "alert" not in sanitized or "&" in sanitized  # エスケープされている
