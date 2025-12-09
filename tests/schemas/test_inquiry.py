"""
問い合わせスキーマのテスト

InquiryCreate, InquiryUpdate, InquiryReply, InquiryQueryParams 等の
バリデーションとエッジケースをテスト
"""
import pytest
from pydantic import ValidationError
from app.schemas.inquiry import (
    InquiryCreate,
    InquiryUpdate,
    InquiryReply,
    InquiryQueryParams,
    InquiryCreateResponse,
    InquiryUpdateResponse,
    InquiryDeleteResponse,
)
from app.models.enums import InquiryStatus, InquiryPriority


class TestInquiryCreate:
    """InquiryCreate スキーマのテスト"""

    def test_valid_inquiry_create_with_all_fields(self):
        """すべてのフィールドを含む正常な作成リクエスト"""
        data = {
            "title": "質問があります",
            "content": "サービスについて教えてください。",
            "category": "質問",
            "sender_name": "山田太郎",
            "sender_email": "test@example.com"
        }
        inquiry = InquiryCreate(**data)

        assert inquiry.title == "質問があります"
        assert inquiry.content == "サービスについて教えてください。"
        assert inquiry.category == "質問"
        assert inquiry.sender_name == "山田太郎"
        assert inquiry.sender_email == "test@example.com"

    def test_valid_inquiry_create_minimal_fields(self):
        """必須フィールドのみの正常な作成リクエスト"""
        data = {
            "title": "件名",
            "content": "内容"
        }
        inquiry = InquiryCreate(**data)

        assert inquiry.title == "件名"
        assert inquiry.content == "内容"
        assert inquiry.category is None
        assert inquiry.sender_name is None
        assert inquiry.sender_email is None

    def test_title_too_long(self):
        """件名が長すぎる場合"""
        data = {
            "title": "A" * 201,
            "content": "内容"
        }
        with pytest.raises(ValidationError) as exc_info:
            InquiryCreate(**data)

        errors = exc_info.value.errors()
        # Pydantic max_length constraint が先に実行される
        assert any(e.get("type") == "string_too_long" and e.get("loc") == ("title",) for e in errors)

    def test_title_empty_string(self):
        """件名が空文字の場合"""
        data = {
            "title": "   ",
            "content": "内容"
        }
        with pytest.raises(ValidationError) as exc_info:
            InquiryCreate(**data)

        errors = exc_info.value.errors()
        assert any("件名は空にできません" in str(e.get("msg", "")) for e in errors)

    def test_content_too_long(self):
        """内容が長すぎる場合"""
        data = {
            "title": "件名",
            "content": "A" * 20001
        }
        with pytest.raises(ValidationError) as exc_info:
            InquiryCreate(**data)

        errors = exc_info.value.errors()
        # Pydantic max_length constraint が先に実行される
        assert any(e.get("type") == "string_too_long" and e.get("loc") == ("content",) for e in errors)

    def test_content_empty_string(self):
        """内容が空文字の場合"""
        data = {
            "title": "件名",
            "content": "   "
        }
        with pytest.raises(ValidationError) as exc_info:
            InquiryCreate(**data)

        errors = exc_info.value.errors()
        assert any("内容は空にできません" in str(e.get("msg", "")) for e in errors)

    def test_invalid_category(self):
        """不正なカテゴリの場合"""
        data = {
            "title": "件名",
            "content": "内容",
            "category": "無効なカテゴリ"
        }
        with pytest.raises(ValidationError) as exc_info:
            InquiryCreate(**data)

        errors = exc_info.value.errors()
        assert any("不具合, 質問, その他" in str(e.get("msg", "")) for e in errors)

    def test_valid_categories(self):
        """正常なカテゴリの検証"""
        valid_categories = ["不具合", "質問", "その他"]

        for category in valid_categories:
            data = {
                "title": "件名",
                "content": "内容",
                "category": category
            }
            inquiry = InquiryCreate(**data)
            assert inquiry.category == category

    def test_sender_name_too_long(self):
        """送信者名が長すぎる場合"""
        data = {
            "title": "件名",
            "content": "内容",
            "sender_name": "A" * 101
        }
        with pytest.raises(ValidationError) as exc_info:
            InquiryCreate(**data)

        errors = exc_info.value.errors()
        # Pydantic max_length constraint が先に実行される
        assert any(e.get("type") == "string_too_long" and e.get("loc") == ("sender_name",) for e in errors)

    def test_sender_name_whitespace_only(self):
        """送信者名が空白のみの場合（None に変換される）"""
        data = {
            "title": "件名",
            "content": "内容",
            "sender_name": "   "
        }
        inquiry = InquiryCreate(**data)
        assert inquiry.sender_name is None

    def test_invalid_email(self):
        """不正なメールアドレスの場合"""
        data = {
            "title": "件名",
            "content": "内容",
            "sender_email": "invalid-email"
        }
        with pytest.raises(ValidationError):
            InquiryCreate(**data)

    def test_valid_email(self):
        """正常なメールアドレス"""
        data = {
            "title": "件名",
            "content": "内容",
            "sender_email": "test@example.com"
        }
        inquiry = InquiryCreate(**data)
        assert inquiry.sender_email == "test@example.com"

    def test_title_and_content_stripped(self):
        """件名と内容の前後の空白が削除される"""
        data = {
            "title": "  件名  ",
            "content": "  内容  "
        }
        inquiry = InquiryCreate(**data)
        assert inquiry.title == "件名"
        assert inquiry.content == "内容"


class TestInquiryUpdate:
    """InquiryUpdate スキーマのテスト"""

    def test_valid_update_all_fields(self):
        """すべてのフィールドを含む更新リクエスト"""
        data = {
            "status": InquiryStatus.open,
            "assigned_staff_id": "12345678-1234-5678-1234-567812345678",
            "priority": InquiryPriority.high,
            "admin_notes": "対応中です"
        }
        update = InquiryUpdate(**data)

        assert update.status == InquiryStatus.open
        assert str(update.assigned_staff_id) == "12345678-1234-5678-1234-567812345678"
        assert update.priority == InquiryPriority.high
        assert update.admin_notes == "対応中です"

    def test_valid_update_partial_fields(self):
        """一部のフィールドのみの更新リクエスト"""
        data = {
            "status": InquiryStatus.in_progress
        }
        update = InquiryUpdate(**data)

        assert update.status == InquiryStatus.in_progress
        assert update.assigned_staff_id is None
        assert update.priority is None
        assert update.admin_notes is None

    def test_admin_notes_too_long(self):
        """管理者メモが長すぎる場合"""
        data = {
            "admin_notes": "A" * 5001
        }
        with pytest.raises(ValidationError) as exc_info:
            InquiryUpdate(**data)

        errors = exc_info.value.errors()
        assert any("管理者メモは5,000文字以内" in str(e.get("msg", "")) for e in errors)

    def test_admin_notes_whitespace_only(self):
        """管理者メモが空白のみの場合（None に変換される）"""
        data = {
            "admin_notes": "   "
        }
        update = InquiryUpdate(**data)
        assert update.admin_notes is None

    def test_valid_status_values(self):
        """正常なステータス値の検証"""
        statuses = [
            InquiryStatus.new,
            InquiryStatus.open,
            InquiryStatus.in_progress,
            InquiryStatus.answered,
            InquiryStatus.closed,
            InquiryStatus.spam
        ]

        for status in statuses:
            data = {"status": status}
            update = InquiryUpdate(**data)
            assert update.status == status

    def test_valid_priority_values(self):
        """正常な優先度値の検証"""
        priorities = [
            InquiryPriority.low,
            InquiryPriority.normal,
            InquiryPriority.high
        ]

        for priority in priorities:
            data = {"priority": priority}
            update = InquiryUpdate(**data)
            assert update.priority == priority


class TestInquiryReply:
    """InquiryReply スキーマのテスト"""

    def test_valid_reply(self):
        """正常な返信リクエスト"""
        data = {
            "body": "お問い合わせありがとうございます。",
            "send_email": True
        }
        reply = InquiryReply(**data)

        assert reply.body == "お問い合わせありがとうございます。"
        assert reply.send_email is True

    def test_reply_without_email_flag(self):
        """メール送信フラグなしの返信（デフォルトFalse）"""
        data = {
            "body": "返信内容"
        }
        reply = InquiryReply(**data)

        assert reply.body == "返信内容"
        assert reply.send_email is False

    def test_reply_body_too_long(self):
        """返信内容が長すぎる場合"""
        data = {
            "body": "A" * 20001
        }
        with pytest.raises(ValidationError) as exc_info:
            InquiryReply(**data)

        errors = exc_info.value.errors()
        # Pydantic max_length constraint が先に実行される
        assert any(e.get("type") == "string_too_long" and e.get("loc") == ("body",) for e in errors)

    def test_reply_body_empty(self):
        """返信内容が空の場合"""
        data = {
            "body": "   "
        }
        with pytest.raises(ValidationError) as exc_info:
            InquiryReply(**data)

        errors = exc_info.value.errors()
        assert any("返信内容は空にできません" in str(e.get("msg", "")) for e in errors)

    def test_reply_body_stripped(self):
        """返信内容の前後の空白が削除される"""
        data = {
            "body": "  返信内容  "
        }
        reply = InquiryReply(**data)
        assert reply.body == "返信内容"


class TestInquiryQueryParams:
    """InquiryQueryParams スキーマのテスト"""

    def test_valid_query_all_params(self):
        """すべてのパラメータを含むクエリ"""
        data = {
            "status": InquiryStatus.new,
            "assigned": "12345678-1234-5678-1234-567812345678",
            "priority": InquiryPriority.high,
            "search": "キーワード",
            "skip": 10,
            "limit": 50,
            "sort": "updated_at"
        }
        query = InquiryQueryParams(**data)

        assert query.status == InquiryStatus.new
        assert str(query.assigned) == "12345678-1234-5678-1234-567812345678"
        assert query.priority == InquiryPriority.high
        assert query.search == "キーワード"
        assert query.skip == 10
        assert query.limit == 50
        assert query.sort == "updated_at"

    def test_valid_query_default_params(self):
        """デフォルト値のクエリ"""
        query = InquiryQueryParams()

        assert query.status is None
        assert query.assigned is None
        assert query.priority is None
        assert query.search is None
        assert query.skip == 0
        assert query.limit == 20
        assert query.sort == "created_at"

    def test_skip_negative(self):
        """skip が負の数の場合"""
        data = {
            "skip": -1
        }
        with pytest.raises(ValidationError):
            InquiryQueryParams(**data)

    def test_limit_zero(self):
        """limit が 0 の場合"""
        data = {
            "limit": 0
        }
        with pytest.raises(ValidationError):
            InquiryQueryParams(**data)

    def test_limit_exceeds_max(self):
        """limit が最大値を超える場合"""
        data = {
            "limit": 101
        }
        with pytest.raises(ValidationError):
            InquiryQueryParams(**data)

    def test_limit_at_max(self):
        """limit が最大値（100）の場合"""
        data = {
            "limit": 100
        }
        query = InquiryQueryParams(**data)
        assert query.limit == 100

    def test_invalid_sort_key(self):
        """不正なソートキーの場合"""
        data = {
            "sort": "invalid_sort"
        }
        with pytest.raises(ValidationError) as exc_info:
            InquiryQueryParams(**data)

        errors = exc_info.value.errors()
        assert any("created_at, updated_at, priority" in str(e.get("msg", "")) for e in errors)

    def test_valid_sort_keys(self):
        """正常なソートキーの検証"""
        valid_sorts = ["created_at", "updated_at", "priority"]

        for sort_key in valid_sorts:
            data = {"sort": sort_key}
            query = InquiryQueryParams(**data)
            assert query.sort == sort_key

    def test_search_too_long(self):
        """検索キーワードが長すぎる場合"""
        data = {
            "search": "A" * 201
        }
        with pytest.raises(ValidationError) as exc_info:
            InquiryQueryParams(**data)

        errors = exc_info.value.errors()
        # Pydantic max_length constraint が先に実行される
        assert any(e.get("type") == "string_too_long" and e.get("loc") == ("search",) for e in errors)

    def test_search_whitespace_only(self):
        """検索キーワードが空白のみの場合（None に変換される）"""
        data = {
            "search": "   "
        }
        query = InquiryQueryParams(**data)
        assert query.search is None

    def test_search_stripped(self):
        """検索キーワードの前後の空白が削除される"""
        data = {
            "search": "  キーワード  "
        }
        query = InquiryQueryParams(**data)
        assert query.search == "キーワード"


class TestResponseSchemas:
    """レスポンススキーマのテスト"""

    def test_inquiry_create_response(self):
        """問い合わせ作成レスポンス"""
        data = {
            "id": "12345678-1234-5678-1234-567812345678",
            "message": "問い合わせを受け付けました"
        }
        response = InquiryCreateResponse(**data)

        assert str(response.id) == "12345678-1234-5678-1234-567812345678"
        assert response.message == "問い合わせを受け付けました"

    def test_inquiry_create_response_default_message(self):
        """問い合わせ作成レスポンス（デフォルトメッセージ）"""
        data = {
            "id": "12345678-1234-5678-1234-567812345678"
        }
        response = InquiryCreateResponse(**data)

        assert response.message == "問い合わせを受け付けました"

    def test_inquiry_update_response(self):
        """問い合わせ更新レスポンス"""
        data = {
            "id": "12345678-1234-5678-1234-567812345678",
            "message": "更新しました"
        }
        response = InquiryUpdateResponse(**data)

        assert str(response.id) == "12345678-1234-5678-1234-567812345678"
        assert response.message == "更新しました"

    def test_inquiry_delete_response(self):
        """問い合わせ削除レスポンス"""
        data = {
            "message": "削除しました"
        }
        response = InquiryDeleteResponse(**data)

        assert response.message == "削除しました"

    def test_inquiry_delete_response_default_message(self):
        """問い合わせ削除レスポンス（デフォルトメッセージ）"""
        response = InquiryDeleteResponse()

        assert response.message == "削除しました"


class TestEdgeCases:
    """エッジケースのテスト"""

    def test_title_exactly_200_chars(self):
        """件名がちょうど200文字の場合"""
        data = {
            "title": "A" * 200,
            "content": "内容"
        }
        inquiry = InquiryCreate(**data)
        assert len(inquiry.title) == 200

    def test_content_exactly_20000_chars(self):
        """内容がちょうど20,000文字の場合"""
        data = {
            "title": "件名",
            "content": "A" * 20000
        }
        inquiry = InquiryCreate(**data)
        assert len(inquiry.content) == 20000

    def test_sender_name_exactly_100_chars(self):
        """送信者名がちょうど100文字の場合"""
        data = {
            "title": "件名",
            "content": "内容",
            "sender_name": "A" * 100
        }
        inquiry = InquiryCreate(**data)
        assert len(inquiry.sender_name) == 100

    def test_admin_notes_exactly_5000_chars(self):
        """管理者メモがちょうど5,000文字の場合"""
        data = {
            "admin_notes": "A" * 5000
        }
        update = InquiryUpdate(**data)
        assert len(update.admin_notes) == 5000

    def test_reply_body_exactly_20000_chars(self):
        """返信内容がちょうど20,000文字の場合"""
        data = {
            "body": "A" * 20000
        }
        reply = InquiryReply(**data)
        assert len(reply.body) == 20000

    def test_search_exactly_200_chars(self):
        """検索キーワードがちょうど200文字の場合"""
        data = {
            "search": "A" * 200
        }
        query = InquiryQueryParams(**data)
        assert len(query.search) == 200

    def test_unicode_characters(self):
        """Unicode文字の処理"""
        data = {
            "title": "件名🔥",
            "content": "内容😀",
            "sender_name": "山田 太郎"
        }
        inquiry = InquiryCreate(**data)

        assert inquiry.title == "件名🔥"
        assert inquiry.content == "内容😀"
        assert inquiry.sender_name == "山田 太郎"

    def test_newlines_and_tabs_in_content(self):
        """内容に改行やタブが含まれる場合"""
        data = {
            "title": "件名",
            "content": "1行目\n2行目\t3行目"
        }
        inquiry = InquiryCreate(**data)

        # バリデーションを通過することを確認
        assert "1行目" in inquiry.content
        assert "2行目" in inquiry.content
        assert "3行目" in inquiry.content
