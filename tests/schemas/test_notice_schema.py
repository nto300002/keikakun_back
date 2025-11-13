import pytest
from pydantic import ValidationError
from datetime import datetime
import uuid

from app.schemas.notice import NoticeCreate, NoticeUpdate, NoticeResponse


def test_notice_create_valid():
    """正常なデータでNoticeCreateモデルが作成できることをテスト"""
    valid_data = {
        "recipient_staff_id": str(uuid.uuid4()),
        "office_id": str(uuid.uuid4()),
        "type": "plan_deadline",
        "title": "計画書の期限が近づいています",
        "content": "山田太郎さんの個別支援計画書の期限が7日後です。",
        "link_url": "/plans/123",
    }
    notice = NoticeCreate(**valid_data)
    assert notice.type == "plan_deadline"
    assert notice.title == "計画書の期限が近づいています"
    assert notice.content == "山田太郎さんの個別支援計画書の期限が7日後です。"
    assert notice.link_url == "/plans/123"


def test_notice_create_minimal_valid():
    """最小限の必須フィールドでNoticeCreateモデルが作成できることをテスト"""
    minimal_data = {
        "recipient_staff_id": str(uuid.uuid4()),
        "office_id": str(uuid.uuid4()),
        "type": "system",
        "title": "システム通知",
    }
    notice = NoticeCreate(**minimal_data)
    assert notice.type == "system"
    assert notice.title == "システム通知"
    assert notice.content is None
    assert notice.link_url is None


def test_notice_create_missing_required_field():
    """必須フィールドが不足している場合にValidationErrorが発生することをテスト"""
    invalid_data = {
        "recipient_staff_id": str(uuid.uuid4()),
        "office_id": str(uuid.uuid4()),
        "type": "test",
        # titleが欠落
    }
    with pytest.raises(ValidationError) as exc_info:
        NoticeCreate(**invalid_data)
    errors = exc_info.value.errors()
    assert any(error["loc"] == ("title",) for error in errors)


def test_notice_create_empty_title():
    """空のタイトルでValidationErrorが発生することをテスト"""
    invalid_data = {
        "recipient_staff_id": str(uuid.uuid4()),
        "office_id": str(uuid.uuid4()),
        "type": "test",
        "title": "",  # 空文字列
    }
    with pytest.raises(ValidationError) as exc_info:
        NoticeCreate(**invalid_data)
    errors = exc_info.value.errors()
    assert any(error["loc"] == ("title",) for error in errors)


def test_notice_create_long_title():
    """255文字を超えるタイトルでValidationErrorが発生することをテスト"""
    invalid_data = {
        "recipient_staff_id": str(uuid.uuid4()),
        "office_id": str(uuid.uuid4()),
        "type": "test",
        "title": "a" * 256,  # 256文字
    }
    with pytest.raises(ValidationError) as exc_info:
        NoticeCreate(**invalid_data)
    errors = exc_info.value.errors()
    assert any(error["loc"] == ("title",) for error in errors)


def test_notice_update_valid():
    """正常なデータでNoticeUpdateモデルが作成できることをテスト"""
    update_data = {
        "is_read": True,
    }
    notice_update = NoticeUpdate(**update_data)
    assert notice_update.is_read is True


def test_notice_update_partial():
    """部分的な更新データでNoticeUpdateモデルが作成できることをテスト"""
    update_data = {
        "title": "更新されたタイトル",
    }
    notice_update = NoticeUpdate(**update_data)
    assert notice_update.title == "更新されたタイトル"
    assert notice_update.is_read is None


def test_notice_update_all_fields():
    """全フィールドを更新するNoticeUpdateモデルが作成できることをテスト"""
    update_data = {
        "type": "updated_type",
        "title": "更新されたタイトル",
        "content": "更新されたコンテンツ",
        "link_url": "/updated/link",
        "is_read": True,
    }
    notice_update = NoticeUpdate(**update_data)
    assert notice_update.type == "updated_type"
    assert notice_update.title == "更新されたタイトル"
    assert notice_update.content == "更新されたコンテンツ"
    assert notice_update.link_url == "/updated/link"
    assert notice_update.is_read is True


def test_notice_response_valid():
    """正常なデータでNoticeResponseモデルが作成できることをテスト"""
    response_data = {
        "id": str(uuid.uuid4()),
        "recipient_staff_id": str(uuid.uuid4()),
        "office_id": str(uuid.uuid4()),
        "type": "plan_deadline",
        "title": "通知タイトル",
        "content": "通知内容",
        "link_url": "/link",
        "is_read": False,
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
    }
    notice_response = NoticeResponse(**response_data)
    assert notice_response.id == uuid.UUID(response_data["id"])
    assert notice_response.notice_type == "plan_deadline"
    assert notice_response.notice_title == "通知タイトル"
    assert notice_response.is_read is False


def test_notice_response_from_attributes():
    """from_attributes=Trueが設定されていることをテスト"""
    # ConfigDictでfrom_attributes=Trueが設定されているかを確認
    assert NoticeResponse.model_config.get("from_attributes") is True
