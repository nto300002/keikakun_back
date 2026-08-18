"""
app_admin合言葉認証のテスト

TDD形式でapp_admin用の合言葉（セカンドパスワード）認証をテスト
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import StaffRole
from app.models.mfa import MFAAuditLog
from app.core.security import create_access_token, get_password_hash
from unittest.mock import patch

pytestmark = pytest.mark.asyncio


# ========================================
# app_admin ログイン（合言葉あり）
# ========================================

async def test_app_admin_login_with_valid_passphrase(
    async_client: AsyncClient,
    db_session: AsyncSession,
    app_admin_user_factory
):
    """正常系: app_adminが正しい合言葉でログイン"""
    # Arrange
    passphrase = "secret123!"
    app_admin = await app_admin_user_factory()

    # 合言葉を設定
    app_admin.hashed_passphrase = get_password_hash(passphrase)
    await db_session.commit()

    # Act
    response = await async_client.post(
        "/api/v1/auth/token",
        data={
            "username": app_admin.email,
            "password": "a-very-secure-password",  # factory default
            "passphrase": passphrase
        }
    )

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert "refresh_token" in data or "requires_mfa_verification" in data


async def test_app_admin_can_enroll_verify_and_require_mfa_on_login(
    async_client: AsyncClient,
    db_session: AsyncSession,
    app_admin_user_factory,
):
    """app_adminも本人用のMFAを設定し、次回ログインでMFA確認を要求される。"""
    passphrase = "secret123!"
    app_admin = await app_admin_user_factory()
    app_admin.hashed_passphrase = get_password_hash(passphrase)
    await db_session.commit()

    access_token = create_access_token(subject=str(app_admin.id))
    headers = {"Authorization": f"Bearer {access_token}"}

    enroll_response = await async_client.post(
        "/api/v1/auth/mfa/enroll",
        headers=headers,
    )

    assert enroll_response.status_code == 200
    assert enroll_response.json()["qr_code_uri"].startswith("otpauth://totp/")

    with patch("app.services.mfa.verify_totp", return_value=True):
        verify_response = await async_client.post(
            "/api/v1/auth/mfa/verify",
            headers=headers,
            json={"totp_code": "123456"},
        )

    assert verify_response.status_code == 200
    await db_session.refresh(app_admin)
    assert app_admin.is_mfa_enabled is True
    assert app_admin.is_mfa_verified_by_user is True

    login_response = await async_client.post(
        "/api/v1/auth/token",
        data={
            "username": app_admin.email,
            "password": "a-very-secure-password",
            "passphrase": passphrase,
        },
    )

    assert login_response.status_code == 200
    assert login_response.json()["requires_mfa_verification"] is True

    disable_response = await async_client.post(
        "/api/v1/auth/mfa/disable",
        headers=headers,
        json={"password": "a-very-secure-password"},
    )

    assert disable_response.status_code == 200
    await db_session.refresh(app_admin)
    assert app_admin.is_mfa_enabled is False

    audit_logs = (await db_session.execute(
        select(MFAAuditLog).where(MFAAuditLog.staff_id == app_admin.id)
    )).scalars().all()
    assert [(log.action, log.details) for log in audit_logs] == [
        ("enabled", "self_service"),
        ("disabled", "self_service"),
    ]


async def test_app_admin_login_without_passphrase(
    async_client: AsyncClient,
    db_session: AsyncSession,
    app_admin_user_factory
):
    """異常系: app_adminが合言葉なしでログイン試行 (401)"""
    # Arrange
    passphrase = "secret123!"
    app_admin = await app_admin_user_factory()

    # 合言葉を設定
    app_admin.hashed_passphrase = get_password_hash(passphrase)
    await db_session.commit()

    # Act
    response = await async_client.post(
        "/api/v1/auth/token",
        data={
            "username": app_admin.email,
            "password": "a-very-secure-password"
            # passphrase なし
        }
    )

    # Assert
    assert response.status_code == 401
    data = response.json()
    assert "合言葉を入力してください" in data["detail"]


async def test_app_admin_login_with_wrong_passphrase(
    async_client: AsyncClient,
    db_session: AsyncSession,
    app_admin_user_factory
):
    """異常系: app_adminが間違った合言葉でログイン試行 (401)"""
    # Arrange
    passphrase = "secret123!"
    app_admin = await app_admin_user_factory()

    # 合言葉を設定
    app_admin.hashed_passphrase = get_password_hash(passphrase)
    await db_session.commit()

    # Act
    response = await async_client.post(
        "/api/v1/auth/token",
        data={
            "username": app_admin.email,
            "password": "a-very-secure-password",
            "passphrase": "wrong_passphrase"
        }
    )

    # Assert
    assert response.status_code == 401
    data = response.json()
    assert "認証に失敗しました" in data["detail"]


async def test_app_admin_login_passphrase_not_set(
    async_client: AsyncClient,
    db_session: AsyncSession,
    app_admin_user_factory
):
    """異常系: app_adminに合言葉が設定されていない (403)"""
    # Arrange
    app_admin = await app_admin_user_factory()
    # 合言葉は設定しない（hashed_passphrase = None）
    await db_session.commit()

    # Act
    response = await async_client.post(
        "/api/v1/auth/token",
        data={
            "username": app_admin.email,
            "password": "a-very-secure-password",
            "passphrase": "any_passphrase"
        }
    )

    # Assert
    assert response.status_code == 403
    data = response.json()
    assert "合言葉が設定されていません" in data["detail"]


# ========================================
# 通常ユーザー（合言葉不要）
# ========================================

async def test_owner_login_without_passphrase(
    async_client: AsyncClient,
    db_session: AsyncSession,
    owner_user_factory
):
    """正常系: ownerは合言葉なしでログイン可能"""
    # Arrange
    owner = await owner_user_factory(role=StaffRole.owner)
    await db_session.commit()

    # Act
    response = await async_client.post(
        "/api/v1/auth/token",
        data={
            "username": owner.email,
            "password": "a-very-secure-password"
            # passphrase なし（ownerには不要）
        }
    )

    # Assert
    assert response.status_code == 200


async def test_manager_login_without_passphrase(
    async_client: AsyncClient,
    db_session: AsyncSession,
    manager_user_factory
):
    """正常系: managerは合言葉なしでログイン可能"""
    # Arrange
    manager = await manager_user_factory(role=StaffRole.manager)
    await db_session.commit()

    # Act
    response = await async_client.post(
        "/api/v1/auth/token",
        data={
            "username": manager.email,
            "password": "a-very-secure-password"
        }
    )

    # Assert
    assert response.status_code == 200


async def test_employee_login_without_passphrase(
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory
):
    """正常系: employeeは合言葉なしでログイン可能"""
    # Arrange
    employee = await employee_user_factory(role=StaffRole.employee)
    await db_session.commit()

    # Act
    response = await async_client.post(
        "/api/v1/auth/token",
        data={
            "username": employee.email,
            "password": "a-very-secure-password"
        }
    )

    # Assert
    assert response.status_code == 200


# ========================================
# パスワード間違い（合言葉以前の問題）
# ========================================

async def test_app_admin_login_wrong_password(
    async_client: AsyncClient,
    db_session: AsyncSession,
    app_admin_user_factory
):
    """異常系: app_adminがパスワードを間違えた場合 (401)"""
    # Arrange
    passphrase = "secret123!"
    app_admin = await app_admin_user_factory()
    app_admin.hashed_passphrase = get_password_hash(passphrase)
    await db_session.commit()

    # Act
    response = await async_client.post(
        "/api/v1/auth/token",
        data={
            "username": app_admin.email,
            "password": "wrong_password",
            "passphrase": passphrase
        }
    )

    # Assert
    assert response.status_code == 401
    data = response.json()
    assert "メールアドレスまたはパスワードが正しくありません" in data["detail"]
