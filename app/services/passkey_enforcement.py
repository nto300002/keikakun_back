"""app_adminのパスキー強制化ポリシー。"""

import datetime

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.crud_webauthn import crud_webauthn
from app.models.staff import Staff


class PasskeyEnforcementService:
    async def enforce(self, db: AsyncSession, *, staff: Staff) -> Staff:
        """有効credentialを2件以上保持する本人だけ強制化できる。"""
        credentials = await crud_webauthn.get_active_credentials_for_update(db, staff_id=staff.id)
        if len(credentials) < 2:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="パスキーを2つ以上登録してから強制化してください",
            )
        staff.passkey_enforced_at = datetime.datetime.now(datetime.timezone.utc)
        try:
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        return staff


passkey_enforcement_service = PasskeyEnforcementService()
