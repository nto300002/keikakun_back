"""
Message CRUD のテスト
TDD方式でテストを先に作成
"""
from sqlalchemy.ext.asyncio import AsyncSession
import pytest
from datetime import datetime
from uuid import UUID

from app import crud
from app.models.enums import MessageType, MessagePriority

pytestmark = pytest.mark.asyncio


async def test_create_personal_message(
    db_session: AsyncSession,
    employee_user_factory
) -> None:
    """
    個別メッセージ作成テスト
    """
    sender = await employee_user_factory()
    recipient = await employee_user_factory(
        office=sender.office_associations[0].office if sender.office_associations else None
    )
    office = sender.office_associations[0].office if sender.office_associations else None

    # 個別メッセージデータ
    message_data = {
        "sender_staff_id": sender.id,
        "office_id": office.id,
        "recipient_ids": [recipient.id],
        "message_type": MessageType.personal,
        "priority": MessagePriority.normal,
        "title": "テストメッセージ",
        "content": "これは個別メッセージのテストです。"
    }

    # メッセージを作成
    created_message = await crud.message.create_personal_message(
        db=db_session,
        obj_in=message_data
    )

    assert created_message.id is not None
    assert created_message.sender_staff_id == sender.id
    assert created_message.office_id == office.id
    assert created_message.message_type == MessageType.personal
    assert created_message.title == "テストメッセージ"
    assert len(created_message.recipients) == 1
    assert created_message.recipients[0].recipient_staff_id == recipient.id
    assert created_message.recipients[0].is_read is False


async def test_create_announcement(
    db_session: AsyncSession,
    owner_user_factory,
    employee_user_factory
) -> None:
    """
    一斉通知作成テスト（バルクインサート）
    """
    owner = await owner_user_factory()
    office = owner.office_associations[0].office if owner.office_associations else None

    # 受信者を複数作成
    recipients = []
    for _ in range(10):
        recipient = await employee_user_factory(office=office)
        recipients.append(recipient)

    # 一斉通知データ
    announcement_data = {
        "sender_staff_id": owner.id,
        "office_id": office.id,
        "recipient_ids": [r.id for r in recipients],
        "message_type": MessageType.announcement,
        "priority": MessagePriority.high,
        "title": "重要なお知らせ",
        "content": "全スタッフへの一斉通知です。"
    }

    # 一斉通知を作成
    created_message = await crud.message.create_announcement(
        db=db_session,
        obj_in=announcement_data
    )

    assert created_message.id is not None
    assert created_message.sender_staff_id == owner.id
    assert created_message.message_type == MessageType.announcement
    assert created_message.priority == MessagePriority.high
    assert len(created_message.recipients) == 10
    assert all(not r.is_read for r in created_message.recipients)


async def test_create_announcement_with_large_recipients(
    db_session: AsyncSession,
    owner_user_factory,
    employee_user_factory
) -> None:
    """
    大量受信者への一斉通知テスト（バルクインサート、チャンク処理）
    """
    owner = await owner_user_factory()
    office = owner.office_associations[0].office if owner.office_associations else None

    # 100人の受信者を作成
    recipients = []
    for _ in range(100):
        recipient = await employee_user_factory(office=office)
        recipients.append(recipient)

    announcement_data = {
        "sender_staff_id": owner.id,
        "office_id": office.id,
        "recipient_ids": [r.id for r in recipients],
        "message_type": MessageType.announcement,
        "priority": MessagePriority.urgent,
        "title": "緊急のお知らせ",
        "content": "100人への一斉通知テスト"
    }

    created_message = await crud.message.create_announcement(
        db=db_session,
        obj_in=announcement_data
    )

    assert created_message.id is not None
    assert len(created_message.recipients) == 100


async def test_get_inbox_messages(
    db_session: AsyncSession,
    employee_user_factory
) -> None:
    """
    受信箱取得テスト
    """
    sender = await employee_user_factory()
    recipient = await employee_user_factory(
        office=sender.office_associations[0].office if sender.office_associations else None
    )
    office = sender.office_associations[0].office if sender.office_associations else None

    # 複数のメッセージを作成
    for i in range(3):
        message_data = {
            "sender_staff_id": sender.id,
            "office_id": office.id,
            "recipient_ids": [recipient.id],
            "message_type": MessageType.personal,
            "priority": MessagePriority.normal,
            "title": f"メッセージ{i}",
            "content": f"内容{i}"
        }
        await crud.message.create_personal_message(db=db_session, obj_in=message_data)

    # 受信箱を取得
    inbox_messages = await crud.message.get_inbox_messages(
        db=db_session,
        recipient_staff_id=recipient.id
    )

    assert len(inbox_messages) == 3
    assert all(
        any(r.recipient_staff_id == recipient.id for r in msg.recipients)
        for msg in inbox_messages
    )


async def test_get_unread_messages(
    db_session: AsyncSession,
    employee_user_factory
) -> None:
    """
    未読メッセージのみ取得テスト
    """
    sender = await employee_user_factory()
    recipient = await employee_user_factory(
        office=sender.office_associations[0].office if sender.office_associations else None
    )
    office = sender.office_associations[0].office if sender.office_associations else None

    # 未読メッセージを作成
    unread_data = {
        "sender_staff_id": sender.id,
        "office_id": office.id,
        "recipient_ids": [recipient.id],
        "message_type": MessageType.personal,
        "priority": MessagePriority.normal,
        "title": "未読メッセージ",
        "content": "未読の内容"
    }
    await crud.message.create_personal_message(db=db_session, obj_in=unread_data)

    # 既読メッセージを作成
    read_message_data = {
        "sender_staff_id": sender.id,
        "office_id": office.id,
        "recipient_ids": [recipient.id],
        "message_type": MessageType.personal,
        "priority": MessagePriority.normal,
        "title": "既読メッセージ",
        "content": "既読の内容"
    }
    read_message = await crud.message.create_personal_message(db=db_session, obj_in=read_message_data)

    # 既読にする
    await crud.message.mark_as_read(
        db=db_session,
        message_id=read_message.id,
        recipient_staff_id=recipient.id
    )

    # 未読メッセージのみ取得
    unread_messages = await crud.message.get_unread_messages(
        db=db_session,
        recipient_staff_id=recipient.id
    )

    assert len(unread_messages) >= 1
    assert all(
        not any(r.is_read for r in msg.recipients if r.recipient_staff_id == recipient.id)
        for msg in unread_messages
    )


async def test_mark_as_read(
    db_session: AsyncSession,
    employee_user_factory
) -> None:
    """
    メッセージを既読にするテスト
    """
    sender = await employee_user_factory()
    recipient = await employee_user_factory(
        office=sender.office_associations[0].office if sender.office_associations else None
    )
    office = sender.office_associations[0].office if sender.office_associations else None

    message_data = {
        "sender_staff_id": sender.id,
        "office_id": office.id,
        "recipient_ids": [recipient.id],
        "message_type": MessageType.personal,
        "priority": MessagePriority.normal,
        "title": "既読テスト",
        "content": "既読にするテスト"
    }

    created_message = await crud.message.create_personal_message(db=db_session, obj_in=message_data)

    # 既読前の確認
    assert created_message.recipients[0].is_read is False
    assert created_message.recipients[0].read_at is None

    # 既読にする
    updated_recipient = await crud.message.mark_as_read(
        db=db_session,
        message_id=created_message.id,
        recipient_staff_id=recipient.id
    )

    assert updated_recipient.is_read is True
    assert updated_recipient.read_at is not None
    assert isinstance(updated_recipient.read_at, datetime)


async def test_get_message_stats(
    db_session: AsyncSession,
    employee_user_factory
) -> None:
    """
    メッセージ統計取得テスト
    """
    sender = await employee_user_factory()
    office = sender.office_associations[0].office if sender.office_associations else None

    # 受信者を5人作成
    recipients = []
    for _ in range(5):
        recipient = await employee_user_factory(office=office)
        recipients.append(recipient)

    message_data = {
        "sender_staff_id": sender.id,
        "office_id": office.id,
        "recipient_ids": [r.id for r in recipients],
        "message_type": MessageType.personal,
        "priority": MessagePriority.normal,
        "title": "統計テスト",
        "content": "統計取得のテスト"
    }

    created_message = await crud.message.create_personal_message(db=db_session, obj_in=message_data)

    # 2人を既読にする
    for i in range(2):
        await crud.message.mark_as_read(
            db=db_session,
            message_id=created_message.id,
            recipient_staff_id=recipients[i].id
        )

    # 統計を取得
    stats = await crud.message.get_message_stats(
        db=db_session,
        message_id=created_message.id
    )

    assert stats["total_recipients"] == 5
    assert stats["read_count"] == 2
    assert stats["unread_count"] == 3
    assert stats["read_rate"] == 40.0  # 2/5 * 100


async def test_get_unread_count(
    db_session: AsyncSession,
    employee_user_factory
) -> None:
    """
    未読件数取得テスト
    """
    sender = await employee_user_factory()
    recipient = await employee_user_factory(
        office=sender.office_associations[0].office if sender.office_associations else None
    )
    office = sender.office_associations[0].office if sender.office_associations else None

    # 3つのメッセージを作成
    for i in range(3):
        message_data = {
            "sender_staff_id": sender.id,
            "office_id": office.id,
            "recipient_ids": [recipient.id],
            "message_type": MessageType.personal,
            "priority": MessagePriority.normal,
            "title": f"未読カウント{i}",
            "content": f"内容{i}"
        }
        await crud.message.create_personal_message(db=db_session, obj_in=message_data)

    # 未読件数を取得
    unread_count = await crud.message.get_unread_count(
        db=db_session,
        recipient_staff_id=recipient.id
    )

    assert unread_count == 3


async def test_duplicate_recipient_prevention(
    db_session: AsyncSession,
    employee_user_factory
) -> None:
    """
    同一メッセージ・同一受信者の重複防止テスト
    """
    sender = await employee_user_factory()
    recipient = await employee_user_factory(
        office=sender.office_associations[0].office if sender.office_associations else None
    )
    office = sender.office_associations[0].office if sender.office_associations else None

    message_data = {
        "sender_staff_id": sender.id,
        "office_id": office.id,
        "recipient_ids": [recipient.id, recipient.id],  # 重複
        "message_type": MessageType.personal,
        "priority": MessagePriority.normal,
        "title": "重複テスト",
        "content": "重複した受信者"
    }

    created_message = await crud.message.create_personal_message(db=db_session, obj_in=message_data)

    # 重複が除外され、1件のみ作成されることを確認
    assert len(created_message.recipients) == 1


async def test_get_inbox_with_filters(
    db_session: AsyncSession,
    employee_user_factory
) -> None:
    """
    受信箱のフィルタリングテスト（未読のみ、メッセージタイプ）
    """
    sender = await employee_user_factory()
    recipient = await employee_user_factory(
        office=sender.office_associations[0].office if sender.office_associations else None
    )
    office = sender.office_associations[0].office if sender.office_associations else None

    # personalメッセージを作成
    personal_data = {
        "sender_staff_id": sender.id,
        "office_id": office.id,
        "recipient_ids": [recipient.id],
        "message_type": MessageType.personal,
        "priority": MessagePriority.normal,
        "title": "個別メッセージ",
        "content": "個別の内容"
    }
    await crud.message.create_personal_message(db=db_session, obj_in=personal_data)

    # systemメッセージを作成
    system_data = {
        "sender_staff_id": sender.id,
        "office_id": office.id,
        "recipient_ids": [recipient.id],
        "message_type": MessageType.system,
        "priority": MessagePriority.normal,
        "title": "システムメッセージ",
        "content": "システムの内容"
    }
    await crud.message.create_personal_message(db=db_session, obj_in=system_data)

    # タイプでフィルタリング
    personal_messages = await crud.message.get_inbox_messages(
        db=db_session,
        recipient_staff_id=recipient.id,
        message_type=MessageType.personal
    )

    assert len(personal_messages) >= 1
    assert all(msg.message_type == MessageType.personal for msg in personal_messages)


async def test_transaction_rollback_on_error(
    db_session: AsyncSession,
    employee_user_factory
) -> None:
    """
    エラー発生時のトランザクションロールバックテスト
    """
    sender = await employee_user_factory()
    office = sender.office_associations[0].office if sender.office_associations else None

    # 無効な受信者IDでメッセージを作成しようとする
    from uuid import uuid4
    invalid_message_data = {
        "sender_staff_id": sender.id,
        "office_id": office.id,
        "recipient_ids": [uuid4()],  # 存在しないID
        "message_type": MessageType.personal,
        "priority": MessagePriority.normal,
        "title": "エラーテスト",
        "content": "ロールバックテスト"
    }

    # エラーが発生することを確認
    with pytest.raises(Exception):
        await crud.message.create_personal_message(
            db=db_session,
            obj_in=invalid_message_data
        )

    # ロールバックを実行
    await db_session.rollback()

    # ロールバック後、メッセージが作成されていないことを確認
    messages = await crud.message.get_inbox_messages(
        db=db_session,
        recipient_staff_id=sender.id
    )

    # エラーメッセージは作成されていないはず
    error_messages = [msg for msg in messages if msg.title == "エラーテスト"]
    assert len(error_messages) == 0
