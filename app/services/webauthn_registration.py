"""app_admin本人のWebAuthn credential登録と管理。"""

import json
import secrets
import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from webauthn import generate_registration_options, verify_registration_response
from webauthn.helpers import options_to_json
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    PublicKeyCredentialType,
    UserVerificationRequirement,
)

from app.core.config import settings
from app.core.webauthn import base64url_decode
from app.crud.crud_audit_log import audit_log as crud_audit_log
from app.crud.crud_webauthn import crud_webauthn
from app.messages import ja
from app.models.staff import Staff
from app.models.webauthn import WebAuthnCeremony, WebAuthnCredential


class WebAuthnRegistrationService:
    """登録ceremonyをサービス境界で完結させる。"""

    async def begin_registration(
        self, db: AsyncSession, *, staff: Staff, session_id: bytes
    ) -> dict:
        """サーバー生成challengeを保存し、UV必須の作成optionsを返す。"""
        if not settings.WEBAUTHN_RP_ID or not settings.WEBAUTHN_RP_NAME:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=ja.WEBAUTHN_UNAVAILABLE,
            )

        challenge = secrets.token_bytes(32)
        credentials = await crud_webauthn.get_active_credentials(db, staff_id=staff.id)
        await crud_webauthn.create_challenge(
            db,
            staff_id=staff.id,
            ceremony=WebAuthnCeremony.registration,
            challenge=challenge,
            session_id=session_id,
        )
        options = generate_registration_options(
            rp_id=settings.WEBAUTHN_RP_ID,
            rp_name=settings.WEBAUTHN_RP_NAME,
            user_id=staff.id.bytes,
            user_name=staff.email,
            user_display_name=staff.full_name,
            challenge=challenge,
            authenticator_selection=AuthenticatorSelectionCriteria(
                user_verification=UserVerificationRequirement.REQUIRED,
            ),
            exclude_credentials=[
                PublicKeyCredentialDescriptor(
                    id=credential.credential_id,
                    type=PublicKeyCredentialType.PUBLIC_KEY,
                )
                for credential in credentials
            ],
        )
        try:
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        return json.loads(options_to_json(options))

    async def verify_registration(
        self,
        db: AsyncSession,
        *,
        staff: Staff,
        session_id: bytes,
        credential: dict,
        display_name: str,
    ) -> WebAuthnCredential:
        """challengeを一度だけ消費してから、UV必須でcredentialを永続化する。"""
        challenge = self._get_client_challenge(credential)
        consumed = await crud_webauthn.consume_challenge(
            db,
            staff_id=staff.id,
            ceremony=WebAuthnCeremony.registration,
            challenge=challenge,
            session_id=session_id,
        )
        if consumed is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ja.WEBAUTHN_CHALLENGE_EXPIRED,
            )

        try:
            verified = verify_registration_response(
                credential=credential,
                expected_challenge=challenge,
                expected_rp_id=settings.WEBAUTHN_RP_ID,
                expected_origin=list(settings.webauthn_allowed_origins),
                require_user_verification=True,
            )
        except Exception as exc:
            # 検証失敗時もchallengeは使い切りにしてreplayを防ぐ。
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ja.WEBAUTHN_REGISTRATION_INVALID,
            ) from exc

        if not verified.user_verified:
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ja.WEBAUTHN_USER_VERIFICATION_REQUIRED,
            )

        credential_record = WebAuthnCredential(
            staff_id=staff.id,
            credential_id=verified.credential_id,
            public_key=verified.credential_public_key,
            sign_count=verified.sign_count,
            transports=self._get_transports(credential),
            aaguid=uuid.UUID(verified.aaguid),
            backup_eligible=verified.credential_device_type.value == "multi_device",
            backup_state=verified.credential_backed_up,
            display_name=display_name,
        )
        db.add(credential_record)
        await self._create_audit_log(db, staff=staff, action="webauthn.credential_registered")
        try:
            await db.commit()
            await db.refresh(credential_record)
        except Exception:
            await db.rollback()
            raise
        return credential_record

    async def list_credentials(
        self, db: AsyncSession, *, staff: Staff
    ) -> list[WebAuthnCredential]:
        return await crud_webauthn.get_active_credentials(db, staff_id=staff.id)

    async def revoke_credential(
        self, db: AsyncSession, *, staff: Staff, credential_id: uuid.UUID
    ) -> bool:
        credentials = await crud_webauthn.get_active_credentials_for_update(
            db, staff_id=staff.id
        )
        if not any(credential.id == credential_id for credential in credentials):
            return False
        if len(credentials) == 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ja.WEBAUTHN_LAST_CREDENTIAL_REVOKE_FORBIDDEN,
            )

        credential = await crud_webauthn.revoke_credential(
            db, staff_id=staff.id, credential_id=credential_id
        )
        if credential is None:
            return False
        await self._create_audit_log(db, staff=staff, action="webauthn.credential_revoked")
        try:
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        return True

    async def update_display_name(
        self,
        db: AsyncSession,
        *,
        staff: Staff,
        credential_id: uuid.UUID,
        display_name: str,
    ) -> WebAuthnCredential | None:
        credential = await crud_webauthn.update_display_name(
            db,
            staff_id=staff.id,
            credential_id=credential_id,
            display_name=display_name,
        )
        if credential is None:
            return None
        await self._create_audit_log(db, staff=staff, action="webauthn.credential_renamed")
        try:
            await db.commit()
            await db.refresh(credential)
        except Exception:
            await db.rollback()
            raise
        return credential

    @staticmethod
    async def _create_audit_log(
        db: AsyncSession, *, staff: Staff, action: str
    ) -> None:
        """認証器の秘密・識別値を含めず、操作事実だけを記録する。"""
        await crud_audit_log.create_log(
            db,
            actor_id=staff.id,
            actor_role=staff.role.value,
            action=action,
            target_type="staff",
            target_id=staff.id,
            auto_commit=False,
        )

    @staticmethod
    def _get_client_challenge(credential: dict) -> bytes:
        try:
            client_data = credential["response"]["clientDataJSON"]
            client_data_json = json.loads(base64url_decode(client_data))
            if client_data_json["type"] != "webauthn.create":
                raise ValueError("unexpected ceremony")
            return base64url_decode(client_data_json["challenge"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ja.WEBAUTHN_REGISTRATION_DATA_INVALID,
            ) from exc

    @staticmethod
    def _get_transports(credential: dict) -> list[str]:
        transports = credential.get("response", {}).get("transports", [])
        if not isinstance(transports, list) or not all(
            isinstance(transport, str) for transport in transports
        ):
            return []
        return transports


webauthn_registration_service = WebAuthnRegistrationService()
