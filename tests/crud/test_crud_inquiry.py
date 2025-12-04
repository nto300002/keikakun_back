"""
問い合わせ CRUD のユニットテスト（TDD - RED phase）

要件定義書に基づき、以下の機能をテストする：
- 問い合わせ作成（Message + InquiryDetail の同時作成）
- 問い合わせ一覧取得（フィルタ・ページネーション）
- 問い合わせ詳細取得
- 問い合わせ更新（ステータス、担当者、優先度、メモ）
- 返信作成
- 論理削除
"""
import pytest
from datetime import datetime, timezone
from uuid import uuid4, UUID
from typing import List, Optional

from app.crud.crud_inquiry import crud_inquiry
from app.models.inquiry import InquiryDetail
from app.models.message import Message, MessageRecipient
from app.models.staff import Staff
from app.models.office import Office
from app.models.enums import (
    InquiryStatus, InquiryPriority, MessageType,
    MessagePriority, StaffRole, OfficeType
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def setup_basic_data(db_session):
    """テスト用の基本データ（Office, app_admin）を作成するフィクスチャ"""
    # app_admin を作成
    app_admin = Staff(
        id=uuid4(),
        email="admin@example.com",
        hashed_password="hashed",
        full_name="管理者",
        role=StaffRole.app_admin,
        is_test_data=True
    )
    db_session.add(app_admin)
    await db_session.flush()

    # Office を作成
    test_office = Office(
        id=uuid4(),
        name="テスト事務所",
        type=OfficeType.type_A_office,
        created_by=app_admin.id,
        last_modified_by=app_admin.id,
        is_test_data=True
    )
    db_session.add(test_office)
    await db_session.flush()

    return test_office, app_admin


class TestCRUDInquiryCreate:
    """問い合わせ作成のテスト"""

    async def test_create_inquiry_from_logged_in_user(self, db_session, setup_basic_data):
        """
        ログイン済みユーザーからの問い合わせ作成テスト

        要件:
        - Message レコードを作成（message_type='inquiry'）
        - InquiryDetail レコードを作成
        - MessageRecipient レコードを作成（受信者: app_admin）
        - sender_name, sender_email は NULL（ログイン済みのため）
        - トランザクション内で全て作成
        """
        # 1. Setup: テスト用の Office と Staff を取得
        test_office, app_admin = setup_basic_data

        sender_staff = Staff(
            id=uuid4(),
            email="sender@example.com",
            hashed_password="hashed",
            full_name="送信者",
            role=StaffRole.employee,
            is_test_data=True
        )
        db_session.add(sender_staff)
        await db_session.flush()

        # 2. Execute: 問い合わせ作成
        inquiry_data = {
            "sender_staff_id": sender_staff.id,
            "office_id": test_office.id,
            "title": "機能について質問",
            "content": "〇〇機能の使い方を教えてください。",
            "priority": InquiryPriority.normal,
            "ip_address": "192.168.1.1",
            "user_agent": "Mozilla/5.0",
            "admin_recipient_ids": [app_admin.id]
        }

        inquiry_detail = await crud_inquiry.create_inquiry(
            db=db_session,
            **inquiry_data
        )

        # 3. Assert: レコードが正しく作成されている
        assert inquiry_detail is not None
        assert inquiry_detail.message_id is not None

        # Message が作成されている
        message = inquiry_detail.message
        assert message is not None
        assert message.sender_staff_id == sender_staff.id
        assert message.office_id == test_office.id
        assert message.message_type == MessageType.inquiry
        assert message.priority == MessagePriority.normal
        assert message.title == "機能について質問"
        assert message.content == "〇〇機能の使い方を教えてください。"

        # InquiryDetail が作成されている
        assert inquiry_detail.sender_name is None
        assert inquiry_detail.sender_email is None
        assert inquiry_detail.ip_address == "192.168.1.1"
        assert inquiry_detail.user_agent == "Mozilla/5.0"
        assert inquiry_detail.status == InquiryStatus.new
        assert inquiry_detail.priority == InquiryPriority.normal
        assert inquiry_detail.assigned_staff_id is None

        # MessageRecipient が作成されている
        assert len(message.recipients) == 1
        assert message.recipients[0].recipient_staff_id == app_admin.id
        assert message.recipients[0].is_read is False

    async def test_create_inquiry_from_guest_user(self, db_session):
        """
        未ログインユーザーからの問い合わせ作成テスト

        要件:
        - sender_staff_id は NULL
        - sender_name, sender_email に値が入る
        - office_id は NULL または システム用office_id
        - MessageRecipient として app_admin が受信
        """
        # 1. Setup: app_admin を作成
        app_admin = Staff(
            id=uuid4(),
            email="admin@example.com",
            hashed_password="hashed",
            full_name="管理者",
            role=StaffRole.app_admin,
            is_test_data=True
        )
        db_session.add(app_admin)
        await db_session.flush()

        # システム用 office を作成（または NULL を許容）
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

        # 2. Execute: 未ログインユーザーからの問い合わせ
        inquiry_data = {
            "sender_staff_id": None,
            "office_id": system_office.id,
            "title": "利用方法について",
            "content": "このアプリの使い方を教えてください。",
            "sender_name": "ゲストユーザー",
            "sender_email": "guest@example.com",
            "priority": InquiryPriority.normal,
            "ip_address": "203.0.113.42",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0)",
            "admin_recipient_ids": [app_admin.id]
        }

        inquiry_detail = await crud_inquiry.create_inquiry(
            db=db_session,
            **inquiry_data
        )

        # 3. Assert
        assert inquiry_detail is not None
        assert inquiry_detail.sender_name == "ゲストユーザー"
        assert inquiry_detail.sender_email == "guest@example.com"

        message = inquiry_detail.message
        assert message.sender_staff_id is None
        assert message.title == "利用方法について"
        assert len(message.recipients) == 1
        assert message.recipients[0].recipient_staff_id == app_admin.id

    async def test_create_inquiry_with_high_priority(self, db_session):
        """
        高優先度の問い合わせ作成テスト

        要件:
        - priority を 'high' に設定
        - Message の priority も連動して設定
        """
        # 1. Setup
        app_admin = Staff(
            id=uuid4(),
            email="admin@example.com",
            hashed_password="hashed",
            full_name="管理者",
            role=StaffRole.app_admin,
            is_test_data=True
        )
        db_session.add(app_admin)
        await db_session.flush()

        test_office = Office(
            id=uuid4(),
            name="テスト事務所",
            type=OfficeType.type_A_office,
            created_by=app_admin.id,
            last_modified_by=app_admin.id,
            is_test_data=True
        )
        db_session.add(test_office)

        sender_staff = Staff(
            id=uuid4(),
            email="sender@example.com",
            hashed_password="hashed",
            full_name="送信者",
            role=StaffRole.employee,
            is_test_data=True
        )
        db_session.add(sender_staff)
        await db_session.flush()

        # 2. Execute
        inquiry_data = {
            "sender_staff_id": sender_staff.id,
            "office_id": test_office.id,
            "title": "緊急：システムエラー",
            "content": "システムエラーが発生しています。",
            "priority": InquiryPriority.high,
            "ip_address": "192.168.1.1",
            "user_agent": "Mozilla/5.0",
            "admin_recipient_ids": [app_admin.id]
        }

        inquiry_detail = await crud_inquiry.create_inquiry(
            db=db_session,
            **inquiry_data
        )

        # 3. Assert
        assert inquiry_detail.priority == InquiryPriority.high
        assert inquiry_detail.message.priority == MessagePriority.high


class TestCRUDInquiryRetrieve:
    """問い合わせ取得のテスト"""

    async def test_get_inquiries_with_status_filter(self, db_session):
        """
        ステータスでフィルタリングした一覧取得テスト

        要件:
        - status パラメータで絞り込み
        - ページネーション対応（skip, limit）
        - created_at 降順でソート
        """
        # 1. Setup: 複数の問い合わせを作成
        app_admin = Staff(
            id=uuid4(),
            email="admin@example.com",
            hashed_password="hashed",
            full_name="管理者",
            role=StaffRole.app_admin,
            is_test_data=True
        )
        db_session.add(app_admin)
        await db_session.flush()

        test_office = Office(
            id=uuid4(),
            name="テスト事務所",
            type=OfficeType.type_A_office,
            created_by=app_admin.id,
            last_modified_by=app_admin.id,
            is_test_data=True
        )
        db_session.add(test_office)
        await db_session.flush()

        # new ステータスの問い合わせを2件作成
        for i in range(2):
            inquiry_data = {
                "sender_staff_id": None,
                "office_id": test_office.id,
                "title": f"問い合わせ{i+1}",
                "content": f"内容{i+1}",
                "sender_name": f"ゲスト{i+1}",
                "sender_email": f"guest{i+1}@example.com",
                "priority": InquiryPriority.normal,
                "admin_recipient_ids": [app_admin.id]
            }
            await crud_inquiry.create_inquiry(db=db_session, **inquiry_data)

        # answered ステータスの問い合わせを1件作成（後で更新）
        inquiry_data_answered = {
            "sender_staff_id": None,
            "office_id": test_office.id,
            "title": "回答済み問い合わせ",
            "content": "既に回答済み",
            "sender_name": "ゲスト3",
            "sender_email": "guest3@example.com",
            "priority": InquiryPriority.normal,
            "admin_recipient_ids": [app_admin.id]
        }
        inquiry_answered = await crud_inquiry.create_inquiry(
            db=db_session, **inquiry_data_answered
        )
        await crud_inquiry.update_inquiry(
            db=db_session,
            inquiry_id=inquiry_answered.id,
            status=InquiryStatus.answered
        )

        await db_session.flush()

        # 2. Execute: new ステータスのみ取得
        inquiries, total = await crud_inquiry.get_inquiries(
            db=db_session,
            status=InquiryStatus.new,
            skip=0,
            limit=10
        )

        # 3. Assert
        assert total == 2
        assert len(inquiries) == 2
        for inquiry in inquiries:
            assert inquiry.status == InquiryStatus.new

    async def test_get_inquiries_with_assigned_filter(self, db_session):
        """
        担当者でフィルタリングした一覧取得テスト

        要件:
        - assigned_staff_id パラメータで絞り込み
        """
        # 1. Setup
        app_admin = Staff(
            id=uuid4(),
            email="admin@example.com",
            hashed_password="hashed",
            full_name="管理者",
            role=StaffRole.app_admin,
            is_test_data=True
        )
        db_session.add(app_admin)
        await db_session.flush()

        test_office = Office(
            id=uuid4(),
            name="テスト事務所",
            type=OfficeType.type_A_office,
            created_by=app_admin.id,
            last_modified_by=app_admin.id,
            is_test_data=True
        )
        db_session.add(test_office)

        staff_member = Staff(
            id=uuid4(),
            email="staff@example.com",
            hashed_password="hashed",
            full_name="スタッフ",
            role=StaffRole.manager,
            is_test_data=True
        )
        db_session.add(staff_member)
        await db_session.flush()

        # 担当者ありの問い合わせ
        inquiry_data_assigned = {
            "sender_staff_id": None,
            "office_id": test_office.id,
            "title": "担当者あり",
            "content": "内容",
            "sender_name": "ゲスト1",
            "sender_email": "guest1@example.com",
            "priority": InquiryPriority.normal,
            "admin_recipient_ids": [app_admin.id]
        }
        inquiry_assigned = await crud_inquiry.create_inquiry(
            db=db_session, **inquiry_data_assigned
        )
        await crud_inquiry.update_inquiry(
            db=db_session,
            inquiry_id=inquiry_assigned.id,
            assigned_staff_id=staff_member.id
        )

        # 担当者なしの問い合わせ
        inquiry_data_unassigned = {
            "sender_staff_id": None,
            "office_id": test_office.id,
            "title": "担当者なし",
            "content": "内容",
            "sender_name": "ゲスト2",
            "sender_email": "guest2@example.com",
            "priority": InquiryPriority.normal,
            "admin_recipient_ids": [app_admin.id]
        }
        await crud_inquiry.create_inquiry(db=db_session, **inquiry_data_unassigned)
        await db_session.flush()

        # 2. Execute: 担当者ありのみ取得
        inquiries, total = await crud_inquiry.get_inquiries(
            db=db_session,
            assigned_staff_id=staff_member.id,
            skip=0,
            limit=10
        )

        # 3. Assert
        assert total == 1
        assert len(inquiries) == 1
        assert inquiries[0].assigned_staff_id == staff_member.id

    async def test_get_inquiries_with_priority_filter(self, db_session):
        """
        優先度でフィルタリングした一覧取得テスト

        要件:
        - priority パラメータで絞り込み
        """
        # 1. Setup
        app_admin = Staff(
            id=uuid4(),
            email="admin@example.com",
            hashed_password="hashed",
            full_name="管理者",
            role=StaffRole.app_admin,
            is_test_data=True
        )
        db_session.add(app_admin)
        await db_session.flush()

        test_office = Office(
            id=uuid4(),
            name="テスト事務所",
            type=OfficeType.type_A_office,
            created_by=app_admin.id,
            last_modified_by=app_admin.id,
            is_test_data=True
        )
        db_session.add(test_office)
        await db_session.flush()

        # 高優先度
        inquiry_data_high = {
            "sender_staff_id": None,
            "office_id": test_office.id,
            "title": "高優先度",
            "content": "内容",
            "sender_name": "ゲスト1",
            "sender_email": "guest1@example.com",
            "priority": InquiryPriority.high,
            "admin_recipient_ids": [app_admin.id]
        }
        await crud_inquiry.create_inquiry(db=db_session, **inquiry_data_high)

        # 通常優先度
        inquiry_data_normal = {
            "sender_staff_id": None,
            "office_id": test_office.id,
            "title": "通常優先度",
            "content": "内容",
            "sender_name": "ゲスト2",
            "sender_email": "guest2@example.com",
            "priority": InquiryPriority.normal,
            "admin_recipient_ids": [app_admin.id]
        }
        await crud_inquiry.create_inquiry(db=db_session, **inquiry_data_normal)
        await db_session.flush()

        # 2. Execute: 高優先度のみ取得
        inquiries, total = await crud_inquiry.get_inquiries(
            db=db_session,
            priority=InquiryPriority.high,
            skip=0,
            limit=10
        )

        # 3. Assert
        assert total == 1
        assert len(inquiries) == 1
        assert inquiries[0].priority == InquiryPriority.high

    async def test_get_inquiries_with_pagination(self, db_session):
        """
        ページネーションのテスト

        要件:
        - skip, limit パラメータで取得範囲を制御
        - total カウントは正確
        """
        # 1. Setup: 5件の問い合わせを作成
        app_admin = Staff(
            id=uuid4(),
            email="admin@example.com",
            hashed_password="hashed",
            full_name="管理者",
            role=StaffRole.app_admin,
            is_test_data=True
        )
        db_session.add(app_admin)
        await db_session.flush()

        test_office = Office(
            id=uuid4(),
            name="テスト事務所",
            type=OfficeType.type_A_office,
            created_by=app_admin.id,
            last_modified_by=app_admin.id,
            is_test_data=True
        )
        db_session.add(test_office)
        await db_session.flush()

        for i in range(5):
            inquiry_data = {
                "sender_staff_id": None,
                "office_id": test_office.id,
                "title": f"問い合わせ{i+1}",
                "content": f"内容{i+1}",
                "sender_name": f"ゲスト{i+1}",
                "sender_email": f"guest{i+1}@example.com",
                "priority": InquiryPriority.normal,
                "admin_recipient_ids": [app_admin.id]
            }
            await crud_inquiry.create_inquiry(db=db_session, **inquiry_data)
        await db_session.flush()

        # 2. Execute: 最初の2件を取得
        inquiries_page1, total = await crud_inquiry.get_inquiries(
            db=db_session,
            skip=0,
            limit=2
        )

        # 3. Assert
        assert total == 5
        assert len(inquiries_page1) == 2

        # 次の2件を取得
        inquiries_page2, total = await crud_inquiry.get_inquiries(
            db=db_session,
            skip=2,
            limit=2
        )
        assert total == 5
        assert len(inquiries_page2) == 2

        # 最後の1件を取得
        inquiries_page3, total = await crud_inquiry.get_inquiries(
            db=db_session,
            skip=4,
            limit=2
        )
        assert total == 5
        assert len(inquiries_page3) == 1

    async def test_get_inquiry_by_id(self, db_session):
        """
        IDによる詳細取得テスト

        要件:
        - inquiry_id で1件取得
        - Message と InquiryDetail の情報を両方取得
        - 存在しない ID の場合は None を返す
        """
        # 1. Setup
        app_admin = Staff(
            id=uuid4(),
            email="admin@example.com",
            hashed_password="hashed",
            full_name="管理者",
            role=StaffRole.app_admin,
            is_test_data=True
        )
        db_session.add(app_admin)
        await db_session.flush()

        test_office = Office(
            id=uuid4(),
            name="テスト事務所",
            type=OfficeType.type_A_office,
            created_by=app_admin.id,
            last_modified_by=app_admin.id,
            is_test_data=True
        )
        db_session.add(test_office)
        await db_session.flush()

        inquiry_data = {
            "sender_staff_id": None,
            "office_id": test_office.id,
            "title": "詳細取得テスト",
            "content": "テスト内容",
            "sender_name": "ゲスト",
            "sender_email": "guest@example.com",
            "priority": InquiryPriority.normal,
            "admin_recipient_ids": [app_admin.id]
        }
        inquiry = await crud_inquiry.create_inquiry(db=db_session, **inquiry_data)
        await db_session.flush()

        # 2. Execute: 詳細取得
        retrieved = await crud_inquiry.get_inquiry_by_id(
            db=db_session,
            inquiry_id=inquiry.id
        )

        # 3. Assert
        assert retrieved is not None
        assert retrieved.id == inquiry.id
        assert retrieved.message.title == "詳細取得テスト"
        assert retrieved.sender_email == "guest@example.com"

        # 存在しない ID
        non_existent = await crud_inquiry.get_inquiry_by_id(
            db=db_session,
            inquiry_id=uuid4()
        )
        assert non_existent is None


class TestCRUDInquiryUpdate:
    """問い合わせ更新のテスト"""

    async def test_update_inquiry_status(self, db_session):
        """
        ステータス更新テスト

        要件:
        - status を更新
        - updated_at が更新される
        """
        # 1. Setup
        app_admin = Staff(
            id=uuid4(),
            email="admin@example.com",
            hashed_password="hashed",
            full_name="管理者",
            role=StaffRole.app_admin,
            is_test_data=True
        )
        db_session.add(app_admin)
        await db_session.flush()

        test_office = Office(
            id=uuid4(),
            name="テスト事務所",
            type=OfficeType.type_A_office,
            created_by=app_admin.id,
            last_modified_by=app_admin.id,
            is_test_data=True
        )
        db_session.add(test_office)
        await db_session.flush()

        inquiry_data = {
            "sender_staff_id": None,
            "office_id": test_office.id,
            "title": "ステータス更新テスト",
            "content": "内容",
            "sender_name": "ゲスト",
            "sender_email": "guest@example.com",
            "priority": InquiryPriority.normal,
            "admin_recipient_ids": [app_admin.id]
        }
        inquiry = await crud_inquiry.create_inquiry(db=db_session, **inquiry_data)
        await db_session.flush()

        original_updated_at = inquiry.updated_at

        # 2. Execute: ステータス更新
        updated = await crud_inquiry.update_inquiry(
            db=db_session,
            inquiry_id=inquiry.id,
            status=InquiryStatus.in_progress
        )

        # 3. Assert
        assert updated.status == InquiryStatus.in_progress
        assert updated.updated_at > original_updated_at

    async def test_update_inquiry_assigned_staff(self, db_session):
        """
        担当者割当テスト

        要件:
        - assigned_staff_id を更新
        """
        # 1. Setup
        app_admin = Staff(
            id=uuid4(),
            email="admin@example.com",
            hashed_password="hashed",
            full_name="管理者",
            role=StaffRole.app_admin,
            is_test_data=True
        )
        db_session.add(app_admin)
        await db_session.flush()

        test_office = Office(
            id=uuid4(),
            name="テスト事務所",
            type=OfficeType.type_A_office,
            created_by=app_admin.id,
            last_modified_by=app_admin.id,
            is_test_data=True
        )
        db_session.add(test_office)

        staff_member = Staff(
            id=uuid4(),
            email="staff@example.com",
            hashed_password="hashed",
            full_name="スタッフ",
            role=StaffRole.manager,
            is_test_data=True
        )
        db_session.add(staff_member)
        await db_session.flush()

        inquiry_data = {
            "sender_staff_id": None,
            "office_id": test_office.id,
            "title": "担当者割当テスト",
            "content": "内容",
            "sender_name": "ゲスト",
            "sender_email": "guest@example.com",
            "priority": InquiryPriority.normal,
            "admin_recipient_ids": [app_admin.id]
        }
        inquiry = await crud_inquiry.create_inquiry(db=db_session, **inquiry_data)
        await db_session.flush()

        # 2. Execute: 担当者割当
        updated = await crud_inquiry.update_inquiry(
            db=db_session,
            inquiry_id=inquiry.id,
            assigned_staff_id=staff_member.id
        )

        # 3. Assert
        assert updated.assigned_staff_id == staff_member.id

    async def test_update_inquiry_priority(self, db_session):
        """
        優先度更新テスト

        要件:
        - priority を更新
        """
        # 1. Setup
        app_admin = Staff(
            id=uuid4(),
            email="admin@example.com",
            hashed_password="hashed",
            full_name="管理者",
            role=StaffRole.app_admin,
            is_test_data=True
        )
        db_session.add(app_admin)
        await db_session.flush()

        test_office = Office(
            id=uuid4(),
            name="テスト事務所",
            type=OfficeType.type_A_office,
            created_by=app_admin.id,
            last_modified_by=app_admin.id,
            is_test_data=True
        )
        db_session.add(test_office)
        await db_session.flush()

        inquiry_data = {
            "sender_staff_id": None,
            "office_id": test_office.id,
            "title": "優先度更新テスト",
            "content": "内容",
            "sender_name": "ゲスト",
            "sender_email": "guest@example.com",
            "priority": InquiryPriority.normal,
            "admin_recipient_ids": [app_admin.id]
        }
        inquiry = await crud_inquiry.create_inquiry(db=db_session, **inquiry_data)
        await db_session.flush()

        # 2. Execute: 優先度更新
        updated = await crud_inquiry.update_inquiry(
            db=db_session,
            inquiry_id=inquiry.id,
            priority=InquiryPriority.high
        )

        # 3. Assert
        assert updated.priority == InquiryPriority.high

    async def test_update_inquiry_admin_notes(self, db_session):
        """
        管理者メモ更新テスト

        要件:
        - admin_notes を更新
        """
        # 1. Setup
        app_admin = Staff(
            id=uuid4(),
            email="admin@example.com",
            hashed_password="hashed",
            full_name="管理者",
            role=StaffRole.app_admin,
            is_test_data=True
        )
        db_session.add(app_admin)
        await db_session.flush()

        test_office = Office(
            id=uuid4(),
            name="テスト事務所",
            type=OfficeType.type_A_office,
            created_by=app_admin.id,
            last_modified_by=app_admin.id,
            is_test_data=True
        )
        db_session.add(test_office)
        await db_session.flush()

        inquiry_data = {
            "sender_staff_id": None,
            "office_id": test_office.id,
            "title": "メモ更新テスト",
            "content": "内容",
            "sender_name": "ゲスト",
            "sender_email": "guest@example.com",
            "priority": InquiryPriority.normal,
            "admin_recipient_ids": [app_admin.id]
        }
        inquiry = await crud_inquiry.create_inquiry(db=db_session, **inquiry_data)
        await db_session.flush()

        # 2. Execute: 管理者メモ更新
        updated = await crud_inquiry.update_inquiry(
            db=db_session,
            inquiry_id=inquiry.id,
            admin_notes="要対応: データ確認が必要"
        )

        # 3. Assert
        assert updated.admin_notes == "要対応: データ確認が必要"

    async def test_update_inquiry_multiple_fields(self, db_session):
        """
        複数フィールド同時更新テスト

        要件:
        - 複数のフィールドを一度に更新できる
        """
        # 1. Setup
        app_admin = Staff(
            id=uuid4(),
            email="admin@example.com",
            hashed_password="hashed",
            full_name="管理者",
            role=StaffRole.app_admin,
            is_test_data=True
        )
        db_session.add(app_admin)
        await db_session.flush()

        test_office = Office(
            id=uuid4(),
            name="テスト事務所",
            type=OfficeType.type_A_office,
            created_by=app_admin.id,
            last_modified_by=app_admin.id,
            is_test_data=True
        )
        db_session.add(test_office)

        staff_member = Staff(
            id=uuid4(),
            email="staff@example.com",
            hashed_password="hashed",
            full_name="スタッフ",
            role=StaffRole.manager,
            is_test_data=True
        )
        db_session.add(staff_member)
        await db_session.flush()

        inquiry_data = {
            "sender_staff_id": None,
            "office_id": test_office.id,
            "title": "複数更新テスト",
            "content": "内容",
            "sender_name": "ゲスト",
            "sender_email": "guest@example.com",
            "priority": InquiryPriority.normal,
            "admin_recipient_ids": [app_admin.id]
        }
        inquiry = await crud_inquiry.create_inquiry(db=db_session, **inquiry_data)
        await db_session.flush()

        # 2. Execute: 複数フィールド更新
        updated = await crud_inquiry.update_inquiry(
            db=db_session,
            inquiry_id=inquiry.id,
            status=InquiryStatus.in_progress,
            assigned_staff_id=staff_member.id,
            priority=InquiryPriority.high,
            admin_notes="至急対応"
        )

        # 3. Assert
        assert updated.status == InquiryStatus.in_progress
        assert updated.assigned_staff_id == staff_member.id
        assert updated.priority == InquiryPriority.high
        assert updated.admin_notes == "至急対応"


class TestCRUDInquiryDelete:
    """問い合わせ削除のテスト"""

    async def test_delete_inquiry(self, db_session):
        """
        論理削除テスト

        要件:
        - Message と InquiryDetail を削除
        - CASCADE により MessageRecipient も削除される
        """
        # 1. Setup
        app_admin = Staff(
            id=uuid4(),
            email="admin@example.com",
            hashed_password="hashed",
            full_name="管理者",
            role=StaffRole.app_admin,
            is_test_data=True
        )
        db_session.add(app_admin)
        await db_session.flush()

        test_office = Office(
            id=uuid4(),
            name="テスト事務所",
            type=OfficeType.type_A_office,
            created_by=app_admin.id,
            last_modified_by=app_admin.id,
            is_test_data=True
        )
        db_session.add(test_office)
        await db_session.flush()

        inquiry_data = {
            "sender_staff_id": None,
            "office_id": test_office.id,
            "title": "削除テスト",
            "content": "内容",
            "sender_name": "ゲスト",
            "sender_email": "guest@example.com",
            "priority": InquiryPriority.normal,
            "admin_recipient_ids": [app_admin.id]
        }
        inquiry = await crud_inquiry.create_inquiry(db=db_session, **inquiry_data)
        message_id = inquiry.message_id
        await db_session.flush()

        # 2. Execute: 削除
        result = await crud_inquiry.delete_inquiry(
            db=db_session,
            inquiry_id=inquiry.id
        )

        # 3. Assert
        assert result is True

        # 削除確認
        deleted_inquiry = await crud_inquiry.get_inquiry_by_id(
            db=db_session,
            inquiry_id=inquiry.id
        )
        assert deleted_inquiry is None

        # Message も削除されている（CASCADE）
        from sqlalchemy import select
        stmt = select(Message).where(Message.id == message_id)
        result = await db_session.execute(stmt)
        message = result.scalar_one_or_none()
        assert message is None
