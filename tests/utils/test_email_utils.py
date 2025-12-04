"""
メール送信ユーティリティのテスト
"""
import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime

from app.utils.email_utils import (
    send_email_with_retry,
    create_delivery_log_entry,
    send_and_log_email
)


class TestSendEmailWithRetry:
    """send_email_with_retryのテスト"""

    @pytest.mark.asyncio
    async def test_success_on_first_try(self, mock_asyncio_sleep):
        """1回目の送信で成功する場合"""
        # メール送信関数のモック
        mock_email_func = AsyncMock()

        result = await send_email_with_retry(
            email_func=mock_email_func,
            max_retries=3,
            recipient_email="test@example.com"
        )

        # 検証
        assert result["success"] is True
        assert result["error"] is None
        assert result["retry_count"] == 0
        assert result["sent_at"] is not None
        assert mock_email_func.call_count == 1
        mock_asyncio_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_success_on_second_try(self, mock_asyncio_sleep):
        """2回目の送信で成功する場合"""
        # 1回目は失敗、2回目は成功
        mock_email_func = AsyncMock(
            side_effect=[Exception("Connection error"), None]
        )

        result = await send_email_with_retry(
            email_func=mock_email_func,
            max_retries=3,
            initial_delay=0.1  # テスト高速化
        )

        # 検証
        assert result["success"] is True
        assert result["error"] is None
        assert result["retry_count"] == 1
        assert result["sent_at"] is not None
        assert mock_email_func.call_count == 2
        assert mock_asyncio_sleep.call_count == 1

    @pytest.mark.asyncio
    async def test_all_retries_fail(self, mock_asyncio_sleep):
        """すべてのリトライが失敗する場合"""
        # すべて失敗
        mock_email_func = AsyncMock(
            side_effect=Exception("Permanent failure")
        )

        result = await send_email_with_retry(
            email_func=mock_email_func,
            max_retries=3,
            initial_delay=0.1
        )

        # 検証
        assert result["success"] is False
        assert result["error"] == "Permanent failure"
        assert result["retry_count"] == 3
        assert result["sent_at"] is None
        assert mock_email_func.call_count == 4  # 初回 + 3回リトライ
        assert mock_asyncio_sleep.call_count == 3

    @pytest.mark.asyncio
    async def test_exponential_backoff(self, mock_asyncio_sleep):
        """Exponential backoffの検証"""
        mock_email_func = AsyncMock(side_effect=Exception("Always fails"))

        await send_email_with_retry(
            email_func=mock_email_func,
            max_retries=3,
            initial_delay=1.0,
            backoff_factor=2.0,
            max_delay=60.0
        )

        # 待機時間を検証
        calls = mock_asyncio_sleep.call_args_list
        assert len(calls) == 3

        # 1回目: 1秒
        assert calls[0][0][0] == 1.0
        # 2回目: 2秒
        assert calls[1][0][0] == 2.0
        # 3回目: 4秒
        assert calls[2][0][0] == 4.0

    @pytest.mark.asyncio
    async def test_max_delay_limit(self, mock_asyncio_sleep):
        """最大待機時間の制限"""
        mock_email_func = AsyncMock(side_effect=Exception("Always fails"))

        await send_email_with_retry(
            email_func=mock_email_func,
            max_retries=3,
            initial_delay=10.0,
            backoff_factor=2.0,
            max_delay=15.0  # 最大15秒
        )

        # 待機時間を検証
        calls = mock_asyncio_sleep.call_args_list
        for call in calls:
            delay = call[0][0]
            assert delay <= 15.0  # 最大15秒を超えない


class TestCreateDeliveryLogEntry:
    """create_delivery_log_entryのテスト"""

    def test_create_entry_success(self):
        """成功時のログエントリ作成"""
        result = {
            "success": True,
            "error": None,
            "retry_count": 0,
            "sent_at": "2025-01-01T00:00:00"
        }

        entry = create_delivery_log_entry(
            recipient="user@example.com",
            subject="テスト件名",
            result=result,
            email_type="inquiry_received"
        )

        # 検証
        assert entry["recipient"] == "user@example.com"
        assert entry["subject"] == "テスト件名"
        assert entry["email_type"] == "inquiry_received"
        assert entry["success"] is True
        assert entry["error"] is None
        assert entry["retry_count"] == 0
        assert entry["sent_at"] == "2025-01-01T00:00:00"
        assert "timestamp" in entry

    def test_create_entry_failure(self):
        """失敗時のログエントリ作成"""
        result = {
            "success": False,
            "error": "Connection timeout",
            "retry_count": 3,
            "sent_at": None
        }

        entry = create_delivery_log_entry(
            recipient="user@example.com",
            subject="テスト件名",
            result=result,
            email_type="inquiry_reply"
        )

        # 検証
        assert entry["success"] is False
        assert entry["error"] == "Connection timeout"
        assert entry["retry_count"] == 3
        assert entry["sent_at"] is None


class TestSendAndLogEmail:
    """send_and_log_emailのテスト"""

    @pytest.mark.asyncio
    async def test_send_and_log_success(
        self,
        db_session,
        inquiry_detail_factory,
        mock_asyncio_sleep
    ):
        """メール送信成功時のログ記録"""
        # InquiryDetailを作成
        inquiry_detail = await inquiry_detail_factory(session=db_session)

        # メール送信関数のモック
        mock_email_func = AsyncMock()

        # メール送信とログ記録
        success = await send_and_log_email(
            db=db_session,
            inquiry_detail_id=inquiry_detail.id,
            email_func=mock_email_func,
            recipient="user@example.com",
            subject="テスト件名",
            email_type="inquiry_received",
            max_retries=3
        )

        # 検証
        assert success is True
        assert mock_email_func.call_count == 1

        # delivery_logが更新されたことを確認
        await db_session.refresh(inquiry_detail)
        assert inquiry_detail.delivery_log is not None
        assert len(inquiry_detail.delivery_log) == 1
        assert inquiry_detail.delivery_log[0]["success"] is True
        assert inquiry_detail.delivery_log[0]["recipient"] == "user@example.com"

    @pytest.mark.asyncio
    async def test_send_and_log_failure(
        self,
        db_session,
        inquiry_detail_factory,
        mock_asyncio_sleep
    ):
        """メール送信失敗時のログ記録と監査ログ"""
        # InquiryDetailを作成
        inquiry_detail = await inquiry_detail_factory(session=db_session)

        # メール送信関数のモック（常に失敗）
        mock_email_func = AsyncMock(side_effect=Exception("Send failed"))

        # 監査ログ作成をモック
        with patch("app.crud.crud_audit_log.audit_log.create_log", new_callable=AsyncMock) as mock_audit:
            # メール送信とログ記録
            success = await send_and_log_email(
                db=db_session,
                inquiry_detail_id=inquiry_detail.id,
                email_func=mock_email_func,
                recipient="user@example.com",
                subject="テスト件名",
                email_type="inquiry_reply",
                max_retries=2
            )

            # 検証
            assert success is False

            # delivery_logが更新されたことを確認
            await db_session.refresh(inquiry_detail)
            assert inquiry_detail.delivery_log is not None
            assert len(inquiry_detail.delivery_log) == 1
            assert inquiry_detail.delivery_log[0]["success"] is False
            assert inquiry_detail.delivery_log[0]["error"] == "Send failed"
            assert inquiry_detail.delivery_log[0]["retry_count"] == 2

            # 監査ログ作成が呼ばれたことを確認
            assert mock_audit.call_count == 1
            call_kwargs = mock_audit.call_args[1]
            assert call_kwargs["action"] == "email_send_failed"
            assert call_kwargs["target_type"] == "inquiry_detail"
            assert call_kwargs["target_id"] == inquiry_detail.id
            assert call_kwargs["details"]["error"] == "Send failed"
            assert call_kwargs["details"]["retry_count"] == 2

    @pytest.mark.asyncio
    async def test_multiple_delivery_logs(
        self,
        db_session,
        inquiry_detail_factory,
        mock_asyncio_sleep
    ):
        """複数回のメール送信でdelivery_logが蓄積される"""
        # InquiryDetailを作成
        inquiry_detail = await inquiry_detail_factory(session=db_session)

        mock_email_func = AsyncMock()

        # 1回目の送信
        await send_and_log_email(
            db=db_session,
            inquiry_detail_id=inquiry_detail.id,
            email_func=mock_email_func,
            recipient="user1@example.com",
            subject="1回目",
            email_type="inquiry_received"
        )

        # 2回目の送信
        await send_and_log_email(
            db=db_session,
            inquiry_detail_id=inquiry_detail.id,
            email_func=mock_email_func,
            recipient="user2@example.com",
            subject="2回目",
            email_type="inquiry_reply"
        )

        # 検証
        await db_session.refresh(inquiry_detail)
        assert len(inquiry_detail.delivery_log) == 2
        assert inquiry_detail.delivery_log[0]["recipient"] == "user1@example.com"
        assert inquiry_detail.delivery_log[1]["recipient"] == "user2@example.com"
