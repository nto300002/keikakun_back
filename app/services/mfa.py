from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import (
    generate_totp_secret,
    generate_totp_uri,
    verify_totp,
    decrypt_mfa_secret,
)
from app import models, crud

class MfaService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def enroll(self, user: models.Staff) -> dict[str, str]:
        import logging
        logger = logging.getLogger(__name__)

        # 平文のMFAシークレットを生成
        mfa_secret = generate_totp_secret()
        logger.info(f"[MFA ENROLL] Generated secret for user {user.email}. Secret length: {len(mfa_secret)}")

        # 暗号化して保存
        user.set_mfa_secret(mfa_secret)
        logger.info(f"[MFA ENROLL] Secret encrypted and set. Encrypted length: {len(user.mfa_secret)}")

        # is_mfa_enabled は verify で有効にするのでここでは True にしない
        # NOTE: トランザクション管理はエンドポイント層で行う
        logger.info(f"[MFA ENROLL] Enroll completed. DB secret length: {len(user.mfa_secret) if user.mfa_secret else 0}")

        # QRコードURIは平文のシークレットを使用
        qr_code_uri = generate_totp_uri(user.email, mfa_secret)

        # 平文のシークレットをレスポンスとして返す（ユーザーが手動で入力する場合のため）
        return {"secret_key": mfa_secret, "qr_code_uri": qr_code_uri}

    async def verify(self, user: models.Staff, totp_code: str) -> bool:
        import logging
        logger = logging.getLogger(__name__)

        if not user.mfa_secret:
            logger.warning(f"[MFA VERIFY] No mfa_secret for user {user.email}")
            return False

        logger.info(f"[MFA VERIFY] Starting verification for user {user.email}. Encrypted secret length: {len(user.mfa_secret)}")

        # mfa_secretは暗号化されているため、復号化が必要
        try:
            secret = user.get_mfa_secret()
        except ValueError as e:
            # 復号化失敗をログに記録して False を返す
            logger.error(f"[MFA VERIFY] Decryption failed for user {user.email}: {str(e)}")
            return False

        if not secret:
            logger.warning(f"[MFA VERIFY] Decryption returned None for user {user.email}")
            return False

        logger.info(f"[MFA VERIFY] Decrypted secret length: {len(secret)}")

        if verify_totp(secret=secret, token=totp_code):
            user.is_mfa_enabled = True
            # NOTE: トランザクション管理はエンドポイント層で行う（テストではコミットが必要）
            logger.info(f"[MFA VERIFY] Verification successful for user {user.email}")
            return True

        logger.warning(f"[MFA VERIFY] Verification failed for user {user.email}")
        return False

    async def verify_totp_code(self, user: models.Staff, totp_code: str) -> bool:
        """
        TOTPコードを検証する（コミットなし）

        エンドポイント層でトランザクション管理を行う場合に使用します。
        このメソッドは検証のみを行い、データベースへの変更はコミットしません。

        Args:
            user: 検証対象のユーザー
            totp_code: 検証するTOTPコード

        Returns:
            bool: 検証が成功した場合True、失敗した場合False
        """
        import logging
        logger = logging.getLogger(__name__)

        if not user.mfa_secret:
            logger.warning(f"[MFA VERIFY] No mfa_secret for user {user.email}")
            return False

        logger.info(f"[MFA VERIFY TOTP] Starting verification for user {user.email}")

        # mfa_secretは暗号化されているため、復号化が必要
        try:
            secret = user.get_mfa_secret()
        except ValueError as e:
            # 復号化失敗をログに記録して False を返す
            logger.error(f"[MFA VERIFY TOTP] Decryption failed for user {user.email}: {str(e)}")
            return False

        if not secret:
            logger.warning(f"[MFA VERIFY TOTP] Decryption returned None for user {user.email}")
            return False

        logger.info(f"[MFA VERIFY TOTP] Decrypted secret length: {len(secret)}")

        # TOTP検証のみ実行（コミットしない）
        is_valid = verify_totp(secret=secret, token=totp_code)

        if is_valid:
            logger.info(f"[MFA VERIFY TOTP] Verification successful for user {user.email}")
        else:
            logger.warning(f"[MFA VERIFY TOTP] Verification failed for user {user.email}")

        return is_valid
