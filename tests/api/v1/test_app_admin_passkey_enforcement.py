"""#215 app_adminパスキー強制化とstep-upの受け入れテスト。"""

import pytest
from fastapi import HTTPException
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from sqlalchemy.exc import IntegrityError
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash
from app.models.webauthn import WebAuthnAuthenticationSession, WebAuthnCredential
from app.core.webauthn import hash_challenge
from app.services.passkey_enforcement import passkey_enforcement_service


async def _add_credentials(db: AsyncSession, staff_id, count: int) -> None:
    for index in range(count):
        db.add(
            WebAuthnCredential(
                staff_id=staff_id,
                credential_id=f"enforcement-credential-{index}".encode(),
                public_key=b"public-key",
                display_name=f"Authenticator {index}",
                transports=["internal"],
            )
        )
    await db.commit()


@pytest.mark.asyncio
async def test_app_admin_cannot_enforce_with_fewer_than_two_credentials(
    db_session: AsyncSession, app_admin_user_factory
):
    app_admin = await app_admin_user_factory()
    await _add_credentials(db_session, app_admin.id, 1)

    with pytest.raises(HTTPException) as exc_info:
        await passkey_enforcement_service.enforce(db_session, staff=app_admin)

    assert exc_info.value.status_code == 409
    await db_session.refresh(app_admin)
    assert app_admin.passkey_enforced_at is None


@pytest.mark.asyncio
async def test_enforced_app_admin_login_does_not_use_passphrase(
    async_client: AsyncClient, db_session: AsyncSession, app_admin_user_factory
):
    app_admin = await app_admin_user_factory()
    app_admin.hashed_passphrase = get_password_hash("old-passphrase")
    await db_session.commit()
    await _add_credentials(db_session, app_admin.id, 2)
    await passkey_enforcement_service.enforce(db_session, staff=app_admin)

    response = await async_client.post(
        "/api/v1/auth/token",
        data={"username": app_admin.email, "password": "a-very-secure-password"},
    )

    assert response.status_code == 200
    assert response.cookies.get("access_token") is None
    assert response.json()["requires_webauthn_verification"] is True


@pytest.mark.asyncio
async def test_step_up_is_separate_from_normal_cookie(
    async_client: AsyncClient, db_session: AsyncSession, app_admin_user_factory, monkeypatch
):
    app_admin = await app_admin_user_factory()
    await _add_credentials(db_session, app_admin.id, 2)
    from app.services import webauthn_authentication

    monkeypatch.setattr(webauthn_authentication.settings, "WEBAUTHN_RP_ID", "test.local")

    from app.core.security import create_access_token

    access_token = create_access_token(str(app_admin.id), session_type="standard")
    response = await async_client.post(
        "/api/v1/auth/webauthn/step-up/options",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    assert response.cookies.get("access_token") is None
    assert response.json()["webauthn_pending_token"]
    assert response.json()["publicKey"]["userVerification"] == "required"


@pytest.mark.asyncio
async def test_enforced_high_risk_credential_revoke_requires_step_up(
    async_client: AsyncClient, db_session: AsyncSession, app_admin_user_factory
):
    app_admin = await app_admin_user_factory()
    credential = WebAuthnCredential(
        staff_id=app_admin.id,
        credential_id=b"revoke-credential",
        public_key=b"public-key",
        display_name="Security key",
        transports=["usb"],
    )
    db_session.add(credential)
    await db_session.commit()
    await _add_credentials(db_session, app_admin.id, 1)
    await passkey_enforcement_service.enforce(db_session, staff=app_admin)

    from app.core.security import create_access_token

    standard_token = create_access_token(
        str(app_admin.id), expires_delta=timedelta(minutes=5), session_type="standard"
    )
    response = await async_client.delete(
        f"/api/v1/auth/webauthn/credentials/{credential.id}",
        headers={"Authorization": f"Bearer {standard_token}"},
    )

    assert response.status_code == 403
    assert "追加のパスキー認証" in response.json()["detail"]


@pytest.mark.asyncio
async def test_enforce_endpoint_requires_step_up(
    async_client: AsyncClient, db_session: AsyncSession, app_admin_user_factory
):
    app_admin = await app_admin_user_factory()
    await _add_credentials(db_session, app_admin.id, 2)
    from app.core.security import create_access_token

    standard_token = create_access_token(str(app_admin.id), session_type="standard")
    response = await async_client.post(
        "/api/v1/auth/webauthn/enforce",
        headers={"Authorization": f"Bearer {standard_token}"},
    )

    assert response.status_code == 403
    await db_session.refresh(app_admin)
    assert app_admin.passkey_enforced_at is None


@pytest.mark.asyncio
async def test_step_up_verify_requires_csrf_for_cookie_auth(
    async_client: AsyncClient, app_admin_user_factory
):
    app_admin = await app_admin_user_factory()
    from app.core.security import create_access_token

    access_token = create_access_token(str(app_admin.id), session_type="standard")
    response = await async_client.post(
        "/api/v1/auth/webauthn/step-up/verify",
        cookies={"access_token": access_token},
        json={"pending_token": "pending", "credential": {}},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_authentication_session_purpose_is_database_constrained(
    db_session: AsyncSession, app_admin_user_factory
):
    app_admin = await app_admin_user_factory()
    db_session.add(
        WebAuthnAuthenticationSession(
            staff_id=app_admin.id,
            token_hash=hash_challenge(b"invalid-purpose"),
            purpose="unsupported",
            expires_at=datetime.now(timezone.utc),
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_enforced_high_risk_apis_reject_invalid_step_up_tokens(
    async_client: AsyncClient, db_session: AsyncSession, app_admin_user_factory
):
    app_admin = await app_admin_user_factory()
    other_admin = await app_admin_user_factory()
    await _add_credentials(db_session, app_admin.id, 2)
    await passkey_enforcement_service.enforce(db_session, staff=app_admin)
    from app.core.security import create_access_token

    access_token = create_access_token(str(app_admin.id), session_type="standard")
    other_token = create_access_token(str(other_admin.id), session_type="step_up")
    expired_token = create_access_token(
        str(app_admin.id), expires_delta_seconds=-1, session_type="step_up"
    )
    operations = [
        ("post", "/api/v1/admin/announcements", {"title": "通知", "content": "本文"}),
        ("patch", f"/api/v1/admin/inquiries/{uuid4()}", {"status": "in_progress"}),
        ("post", f"/api/v1/admin/inquiries/{uuid4()}/reply", {"body": "返信", "send_email": False}),
        ("delete", f"/api/v1/admin/inquiries/{uuid4()}", None),
    ]
    for method, path, payload in operations:
        for step_up_token in (None, "not-a-jwt", expired_token, other_token):
            headers = {"Authorization": f"Bearer {access_token}"}
            if step_up_token:
                headers["X-Step-Up-Token"] = step_up_token
            response = await async_client.request(
                method, path, json=payload, headers=headers
            )
            assert response.status_code == 403, (method, path, response.text)


@pytest.mark.asyncio
async def test_high_risk_apis_reject_cookie_auth_without_csrf(
    async_client: AsyncClient, app_admin_user_factory
):
    app_admin = await app_admin_user_factory()
    from app.core.security import create_access_token

    access_token = create_access_token(str(app_admin.id), session_type="standard")
    operations = [
        ("post", "/api/v1/admin/announcements", {"title": "通知", "content": "本文"}),
        ("patch", f"/api/v1/admin/inquiries/{uuid4()}", {"status": "in_progress"}),
        ("post", f"/api/v1/admin/inquiries/{uuid4()}/reply", {"body": "返信", "send_email": False}),
        ("delete", f"/api/v1/admin/inquiries/{uuid4()}", None),
    ]
    for method, path, payload in operations:
        response = await async_client.request(
            method, path, json=payload, cookies={"access_token": access_token}
        )
        assert response.status_code == 403, (method, path, response.text)
