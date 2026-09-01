import json
from datetime import timedelta
from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from webauthn import verify_registration_response

from app.core.security import create_access_token
from app.core.webauthn import base64url_decode, base64url_encode
from app.crud.crud_webauthn import crud_webauthn
from app.models.staff_profile import AuditLog
from app.models.webauthn import WebAuthnCeremony, WebAuthnChallenge, WebAuthnCredential


async def _csrf(async_client: AsyncClient) -> tuple[dict[str, str], str]:
    response = await async_client.get("/api/v1/csrf-token")
    response.raise_for_status()
    return (
        {"X-CSRF-Token": response.json()["csrf_token"]},
        response.cookies.get("fastapi-csrf-token"),
    )


@pytest.mark.asyncio
async def test_app_admin_registration_options_uses_server_generated_hashed_challenge(
    async_client: AsyncClient,
    db_session: AsyncSession,
    app_admin_user_factory,
    monkeypatch,
):
    from app.services import webauthn_registration

    monkeypatch.setattr(webauthn_registration.settings, "WEBAUTHN_RP_ID", "test.local")
    monkeypatch.setattr(webauthn_registration.settings, "WEBAUTHN_RP_NAME", "Keikakun Test")
    app_admin = await app_admin_user_factory()
    headers, csrf_cookie = await _csrf(async_client)
    access_token = create_access_token(str(app_admin.id), timedelta(minutes=30))

    response = await async_client.post(
        "/api/v1/auth/webauthn/registration/options",
        cookies={
            "access_token": access_token,
            "fastapi-csrf-token": csrf_cookie,
        },
        headers=headers,
    )

    assert response.status_code == 200
    public_key = response.json()["publicKey"]
    assert public_key["challenge"]
    assert public_key["authenticatorSelection"]["userVerification"] == "required"
    assert "authenticatorAttachment" not in public_key["authenticatorSelection"]

    result = await db_session.execute(
        select(WebAuthnChallenge).where(WebAuthnChallenge.staff_id == app_admin.id)
    )
    challenge = result.scalar_one()
    assert challenge.ceremony == "registration"
    assert challenge.challenge_hash != public_key["challenge"]


@pytest.mark.asyncio
async def test_app_admin_registration_options_requires_csrf_for_cookie_auth(
    async_client: AsyncClient,
    app_admin_user_factory,
    monkeypatch,
):
    from app.services import webauthn_registration

    monkeypatch.setattr(webauthn_registration.settings, "WEBAUTHN_RP_ID", "test.local")
    monkeypatch.setattr(webauthn_registration.settings, "WEBAUTHN_RP_NAME", "Keikakun Test")
    app_admin = await app_admin_user_factory()
    access_token = create_access_token(str(app_admin.id), timedelta(minutes=30))

    response = await async_client.post(
        "/api/v1/auth/webauthn/registration/options",
        cookies={"access_token": access_token},
    )

    assert response.status_code == 403


def _verified_registration(*, user_verified: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        credential_id=b"registered-credential-id",
        credential_public_key=b"registered-public-key",
        sign_count=0,
        aaguid="00000000-0000-0000-0000-000000000000",
        credential_device_type=SimpleNamespace(value="multi_device"),
        credential_backed_up=True,
        user_verified=user_verified,
    )


def _registration_credential(challenge: bytes) -> dict:
    return {
        "id": base64url_encode(b"registered-credential-id"),
        "rawId": base64url_encode(b"registered-credential-id"),
        "type": "public-key",
        "response": {
            "clientDataJSON": base64url_encode(
                json.dumps(
                    {"type": "webauthn.create", "challenge": base64url_encode(challenge)}
                ).encode()
            ),
            "attestationObject": base64url_encode(b"mock-attestation"),
            "transports": ["internal"],
        },
    }


@pytest.mark.asyncio
async def test_app_admin_registration_verify_stores_only_public_credential_material(
    async_client: AsyncClient,
    db_session: AsyncSession,
    app_admin_user_factory,
    monkeypatch,
):
    from app.services import webauthn_registration

    app_admin = await app_admin_user_factory()
    headers, csrf_cookie = await _csrf(async_client)
    access_token = create_access_token(str(app_admin.id), timedelta(minutes=30))
    challenge = b"server-generated-registration-challenge"
    await crud_webauthn.create_challenge(
        db_session,
        staff_id=app_admin.id,
        ceremony=WebAuthnCeremony.registration,
        challenge=challenge,
        session_id=access_token.encode("ascii"),
    )
    await db_session.commit()
    monkeypatch.setattr(webauthn_registration.settings, "WEBAUTHN_RP_ID", "test.local")
    monkeypatch.setattr(
        webauthn_registration.settings,
        "WEBAUTHN_ALLOWED_ORIGINS",
        "https://test.local",
    )
    monkeypatch.setattr(
        webauthn_registration,
        "verify_registration_response",
        lambda **_: _verified_registration(),
    )

    response = await async_client.post(
        "/api/v1/auth/webauthn/registration/verify",
        json={"credential": _registration_credential(challenge), "display_name": "Touch ID"},
        cookies={
            "access_token": access_token,
            "fastapi-csrf-token": csrf_cookie,
        },
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["display_name"] == "Touch ID"
    assert "public_key" not in response.json()
    credential = await db_session.get(WebAuthnCredential, response.json()["id"])
    assert credential is not None
    assert credential.public_key == b"registered-public-key"
    assert credential.transports == ["internal"]
    assert credential.backup_eligible is True
    assert credential.backup_state is True
    audit_result = await db_session.execute(
        select(AuditLog).where(AuditLog.action == "webauthn.credential_registered")
    )
    audit_log = audit_result.scalar_one()
    assert audit_log.staff_id == app_admin.id
    assert audit_log.target_id == app_admin.id
    assert audit_log.details is None
    assert audit_log.old_value is None
    assert audit_log.new_value is None


@pytest.mark.asyncio
async def test_app_admin_registration_verify_rejects_missing_user_verification(
    async_client: AsyncClient,
    db_session: AsyncSession,
    app_admin_user_factory,
    monkeypatch,
):
    from app.services import webauthn_registration

    app_admin = await app_admin_user_factory()
    headers, csrf_cookie = await _csrf(async_client)
    access_token = create_access_token(str(app_admin.id), timedelta(minutes=30))
    challenge = b"user-verification-required-challenge"
    await crud_webauthn.create_challenge(
        db_session,
        staff_id=app_admin.id,
        ceremony=WebAuthnCeremony.registration,
        challenge=challenge,
        session_id=access_token.encode("ascii"),
    )
    await db_session.commit()
    monkeypatch.setattr(webauthn_registration.settings, "WEBAUTHN_RP_ID", "test.local")
    monkeypatch.setattr(
        webauthn_registration.settings,
        "WEBAUTHN_ALLOWED_ORIGINS",
        "https://test.local",
    )
    monkeypatch.setattr(
        webauthn_registration,
        "verify_registration_response",
        lambda **_: _verified_registration(user_verified=False),
    )

    response = await async_client.post(
        "/api/v1/auth/webauthn/registration/verify",
        json={"credential": _registration_credential(challenge), "display_name": "Security Key"},
        cookies={
            "access_token": access_token,
            "fastapi-csrf-token": csrf_cookie,
        },
        headers=headers,
    )

    assert response.status_code == 400
    assert "本人確認" in response.json()["detail"]
    consumed = await crud_webauthn.consume_challenge(
        db_session,
        staff_id=app_admin.id,
        ceremony=WebAuthnCeremony.registration,
        challenge=challenge,
        session_id=access_token.encode("ascii"),
    )
    assert consumed is None


@pytest.mark.asyncio
async def test_app_admin_can_list_and_revoke_only_own_active_credential(
    async_client: AsyncClient,
    db_session: AsyncSession,
    app_admin_user_factory,
):
    app_admin = await app_admin_user_factory()
    credential = WebAuthnCredential(
        staff_id=app_admin.id,
        credential_id=b"credential-to-revoke",
        public_key=b"public-key",
        display_name="Hardware key",
        transports=["usb"],
    )
    backup_credential = WebAuthnCredential(
        staff_id=app_admin.id,
        credential_id=b"backup-credential",
        public_key=b"backup-public-key",
        display_name="Backup key",
        transports=["internal"],
    )
    db_session.add_all([credential, backup_credential])
    await db_session.commit()
    headers, csrf_cookie = await _csrf(async_client)
    access_token = create_access_token(str(app_admin.id), timedelta(minutes=30))

    listed = await async_client.get(
        "/api/v1/auth/webauthn/credentials",
        cookies={"access_token": access_token},
    )
    assert listed.status_code == 200
    assert {item["id"] for item in listed.json()} == {
        str(credential.id),
        str(backup_credential.id),
    }

    deleted = await async_client.delete(
        f"/api/v1/auth/webauthn/credentials/{credential.id}",
        cookies={
            "access_token": access_token,
            "fastapi-csrf-token": csrf_cookie,
        },
        headers=headers,
    )
    assert deleted.status_code == 204
    await db_session.refresh(credential)
    assert credential.revoked_at is not None
    audit_result = await db_session.execute(
        select(AuditLog).where(AuditLog.action == "webauthn.credential_revoked")
    )
    audit_log = audit_result.scalar_one()
    assert audit_log.details is None


@pytest.mark.asyncio
async def test_app_admin_can_update_credential_display_name_without_audit_details(
    async_client: AsyncClient,
    db_session: AsyncSession,
    app_admin_user_factory,
):
    app_admin = await app_admin_user_factory()
    credential = WebAuthnCredential(
        staff_id=app_admin.id,
        credential_id=b"credential-to-rename",
        public_key=b"public-key",
        display_name="Old name",
    )
    db_session.add(credential)
    await db_session.commit()
    headers, csrf_cookie = await _csrf(async_client)
    access_token = create_access_token(str(app_admin.id), timedelta(minutes=30))

    response = await async_client.patch(
        f"/api/v1/auth/webauthn/credentials/{credential.id}",
        json={"display_name": "New name"},
        cookies={
            "access_token": access_token,
            "fastapi-csrf-token": csrf_cookie,
        },
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["display_name"] == "New name"
    await db_session.refresh(credential)
    assert credential.display_name == "New name"
    audit_result = await db_session.execute(
        select(AuditLog).where(AuditLog.action == "webauthn.credential_renamed")
    )
    audit_log = audit_result.scalar_one()
    assert audit_log.details is None
    assert audit_log.old_value is None
    assert audit_log.new_value is None


@pytest.mark.asyncio
async def test_app_admin_cannot_revoke_last_active_credential(
    async_client: AsyncClient,
    db_session: AsyncSession,
    app_admin_user_factory,
):
    app_admin = await app_admin_user_factory()
    credential = WebAuthnCredential(
        staff_id=app_admin.id,
        credential_id=b"only-active-credential",
        public_key=b"public-key",
        display_name="Only key",
    )
    db_session.add(credential)
    await db_session.commit()
    headers, csrf_cookie = await _csrf(async_client)
    access_token = create_access_token(str(app_admin.id), timedelta(minutes=30))

    response = await async_client.delete(
        f"/api/v1/auth/webauthn/credentials/{credential.id}",
        cookies={
            "access_token": access_token,
            "fastapi-csrf-token": csrf_cookie,
        },
        headers=headers,
    )

    assert response.status_code == 400
    assert "最後" in response.json()["detail"]
    await db_session.refresh(credential)
    assert credential.revoked_at is None
    audit_result = await db_session.execute(
        select(AuditLog).where(AuditLog.action == "webauthn.credential_revoked")
    )
    assert audit_result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_non_app_admin_cannot_start_registration(
    async_client: AsyncClient,
    employee_user_factory,
):
    employee = await employee_user_factory()
    headers, csrf_cookie = await _csrf(async_client)
    access_token = create_access_token(str(employee.id), timedelta(minutes=30))

    response = await async_client.post(
        "/api/v1/auth/webauthn/registration/options",
        cookies={
            "access_token": access_token,
            "fastapi-csrf-token": csrf_cookie,
        },
        headers=headers,
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_registration_options_has_an_individual_rate_limit(
    async_client: AsyncClient,
    app_admin_user_factory,
    monkeypatch,
):
    from app.services import webauthn_registration

    app_admin = await app_admin_user_factory()
    monkeypatch.setattr(webauthn_registration.settings, "WEBAUTHN_RP_ID", "test.local")
    monkeypatch.setattr(webauthn_registration.settings, "WEBAUTHN_RP_NAME", "Keikakun Test")
    headers, csrf_cookie = await _csrf(async_client)
    access_token = create_access_token(str(app_admin.id), timedelta(minutes=30))
    cookies = {
        "access_token": access_token,
        "fastapi-csrf-token": csrf_cookie,
    }

    responses = [
        await async_client.post(
            "/api/v1/auth/webauthn/registration/options",
            cookies=cookies,
            headers=headers,
        )
        for _ in range(6)
    ]

    assert [response.status_code for response in responses[:5]] == [200] * 5
    assert responses[5].status_code == 429


@pytest.mark.asyncio
async def test_app_admin_cannot_revoke_another_admin_credential(
    async_client: AsyncClient,
    db_session: AsyncSession,
    app_admin_user_factory,
):
    app_admin = await app_admin_user_factory()
    another_app_admin = await app_admin_user_factory()
    another_credential = WebAuthnCredential(
        staff_id=another_app_admin.id,
        credential_id=b"another-admin-credential",
        public_key=b"public-key",
        display_name="Another hardware key",
    )
    db_session.add(another_credential)
    await db_session.commit()
    headers, csrf_cookie = await _csrf(async_client)
    access_token = create_access_token(str(app_admin.id), timedelta(minutes=30))

    response = await async_client.delete(
        f"/api/v1/auth/webauthn/credentials/{another_credential.id}",
        cookies={
            "access_token": access_token,
            "fastapi-csrf-token": csrf_cookie,
        },
        headers=headers,
    )

    assert response.status_code == 404
    await db_session.refresh(another_credential)
    assert another_credential.revoked_at is None


# py_webauthn公式registration exampleの実attestationベクタ。
REAL_ATTESTATION_CREDENTIAL = {
    "id": "ZoIKP1JQvKdrYj1bTUPJ2eTUsbLeFkv-X5xJQNr4k6s",
    "rawId": "ZoIKP1JQvKdrYj1bTUPJ2eTUsbLeFkv-X5xJQNr4k6s",
    "response": {
        "attestationObject": "o2NmbXRkbm9uZWdhdHRTdG10oGhhdXRoRGF0YVkBZ0mWDeWIDoxodDQXD2R2YFuP5K65ooYyx5lc87qDHZdjRQAAAAAAAAAAAAAAAAAAAAAAAAAAACBmggo_UlC8p2tiPVtNQ8nZ5NSxst4WS_5fnElA2viTq6QBAwM5AQAgWQEA31dtHqc70D_h7XHQ6V_nBs3Tscu91kBL7FOw56_VFiaKYRH6Z4KLr4J0S12hFJ_3fBxpKfxyMfK66ZMeAVbOl_wemY4S5Xs4yHSWy21Xm_dgWhLJjZ9R1tjfV49kDPHB_ssdvP7wo3_NmoUPYMgK-edgZ_ehttp_I6hUUCnVaTvn_m76b2j9yEPReSwl-wlGsabYG6INUhTuhSOqG-UpVVQdNJVV7GmIPHCA2cQpJBDZBohT4MBGme_feUgm4sgqVCWzKk6CzIKIz5AIVnspLbu05SulAVnSTB3NxTwCLNJR_9v9oSkvphiNbmQBVQH1tV_psyi9HM1Jtj9VJVKMeyFDAQAB",
        "clientDataJSON": "eyJ0eXBlIjoid2ViYXV0aG4uY3JlYXRlIiwiY2hhbGxlbmdlIjoiQ2VUV29nbWcwY2NodWlZdUZydjhEWFhkTVpTSVFSVlpKT2dhX3hheVZWRWNCajBDdzN5NzN5aEQ0RmtHU2UtUnJQNmhQSkpBSW0zTFZpZW40aFhFTGciLCJvcmlnaW4iOiJodHRwOi8vbG9jYWxob3N0OjUwMDAiLCJjcm9zc09yaWdpbiI6ZmFsc2V9",
        "transports": ["internal"],
    },
    "type": "public-key",
}
REAL_ATTESTATION_CHALLENGE = base64url_encode(
    base64url_decode(
        "CeTWogmg0cchuiYuFrv8DXXdMZSIQRVZJOga_xayVVEcBj0Cw3y73yhD4FkGSe-RrP6hPJJAIm3LVien4hXELg"
    )
)


def test_real_attestation_verifies_rp_origin_type_and_user_verification():
    """実 attestation を使い、ライブラリの登録検証を回帰確認する。"""
    challenge = base64url_decode(REAL_ATTESTATION_CHALLENGE)
    verified = verify_registration_response(
        credential=REAL_ATTESTATION_CREDENTIAL,
        expected_challenge=challenge,
        expected_rp_id="localhost",
        expected_origin="http://localhost:5000",
        require_user_verification=True,
    )
    assert verified.user_verified is True

    with pytest.raises(Exception):
        verify_registration_response(
            credential=REAL_ATTESTATION_CREDENTIAL,
            expected_challenge=challenge,
            expected_rp_id="wrong.localhost",
            expected_origin="http://localhost:5000",
            require_user_verification=True,
        )
    with pytest.raises(Exception):
        verify_registration_response(
            credential=REAL_ATTESTATION_CREDENTIAL,
            expected_challenge=challenge,
            expected_rp_id="localhost",
            expected_origin="http://wrong.localhost:5000",
            require_user_verification=True,
        )
    with pytest.raises(Exception):
        verify_registration_response(
            credential={**REAL_ATTESTATION_CREDENTIAL, "type": "not-public-key"},
            expected_challenge=challenge,
            expected_rp_id="localhost",
            expected_origin="http://localhost:5000",
            require_user_verification=True,
        )
