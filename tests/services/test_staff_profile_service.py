# tests/services/test_staff_profile_service.py

import pytest
import pytest_asyncio
from unittest.mock import Mock, AsyncMock, patch
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
from uuid import uuid4

from app.services.staff_profile_service import StaffProfileService
from app.schemas.staff_profile import StaffNameUpdate, PasswordChange
from app.models.staff import Staff
from app.models.staff_profile import AuditLog, PasswordHistory

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
    staff.email = "test@example.com"
    staff.last_name = "旧姓"
    staff.first_name = "旧名"
    staff.hashed_password = "$2b$12$mockhashedpassword"
    staff.failed_password_attempts = 0
    staff.is_locked = False
    return staff


class TestStaffProfileServiceNameUpdate:
    """名前更新機能のサービス層テスト"""

    async def test_update_name_success(self, staff_profile_service, mock_staff):
        """正常系: 名前更新が成功する"""
        # Arrange
        mock_db = AsyncMock(spec=AsyncSession)
        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(return_value=mock_staff)
        mock_db.execute.return_value = mock_result

        name_data = StaffNameUpdate(
            last_name="山田",
            first_name="太郎",
            last_name_furigana="やまだ",
            first_name_furigana="たろう"
        )

        # Act
        result = await staff_profile_service.update_name(
            db=mock_db,
            staff_id=str(mock_staff.id),
            name_data=name_data
        )

        # Assert
        assert mock_staff.last_name == "山田"
        assert mock_staff.first_name == "太郎"
        assert mock_staff.full_name == "山田 太郎"
        assert mock_staff.last_name_furigana == "やまだ"
        assert mock_staff.first_name_furigana == "たろう"
        mock_db.flush.assert_called()
        mock_db.commit.assert_called_once()

    async def test_update_name_staff_not_found(self, staff_profile_service):
        """異常系: スタッフが見つからない場合エラー"""
        # Arrange
        mock_db = AsyncMock(spec=AsyncSession)
        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(return_value=None)
        mock_db.execute.return_value = mock_result

        name_data = StaffNameUpdate(
            last_name="山田",
            first_name="太郎",
            last_name_furigana="やまだ",
            first_name_furigana="たろう"
        )

        # Act & Assert
        with pytest.raises(ValueError, match="スタッフが見つかりません"):
            await staff_profile_service.update_name(
                db=mock_db,
                staff_id=str(uuid4()),
                name_data=name_data
            )

    async def test_log_name_change(self, staff_profile_service):
        """監査ログが正しく記録される"""
        # Arrange
        mock_db = AsyncMock(spec=AsyncSession)
        staff_id = str(uuid4())

        # Act
        await staff_profile_service._log_name_change(
            db=mock_db,
            staff_id=staff_id,
            old_name="旧姓 旧名",
            new_name="山田 太郎"
        )

        # Assert
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()
        # addに渡されたオブジェクトを検証
        audit_log = mock_db.add.call_args[0][0]
        assert isinstance(audit_log, AuditLog)
        assert audit_log.action == "UPDATE_NAME"
        assert audit_log.old_value == "旧姓 旧名"
        assert audit_log.new_value == "山田 太郎"


class TestStaffProfileServicePasswordChange:
    """パスワード変更機能のサービス層テスト"""

    async def test_change_password_success(self, staff_profile_service, mock_staff):
        """正常系: パスワード変更が成功する"""
        # Arrange
        mock_db = AsyncMock(spec=AsyncSession)

        # 最初のexecute: スタッフ取得
        mock_result_staff = Mock()
        mock_result_staff.scalar_one_or_none = Mock(return_value=mock_staff)

        # 2回目のexecute: レート制限チェック（カウント0）
        mock_result_rate_limit = Mock()
        mock_result_rate_limit.scalar = Mock(return_value=0)

        # 3回目のexecute: パスワード履歴チェック（空の履歴）
        mock_scalars = Mock()
        mock_scalars.all = Mock(return_value=[])
        mock_result_history = Mock()
        mock_result_history.scalars = Mock(return_value=mock_scalars)

        # 4回目のexecute: パスワード履歴クリーンアップのSELECT（空のリスト）
        mock_result_cleanup = Mock()
        mock_result_cleanup.all = Mock(return_value=[])

        # 5回目のexecute: パスワード履歴クリーンアップのDELETE
        mock_result_delete = Mock()

        # executeを呼ぶ順序に応じて異なる値を返す
        mock_db.execute.side_effect = [
            mock_result_staff,
            mock_result_rate_limit,
            mock_result_history,
            mock_result_cleanup,
            mock_result_delete
        ]

        password_change = PasswordChange(
            current_password="OldPassword123!",
            new_password="NewPassword456!",
            new_password_confirm="NewPassword456!"
        )

        with patch('app.services.staff_profile_service.pwd_context.verify', return_value=True), \
             patch('app.services.staff_profile_service.pwd_context.hash', return_value="$2b$12$newhash"):

            # Act
            result = await staff_profile_service.change_password(
                db=mock_db,
                staff_id=str(mock_staff.id),
                password_change=password_change
            )

        # Assert
        assert result["message"] == "パスワードを変更しました"
        assert "updated_at" in result
        assert mock_staff.failed_password_attempts == 0
        mock_db.commit.assert_called_once()

    async def test_change_password_wrong_current(self, staff_profile_service, mock_staff):
        """異常系: 現在のパスワードが間違っている"""
        # Arrange
        mock_db = AsyncMock(spec=AsyncSession)

        # 最初のexecute: スタッフ取得
        mock_result_staff = Mock()
        mock_result_staff.scalar_one_or_none = Mock(return_value=mock_staff)

        # 2回目のexecute: レート制限チェック（カウント0）
        mock_result_rate_limit = Mock()
        mock_result_rate_limit.scalar = Mock(return_value=0)

        mock_db.execute.side_effect = [mock_result_staff, mock_result_rate_limit]

        password_change = PasswordChange(
            current_password="WrongPassword123!",
            new_password="NewPassword456!",
            new_password_confirm="NewPassword456!"
        )

        with patch('app.services.staff_profile_service.pwd_context.verify', return_value=False):
            # Act & Assert
            with pytest.raises(ValueError, match="現在のパスワードが正しくありません"):
                await staff_profile_service.change_password(
                    db=mock_db,
                    staff_id=str(mock_staff.id),
                    password_change=password_change
                )

            # 失敗回数がインクリメントされたか確認
            assert mock_staff.failed_password_attempts == 1

    async def test_change_password_mismatch(self, staff_profile_service, mock_staff):
        """異常系: 新パスワードが一致しない"""
        # Arrange
        mock_db = AsyncMock(spec=AsyncSession)

        # 最初のexecute: スタッフ取得
        mock_result_staff = Mock()
        mock_result_staff.scalar_one_or_none = Mock(return_value=mock_staff)

        # 2回目のexecute: レート制限チェック（カウント0）
        mock_result_rate_limit = Mock()
        mock_result_rate_limit.scalar = Mock(return_value=0)

        mock_db.execute.side_effect = [mock_result_staff, mock_result_rate_limit]

        password_change = PasswordChange(
            current_password="OldPassword123!",
            new_password="NewPassword456!",
            new_password_confirm="DifferentPassword789!"
        )

        # Act & Assert
        with pytest.raises(ValueError, match="新しいパスワードが一致しません"):
            await staff_profile_service.change_password(
                db=mock_db,
                staff_id=str(mock_staff.id),
                password_change=password_change
            )

    async def test_check_password_similarity_email(self, staff_profile_service, mock_staff):
        """異常系: パスワードにメールアドレスの一部が含まれる"""
        # Arrange
        mock_staff.email = "yamada@example.com"

        # Act & Assert
        with pytest.raises(ValueError, match="メールアドレスの一部を含めることはできません"):
            staff_profile_service._check_password_similarity("Yamada123!", mock_staff)

    async def test_check_password_similarity_name(self, staff_profile_service, mock_staff):
        """異常系: パスワードに名前が含まれる"""
        # Arrange
        mock_staff.last_name = "yamada"
        mock_staff.first_name = "taro"

        # Act & Assert
        with pytest.raises(ValueError, match="パスワードに名前を含めることはできません"):
            staff_profile_service._check_password_similarity("Yamada123!", mock_staff)

    async def test_check_password_history_reuse_prevention(self, staff_profile_service):
        """異常系: 過去のパスワードは再利用できない"""
        # Arrange
        mock_db = AsyncMock(spec=AsyncSession)

        # 過去のパスワード履歴をモック
        old_hash = "$2b$12$oldhash"
        mock_history = Mock(spec=PasswordHistory)
        mock_history.hashed_password = old_hash

        mock_scalars = Mock()
        mock_scalars.all = Mock(return_value=[mock_history])
        mock_result = Mock()
        mock_result.scalars = Mock(return_value=mock_scalars)
        mock_db.execute.return_value = mock_result

        with patch('app.services.staff_profile_service.pwd_context.verify', return_value=True):
            # Act & Assert
            with pytest.raises(ValueError, match="過去に使用したパスワードは使用できません"):
                await staff_profile_service._check_password_history(
                    db=mock_db,
                    staff_id=str(uuid4()),
                    new_password="OldPassword123!"
                )

    async def test_cleanup_password_history(self, staff_profile_service):
        """パスワード履歴のクリーンアップが正しく動作する"""
        # Arrange
        mock_db = AsyncMock(spec=AsyncSession)
        staff_id = str(uuid4())

        # 4件の履歴IDをモック（最新3件を保持、1件削除される）
        mock_result = Mock()
        mock_result.all = Mock(return_value=[
            (uuid4(),),  # 保持
            (uuid4(),),  # 保持
            (uuid4(),),  # 保持
        ])
        mock_db.execute.return_value = mock_result

        # Act
        await staff_profile_service._cleanup_password_history(
            db=mock_db,
            staff_id=staff_id,
            keep_recent=3
        )

        # Assert
        # DELETE文が実行されたことを確認
        assert mock_db.execute.call_count >= 2  # SELECT + DELETE
        mock_db.flush.assert_called_once()

    async def test_increment_failed_password_attempts_lock_account(self, staff_profile_service, mock_staff):
        """異常系: 5回失敗でアカウントロック"""
        # Arrange
        mock_db = AsyncMock(spec=AsyncSession)
        mock_staff.failed_password_attempts = 4  # 次で5回目

        # Act
        await staff_profile_service._increment_failed_password_attempts(
            db=mock_db,
            staff=mock_staff
        )

        # Assert
        assert mock_staff.failed_password_attempts == 5
        assert mock_staff.is_locked is True
        assert mock_staff.locked_at is not None
        mock_db.flush.assert_called_once()

    async def test_log_password_change(self, staff_profile_service):
        """パスワード変更の監査ログが記録される"""
        # Arrange
        mock_db = AsyncMock(spec=AsyncSession)
        staff_id = str(uuid4())

        # Act
        await staff_profile_service._log_password_change(
            db=mock_db,
            staff_id=staff_id
        )

        # Assert
        mock_db.add.assert_called_once()
        audit_log = mock_db.add.call_args[0][0]
        assert isinstance(audit_log, AuditLog)
        assert audit_log.action == "CHANGE_PASSWORD"
        assert audit_log.old_value is None  # セキュリティのためパスワードは記録しない
        assert audit_log.new_value is None


class TestStaffProfileServiceEdgeCases:
    """エッジケースとエラーハンドリングのテスト"""

    async def test_update_name_with_empty_old_name(self, staff_profile_service):
        """名前更新: 旧名前が空の場合も正しく処理される"""
        # Arrange
        mock_db = AsyncMock(spec=AsyncSession)
        mock_staff = Mock(spec=Staff)
        mock_staff.id = uuid4()
        mock_staff.last_name = None
        mock_staff.first_name = None
        mock_staff.name = "テスト太郎"

        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(return_value=mock_staff)
        mock_db.execute.return_value = mock_result

        name_data = StaffNameUpdate(
            last_name="山田",
            first_name="太郎",
            last_name_furigana="やまだ",
            first_name_furigana="たろう"
        )

        # Act
        await staff_profile_service.update_name(
            db=mock_db,
            staff_id=str(mock_staff.id),
            name_data=name_data
        )

        # Assert - エラーなく完了することを確認
        assert mock_staff.full_name == "山田 太郎"
        mock_db.commit.assert_called_once()
