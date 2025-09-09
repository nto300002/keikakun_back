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
        mfa_secret = generate_totp_secret()
        user.mfa_secret = mfa_secret
        # is_mfa_enabled は verify で有効にするのでここでは True にしない
        await self.db.commit()
        await self.db.refresh(user)

        qr_code_uri = generate_totp_uri(user.email, mfa_secret)

        return {"secret_key": mfa_secret, "qr_code_uri": qr_code_uri}

    async def verify(self, user: models.Staff, totp_code: str) -> bool:
        if not user.mfa_secret:
            return False

        # TODO: mfa_secretが暗号化されている場合はここで復号する
        # secret = decrypt_mfa_secret(user.mfa_secret)
        secret = user.mfa_secret

        if verify_totp(secret=secret, token=totp_code):
            user.is_mfa_enabled = True
            await self.db.commit()
            return True
        
        return False
