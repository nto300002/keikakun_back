"""
メッセージスキーマのテスト

バリデーションルール、フィールド制約、レスポンススキーマの動作を検証
"""
import pytest
from pydantic import ValidationError
from datetime import datetime
import uuid

from app.schemas.message import (
    MessagePersonalCreate,
    MessageAnnouncementCreate,
    MessageResponse,
    MessageDetailResponse,
    MessageSenderInfo,
    MessageRecipientResponse,
    MessageInboxItem,
    MessageInboxResponse,
    MessageStatsResponse,
    UnreadCountResponse,
    MessageMarkAsReadRequest,
    MessageArchiveRequest,
    MessageBulkMarkAsReadRequest,
    MessageBulkOperationResponse
)
from app.models.enums import MessageType, MessagePriority


# ========================================
# MessagePersonalCreate のテスト
# ========================================

def test_message_personal_create_valid():
    """正常なデータでMessagePersonalCreateモデルが作成できることをテスト"""
    valid_data = {
        "title": "テストメッセージ",
        "content": "これはテストメッセージの本文です。",
        "priority": MessagePriority.normal,
        "recipient_staff_ids": [str(uuid.uuid4()), str(uuid.uuid4())]
    }
    message = MessagePersonalCreate(**valid_data)
    assert message.title == "テストメッセージ"
    assert message.content == "これはテストメッセージの本文です。"
    assert message.priority == MessagePriority.normal
    assert len(message.recipient_staff_ids) == 2


def test_message_personal_create_single_recipient():
    """1人の受信者でMessagePersonalCreateモデルが作成できることをテスト"""
    valid_data = {
        "title": "個別メッセージ",
        "content": "1人だけへの送信",
        "recipient_staff_ids": [str(uuid.uuid4())]
    }
    message = MessagePersonalCreate(**valid_data)
    assert len(message.recipient_staff_ids) == 1


def test_message_personal_create_default_priority():
    """優先度のデフォルト値がnormalであることをテスト"""
    valid_data = {
        "title": "デフォルト優先度",
        "content": "優先度未指定",
        "recipient_staff_ids": [str(uuid.uuid4())]
    }
    message = MessagePersonalCreate(**valid_data)
    assert message.priority == MessagePriority.normal


def test_message_personal_create_empty_title():
    """空のタイトルでValidationErrorが発生することをテスト"""
    invalid_data = {
        "title": "",
        "content": "本文",
        "recipient_staff_ids": [str(uuid.uuid4())]
    }
    with pytest.raises(ValidationError) as exc_info:
        MessagePersonalCreate(**invalid_data)
    errors = exc_info.value.errors()
    # min_length制約またはカスタムバリデータのエラーを確認
    assert any(error["loc"] == ("title",) for error in errors)


def test_message_personal_create_whitespace_only_title():
    """空白のみのタイトルでValidationErrorが発生することをテスト"""
    invalid_data = {
        "title": "   ",
        "content": "本文",
        "recipient_staff_ids": [str(uuid.uuid4())]
    }
    with pytest.raises(ValidationError) as exc_info:
        MessagePersonalCreate(**invalid_data)
    errors = exc_info.value.errors()
    assert any("タイトル" in str(error.get("ctx", {}).get("error", "")) for error in errors)


def test_message_personal_create_long_title():
    """200文字を超えるタイトルでValidationErrorが発生することをテスト"""
    invalid_data = {
        "title": "あ" * 201,
        "content": "本文",
        "recipient_staff_ids": [str(uuid.uuid4())]
    }
    with pytest.raises(ValidationError) as exc_info:
        MessagePersonalCreate(**invalid_data)
    errors = exc_info.value.errors()
    assert any(error["loc"] == ("title",) for error in errors)


def test_message_personal_create_empty_content():
    """空の本文でValidationErrorが発生することをテスト"""
    invalid_data = {
        "title": "タイトル",
        "content": "",
        "recipient_staff_ids": [str(uuid.uuid4())]
    }
    with pytest.raises(ValidationError) as exc_info:
        MessagePersonalCreate(**invalid_data)
    errors = exc_info.value.errors()
    # min_length制約またはカスタムバリデータのエラーを確認
    assert any(error["loc"] == ("content",) for error in errors)


def test_message_personal_create_long_content():
    """10000文字を超える本文でValidationErrorが発生することをテスト"""
    invalid_data = {
        "title": "タイトル",
        "content": "あ" * 10001,
        "recipient_staff_ids": [str(uuid.uuid4())]
    }
    with pytest.raises(ValidationError) as exc_info:
        MessagePersonalCreate(**invalid_data)
    errors = exc_info.value.errors()
    assert any("本文" in str(error.get("ctx", {}).get("error", "")) for error in errors)


def test_message_personal_create_no_recipients():
    """受信者なしでValidationErrorが発生することをテスト"""
    invalid_data = {
        "title": "タイトル",
        "content": "本文",
        "recipient_staff_ids": []
    }
    with pytest.raises(ValidationError) as exc_info:
        MessagePersonalCreate(**invalid_data)
    errors = exc_info.value.errors()
    assert any(error["loc"] == ("recipient_staff_ids",) for error in errors)


def test_message_personal_create_too_many_recipients():
    """100人を超える受信者でValidationErrorが発生することをテスト"""
    invalid_data = {
        "title": "タイトル",
        "content": "本文",
        "recipient_staff_ids": [str(uuid.uuid4()) for _ in range(101)]
    }
    with pytest.raises(ValidationError) as exc_info:
        MessagePersonalCreate(**invalid_data)
    errors = exc_info.value.errors()
    assert any("100人" in str(error.get("ctx", {}).get("error", "")) for error in errors)


def test_message_personal_create_duplicate_recipients():
    """重複した受信者でValidationErrorが発生することをテスト"""
    recipient_id = str(uuid.uuid4())
    invalid_data = {
        "title": "タイトル",
        "content": "本文",
        "recipient_staff_ids": [recipient_id, recipient_id]
    }
    with pytest.raises(ValidationError) as exc_info:
        MessagePersonalCreate(**invalid_data)
    errors = exc_info.value.errors()
    assert any("重複" in str(error.get("ctx", {}).get("error", "")) for error in errors)


# ========================================
# MessageAnnouncementCreate のテスト
# ========================================

def test_message_announcement_create_valid():
    """正常なデータでMessageAnnouncementCreateモデルが作成できることをテスト"""
    valid_data = {
        "title": "全体お知らせ",
        "content": "全スタッフへのお知らせです",
        "priority": MessagePriority.high
    }
    message = MessageAnnouncementCreate(**valid_data)
    assert message.title == "全体お知らせ"
    assert message.content == "全スタッフへのお知らせです"
    assert message.priority == MessagePriority.high


def test_message_announcement_create_urgent():
    """緊急度が高いお知らせが作成できることをテスト"""
    valid_data = {
        "title": "緊急お知らせ",
        "content": "緊急の連絡事項です",
        "priority": MessagePriority.urgent
    }
    message = MessageAnnouncementCreate(**valid_data)
    assert message.priority == MessagePriority.urgent


# ========================================
# MessageResponse のテスト
# ========================================

def test_message_response_valid():
    """正常なデータでMessageResponseモデルが作成できることをテスト"""
    response_data = {
        "id": str(uuid.uuid4()),
        "sender_staff_id": str(uuid.uuid4()),
        "office_id": str(uuid.uuid4()),
        "message_type": MessageType.personal,
        "priority": MessagePriority.normal,
        "title": "テストメッセージ",
        "content": "本文",
        "created_at": datetime.now(),
        "updated_at": datetime.now()
    }
    message = MessageResponse(**response_data)
    assert message.id == uuid.UUID(response_data["id"])
    assert message.message_type == MessageType.personal
    assert message.priority == MessagePriority.normal


def test_message_response_from_attributes():
    """from_attributes=Trueが設定されていることをテスト"""
    assert MessageResponse.model_config.get("from_attributes") is True


def test_message_response_nullable_sender():
    """送信者IDがNoneでも作成できることをテスト（削除されたスタッフの場合）"""
    response_data = {
        "id": str(uuid.uuid4()),
        "sender_staff_id": None,
        "office_id": str(uuid.uuid4()),
        "message_type": MessageType.system,
        "priority": MessagePriority.normal,
        "title": "システムメッセージ",
        "content": "自動送信",
        "created_at": datetime.now(),
        "updated_at": datetime.now()
    }
    message = MessageResponse(**response_data)
    assert message.sender_staff_id is None


# ========================================
# MessageSenderInfo のテスト
# ========================================

def test_message_sender_info_valid():
    """正常なデータでMessageSenderInfoモデルが作成できることをテスト"""
    sender_data = {
        "id": str(uuid.uuid4()),
        "first_name": "太郎",
        "last_name": "山田",
        "email": "yamada@example.com"
    }
    sender = MessageSenderInfo(**sender_data)
    assert sender.first_name == "太郎"
    assert sender.last_name == "山田"
    assert sender.full_name == "山田 太郎"


# ========================================
# MessageInboxItem のテスト
# ========================================

def test_message_inbox_item_valid():
    """正常なデータでMessageInboxItemモデルが作成できることをテスト"""
    sender_id = uuid.uuid4()
    inbox_data = {
        "message_id": str(uuid.uuid4()),
        "title": "受信メッセージ",
        "content": "受信箱のメッセージ",
        "message_type": MessageType.personal,
        "priority": MessagePriority.normal,
        "created_at": datetime.now(),
        "sender_staff_id": str(sender_id),
        "sender": {
            "id": str(sender_id),
            "first_name": "太郎",
            "last_name": "山田",
            "email": "yamada@example.com"
        },
        "recipient_id": str(uuid.uuid4()),
        "is_read": False,
        "read_at": None,
        "is_archived": False
    }
    inbox_item = MessageInboxItem(**inbox_data)
    assert inbox_item.is_read is False
    assert inbox_item.sender.full_name == "山田 太郎"


# ========================================
# MessageInboxResponse のテスト
# ========================================

def test_message_inbox_response_valid():
    """正常なデータでMessageInboxResponseモデルが作成できることをテスト"""
    inbox_data = {
        "messages": [],
        "total": 0,
        "unread_count": 0
    }
    inbox = MessageInboxResponse(**inbox_data)
    assert inbox.total == 0
    assert inbox.unread_count == 0
    assert len(inbox.messages) == 0


# ========================================
# MessageStatsResponse のテスト
# ========================================

def test_message_stats_response_valid():
    """正常なデータでMessageStatsResponseモデルが作成できることをテスト"""
    stats_data = {
        "message_id": str(uuid.uuid4()),
        "total_recipients": 10,
        "read_count": 7,
        "unread_count": 3,
        "read_rate": 0.7
    }
    stats = MessageStatsResponse(**stats_data)
    assert stats.total_recipients == 10
    assert stats.read_count == 7
    assert stats.unread_count == 3
    assert stats.read_rate == 0.7


def test_message_stats_response_zero_recipients():
    """受信者0人の統計が作成できることをテスト"""
    stats_data = {
        "message_id": str(uuid.uuid4()),
        "total_recipients": 0,
        "read_count": 0,
        "unread_count": 0,
        "read_rate": 0.0
    }
    stats = MessageStatsResponse(**stats_data)
    assert stats.read_rate == 0.0


# ========================================
# UnreadCountResponse のテスト
# ========================================

def test_unread_count_response_valid():
    """正常なデータでUnreadCountResponseモデルが作成できることをテスト"""
    unread_data = {
        "unread_count": 5
    }
    unread = UnreadCountResponse(**unread_data)
    assert unread.unread_count == 5


# ========================================
# MessageBulkMarkAsReadRequest のテスト
# ========================================

def test_message_bulk_mark_as_read_request_valid():
    """正常なデータでMessageBulkMarkAsReadRequestモデルが作成できることをテスト"""
    valid_data = {
        "message_ids": [str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())]
    }
    request = MessageBulkMarkAsReadRequest(**valid_data)
    assert len(request.message_ids) == 3


def test_message_bulk_mark_as_read_request_empty():
    """空のメッセージIDリストでValidationErrorが発生することをテスト"""
    invalid_data = {
        "message_ids": []
    }
    with pytest.raises(ValidationError) as exc_info:
        MessageBulkMarkAsReadRequest(**invalid_data)
    errors = exc_info.value.errors()
    assert any(error["loc"] == ("message_ids",) for error in errors)


def test_message_bulk_mark_as_read_request_too_many():
    """100件を超えるメッセージIDでValidationErrorが発生することをテスト"""
    invalid_data = {
        "message_ids": [str(uuid.uuid4()) for _ in range(101)]
    }
    with pytest.raises(ValidationError) as exc_info:
        MessageBulkMarkAsReadRequest(**invalid_data)
    errors = exc_info.value.errors()
    # max_length制約またはカスタムバリデータのエラーを確認
    assert any(error["loc"] == ("message_ids",) for error in errors)


def test_message_bulk_mark_as_read_request_duplicates():
    """重複したメッセージIDでValidationErrorが発生することをテスト"""
    message_id = str(uuid.uuid4())
    invalid_data = {
        "message_ids": [message_id, message_id]
    }
    with pytest.raises(ValidationError) as exc_info:
        MessageBulkMarkAsReadRequest(**invalid_data)
    errors = exc_info.value.errors()
    assert any("重複" in str(error.get("ctx", {}).get("error", "")) for error in errors)


# ========================================
# MessageBulkOperationResponse のテスト
# ========================================

def test_message_bulk_operation_response_valid():
    """正常なデータでMessageBulkOperationResponseモデルが作成できることをテスト"""
    response_data = {
        "success_count": 8,
        "failed_count": 2,
        "total_count": 10
    }
    response = MessageBulkOperationResponse(**response_data)
    assert response.success_count == 8
    assert response.failed_count == 2
    assert response.total_count == 10


# ========================================
# MessageArchiveRequest のテスト
# ========================================

def test_message_archive_request_valid():
    """正常なデータでMessageArchiveRequestモデルが作成できることをテスト"""
    valid_data = {
        "is_archived": True
    }
    request = MessageArchiveRequest(**valid_data)
    assert request.is_archived is True


def test_message_archive_request_unarchive():
    """アーカイブ解除のリクエストが作成できることをテスト"""
    valid_data = {
        "is_archived": False
    }
    request = MessageArchiveRequest(**valid_data)
    assert request.is_archived is False
