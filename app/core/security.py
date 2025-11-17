import os
import secrets
import string
import base64
from datetime import datetime, timedelta, timezone
from typing import Any, Union, Optional, List
from io import BytesIO

from jose import jwt
from passlib.context import CryptContext
import pyotp
import qrcode
from cryptography.fernet import Fernet

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7  # リフレッシュトークンの有効期限（7日間）
EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS = 24 # メール確認トークンの有効期限（24時間）

# MFA関連の定数
TEMPORARY_TOKEN_EXPIRE_MINUTES = 10  # 一時トークンの有効期限（10分）
TOTP_WINDOW = 1  # TOTP検証時間窓（30秒 * 1 = 前後30秒）
RECOVERY_CODE_COUNT = 10  # 生成するリカバリーコード数
MFA_APP_NAME = "KeikakuApp"  # TOTP アプリに表示される名前


def create_email_verification_token(email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS)
    to_encode = {"exp": expire, "sub": email, "scope": "email_verification"}
    secret_key = os.getenv("SECRET_KEY", "test_secret_key_for_pytest")
    encoded_jwt = jwt.encode(to_encode, secret_key, algorithm=ALGORITHM)
    return encoded_jwt

def verify_email_verification_token(token: str) -> str | None:
    try:
        secret_key = os.getenv("SECRET_KEY", "test_secret_key_for_pytest")
        payload = jwt.decode(token, secret_key, algorithms=[ALGORITHM])
        if payload.get("scope") == "email_verification":
            return payload.get("sub")
        return None
    except jwt.JWTError:
        return None


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(
    subject: Union[str, Any],
    expires_delta: timedelta = None,
    expires_delta_seconds: int = None,
    session_type: str = "standard"
) -> str:
    now = datetime.now(timezone.utc)

    if expires_delta_seconds:
        expire = now + timedelta(seconds=expires_delta_seconds)
    elif expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    # セッション期間を秒で計算
    session_duration = int((expire - now).total_seconds())

    to_encode = {
        "exp": expire,
        "sub": str(subject),
        "iat": now,
        "session_type": session_type,
        "session_duration": session_duration
    }
    secret_key = os.getenv("SECRET_KEY", "test_secret_key_for_pytest")
    encoded_jwt = jwt.encode(to_encode, secret_key, algorithm=ALGORITHM)
    return encoded_jwt

def create_refresh_token(
    subject: Union[str, Any],
    session_duration: int = 3600,
    session_type: str = "standard"
) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode = {
        "exp": expire,
        "sub": str(subject),
        "session_duration": session_duration,
        "session_type": session_type
    }
    secret_key = os.getenv("SECRET_KEY", "test_secret_key_for_pytest")
    encoded_jwt = jwt.encode(to_encode, secret_key, algorithm=ALGORITHM)
    return encoded_jwt


# =====================================================================
# MFA (Multi-Factor Authentication) 関連の関数
# =====================================================================

def get_encryption_key() -> bytes:
    """暗号化キーを取得（環境変数またはシークレットキーから生成）"""
    key_source = os.getenv("ENCRYPTION_KEY", os.getenv("SECRET_KEY", "test_secret_key_for_pytest"))
    # Fernetキーは32バイト必要なので、適切な長さに調整
    key_bytes = key_source.encode()[:32].ljust(32, b'0')
    return base64.urlsafe_b64encode(key_bytes)


def encrypt_mfa_secret(secret: str) -> str:
    """MFAシークレットを暗号化"""
    fernet = Fernet(get_encryption_key())
    encrypted = fernet.encrypt(secret.encode())
    return base64.urlsafe_b64encode(encrypted).decode()


def decrypt_mfa_secret(encrypted_secret: str) -> str:
    """MFAシークレットを復号"""
    fernet = Fernet(get_encryption_key())
    encrypted_bytes = base64.urlsafe_b64decode(encrypted_secret.encode())
    decrypted = fernet.decrypt(encrypted_bytes)
    return decrypted.decode()


def generate_totp_secret() -> str:
    """TOTPシークレットを生成"""
    return pyotp.random_base32()


def generate_totp_uri(email: str, secret: str, issuer_name: str = MFA_APP_NAME) -> str:
    """TOTPプロビジョニングURIを生成"""
    return pyotp.totp.TOTP(secret).provisioning_uri(
        name=email, issuer_name=issuer_name
    )


def generate_qr_code(secret: str, email: str, issuer: Optional[str] = None) -> str:
    """QRコードを生成してBase64エンコードした画像データURLを返す"""
    if issuer is None:
        issuer = MFA_APP_NAME
    
    # TOTP URIを生成
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(
        name=email,
        issuer_name=issuer
    )
    
    # QRコードを生成
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(provisioning_uri)
    qr.make(fit=True)
    
    # 画像を作成
    img = qr.make_image(fill_color="black", back_color="white")
    
    # BytesIOを使ってBase64エンコード
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    img_str = base64.b64encode(buffer.getvalue()).decode()
    
    return f"data:image/png;base64,{img_str}"


def verify_totp(secret: str, token: str, window: int = TOTP_WINDOW) -> bool:
    """TOTPトークンを検証"""
    import logging
    logger = logging.getLogger(__name__)

    try:
        logger.info(f"[TOTP VERIFY] Starting verification")
        logger.info(f"[TOTP VERIFY] Secret exists: {bool(secret)}, Token: {token}")

        if not secret or not token:
            logger.warning(f"[TOTP VERIFY] Missing secret or token")
            return False

        # トークンを正規化（空白除去、6桁チェック）
        original_token = token
        token = sanitize_totp_code(token)
        logger.info(f"[TOTP VERIFY] Original token: {original_token}, Sanitized token: {token}")

        if not token:
            logger.warning(f"[TOTP VERIFY] Token sanitization failed")
            return False

        totp = pyotp.TOTP(secret)
        result = totp.verify(token, valid_window=window)
        logger.info(f"[TOTP VERIFY] Verification result: {result}")

        # デバッグ用: 現在の時刻で生成されるコードを確認
        current_code = totp.now()
        logger.info(f"[TOTP VERIFY] Current valid code would be: {current_code}")

        return result
    except Exception as e:
        logger.error(f"[TOTP VERIFY] Exception occurred: {str(e)}")
        return False


def sanitize_totp_code(code: str) -> Optional[str]:
    """TOTPコードを正規化"""
    if not code:
        return None
    
    # 空白を除去
    code = code.strip().replace(" ", "")
    
    # 6桁の数字でない場合はNone
    if len(code) != 6 or not code.isdigit():
        return None
    
    return code


def generate_recovery_codes(count: int = RECOVERY_CODE_COUNT) -> List[str]:
    """リカバリーコードを生成"""
    codes = []
    for _ in range(count):
        # 4-4-4-4 形式のコードを生成
        groups = []
        for _ in range(4):
            group = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4))
            groups.append(group)
        code = '-'.join(groups)
        codes.append(code)
    
    return codes


def hash_recovery_code(code: str) -> str:
    """リカバリーコードをハッシュ化"""
    return pwd_context.hash(code)


def verify_recovery_code(code: str, hashed_code: str) -> bool:
    """リカバリーコードを検証"""
    try:
        if not is_recovery_code_format(code):
            return False
        return pwd_context.verify(code, hashed_code)
    except Exception:
        return False


def is_recovery_code_format(code: str) -> bool:
    """リカバリーコードの形式をチェック"""
    if not code:
        return False
    
    # 4-4-4-4 形式をチェック
    parts = code.split('-')
    if len(parts) != 4:
        return False
    
    for part in parts:
        if len(part) != 4 or not part.isalnum():
            return False
    
    return True


def create_temporary_token(
    user_id: str,
    token_type: str,
    expires_minutes: int = TEMPORARY_TOKEN_EXPIRE_MINUTES,
    session_duration: int = None,
    session_type: str = "standard"
) -> str:
    """一時トークンを生成"""
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    to_encode = {
        "exp": expire,
        "sub": str(user_id),
        "type": token_type,
        "scope": "temporary"
    }

    # セッション情報を追加（MFA検証時に元のセッション設定を保持するため）
    if session_duration is not None:
        to_encode["session_duration"] = session_duration
        to_encode["session_type"] = session_type

    secret_key = os.getenv("SECRET_KEY", "test_secret_key_for_pytest")
    encoded_jwt = jwt.encode(to_encode, secret_key, algorithm=ALGORITHM)
    return encoded_jwt


def verify_temporary_token(token: str, expected_type: str) -> Optional[str]:
    """一時トークンを検証してユーザーIDを返す（後方互換性のため）"""
    try:
        secret_key = os.getenv("SECRET_KEY", "test_secret_key_for_pytest")
        payload = jwt.decode(token, secret_key, algorithms=[ALGORITHM])

        # スコープとタイプをチェック
        if payload.get("scope") != "temporary":
            return None
        if payload.get("type") != expected_type:
            return None

        return payload.get("sub")
    except jwt.JWTError:
        return None


def verify_temporary_token_with_session(token: str, expected_type: str) -> Optional[dict]:
    """一時トークンを検証してユーザーIDとセッション情報を返す"""
    try:
        secret_key = os.getenv("SECRET_KEY", "test_secret_key_for_pytest")
        payload = jwt.decode(token, secret_key, algorithms=[ALGORITHM])

        # スコープとタイプをチェック
        if payload.get("scope") != "temporary":
            return None
        if payload.get("type") != expected_type:
            return None

        return {
            "user_id": payload.get("sub"),
            "session_duration": payload.get("session_duration", 3600),  # デフォルト1時間
            "session_type": payload.get("session_type", "standard")
        }
    except jwt.JWTError:
        return None


def mask_recovery_codes(codes: List[str]) -> List[str]:
    """リカバリーコードを部分的にマスキング"""
    masked = []
    for code in codes:
        parts = code.split('-')
        if len(parts) == 4:
            masked_code = f"{parts[0]}-****-****-{parts[3]}"
            masked.append(masked_code)
        else:
            masked.append("****-****-****-****")
    return masked


def get_mfa_backup_info(recovery_codes: List[str]) -> dict:
    """MFAバックアップ情報を取得"""
    return {
        "total_codes": len(recovery_codes),
        "codes_remaining": len(recovery_codes),
        "last_used": None
    }
def decode_access_token(token: str) -> Optional[dict]:
    """アクセストークンをデコードしてペイロードを返す。無効な場合は None を返す。"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.JWTError:
        return None
