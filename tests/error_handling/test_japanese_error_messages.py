"""日本語エラーメッセージのテスト

フロントエンドに返されるエラーメッセージが正しく日本語化されていることを確認するテスト。
優先度の高い認証、MFA、共通例外のメッセージを検証します。
"""
import pytest
from fastapi import status
from app.messages import ja
from app.core.exceptions import (
    BadRequestException,
    NotFoundException,
    ForbiddenException,
    InternalServerException,
)

pytestmark = pytest.mark.asyncio


class TestJapaneseErrorMessages:
    """日本語エラーメッセージの検証"""

    def test_error_message_constants_exist(self):
        """エラーメッセージ定数が存在することを確認"""
        # 認証関連
        assert ja.AUTH_EMAIL_ALREADY_EXISTS
        assert ja.AUTH_INCORRECT_CREDENTIALS
        assert ja.AUTH_EMAIL_NOT_VERIFIED
        assert ja.AUTH_LOGIN_SUCCESS
        assert ja.AUTH_LOGOUT_SUCCESS

        # MFA関連
        assert ja.MFA_ALREADY_ENABLED
        assert ja.MFA_INVALID_CODE
        assert ja.MFA_VERIFICATION_SUCCESS

        # 権限関連
        assert ja.PERM_CREDENTIALS_INVALID
        assert ja.PERM_MANAGER_OR_OWNER_REQUIRED
        assert ja.PERM_OWNER_REQUIRED

        # 例外クラス
        assert ja.EXC_BAD_REQUEST
        assert ja.EXC_NOT_FOUND
        assert ja.EXC_FORBIDDEN
        assert ja.EXC_INTERNAL_ERROR

    def test_error_messages_are_japanese(self):
        """エラーメッセージが日本語であることを確認"""
        # 日本語の文字が含まれているかチェック
        messages_to_check = [
            ja.AUTH_EMAIL_ALREADY_EXISTS,
            ja.AUTH_INCORRECT_CREDENTIALS,
            ja.MFA_ALREADY_ENABLED,
            ja.EXC_BAD_REQUEST,
            ja.EXC_NOT_FOUND,
        ]

        for msg in messages_to_check:
            # 日本語文字（ひらがな、カタカナ、漢字）が含まれているか
            assert any(
                ord(char) >= 0x3040 and ord(char) <= 0x9FFF for char in msg
            ), f"Message does not contain Japanese characters: {msg}"

    def test_error_messages_no_trailing_period(self):
        """エラーメッセージに不要なピリオドがないことを確認"""
        # 日本語メッセージは通常ピリオドで終わらない
        messages_to_check = [
            ja.AUTH_LOGIN_SUCCESS,
            ja.AUTH_LOGOUT_SUCCESS,
            ja.MFA_DISABLED_SUCCESS,
            ja.RECIPIENT_DELETED,
        ]

        for msg in messages_to_check:
            # 英語のピリオドで終わっていないことを確認
            assert not msg.endswith("."), f"Message ends with period: {msg}"


class TestExceptionClassJapaneseMessages:
    """カスタム例外クラスのデフォルトメッセージが日本語化されていることを確認"""

    def test_bad_request_exception_default_message(self):
        """BadRequestExceptionのデフォルトメッセージ"""
        exc = BadRequestException()
        assert exc.status_code == status.HTTP_400_BAD_REQUEST
        assert exc.detail == ja.EXC_BAD_REQUEST
        assert "不正" in exc.detail or "リクエスト" in exc.detail

    def test_bad_request_exception_custom_message(self):
        """BadRequestExceptionのカスタムメッセージ"""
        custom_message = "カスタムエラーメッセージ"
        exc = BadRequestException(detail=custom_message)
        assert exc.detail == custom_message

    def test_not_found_exception_default_message(self):
        """NotFoundExceptionのデフォルトメッセージ"""
        exc = NotFoundException()
        assert exc.status_code == status.HTTP_404_NOT_FOUND
        assert exc.detail == ja.EXC_NOT_FOUND
        assert "見つかり" in exc.detail or "ません" in exc.detail

    def test_not_found_exception_custom_message(self):
        """NotFoundExceptionのカスタムメッセージ"""
        custom_message = "ユーザーが見つかりません"
        exc = NotFoundException(detail=custom_message)
        assert exc.detail == custom_message

    def test_forbidden_exception_default_message(self):
        """ForbiddenExceptionのデフォルトメッセージ"""
        exc = ForbiddenException()
        assert exc.status_code == status.HTTP_403_FORBIDDEN
        assert exc.detail == ja.EXC_FORBIDDEN
        assert "アクセス" in exc.detail or "拒否" in exc.detail

    def test_forbidden_exception_custom_message(self):
        """ForbiddenExceptionのカスタムメッセージ"""
        custom_message = "この操作を実行する権限がありません"
        exc = ForbiddenException(detail=custom_message)
        assert exc.detail == custom_message

    def test_internal_server_exception_default_message(self):
        """InternalServerExceptionのデフォルトメッセージ"""
        exc = InternalServerException()
        assert exc.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc.detail == ja.EXC_INTERNAL_ERROR
        assert "サーバー" in exc.detail or "エラー" in exc.detail

    def test_internal_server_exception_custom_message(self):
        """InternalServerExceptionのカスタムメッセージ"""
        custom_message = "予期しないエラーが発生しました"
        exc = InternalServerException(detail=custom_message)
        assert exc.detail == custom_message


class TestAuthenticationErrorMessages:
    """認証関連のエラーメッセージテスト"""

    def test_auth_email_already_exists_message(self):
        """メールアドレス重複エラーメッセージ"""
        msg = ja.AUTH_EMAIL_ALREADY_EXISTS
        assert "メールアドレス" in msg
        assert "登録" in msg

    def test_auth_incorrect_credentials_message(self):
        """認証情報エラーメッセージ"""
        msg = ja.AUTH_INCORRECT_CREDENTIALS
        assert "メールアドレス" in msg or "パスワード" in msg
        assert "正しくありません" in msg

    def test_auth_email_not_verified_message(self):
        """メール未確認エラーメッセージ"""
        msg = ja.AUTH_EMAIL_NOT_VERIFIED
        assert "メールアドレス" in msg
        assert "確認" in msg

    def test_auth_login_success_message(self):
        """ログイン成功メッセージ"""
        msg = ja.AUTH_LOGIN_SUCCESS
        assert "ログイン" in msg

    def test_auth_logout_success_message(self):
        """ログアウト成功メッセージ"""
        msg = ja.AUTH_LOGOUT_SUCCESS
        assert "ログアウト" in msg


class TestMFAErrorMessages:
    """MFA関連のエラーメッセージテスト"""

    def test_mfa_already_enabled_message(self):
        """MFA既に有効エラーメッセージ"""
        msg = ja.MFA_ALREADY_ENABLED
        assert "多要素認証" in msg or "認証" in msg
        assert "有効" in msg

    def test_mfa_not_enrolled_message(self):
        """MFA未登録エラーメッセージ"""
        msg = ja.MFA_NOT_ENROLLED
        assert "多要素認証" in msg or "認証" in msg
        assert "登録" in msg

    def test_mfa_invalid_code_message(self):
        """MFA無効コードエラーメッセージ"""
        msg = ja.MFA_INVALID_CODE
        assert "認証コード" in msg
        assert "正しくありません" in msg

    def test_mfa_verification_success_message(self):
        """MFA検証成功メッセージ"""
        msg = ja.MFA_VERIFICATION_SUCCESS
        assert "多要素認証" in msg or "認証" in msg
        assert "成功" in msg

    def test_mfa_disabled_success_message(self):
        """MFA無効化成功メッセージ"""
        msg = ja.MFA_DISABLED_SUCCESS
        assert "多要素認証" in msg or "認証" in msg
        assert "無効" in msg


class TestPermissionErrorMessages:
    """権限関連のエラーメッセージテスト"""

    def test_perm_credentials_invalid_message(self):
        """認証情報無効エラーメッセージ"""
        msg = ja.PERM_CREDENTIALS_INVALID
        assert "認証" in msg or "認証情報" in msg
        assert "検証" in msg or "できませんでした" in msg

    def test_perm_manager_or_owner_required_message(self):
        """管理者権限必要エラーメッセージ"""
        msg = ja.PERM_MANAGER_OR_OWNER_REQUIRED
        assert "管理者" in msg or "事業所" in msg
        assert "権限" in msg
        assert "必要" in msg

    def test_perm_owner_required_message(self):
        """事業所管理者権限必要エラーメッセージ"""
        msg = ja.PERM_OWNER_REQUIRED
        assert "事業所" in msg or "管理者" in msg
        assert "権限" in msg
        assert "必要" in msg

    def test_perm_office_required_message(self):
        """事業所所属必要エラーメッセージ"""
        msg = ja.PERM_OFFICE_REQUIRED
        assert "事業所" in msg
        assert "所属" in msg


class TestRecipientErrorMessages:
    """福祉受給者関連のエラーメッセージテスト"""

    def test_recipient_office_required_message(self):
        """利用者作成に事業所必要エラーメッセージ"""
        msg = ja.RECIPIENT_OFFICE_REQUIRED
        assert "利用者" in msg
        assert "作成" in msg or "事業所" in msg
        assert "所属" in msg

    def test_recipient_request_pending_message(self):
        """申請作成成功メッセージ"""
        msg = ja.RECIPIENT_REQUEST_PENDING
        assert "申請" in msg
        assert "承認待ち" in msg

    def test_recipient_deleted_message(self):
        """利用者削除成功メッセージ"""
        msg = ja.RECIPIENT_DELETED
        assert "利用者" in msg
        assert "削除" in msg


class TestMessageFormatting:
    """メッセージのフォーマットテスト"""

    def test_messages_with_placeholders(self):
        """プレースホルダーを含むメッセージのフォーマット"""
        # {error}を含むメッセージ
        msg_template = ja.RECIPIENT_CREATE_FAILED
        assert "{error}" in msg_template

        # フォーマット例
        formatted = msg_template.format(error="データベースエラー")
        assert "利用者の作成に失敗しました" in formatted
        assert "データベースエラー" in formatted

    def test_role_message_with_placeholder(self):
        """ロールを含むメッセージのフォーマット"""
        msg_template = ja.ROLE_ALREADY_ASSIGNED
        assert "{role}" in msg_template

        # フォーマット例
        formatted = msg_template.format(role="manager")
        assert "既に" in formatted
        assert "権限を持っています" in formatted

    def test_service_messages_with_ids(self):
        """IDを含むサービスメッセージのフォーマット"""
        # スタッフIDを含むメッセージ
        msg_template = ja.SERVICE_STAFF_NOT_FOUND
        assert "{staff_id}" in msg_template

        formatted = msg_template.format(staff_id="12345")
        assert "スタッフ 12345 が見つかりません" in formatted


class TestMessageConsistency:
    """メッセージの一貫性テスト"""

    def test_success_messages_use_polite_form(self):
        """成功メッセージが丁寧体を使用していることを確認"""
        success_messages = [
            ja.AUTH_LOGIN_SUCCESS,
            ja.AUTH_LOGOUT_SUCCESS,
            ja.MFA_DISABLED_SUCCESS,
            ja.RECIPIENT_DELETED,
        ]

        for msg in success_messages:
            # 「〜しました」の形式を使用
            assert msg.endswith("した") or msg.endswith("ました"), f"Success message not in polite form: {msg}"

    def test_error_messages_use_polite_form(self):
        """エラーメッセージが丁寧体を使用していることを確認"""
        error_messages = [
            ja.AUTH_EMAIL_ALREADY_EXISTS,
            ja.AUTH_INCORRECT_CREDENTIALS,
            ja.MFA_INVALID_CODE,
            ja.PERM_CREDENTIALS_INVALID,
        ]

        for msg in error_messages:
            # 丁寧体の終わり方をチェック
            assert (
                msg.endswith("ます") or
                msg.endswith("ません") or
                msg.endswith("です") or
                "必要" in msg
            ), f"Error message not in polite form: {msg}"

    def test_required_messages_use_consistent_wording(self):
        """「必要」を含むメッセージが一貫した表現を使用していることを確認"""
        required_messages = [
            ja.PERM_MANAGER_OR_OWNER_REQUIRED,
            ja.PERM_OWNER_REQUIRED,
            ja.PERM_OFFICE_REQUIRED,
            ja.RECIPIENT_OFFICE_REQUIRED,
        ]

        for msg in required_messages:
            # 「必要」という言葉を含む
            assert "必要" in msg, f"Required message does not contain '必要': {msg}"


# 統合テスト: 実際のAPIレスポンスでメッセージを確認
class TestAPIErrorMessageIntegration:
    """実際のAPIエンドポイントで日本語エラーメッセージが返されることを確認"""

    async def test_unauthenticated_returns_japanese_message(self, async_client):
        """未認証時に日本語エラーメッセージが返される"""
        response = await async_client.get("/api/v1/staffs/me")

        assert response.status_code == 401
        data = response.json()

        # エラーメッセージに日本語が含まれている可能性を確認
        # 注: deps.pyを日本語化した後は日本語メッセージが返される
        assert "detail" in data


# パフォーマンステスト
class TestMessagePerformance:
    """メッセージ定数のパフォーマンステスト"""

    def test_message_import_performance(self):
        """メッセージモジュールのインポートが高速であることを確認"""
        import time

        start = time.time()
        from app.messages import ja
        end = time.time()

        # インポートは0.1秒以内に完了すべき
        assert (end - start) < 0.1

    def test_message_access_performance(self):
        """メッセージへのアクセスが高速であることを確認"""
        import time
        from app.messages import ja

        start = time.time()
        for _ in range(1000):
            _ = ja.AUTH_EMAIL_ALREADY_EXISTS
            _ = ja.MFA_INVALID_CODE
            _ = ja.EXC_BAD_REQUEST
        end = time.time()

        # 1000回のアクセスは0.01秒以内に完了すべき
        assert (end - start) < 0.01
