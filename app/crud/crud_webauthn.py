"""WebAuthn credentialとchallengeのデータアクセス。"""

import datetime
import uuid
from typing import Optional

from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.webauthn import hash_challenge
from app.models.webauthn import WebAuthnCeremony, WebAuthnChallenge


MAX_CHALLENGE_TTL = datetime.timedelta(minutes=5)


class CRUDWebAuthn:
    """WebAuthn ceremonyで共有する、commitを持たないCRUD。"""

    async def create_challenge(
        self,
        db: AsyncSession,
        *,
        staff_id: uuid.UUID,
        ceremony: WebAuthnCeremony | str,
        challenge: bytes,
        session_id: bytes,
    ) -> WebAuthnChallenge:
        """平文を保存せず、サーバー固定の短命challengeを追加する。"""
        ceremony_value = WebAuthnCeremony(ceremony).value
        record = WebAuthnChallenge(
            staff_id=staff_id,
            ceremony=ceremony_value,
            challenge_hash=hash_challenge(challenge),
            session_id_hash=hash_challenge(session_id),
            expires_at=datetime.datetime.now(datetime.timezone.utc) + MAX_CHALLENGE_TTL,
        )
        db.add(record)
        return record

    async def consume_challenge(
        self,
        db: AsyncSession,
        *,
        staff_id: uuid.UUID,
        ceremony: WebAuthnCeremony | str,
        challenge: bytes,
        session_id: bytes,
    ) -> Optional[WebAuthnChallenge]:
        """有効なchallengeを原子的に使用済みにし、再利用時はNoneを返す。"""
        ceremony_value = WebAuthnCeremony(ceremony).value
        query = (
            update(WebAuthnChallenge)
            .where(WebAuthnChallenge.staff_id == staff_id)
            .where(WebAuthnChallenge.ceremony == ceremony_value)
            .where(WebAuthnChallenge.challenge_hash == hash_challenge(challenge))
            .where(WebAuthnChallenge.session_id_hash == hash_challenge(session_id))
            .where(WebAuthnChallenge.used_at.is_(None))
            .where(WebAuthnChallenge.expires_at > func.now())
            .values(used_at=func.now())
            .returning(WebAuthnChallenge)
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()


crud_webauthn = CRUDWebAuthn()
