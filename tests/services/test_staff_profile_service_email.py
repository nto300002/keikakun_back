# tests/services/test_staff_profile_service_email.py
"""
メールアドレス変更機能のサービス層テスト
TDD: RED phase - テストを先に書いてバグを検出
"""

import pytest
import pytest_asyncio
from unittest.mock import Mock, AsyncMock, patch, call
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.services.staff_profile_service import StaffProfileService, RateLimitExceededError
from app.schemas.staff_profile import EmailChangeRequest as EmailChangeRequestSchema
from app.models.staff import Staff
from app.models.staff_profile import EmailChangeRequest as EmailChangeRequestModel, AuditLog

# Pytestに非同期テストであることを認識させる
pytestmark = pytest.mark.asyncio


@pytest.fixture
def staff_profile_service():
    """StaffProfileServiceインスタンス"""
    return StaffProfileService()


@pytest.fixture
def mock_staff():
    """モックスタッフオブジェクト"""
    staff = Mock(spec=Staff)
    staff.id = uuid4()
    staff.email = "old.email@example.com"
    staff.name = "テスト太郎"
    staff.full_name = "テスト 太郎"
    staff.hashed_password = "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5NU7d.o7uS9mG"  # "ValidPassword123!"
    return staff


class TestEmailChangeRequestCreation:
    """メールアドレス変更リクエスト作成のテスト"""

    async def test_request_email_change_success(self, staff_profile_service, mock_staff):
        """正常系: メールアドレス変更リクエストが正常に作成される"""
        # Arrange
        mock_db = AsyncMock(spec=AsyncSession)

        # スタッフ取得のモック
        mock_staff_result = Mock()
        mock_staff_result.scalar_one_or_none = Mock(return_value=mock_staff)

        # レート制限チェック（0件）
        mock_rate_limit_result = Mock()
        mock_rate_limit_result.scalar = Mock(return_value=0)

        # メールアドレス重複チェック（重複なし）
        mock_email_check_result = Mock()
        mock_email_check_result.scalar_one_or_none = Mock(return_value=None)

        # execute()の呼び出し順にモックを設定
        mock_db.execute.side_effect = [
            mock_staff_result,      # スタッフ取得
            mock_rate_limit_result, # レート制限チェック
            mock_email_check_result # メール重複チェック
        ]

        email_request = EmailChangeRequestSchema(
            new_email="new.email@example.com",
            password="ValidPassword123!"
        )

        # メール送信とパスワード検証をモック
        with patch('app.core.mail.send_email_change_verification') as mock_verification, \
             patch('app.core.mail.send_email_change_notification') as mock_notification, \
             patch('app.services.staff_profile_service.pwd_context.verify', return_value=True):

            # Act
            result = await staff_profile_service.request_email_change(
                db=mock_db,
                staff_id=str(mock_staff.id),
                email_request=email_request
            )

        # Assert
        assert result["status"] == "pending"
        assert "確認メールを送信しました" in result["message"]
        assert "verification_token_expires_at" in result

        # EmailChangeRequestが作成されたことを確認
        mock_db.add.assert_called_once()
        email_change_request = mock_db.add.call_args[0][0]
        assert isinstance(email_change_request, EmailChangeRequestModel)
        assert email_change_request.staff_id == str(mock_staff.id)
        assert email_change_request.new_email == "new.email@example.com"

        # 🔴 TDD: この時点でバグを検出 - old_emailが設定されていない！
        assert email_change_request.old_email == "old.email@example.com", \
            "old_emailフィールドが設定されていません！NOT NULL制約違反が発生します"

        assert email_change_request.status == "pending"
        assert email_change_request.verification_token is not None
        assert email_change_request.expires_at is not None

        # メール送信が呼ばれたことを確認
        mock_verification.assert_called_once()
        mock_notification.assert_called_once()

        mock_db.commit.assert_called_once()

    async def test_request_email_change_wrong_password(self, staff_profile_service, mock_staff):
        """異常系: パスワードが間違っている場合エラーになる"""
        # Arrange
        mock_db = AsyncMock(spec=AsyncSession)
        mock_staff_result = Mock()
        mock_staff_result.scalar_one_or_none = Mock(return_value=mock_staff)
        mock_db.execute.return_value = mock_staff_result

        email_request = EmailChangeRequestSchema(
            new_email="new.email@example.com",
            password="WrongPassword123!"
        )

        # Act & Assert
        with pytest.raises(ValueError, match="現在のパスワードが正しくありません"):
            await staff_profile_service.request_email_change(
                db=mock_db,
                staff_id=str(mock_staff.id),
                email_request=email_request
            )

    async def test_request_email_change_rate_limit_exceeded(self, staff_profile_service, mock_staff):
        """異常系: 24時間以内に3回を超える変更はエラーになる"""
        # Arrange
        mock_db = AsyncMock(spec=AsyncSession)

        # スタッフ取得
        mock_staff_result = Mock()
        mock_staff_result.scalar_one_or_none = Mock(return_value=mock_staff)

        # レート制限チェック（既に3回リクエスト済み）
        mock_rate_limit_result = Mock()
        mock_rate_limit_result.scalar = Mock(return_value=3)

        mock_db.execute.side_effect = [
            mock_staff_result,
            mock_rate_limit_result
        ]

        email_request = EmailChangeRequestSchema(
            new_email="new.email@example.com",
            password="ValidPassword123!"
        )

        # Act & Assert
        with patch('app.services.staff_profile_service.pwd_context.verify', return_value=True):
            with pytest.raises(RateLimitExceededError, match="24時間後に再度お試しください"):
                await staff_profile_service.request_email_change(
                    db=mock_db,
                    staff_id=str(mock_staff.id),
                    email_request=email_request
                )

    async def test_request_email_change_duplicate_email(self, staff_profile_service, mock_staff):
        """異常系: 既に使用中のメールアドレスは使用できない"""
        # Arrange
        mock_db = AsyncMock(spec=AsyncSession)

        # 既存のスタッフ
        existing_staff = Mock(spec=Staff)
        existing_staff.id = uuid4()
        existing_staff.email = "existing@example.com"

        # スタッフ取得
        mock_staff_result = Mock()
        mock_staff_result.scalar_one_or_none = Mock(return_value=mock_staff)

        # レート制限チェック（0件）
        mock_rate_limit_result = Mock()
        mock_rate_limit_result.scalar = Mock(return_value=0)

        # メールアドレス重複チェック（重複あり）
        mock_email_check_result = Mock()
        mock_email_check_result.scalar_one_or_none = Mock(return_value=existing_staff)

        mock_db.execute.side_effect = [
            mock_staff_result,
            mock_rate_limit_result,
            mock_email_check_result
        ]

        email_request = EmailChangeRequestSchema(
            new_email="existing@example.com",
            password="ValidPassword123!"
        )

        # Act & Assert
        with patch('app.services.staff_profile_service.pwd_context.verify', return_value=True):
            with pytest.raises(ValueError, match="このメールアドレスは既に使用されています"):
                await staff_profile_service.request_email_change(
                    db=mock_db,
                    staff_id=str(mock_staff.id),
                    email_request=email_request
                )


class TestEmailChangeVerification:
    """メールアドレス変更確認のテスト"""

    async def test_verify_email_change_success(self, staff_profile_service, mock_staff):
        """正常系: 確認トークンでメールアドレス変更が完了する"""
        # Arrange
        mock_db = AsyncMock(spec=AsyncSession)

        # メールアドレス変更リクエスト
        email_request = Mock(spec=EmailChangeRequestModel)
        email_request.staff_id = mock_staff.id
        email_request.old_email = "old.email@example.com"
        email_request.new_email = "new.email@example.com"
        email_request.verification_token = "valid-token-123"
        email_request.status = "pending"
        email_request.expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

        # リクエスト取得
        mock_request_result = Mock()
        mock_request_result.scalar_one_or_none = Mock(return_value=email_request)

        # スタッフ取得
        mock_staff_result = Mock()
        mock_staff_result.scalar_one_or_none = Mock(return_value=mock_staff)

        mock_db.execute.side_effect = [
            mock_request_result,
            mock_staff_result
        ]

        # メール送信をモック
        with patch('app.core.mail.send_email_change_completed') as mock_completed:
            # Act
            result = await staff_profile_service.verify_email_change(
                db=mock_db,
                verification_token="valid-token-123"
            )

        # Assert
        assert result["message"] == "メールアドレスを変更しました"
        assert result["new_email"] == "new.email@example.com"

        # スタッフのメールアドレスが更新されたことを確認
        assert mock_staff.email == "new.email@example.com"

        # リクエストのステータスが更新されたことを確認
        assert email_request.status == "completed"

        # 監査ログが作成されたことを確認
        mock_db.add.assert_called_once()
        audit_log = mock_db.add.call_args[0][0]
        assert isinstance(audit_log, AuditLog)
        assert audit_log.action == "UPDATE_EMAIL"
        assert audit_log.old_value == "old.email@example.com"
        assert audit_log.new_value == "new.email@example.com"

        # 完了通知メールが送信されたことを確認
        mock_completed.assert_called_once()

        mock_db.commit.assert_called_once()

    async def test_verify_email_change_invalid_token(self, staff_profile_service):
        """異常系: 無効なトークンはエラーになる"""
        # Arrange
        mock_db = AsyncMock(spec=AsyncSession)
        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(return_value=None)
        mock_db.execute.return_value = mock_result

        # Act & Assert
        with pytest.raises(ValueError, match="無効な確認トークンです"):
            await staff_profile_service.verify_email_change(
                db=mock_db,
                verification_token="invalid-token"
            )

    async def test_verify_email_change_expired_token(self, staff_profile_service, mock_staff):
        """異常系: 有効期限切れのトークンはエラーになる"""
        # Arrange
        mock_db = AsyncMock(spec=AsyncSession)

        # 期限切れのリクエスト
        email_request = Mock(spec=EmailChangeRequestModel)
        email_request.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)

        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(return_value=email_request)
        mock_db.execute.return_value = mock_result

        # Act & Assert
        with pytest.raises(ValueError, match="確認トークンの有効期限が切れています"):
            await staff_profile_service.verify_email_change(
                db=mock_db,
                verification_token="expired-token"
            )

    async def test_verify_email_change_already_completed(self, staff_profile_service, mock_staff):
        """異常系: 既に使用済みのトークンは再利用できない"""
        # Arrange
        mock_db = AsyncMock(spec=AsyncSession)

        # 既に完了済みのリクエスト
        email_request = Mock(spec=EmailChangeRequestModel)
        email_request.status = "completed"
        email_request.expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(return_value=email_request)
        mock_db.execute.return_value = mock_result

        # Act & Assert
        with pytest.raises(ValueError, match="この変更リクエストは既に処理されています"):
            await staff_profile_service.verify_email_change(
                db=mock_db,
                verification_token="used-token"
            )

    async def test_verify_email_change_with_timezone_aware_datetime(self, staff_profile_service, mock_staff):
        """
        TDD: timezone-aware datetime との比較テスト

        データベースから取得されるdatetimeはtimezone-aware（PostgreSQL）だが、
        Python の datetime.utcnow() はtimezone-naiveなので、比較時にTypeErrorが発生する。
        このテストケースはその問題を検出する。
        """
        # Arrange
        mock_db = AsyncMock(spec=AsyncSession)

        # メールアドレス変更リクエスト（timezone-aware datetime を使用）
        email_request = Mock(spec=EmailChangeRequestModel)
        email_request.staff_id = mock_staff.id
        email_request.old_email = "old.email@example.com"
        email_request.new_email = "new.email@example.com"
        email_request.verification_token = "valid-token-123"
        email_request.status = "pending"
        # PostgreSQLから返されるdatetimeはtimezone-aware
        email_request.expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        email_request.id = uuid4()

        # リクエスト取得
        mock_request_result = Mock()
        mock_request_result.scalar_one_or_none = Mock(return_value=email_request)

        # スタッフ取得
        mock_staff_result = Mock()
        mock_staff_result.scalar_one_or_none = Mock(return_value=mock_staff)

        mock_db.execute.side_effect = [
            mock_request_result,
            mock_staff_result
        ]

        # メール送信をモック
        with patch('app.core.mail.send_email_change_completed') as mock_completed:
            # Act
            # この時点で TypeError が発生する可能性がある
            result = await staff_profile_service.verify_email_change(
                db=mock_db,
                verification_token="valid-token-123"
            )

        # Assert
        assert result["message"] == "メールアドレスを変更しました"
        assert result["new_email"] == "new.email@example.com"
        assert mock_staff.email == "new.email@example.com"
