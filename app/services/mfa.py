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

        # 暗号化して保存
        user.set_mfa_secret(mfa_secret)

        # is_mfa_enabled は verify で有効にするのでここでは True にしない
        # NOTE: トランザクション管理はエンドポイント層で行う

        # QRコードURIは平文のシークレットを使用
        qr_code_uri = generate_totp_uri(user.email, mfa_secret)

        # 平文のシークレットをレスポンスとして返す（ユーザーが手動で入力する場合のため）
        return {"secret_key": mfa_secret, "qr_code_uri": qr_code_uri}

    async def verify(self, user: models.Staff, totp_code: str) -> bool:
        import logging
        logger = logging.getLogger(__name__)

        if not user.mfa_secret:
            logger.warning("[MFA VERIFY] No mfa_secret for user")
            return False


        # mfa_secretは暗号化されているため、復号化が必要
        try:
            secret = user.get_mfa_secret()
        except ValueError as e:
            # 復号化失敗をログに記録して False を返す
            logger.error("[MFA VERIFY] Decryption failed", exc_info=e)
            return False

        if not secret:
            logger.warning("[MFA VERIFY] Decryption returned None")
            return False


        if verify_totp(secret=secret, token=totp_code):
            user.is_mfa_enabled = True
            # NOTE: トランザクション管理はエンドポイント層で行う（テストではコミットが必要）
            return True

        logger.warning("[MFA VERIFY] Verification failed")
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
            logger.warning("[MFA VERIFY] No mfa_secret for user")
            return False


        # mfa_secretは暗号化されているため、復号化が必要
        try:
            secret = user.get_mfa_secret()
        except ValueError as e:
            # 復号化失敗をログに記録して False を返す
            logger.error("[MFA VERIFY TOTP] Decryption failed", exc_info=e)
            return False

        if not secret:
            logger.warning("[MFA VERIFY TOTP] Decryption returned None")
            return False


        # TOTP検証のみ実行（コミットしない）
        is_valid = verify_totp(secret=secret, token=totp_code)

        if not is_valid:
            logger.warning("[MFA VERIFY TOTP] Verification failed")

        return is_valid
