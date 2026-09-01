"""WebAuthn credentialとchallengeのデータアクセス。"""

import datetime
import uuid
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.webauthn import hash_challenge
from app.models.webauthn import (
    WebAuthnAuthenticationSession,
    WebAuthnCeremony,
    WebAuthnChallenge,
    WebAuthnCredential,
)


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

    async def create_authentication_session(
        self, db: AsyncSession, *, staff_id: uuid.UUID, token: bytes
    ) -> WebAuthnAuthenticationSession:
        record = WebAuthnAuthenticationSession(
            staff_id=staff_id,
            token_hash=hash_challenge(token),
            expires_at=datetime.datetime.now(datetime.timezone.utc) + MAX_CHALLENGE_TTL,
        )
        db.add(record)
        return record

    async def get_authentication_session(
        self, db: AsyncSession, *, token: bytes
    ) -> WebAuthnAuthenticationSession | None:
        result = await db.execute(
            select(WebAuthnAuthenticationSession)
            .where(WebAuthnAuthenticationSession.token_hash == hash_challenge(token))
            .where(WebAuthnAuthenticationSession.used_at.is_(None))
            .where(WebAuthnAuthenticationSession.expires_at > func.now())
        )
        return result.scalar_one_or_none()

    async def consume_authentication_session(
        self, db: AsyncSession, *, token: bytes
    ) -> WebAuthnAuthenticationSession | None:
        result = await db.execute(
            update(WebAuthnAuthenticationSession)
            .where(WebAuthnAuthenticationSession.token_hash == hash_challenge(token))
            .where(WebAuthnAuthenticationSession.used_at.is_(None))
            .where(WebAuthnAuthenticationSession.expires_at > func.now())
            .values(used_at=func.now())
            .returning(WebAuthnAuthenticationSession)
        )
        return result.scalar_one_or_none()

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

    async def get_active_credentials(
        self, db: AsyncSession, *, staff_id: uuid.UUID
    ) -> list[WebAuthnCredential]:
        """本人の有効なcredentialだけを作成日時順で返す。"""
        result = await db.execute(
            select(WebAuthnCredential)
            .where(WebAuthnCredential.staff_id == staff_id)
            .where(WebAuthnCredential.revoked_at.is_(None))
            .order_by(WebAuthnCredential.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_active_credential_by_credential_id(
        self, db: AsyncSession, *, credential_id: bytes
    ) -> WebAuthnCredential | None:
        result = await db.execute(
            select(WebAuthnCredential)
            .where(WebAuthnCredential.credential_id == credential_id)
            .where(WebAuthnCredential.revoked_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_active_credential_by_credential_id_for_update(
        self, db: AsyncSession, *, credential_id: bytes
    ) -> WebAuthnCredential | None:
        """認証中のsign count更新競合を防ぐためcredential行をロックする。"""
        result = await db.execute(
            select(WebAuthnCredential)
            .where(WebAuthnCredential.credential_id == credential_id)
            .where(WebAuthnCredential.revoked_at.is_(None))
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def update_authentication_use(
        self, db: AsyncSession, *, credential_id: bytes, sign_count: int
    ) -> WebAuthnCredential | None:
        result = await db.execute(
            update(WebAuthnCredential)
            .where(WebAuthnCredential.credential_id == credential_id)
            .where(WebAuthnCredential.revoked_at.is_(None))
            .values(sign_count=sign_count, last_used_at=func.now())
            .returning(WebAuthnCredential)
        )
        return result.scalar_one_or_none()

    async def get_active_credentials_for_update(
        self, db: AsyncSession, *, staff_id: uuid.UUID
    ) -> list[WebAuthnCredential]:
        """失効判定中の競合を防ぐため、本人の有効credentialを行ロックして返す。"""
        result = await db.execute(
            select(WebAuthnCredential)
            .where(WebAuthnCredential.staff_id == staff_id)
            .where(WebAuthnCredential.revoked_at.is_(None))
            .order_by(WebAuthnCredential.created_at.asc())
            .with_for_update()
        )
        return list(result.scalars().all())

    async def revoke_credential(
        self,
        db: AsyncSession,
        *,
        staff_id: uuid.UUID,
        credential_id: uuid.UUID,
    ) -> WebAuthnCredential | None:
        """本人所有かつ有効なcredentialだけを論理削除する。"""
        result = await db.execute(
            update(WebAuthnCredential)
            .where(WebAuthnCredential.id == credential_id)
            .where(WebAuthnCredential.staff_id == staff_id)
            .where(WebAuthnCredential.revoked_at.is_(None))
            .values(revoked_at=func.now())
            .returning(WebAuthnCredential)
        )
        return result.scalar_one_or_none()

    async def update_display_name(
        self,
        db: AsyncSession,
        *,
        staff_id: uuid.UUID,
        credential_id: uuid.UUID,
        display_name: str,
    ) -> WebAuthnCredential | None:
        """本人所有かつ有効なcredentialの表示名だけを更新する。"""
        result = await db.execute(
            update(WebAuthnCredential)
            .where(WebAuthnCredential.id == credential_id)
            .where(WebAuthnCredential.staff_id == staff_id)
            .where(WebAuthnCredential.revoked_at.is_(None))
            .values(display_name=display_name)
            .returning(WebAuthnCredential)
        )
        return result.scalar_one_or_none()


crud_webauthn = CRUDWebAuthn()
