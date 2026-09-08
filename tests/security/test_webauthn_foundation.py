import base64
import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.core.webauthn import base64url_decode, base64url_encode, hash_challenge
from app.crud.crud_webauthn import MAX_CHALLENGE_TTL, crud_webauthn
from app.models.enums import StaffRole
from app.models.staff import Staff
from app.models.webauthn import (
    WebAuthnCeremony,
    WebAuthnChallenge,
    WebAuthnCredential,
)


def settings_values(**overrides):
    values = {
        "SECRET_KEY": "test-secret",
        "DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test",
        "FRONTEND_URL": "http://test.local",
        "ENVIRONMENT": "production",
        "WEBAUTHN_RP_ID": "www.keikakun.com",
        "WEBAUTHN_RP_NAME": "Keikakun",
        "WEBAUTHN_ALLOWED_ORIGINS": "https://www.keikakun.com",
    }
    values.update(overrides)
    return values


def test_production_requires_complete_webauthn_relying_party_configuration():
    with pytest.raises(ValidationError, match="WEBAUTHN"):
        Settings(**settings_values(WEBAUTHN_ALLOWED_ORIGINS=None))


def test_webauthn_configuration_rejects_non_https_production_origin():
    with pytest.raises(ValidationError, match="HTTPS"):
        Settings(
            **settings_values(
                WEBAUTHN_ALLOWED_ORIGINS="http://www.keikakun.com",
            )
        )


def test_webauthn_configuration_parses_exact_origin_allowlist():
    settings = Settings(
        **settings_values(
            ENVIRONMENT="development",
            WEBAUTHN_ALLOWED_ORIGINS=(
                "https://www.keikakun.com,https://admin.keikakun.com"
            ),
        )
    )

    assert settings.webauthn_allowed_origins == (
        "https://www.keikakun.com",
        "https://admin.keikakun.com",
    )


def test_development_allows_localhost_http_origin_for_browser_webauthn():
    settings = Settings(
        **settings_values(
            ENVIRONMENT="development",
            WEBAUTHN_RP_ID="localhost",
            WEBAUTHN_ALLOWED_ORIGINS="http://localhost:3000",
        )
    )

    assert settings.webauthn_allowed_origins == ("http://localhost:3000",)


def test_webauthn_configuration_rejects_origin_outside_rp_id():
    with pytest.raises(ValidationError, match="WEBAUTHN_RP_ID"):
        Settings(
            **settings_values(
                WEBAUTHN_ALLOWED_ORIGINS="https://unrelated.example.com",
            )
        )


def test_challenge_helpers_round_trip_without_padding_and_hash_plaintext_once():
    challenge = b"a challenge that is never persisted in plaintext"

    encoded = base64url_encode(challenge)

    assert "=" not in encoded
    assert base64url_decode(encoded) == challenge
    assert hash_challenge(challenge) == hashlib.sha256(challenge).hexdigest()


@pytest.fixture
async def app_admin(db_session):
    staff = Staff(
        email="passkey-admin@example.com",
        hashed_password="hashed-password",
        first_name="管理",
        last_name="テスト",
        full_name="テスト 管理",
        role=StaffRole.app_admin,
        is_test_data=True,
    )
    db_session.add(staff)
    await db_session.commit()
    await db_session.refresh(staff)
    return staff


@pytest.mark.asyncio
async def test_credential_and_hashed_single_use_challenge_are_persisted(
    db_session, app_admin
):
    credential = WebAuthnCredential(
        staff_id=app_admin.id,
        credential_id=b"credential-id",
        public_key=b"credential-public-key",
        transports=["internal"],
        backup_eligible=True,
        backup_state=True,
        display_name="業務用端末",
    )
    challenge_plaintext = b"one-time-challenge"
    challenge = WebAuthnChallenge(
        staff_id=app_admin.id,
        ceremony="registration",
        challenge_hash=hash_challenge(challenge_plaintext),
        session_id_hash=hash_challenge(b"temporary-session"),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    db_session.add_all([credential, challenge])
    await db_session.commit()
    await db_session.refresh(credential)
    await db_session.refresh(challenge)

    assert credential.id is not None
    assert credential.credential_id == b"credential-id"
    assert credential.public_key == b"credential-public-key"
    assert credential.revoked_at is None
    assert challenge.used_at is None
    assert not hasattr(challenge, "challenge")


@pytest.mark.asyncio
async def test_credential_id_is_unique(db_session, app_admin):
    first = WebAuthnCredential(
        staff_id=app_admin.id,
        credential_id=b"duplicate-credential-id",
        public_key=b"first-public-key",
        display_name="1台目",
    )
    db_session.add(first)
    await db_session.commit()

    duplicate = WebAuthnCredential(
        staff_id=app_admin.id,
        credential_id=b"duplicate-credential-id",
        public_key=b"second-public-key",
        display_name="2台目",
    )
    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_challenge_can_be_consumed_only_once_by_bound_staff_and_session(
    db_session, app_admin
):
    challenge = b"bound-one-time-challenge"
    session_id = b"bound-temporary-session"
    await crud_webauthn.create_challenge(
        db_session,
        staff_id=app_admin.id,
        ceremony=WebAuthnCeremony.authentication,
        challenge=challenge,
        session_id=session_id,
    )
    await db_session.commit()

    consumed = await crud_webauthn.consume_challenge(
        db_session,
        staff_id=app_admin.id,
        ceremony="authentication",
        challenge=challenge,
        session_id=session_id,
    )
    replayed = await crud_webauthn.consume_challenge(
        db_session,
        staff_id=app_admin.id,
        ceremony="authentication",
        challenge=challenge,
        session_id=session_id,
    )

    assert consumed is not None
    assert replayed is None


@pytest.mark.asyncio
async def test_challenge_expiry_is_capped_by_server_policy(db_session, app_admin):
    issued_before = datetime.now(timezone.utc)

    challenge = await crud_webauthn.create_challenge(
        db_session,
        staff_id=app_admin.id,
        ceremony=WebAuthnCeremony.registration,
        challenge=b"ttl-capped-challenge",
        session_id=b"ttl-capped-session",
    )
    issued_after = datetime.now(timezone.utc)

    assert issued_before + MAX_CHALLENGE_TTL <= challenge.expires_at
    assert challenge.expires_at <= issued_after + MAX_CHALLENGE_TTL


@pytest.mark.asyncio
async def test_unknown_ceremony_is_rejected_by_crud_and_database(db_session, app_admin):
    with pytest.raises(ValueError):
        await crud_webauthn.create_challenge(
            db_session,
            staff_id=app_admin.id,
            ceremony="unexpected",
            challenge=b"invalid-ceremony",
            session_id=b"invalid-ceremony-session",
        )

    invalid_challenge = WebAuthnChallenge(
        staff_id=app_admin.id,
        ceremony="unexpected",
        challenge_hash=hash_challenge(b"invalid-ceremony-db"),
        session_id_hash=hash_challenge(b"invalid-ceremony-db-session"),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
    )
    db_session.add(invalid_challenge)

    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_consume_challenge_rejects_unknown_ceremony(db_session, app_admin):
    with pytest.raises(ValueError):
        await crud_webauthn.consume_challenge(
            db_session,
            staff_id=app_admin.id,
            ceremony="unexpected",
            challenge=b"unknown-ceremony-challenge",
            session_id=b"unknown-ceremony-session",
        )


@pytest.mark.asyncio
async def test_expired_challenge_cannot_be_consumed(db_session, app_admin):
    challenge = b"expired-one-time-challenge"
    session_id = b"expired-temporary-session"
    expired_challenge = WebAuthnChallenge(
        staff_id=app_admin.id,
        ceremony=WebAuthnCeremony.registration.value,
        challenge_hash=hash_challenge(challenge),
        session_id_hash=hash_challenge(session_id),
        expires_at=datetime(2000, 1, 1, tzinfo=timezone.utc),
    )
    db_session.add(expired_challenge)
    await db_session.commit()

    consumed = await crud_webauthn.consume_challenge(
        db_session,
        staff_id=app_admin.id,
        ceremony="registration",
        challenge=challenge,
        session_id=session_id,
    )

    assert consumed is None
