import pytest
import secrets
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from app.core.security import (
    generate_totp_secret,
    generate_qr_code,
    verify_totp,
    generate_recovery_codes,
    hash_recovery_code,
    verify_recovery_code,
    create_temporary_token,
    verify_temporary_token,
)


class TestTOTPFunctions:
    """TOTP関連関数のユニットテスト"""
    
    def test_generate_totp_secret(self):
        """TOTPシークレット生成のテスト"""
        secret1 = generate_totp_secret()
        secret2 = generate_totp_secret()
        
        # 32文字のBase32文字列であること
        assert len(secret1) == 32
        assert len(secret2) == 32
        assert secret1 != secret2  # 毎回異なる値が生成されること
        
        # Base32文字のみで構成されていること
        valid_chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
        assert all(c in valid_chars for c in secret1)
        
    def test_generate_qr_code(self):
        """QRコード生成のテスト"""
        secret = generate_totp_secret()
        email = "test@example.com"
        
        qr_code = generate_qr_code(secret, email)
        
        # Data URLフォーマットであること
        assert qr_code.startswith("data:image/png;base64,")
        assert len(qr_code) > 100  # Base64エンコードされた画像データなので十分な長さ
        
    def test_generate_qr_code_with_issuer(self):
        """発行者付きQRコード生成のテスト"""
        secret = generate_totp_secret()
        email = "test@example.com"
        issuer = "KeikakuApp"
        
        qr_code = generate_qr_code(secret, email, issuer)
        
        assert qr_code.startswith("data:image/png;base64,")
        # 実際のQRコードにissuer情報が含まれていることは、
        # QRコードをデコードしないと確認できないため省略
        
    @patch('pyotp.TOTP.verify')
    def test_verify_totp_success(self, mock_verify):
        """TOTP検証成功のテスト"""
        mock_verify.return_value = True
        
        secret = generate_totp_secret()
        code = "123456"
        
        result = verify_totp(secret, code)
        
        assert result is True
        mock_verify.assert_called_once_with(code, valid_window=1)
        
    @patch('pyotp.TOTP.verify')
    def test_verify_totp_failure(self, mock_verify):
        """TOTP検証失敗のテスト"""
        mock_verify.return_value = False
        
        secret = generate_totp_secret()
        code = "000000"
        
        result = verify_totp(secret, code)
        
        assert result is False
        
    def test_verify_totp_invalid_secret(self):
        """無効なシークレットでのTOTP検証テスト"""
        # 無効なシークレットはFalseを返す（例外ではない）
        result = verify_totp("invalid_secret", "123456")
        assert result is False
            
    def test_verify_totp_invalid_code_format(self):
        """無効なコード形式でのTOTP検証テスト"""
        secret = generate_totp_secret()
        
        # 6桁以外のコード
        assert verify_totp(secret, "12345") is False
        assert verify_totp(secret, "1234567") is False
        assert verify_totp(secret, "abc123") is False
        assert verify_totp(secret, "") is False


class TestRecoveryCodeFunctions:
    """リカバリーコード関連関数のユニットテスト"""
    
    def test_generate_recovery_codes(self):
        """リカバリーコード生成のテスト"""
        codes = generate_recovery_codes()
        
        assert len(codes) == 10  # 10個のコード
        assert len(set(codes)) == 10  # 全て異なるコード
        
        for code in codes:
            assert len(code) == 19  # 19文字（4-4-4-4形式: 16文字+3つのハイフン）
            assert code.replace('-', '').isalnum()  # 英数字とハイフンのみ
            assert code.count('-') == 3  # ハイフン3個（4-4-4-4形式）
            
    def test_hash_recovery_code(self):
        """リカバリーコードハッシュ化のテスト"""
        code = "ABCD-EFGH-IJKL-MNOP"
        
        hash1 = hash_recovery_code(code)
        hash2 = hash_recovery_code(code)
        
        # bcryptは毎回異なるソルトを使うため、ハッシュは異なる
        assert hash1 != hash2  # 異なるハッシュ（異なるソルト）
        assert hash1 != code  # ハッシュ化されている
        assert len(hash1) > 32  # bcryptハッシュは十分長い
        
        # 両方とも正しいハッシュであることを検証で確認
        assert verify_recovery_code(code, hash1) is True
        assert verify_recovery_code(code, hash2) is True
        
    def test_verify_recovery_code_success(self):
        """リカバリーコード検証成功のテスト"""
        code = "ABCD-EFGH-IJKL-MNOP"
        hashed = hash_recovery_code(code)
        
        result = verify_recovery_code(code, hashed)
        
        assert result is True
        
    def test_verify_recovery_code_failure(self):
        """リカバリーコード検証失敗のテスト"""
        code = "ABCD-EFGH-IJKL-MNOP"
        wrong_code = "WXYZ-UVTS-RQPO-NMLK"
        hashed = hash_recovery_code(code)
        
        result = verify_recovery_code(wrong_code, hashed)
        
        assert result is False
        
    def test_verify_recovery_code_invalid_hash(self):
        """無効なハッシュでのリカバリーコード検証テスト"""
        code = "ABCD-EFGH-IJKL-MNOP"
        
        result = verify_recovery_code(code, "invalid_hash")
        
        assert result is False


class TestTemporaryTokenFunctions:
    """一時トークン関連関数のユニットテスト"""
    
    def test_create_temporary_token(self):
        """一時トークン生成のテスト"""
        user_id = "123e4567-e89b-12d3-a456-426614174000"
        token_type = "mfa_setup"
        
        token = create_temporary_token(user_id, token_type)
        
        assert isinstance(token, str)
        assert len(token) > 100  # JWTトークンは十分長い
        
    def test_create_temporary_token_different_types(self):
        """異なるタイプの一時トークン生成テスト"""
        user_id = "123e4567-e89b-12d3-a456-426614174000"
        
        token1 = create_temporary_token(user_id, "mfa_setup")
        token2 = create_temporary_token(user_id, "mfa_verification")
        
        assert token1 != token2  # タイプが異なれば異なるトークン
        
    def test_verify_temporary_token_success(self):
        """一時トークン検証成功のテスト"""
        user_id = "123e4567-e89b-12d3-a456-426614174000"
        token_type = "mfa_setup"
        
        token = create_temporary_token(user_id, token_type)
        result = verify_temporary_token(token, token_type)
        
        assert result == user_id
        
    def test_verify_temporary_token_wrong_type(self):
        """間違ったタイプでの一時トークン検証テスト"""
        user_id = "123e4567-e89b-12d3-a456-426614174000"
        
        token = create_temporary_token(user_id, "mfa_setup")
        result = verify_temporary_token(token, "mfa_verification")
        
        assert result is None
        
    def test_verify_temporary_token_invalid(self):
        """無効な一時トークン検証テスト"""
        result = verify_temporary_token("invalid_token", "mfa_setup")
        
        assert result is None
        
    def test_verify_temporary_token_expired(self):
        """期限切れ一時トークン検証テスト"""
        user_id = "123e4567-e89b-12d3-a456-426614174000"
        token_type = "mfa_setup"
        
        # 有効期限を負の値（既に期限切れ）に設定してトークンを作成
        token = create_temporary_token(user_id, token_type, expires_minutes=-1)
        
        result = verify_temporary_token(token, token_type)
        
        # 負の有効期限なので期限切れとなりNoneが返される
        assert result is None  # 期限切れなのでNone


class TestMFASecurityHelpers:
    """MFAセキュリティヘルパー関数のテスト"""
    
    def test_sanitize_totp_code(self):
        """TOTPコード正規化のテスト"""
        from app.core.security import sanitize_totp_code
        
        # 正常なケース
        assert sanitize_totp_code("123456") == "123456"
        assert sanitize_totp_code(" 123456 ") == "123456"  # 空白削除
        
        # 無効なケース
        assert sanitize_totp_code("12345") is None  # 短すぎる
        assert sanitize_totp_code("1234567") is None  # 長すぎる
        assert sanitize_totp_code("12345a") is None  # 非数字
        assert sanitize_totp_code("") is None  # 空文字
        assert sanitize_totp_code(None) is None  # None
        
    def test_is_recovery_code_format(self):
        """リカバリーコード形式チェックのテスト"""
        from app.core.security import is_recovery_code_format
        
        # 正常なケース
        assert is_recovery_code_format("ABCD-EFGH-IJKL-MNOP") is True
        assert is_recovery_code_format("1234-5678-9ABC-DEFG") is True
        
        # 無効なケース
        assert is_recovery_code_format("ABCD-EFGH-IJKL") is False  # 短い
        assert is_recovery_code_format("ABCD-EFGH-IJKL-MNOP-QRST") is False  # 長い
        assert is_recovery_code_format("ABCDEFGHIJKLMNOP") is False  # ハイフンなし
        assert is_recovery_code_format("ABCD_EFGH_IJKL_MNOP") is False  # 違う区切り文字
        assert is_recovery_code_format("") is False  # 空文字
        
    def test_mask_recovery_codes(self):
        """リカバリーコードマスキングのテスト"""
        from app.core.security import mask_recovery_codes
        
        codes = ["ABCD-EFGH-IJKL-MNOP", "1234-5678-9ABC-DEFG"]
        masked = mask_recovery_codes(codes)
        
        assert len(masked) == 2
        assert masked[0] == "ABCD-****-****-MNOP"
        assert masked[1] == "1234-****-****-DEFG"
        
    def test_get_mfa_backup_info(self):
        """MFAバックアップ情報生成のテスト"""
        from app.core.security import get_mfa_backup_info
        
        recovery_codes = ["ABCD-EFGH-IJKL-MNOP", "1234-5678-9ABC-DEFG"]
        info = get_mfa_backup_info(recovery_codes)
        
        assert "total_codes" in info
        assert "codes_remaining" in info
        assert "last_used" in info
        assert info["total_codes"] == 2
        assert info["codes_remaining"] == 2