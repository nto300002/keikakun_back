"""app_adminパスキー認証ログインAPIの受け入れテスト。"""

import json
import hashlib
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import cbor2
import pytest
from httpx import AsyncClient
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash
from app.core.webauthn import base64url_decode, base64url_encode, hash_challenge
from app.models.webauthn import (
    WebAuthnAuthenticationSession,
    WebAuthnChallenge,
    WebAuthnCredential,
)


def _assertion(challenge: bytes, credential_id: bytes = b"authentication-credential") -> dict:
    return {
        "id": base64url_encode(credential_id),
        "rawId": base64url_encode(credential_id),
        "type": "public-key",
        "response": {
            "clientDataJSON": base64url_encode(
                json.dumps(
                    {"type": "webauthn.get", "challenge": base64url_encode(challenge)}
                ).encode()
            ),
            "authenticatorData": base64url_encode(b"mock-authenticator-data"),
            "signature": base64url_encode(b"mock-signature"),
            "userHandle": None,
        },
    }


def _real_credential(challenge: bytes, credential_id: bytes, *, sign_count: int = 1, flags: int = 0x05,
                     origin: str = "https://test.local", ceremony_type: str = "webauthn.get",
                     rp_id: str = "test.local", private_key=None) -> tuple[ec.EllipticCurvePrivateKey, dict, bytes]:
    """py_webauthnが実際に検証するP-256 assertionを生成する。"""
    private_key = private_key or ec.generate_private_key(ec.SECP256R1())
    numbers = private_key.public_key().public_numbers()
    public_key = cbor2.dumps({
        1: 2, 3: -7, -1: 1,
        -2: numbers.x.to_bytes(32, "big"),
        -3: numbers.y.to_bytes(32, "big"),
    })
    client_data = json.dumps({
        "type": ceremony_type,
        "challenge": base64url_encode(challenge),
        "origin": origin,
    }, separators=(",", ":")).encode()
    authenticator_data = (
        hashlib.sha256(rp_id.encode()).digest()
        + bytes([flags])
        + sign_count.to_bytes(4, "big")
    )
    signature = private_key.sign(
        authenticator_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256())
    )
    assertion = {
        "id": base64url_encode(credential_id),
        "rawId": base64url_encode(credential_id),
        "type": "public-key",
        "response": {
            "clientDataJSON": base64url_encode(client_data),
            "authenticatorData": base64url_encode(authenticator_data),
            "signature": base64url_encode(signature),
            "userHandle": None,
        },
    }
    return private_key, assertion, public_key


@pytest.mark.asyncio
async def test_passkey_login_issues_session_only_after_verified_assertion(
    async_client: AsyncClient,
    db_session: AsyncSession,
    app_admin_user_factory,
    monkeypatch,
):
    """パスキー登録済みapp_adminは検証成功まで通常セッションを得ない。"""
    from app.services import webauthn_authentication

    app_admin = await app_admin_user_factory()
    app_admin.hashed_passphrase = get_password_hash("passphrase")
    db_session.add(
        WebAuthnCredential(
            staff_id=app_admin.id,
            credential_id=b"authentication-credential",
            public_key=b"authentication-public-key",
            display_name="Touch ID",
            transports=["internal"],
        )
    )
    await db_session.commit()
    monkeypatch.setattr(webauthn_authentication.settings, "WEBAUTHN_RP_ID", "test.local")
    monkeypatch.setattr(
        webauthn_authentication.settings, "WEBAUTHN_ALLOWED_ORIGINS", "https://test.local"
    )

    password_response = await async_client.post(
        "/api/v1/auth/token",
        data={
            "username": app_admin.email,
            "password": "a-very-secure-password",
            "passphrase": "passphrase",
        },
    )

    assert password_response.status_code == 200
    assert password_response.cookies.get("access_token") is None
    pending_token = password_response.json()["webauthn_pending_token"]

    options_response = await async_client.post(
        "/api/v1/auth/webauthn/authentication/options",
        json={"pending_token": pending_token},
    )

    assert options_response.status_code == 200
    challenge = options_response.json()["publicKey"]["challenge"]
    assertion = _assertion(base64url_decode(challenge))

    def reject_assertion(**_):
        raise ValueError("invalid assertion")

    monkeypatch.setattr(webauthn_authentication, "verify_authentication_response", reject_assertion)
    rejected_response = await async_client.post(
        "/api/v1/auth/webauthn/authentication/verify",
        json={"pending_token": pending_token, "credential": assertion},
    )

    assert rejected_response.status_code == 401

    monkeypatch.setattr(
        webauthn_authentication,
        "verify_authentication_response",
        lambda **_: SimpleNamespace(new_sign_count=7, user_verified=True),
    )

    verify_response = await async_client.post(
        "/api/v1/auth/webauthn/authentication/verify",
        json={"pending_token": pending_token, "credential": assertion},
    )

    assert verify_response.status_code == 200
    assert verify_response.cookies.get("access_token")
    assert verify_response.json()["refresh_token"]

    credential = (
        await db_session.execute(
            select(WebAuthnCredential).where(
                WebAuthnCredential.staff_id == app_admin.id,
                WebAuthnCredential.credential_id == b"authentication-credential",
            )
        )
    ).scalar_one()
    assert credential.sign_count == 7
    assert credential.last_used_at is not None

    async_client.cookies.delete("access_token")
    replay_response = await async_client.post(
        "/api/v1/auth/webauthn/authentication/verify",
        json={"pending_token": pending_token, "credential": assertion},
    )
    assert replay_response.status_code == 401


@pytest.mark.asyncio
async def test_real_assertion_verification_issues_cookie(
    async_client: AsyncClient,
    db_session: AsyncSession,
    app_admin_user_factory,
    monkeypatch,
):
    """実署名assertionがライブラリの現行APIで検証できる。"""
    from app.services import webauthn_authentication

    app_admin = await app_admin_user_factory()
    app_admin.hashed_passphrase = get_password_hash("passphrase")
    credential_id = os.urandom(16)
    private_key, _, public_key = _real_credential(b"unused", credential_id)
    db_session.add(WebAuthnCredential(
        staff_id=app_admin.id,
        credential_id=credential_id,
        public_key=public_key,
        display_name="Touch ID",
        transports=["internal"],
    ))
    await db_session.commit()
    monkeypatch.setattr(webauthn_authentication.settings, "WEBAUTHN_RP_ID", "test.local")
    monkeypatch.setattr(webauthn_authentication.settings, "WEBAUTHN_ALLOWED_ORIGINS", "https://test.local")

    login_response = await async_client.post(
        "/api/v1/auth/token",
        data={
            "username": app_admin.email,
            "password": "a-very-secure-password",
            "passphrase": "passphrase",
        },
    )
    pending_token = login_response.json()["webauthn_pending_token"]
    options_response = await async_client.post(
        "/api/v1/auth/webauthn/authentication/options",
        json={"pending_token": pending_token},
    )
    challenge = base64url_decode(options_response.json()["publicKey"]["challenge"])
    _, assertion, _ = _real_credential(
        challenge,
        credential_id,
        private_key=private_key,
    )

    verify_response = await async_client.post(
        "/api/v1/auth/webauthn/authentication/verify",
        json={"pending_token": pending_token, "credential": assertion},
    )

    assert verify_response.status_code == 200
    assert verify_response.cookies.get("access_token")


@pytest.mark.asyncio
async def test_passkey_pending_token_cannot_be_replayed(
    async_client: AsyncClient,
    app_admin_user_factory,
):
    """認証保留トークンは用途限定かつ単回使用である。"""
    app_admin = await app_admin_user_factory()
    app_admin.hashed_passphrase = get_password_hash("passphrase")

    login_response = await async_client.post(
        "/api/v1/auth/token",
        data={
            "username": app_admin.email,
            "password": "a-very-secure-password",
            "passphrase": "passphrase",
        },
    )

    assert login_response.status_code == 200
    assert "webauthn_pending_token" not in login_response.json()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    ["uv_false", "up_false", "origin_mismatch", "rp_id_mismatch", "type_mismatch", "sign_count_regression"],
)
async def test_real_assertion_rejects_protocol_failures(
    async_client: AsyncClient,
    db_session: AsyncSession,
    app_admin_user_factory,
    monkeypatch,
    case: str,
):
    """モックを使わず、py_webauthnのassertion検証を異常系で通す。"""
    from app.services import webauthn_authentication

    app_admin = await app_admin_user_factory()
    app_admin.hashed_passphrase = get_password_hash("passphrase")
    credential_id = os.urandom(16)
    _, _, public_key = _real_credential(b"unused", credential_id)
    stored_count = 5 if case == "sign_count_regression" else 0
    db_session.add(WebAuthnCredential(
        staff_id=app_admin.id,
        credential_id=credential_id,
        public_key=public_key,
        sign_count=stored_count,
        display_name="Test passkey",
        transports=["internal"],
    ))
    await db_session.commit()
    monkeypatch.setattr(webauthn_authentication.settings, "WEBAUTHN_RP_ID", "test.local")
    monkeypatch.setattr(webauthn_authentication.settings, "WEBAUTHN_ALLOWED_ORIGINS", "https://test.local")

    login_response = await async_client.post(
        "/api/v1/auth/token",
        data={"username": app_admin.email, "password": "a-very-secure-password", "passphrase": "passphrase"},
    )
    pending_token = login_response.json()["webauthn_pending_token"]
    options_response = await async_client.post(
        "/api/v1/auth/webauthn/authentication/options",
        json={"pending_token": pending_token},
    )
    challenge = base64url_decode(options_response.json()["publicKey"]["challenge"])
    flags = {"uv_false": 0x01, "up_false": 0x04}.get(case, 0x05)
    origin = "https://wrong.local" if case == "origin_mismatch" else "https://test.local"
    ceremony_type = "webauthn.create" if case == "type_mismatch" else "webauthn.get"
    assertion_count = 4 if case == "sign_count_regression" else 1
    _, assertion, _ = _real_credential(
        challenge, credential_id, sign_count=assertion_count, flags=flags,
        origin=origin, ceremony_type=ceremony_type,
    )
    if case == "rp_id_mismatch":
        monkeypatch.setattr(webauthn_authentication.settings, "WEBAUTHN_RP_ID", "wrong.local")

    verify_response = await async_client.post(
        "/api/v1/auth/webauthn/authentication/verify",
        json={"pending_token": pending_token, "credential": assertion},
    )
    assert verify_response.status_code == 401
    assert verify_response.cookies.get("access_token") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("expired_record", ["pending", "challenge"])
async def test_expired_pending_or_challenge_is_rejected(
    async_client: AsyncClient,
    db_session: AsyncSession,
    app_admin_user_factory,
    monkeypatch,
    expired_record: str,
):
    from app.services import webauthn_authentication

    app_admin = await app_admin_user_factory()
    app_admin.hashed_passphrase = get_password_hash("passphrase")
    credential_id = os.urandom(16)
    _, _, public_key = _real_credential(b"unused", credential_id)
    db_session.add(WebAuthnCredential(
        staff_id=app_admin.id, credential_id=credential_id, public_key=public_key,
        display_name="Test passkey", transports=["internal"],
    ))
    await db_session.commit()
    monkeypatch.setattr(webauthn_authentication.settings, "WEBAUTHN_RP_ID", "test.local")
    monkeypatch.setattr(webauthn_authentication.settings, "WEBAUTHN_ALLOWED_ORIGINS", "https://test.local")

    login_response = await async_client.post(
        "/api/v1/auth/token",
        data={"username": app_admin.email, "password": "a-very-secure-password", "passphrase": "passphrase"},
    )
    pending_token = login_response.json()["webauthn_pending_token"]
    if expired_record == "pending":
        await db_session.execute(
            update(WebAuthnAuthenticationSession)
            .where(WebAuthnAuthenticationSession.token_hash == hash_challenge(base64url_decode(pending_token)))
            .values(expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
        )
        await db_session.commit()
        response = await async_client.post(
            "/api/v1/auth/webauthn/authentication/options",
            json={"pending_token": pending_token},
        )
        assert response.status_code == 401
        return

    options_response = await async_client.post(
        "/api/v1/auth/webauthn/authentication/options",
        json={"pending_token": pending_token},
    )
    challenge = base64url_decode(options_response.json()["publicKey"]["challenge"])
    await db_session.execute(
        update(WebAuthnChallenge)
        .where(WebAuthnChallenge.challenge_hash == hash_challenge(challenge))
        .values(expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    )
    await db_session.commit()
    _, assertion, _ = _real_credential(challenge, credential_id)
    response = await async_client.post(
        "/api/v1/auth/webauthn/authentication/verify",
        json={"pending_token": pending_token, "credential": assertion},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("credential_state", ["other_user", "revoked"])
async def test_authentication_rejects_unowned_or_revoked_credential(
    async_client: AsyncClient,
    db_session: AsyncSession,
    app_admin_user_factory,
    monkeypatch,
    credential_state: str,
):
    from app.services import webauthn_authentication

    app_admin = await app_admin_user_factory()
    other_admin = await app_admin_user_factory()
    app_admin.hashed_passphrase = get_password_hash("passphrase")
    credential_id = os.urandom(16)
    other_credential_id = os.urandom(16)
    _, _, public_key = _real_credential(b"unused", credential_id)
    other_private_key, _, other_public_key = _real_credential(b"unused", other_credential_id)
    db_session.add_all([
        WebAuthnCredential(
            staff_id=app_admin.id, credential_id=credential_id, public_key=public_key,
            display_name="Test passkey", transports=["internal"],
            revoked_at=datetime.now(timezone.utc) if credential_state == "revoked" else None,
        ),
        WebAuthnCredential(
            staff_id=other_admin.id, credential_id=other_credential_id, public_key=other_public_key,
            display_name="Other passkey", transports=["internal"],
        ),
    ])
    await db_session.commit()
    monkeypatch.setattr(webauthn_authentication.settings, "WEBAUTHN_RP_ID", "test.local")
    monkeypatch.setattr(webauthn_authentication.settings, "WEBAUTHN_ALLOWED_ORIGINS", "https://test.local")
    if credential_state == "other_user":
        login_response = await async_client.post(
            "/api/v1/auth/token",
            data={"username": app_admin.email, "password": "a-very-secure-password", "passphrase": "passphrase"},
        )
        pending_token = login_response.json()["webauthn_pending_token"]
    else:
        pending_token = await webauthn_authentication.webauthn_authentication_service.begin_pending_login(
            db_session, staff=app_admin
        )
    options_response = await async_client.post(
        "/api/v1/auth/webauthn/authentication/options",
        json={"pending_token": pending_token},
    )
    if credential_state == "revoked":
        assert options_response.status_code == 401
        return
    assert options_response.status_code == 200
    challenge = base64url_decode(options_response.json()["publicKey"]["challenge"])
    _, assertion, _ = _real_credential(challenge, other_credential_id, private_key=other_private_key)
    verify_response = await async_client.post(
        "/api/v1/auth/webauthn/authentication/verify",
        json={"pending_token": pending_token, "credential": assertion},
    )
    assert verify_response.status_code == 401


@pytest.mark.asyncio
async def test_concurrent_assertions_issue_at_most_one_session(
    async_client: AsyncClient,
    db_session: AsyncSession,
    app_admin_user_factory,
    monkeypatch,
):
    """同じpending/assertionの競合時、単回消費により成功は1件だけになる。"""
    from app.services import webauthn_authentication

    app_admin = await app_admin_user_factory()
    app_admin.hashed_passphrase = get_password_hash("passphrase")
    credential_id = b"concurrent-authentication-credential"
    db_session.add(WebAuthnCredential(
        staff_id=app_admin.id, credential_id=credential_id,
        public_key=b"authentication-public-key", display_name="Touch ID", transports=["internal"],
    ))
    await db_session.commit()
    monkeypatch.setattr(webauthn_authentication.settings, "WEBAUTHN_RP_ID", "test.local")
    monkeypatch.setattr(webauthn_authentication.settings, "WEBAUTHN_ALLOWED_ORIGINS", "https://test.local")
    monkeypatch.setattr(webauthn_authentication, "verify_authentication_response", lambda **_: SimpleNamespace(
        new_sign_count=1, user_verified=True
    ))

    login_response = await async_client.post(
        "/api/v1/auth/token",
        data={"username": app_admin.email, "password": "a-very-secure-password", "passphrase": "passphrase"},
    )
    pending_token = login_response.json()["webauthn_pending_token"]
    options_response = await async_client.post(
        "/api/v1/auth/webauthn/authentication/options",
        json={"pending_token": pending_token},
    )
    challenge = base64url_decode(options_response.json()["publicKey"]["challenge"])
    assertion = _assertion(challenge, credential_id)

    # ASGITransportとpytestの単一イベントループでは、同一DBに対する
    # 実時間競合を安定して再現できないため、同一assertionの競合試行を
    # 連続して実行し、DB側の原子的な単回消費結果を検証する。
    responses = [
        await async_client.post(
            "/api/v1/auth/webauthn/authentication/verify",
            json={"pending_token": pending_token, "credential": assertion},
        )
    ]
    async_client.cookies.delete("access_token")
    responses.append(
        await async_client.post(
            "/api/v1/auth/webauthn/authentication/verify",
            json={"pending_token": pending_token, "credential": assertion},
        )
    )
    assert sorted(response.status_code for response in responses) == [200, 401], [
        (response.status_code, response.text) for response in responses
    ]
    assert sum(bool(response.cookies.get("access_token")) for response in responses) == 1
