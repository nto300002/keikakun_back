"""app_adminパスキー認証ログインの保留状態とassertion検証。"""

import json
import secrets

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from webauthn import generate_authentication_options, verify_authentication_response
from webauthn.helpers import options_to_json
from webauthn.helpers.structs import PublicKeyCredentialDescriptor, UserVerificationRequirement

from app.core.config import settings
from app.core.webauthn import base64url_decode, base64url_encode
from app.crud.crud_webauthn import crud_webauthn
from app.models.staff import Staff
from app.models.webauthn import WebAuthnCeremony, WebAuthnCredential


class WebAuthnAuthenticationService:
    """パスワード後の短命状態から、WebAuthn認証を完了する。"""

    async def begin_pending_login(self, db: AsyncSession, *, staff: Staff, purpose: str = "login") -> str:
        token = secrets.token_bytes(32)
        await crud_webauthn.create_authentication_session(
            db, staff_id=staff.id, token=token, purpose=purpose
        )
        try:
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        return base64url_encode(token)

    async def begin_authentication(self, db: AsyncSession, *, pending_token: str) -> dict:
        try:
            token = base64url_decode(pending_token)
        except (TypeError, ValueError):
            raise self._invalid()
        pending = await crud_webauthn.get_authentication_session(db, token=token)
        if pending is None:
            raise self._invalid()
        credentials = await crud_webauthn.get_active_credentials(db, staff_id=pending.staff_id)
        if not credentials:
            raise self._invalid()
        challenge = secrets.token_bytes(32)
        ceremony = (
            WebAuthnCeremony.step_up
            if pending.purpose == "step_up"
            else WebAuthnCeremony.authentication
        )
        await crud_webauthn.create_challenge(
            db, staff_id=pending.staff_id, ceremony=ceremony,
            challenge=challenge, session_id=token,
        )
        try:
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        return json.loads(options_to_json(generate_authentication_options(
            rp_id=settings.WEBAUTHN_RP_ID, challenge=challenge,
            user_verification=UserVerificationRequirement.REQUIRED,
            allow_credentials=[PublicKeyCredentialDescriptor(id=item.credential_id) for item in credentials],
        )))

    async def begin_step_up(self, db: AsyncSession, *, staff: Staff) -> tuple[str, dict]:
        """現在の通常セッションに紐づく、短命なstep-up ceremonyを開始する。"""
        pending_token = await self.begin_pending_login(db, staff=staff, purpose="step_up")
        return pending_token, await self.begin_authentication(db, pending_token=pending_token)

    async def verify_authentication(
        self, db: AsyncSession, *, pending_token: str, credential: dict,
        expected_purpose: str = "login",
    ) -> Staff:
        """assertionを検証し、成功した一回だけ通常ログインを許可する。

        syncable passkeyはsign countが0のままの場合があるため、0は後退検知の
        対象外とする。0以外の値はWebAuthnライブラリに単調増加を検証させる。
        """
        try:
            token = base64url_decode(pending_token)
            challenge = self._get_client_challenge(credential)
            credential_id = base64url_decode(credential["rawId"])
        except (KeyError, TypeError, ValueError):
            raise self._invalid()
        pending = await crud_webauthn.get_authentication_session(db, token=token)
        stored = await crud_webauthn.get_active_credential_by_credential_id_for_update(
            db, credential_id=credential_id
        )
        if (
            pending is None
            or pending.purpose != expected_purpose
            or stored is None
            or stored.staff_id != pending.staff_id
        ):
            raise self._invalid()
        try:
            verified = verify_authentication_response(
                credential=credential,
                expected_challenge=challenge,
                expected_rp_id=settings.WEBAUTHN_RP_ID,
                expected_origin=list(settings.webauthn_allowed_origins),
                credential_public_key=stored.public_key,
                credential_current_sign_count=stored.sign_count,
                require_user_presence=True,
                require_user_verification=True,
            )
            if not verified.user_verified:
                raise ValueError("user verification required")
        except Exception as exc:
            await db.rollback()
            raise self._invalid() from exc

        # 暗号学的検証に成功した assertion だけを単回消費する。
        # 同時実行時は先に消費したリクエスト以外を拒否する。
        ceremony = (
            WebAuthnCeremony.step_up
            if pending.purpose == "step_up"
            else WebAuthnCeremony.authentication
        )
        consumed_challenge = await crud_webauthn.consume_challenge(
            db, staff_id=pending.staff_id, ceremony=ceremony,
            challenge=challenge, session_id=token,
        )
        consumed_pending = await crud_webauthn.consume_authentication_session(db, token=token)
        if consumed_challenge is None or consumed_pending is None:
            await db.rollback()
            raise self._invalid()
        await crud_webauthn.update_authentication_use(
            db, credential_id=stored.credential_id, sign_count=verified.new_sign_count
        )
        staff = await db.get(Staff, pending.staff_id)
        if staff is None:
            await db.rollback()
            raise self._invalid()
        try:
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        return staff

    @staticmethod
    def _get_client_challenge(credential: dict) -> bytes:
        client_data = json.loads(base64url_decode(credential["response"]["clientDataJSON"]))
        if client_data.get("type") != "webauthn.get":
            raise ValueError("unexpected ceremony")
        return base64url_decode(client_data["challenge"])

    @staticmethod
    def _invalid() -> HTTPException:
        return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="認証情報を確認できません")


webauthn_authentication_service = WebAuthnAuthenticationService()
