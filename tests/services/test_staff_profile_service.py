# tests/services/test_staff_profile_service.py

import pytest
import pytest_asyncio
from unittest.mock import Mock, AsyncMock, patch
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta
from uuid import uuid4

from app.db.session import AsyncSessionLocal
from app.services.staff_profile_service import StaffProfileService, staff_profile_service
from app.schemas.staff_profile import StaffNameUpdate, PasswordChange
from app.models.staff import Staff
from app.models.staff_profile import AuditLog, PasswordHistory
from app.models.enums import StaffRole
from app.core.security import get_password_hash

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
        from fastapi import HTTPException
        from app.messages import ja

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
        with pytest.raises(HTTPException) as exc_info:
            await staff_profile_service.update_name(
                db=mock_db,
                staff_id=str(uuid4()),
                name_data=name_data
            )
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == ja.STAFF_NOT_FOUND

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
        from fastapi import HTTPException
        from app.messages import ja

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
            with pytest.raises(HTTPException) as exc_info:
                await staff_profile_service.change_password(
                    db=mock_db,
                    staff_id=str(mock_staff.id),
                    password_change=password_change
                )
            assert exc_info.value.status_code == 400
            assert exc_info.value.detail == ja.STAFF_CURRENT_PASSWORD_INCORRECT

            # 失敗回数がインクリメントされたか確認
            assert mock_staff.failed_password_attempts == 1

    async def test_change_password_mismatch(self, staff_profile_service, mock_staff):
        """異常系: 新パスワードが一致しない"""
        # Arrange
        from fastapi import HTTPException
        from app.messages import ja

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
        with pytest.raises(HTTPException) as exc_info:
            await staff_profile_service.change_password(
                db=mock_db,
                staff_id=str(mock_staff.id),
                password_change=password_change
            )
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == ja.STAFF_PASSWORD_MISMATCH

    async def test_check_password_similarity_email(self, staff_profile_service, mock_staff):
        """異常系: パスワードにメールアドレスの一部が含まれる"""
        # Arrange
        from fastapi import HTTPException
        from app.messages import ja

        mock_staff.email = "yamada@example.com"

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            staff_profile_service._check_password_similarity("Yamada123!", mock_staff)
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == ja.STAFF_PASSWORD_CONTAINS_EMAIL

    async def test_check_password_similarity_name(self, staff_profile_service, mock_staff):
        """異常系: パスワードに名前が含まれる"""
        # Arrange
        from fastapi import HTTPException
        from app.messages import ja

        mock_staff.last_name = "yamada"
        mock_staff.first_name = "taro"

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            staff_profile_service._check_password_similarity("Yamada123!", mock_staff)
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == ja.STAFF_PASSWORD_CONTAINS_NAME

    async def test_check_password_history_reuse_prevention(self, staff_profile_service):
        """異常系: 過去のパスワードは再利用できない"""
        # Arrange
        from fastapi import HTTPException

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
            with pytest.raises(HTTPException) as exc_info:
                await staff_profile_service._check_password_history(
                    db=mock_db,
                    staff_id=str(uuid4()),
                    new_password="OldPassword123!"
                )
            assert exc_info.value.status_code == 400
            assert "過去に使用したパスワードは使用できません" in exc_info.value.detail

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


# ===== TDD: rollbackテスト (Issue #02) =====

@pytest.fixture(scope="function")
async def db() -> AsyncSession:
    """実DBセッションを提供するフィクスチャ（rollbackテスト用）"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            try:
                await session.rollback()
            except Exception:
                pass


@pytest.fixture(scope="function")
async def setup_staff(db: AsyncSession):
    """
    テスト用スタッフを実DBに作成
    Returns: (staff_id, original_last_name)
    """
    staff = Staff(
        first_name="太郎",
        last_name="田中",
        full_name="田中 太郎",
        email=f"staff_{uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash("password"),
        role=StaffRole.employee,
    )
    db.add(staff)
    await db.flush()

    staff_id = staff.id
    original_last_name = staff.last_name

    await db.commit()

    return staff_id, original_last_name


async def test_update_name_rollback_on_error(
    db: AsyncSession,
    setup_staff,
    staff_profile_service: StaffProfileService
):
    """
    update_name で例外発生時、名前変更がDBに残らないことを確認

    Red → try-except-rollbackがなければ、flush()済みの変更がセッション内で
          見えたまま（rollbackされない）になるか、セッションが壊れた状態になる。
    """
    staff_id, original_last_name = setup_staff

    # _log_name_change で例外を発生させる（flush後、commit前で失敗するシナリオ）
    with patch.object(
        StaffProfileService,
        '_log_name_change',
        new=AsyncMock(side_effect=Exception("監査ログ作成で意図的なエラー"))
    ):
        with pytest.raises(Exception, match="監査ログ作成で意図的なエラー"):
            await staff_profile_service.update_name(
                db=db,
                staff_id=str(staff_id),
                name_data=StaffNameUpdate(
                    last_name="山田",
                    first_name="次郎",
                    last_name_furigana="やまだ",
                    first_name_furigana="じろう"
                )
            )

    # 例外発生後、DBのスタッフ名が元のままであることを確認（rollbackされていること）
    result = await db.execute(
        select(Staff).where(Staff.id == staff_id)
    )
    staff = result.scalar_one()
    assert staff.last_name == original_last_name, (
        f"例外発生後にlast_nameが'{staff.last_name}'に変更されています。"
        "try-except-rollbackが正しく実装されていません。"
    )


async def test_change_password_rollback_on_error(
    db: AsyncSession,
    setup_staff,
    staff_profile_service: StaffProfileService
):
    """
    change_password でflush後に例外発生時、パスワード変更がDBに残らないことを確認

    Red → 現在のtry-finallyは例外時でもfinallyでcommitしてしまうため、
          flush済みのパスワード変更が意図せずcommitされる。
    """
    from sqlalchemy import select as sa_select
    from app.core.security import verify_password

    staff_id, _ = setup_staff

    # 現在のパスワードハッシュを取得
    result = await db.execute(sa_select(Staff).where(Staff.id == staff_id))
    staff_before = result.scalar_one()
    original_hashed_password = staff_before.hashed_password

    # _cleanup_password_history で例外を発生させる
    # （flush後のステップで失敗 → 変更がrollbackされるべき）
    with patch.object(
        StaffProfileService,
        '_cleanup_password_history',
        new=AsyncMock(side_effect=Exception("履歴クリーンアップで意図的なエラー"))
    ):
        with pytest.raises(Exception, match="履歴クリーンアップで意図的なエラー"):
            await staff_profile_service.change_password(
                db=db,
                staff_id=str(staff_id),
                password_change=PasswordChange(
                    current_password="password",
                    new_password="NewPassword123!",
                    new_password_confirm="NewPassword123!"
                )
            )

    # 例外発生後、パスワードが変更されていないことを確認（rollbackされていること）
    result = await db.execute(sa_select(Staff).where(Staff.id == staff_id))
    staff_after = result.scalar_one()
    assert staff_after.hashed_password == original_hashed_password, (
        "例外発生後にパスワードが変更されています。"
        "try-except-rollbackが正しく実装されていません。"
    )


async def test_request_email_change_rollback_on_error(
    db: AsyncSession,
    setup_staff,
    staff_profile_service: StaffProfileService
):
    """
    request_email_change でcommit時に例外発生した場合、
    flush済みのEmailChangeRequestがセッション内に残らないことを確認

    Red → try-except-rollbackがなければ、flush済みの変更がrollbackされず
          同セッション内でクエリすると残ったままになる。
    """
    from sqlalchemy import select as sa_select
    from app.models.staff_profile import EmailChangeRequest as EmailChangeRequestModel
    from app.schemas.staff_profile import EmailChangeRequest

    staff_id, _ = setup_staff

    # db.commit で例外を発生させる（flush後・commit前で失敗するシナリオ）
    with patch.object(db, 'commit', side_effect=Exception("commitで意図的なエラー")):
        with pytest.raises(Exception, match="commitで意図的なエラー"):
            await staff_profile_service.request_email_change(
                db=db,
                staff_id=str(staff_id),
                email_request=EmailChangeRequest(
                    new_email="new@example.com",
                    password="password"
                )
            )

    # 例外発生後、同セッションでクエリしてEmailChangeRequestが残っていないことを確認
    # without rollback: flush済みレコードがセッション内で見える → テスト失敗
    # with rollback: セッションはクリーン → 0件
    result = await db.execute(
        sa_select(EmailChangeRequestModel).where(
            EmailChangeRequestModel.staff_id == str(staff_id)
        )
    )
    remaining = result.scalars().all()
    assert len(remaining) == 0, (
        f"例外発生後にEmailChangeRequestが{len(remaining)}件残っています。"
        "try-except-rollbackが正しく実装されていません。"
    )


async def test_verify_email_change_rollback_on_error(
    db: AsyncSession,
    setup_staff,
    staff_profile_service: StaffProfileService
):
    """
    verify_email_change で例外発生時、メールアドレス変更がDBに残らないことを確認

    Red → try-except-rollbackがなければ、flush済みのメール変更がcommitされる可能性がある。
    """
    from sqlalchemy import select as sa_select
    from app.models.staff_profile import EmailChangeRequest as EmailChangeRequestModel
    import secrets
    from datetime import timezone

    staff_id, _ = setup_staff

    # 事前にEmailChangeRequestを作成
    token = secrets.token_urlsafe(32)
    email_request = EmailChangeRequestModel(
        staff_id=str(staff_id),
        old_email="staff@example.com",
        new_email="changed@example.com",
        verification_token=token,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        status="pending"
    )
    db.add(email_request)
    await db.flush()
    await db.commit()

    # AuditLog の flush 後に例外を発生させる（メール変更flush後）
    original_flush = db.flush
    flush_call_count = 0

    async def fail_on_second_flush():
        nonlocal flush_call_count
        flush_call_count += 1
        if flush_call_count >= 2:
            raise Exception("監査ログflushで意図的なエラー")
        await original_flush()

    # 現在のスタッフのメールアドレスを取得
    result = await db.execute(sa_select(Staff).where(Staff.id == staff_id))
    staff_before = result.scalar_one()
    original_email = staff_before.email

    with patch.object(db, 'flush', side_effect=fail_on_second_flush):
        with pytest.raises(Exception, match="監査ログflushで意図的なエラー"):
            await staff_profile_service.verify_email_change(
                db=db,
                verification_token=token
            )

    # 例外発生後、スタッフのメールアドレスが変更されていないことを確認
    result = await db.execute(sa_select(Staff).where(Staff.id == staff_id))
    staff_after = result.scalar_one()
    assert staff_after.email == original_email, (
        f"例外発生後にemailが'{staff_after.email}'に変更されています。"
        "try-except-rollbackが正しく実装されていません。"
    )
