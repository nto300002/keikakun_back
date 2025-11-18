"""
利用規約・プライバシーポリシー同意管理 APIのテスト
TDD (Test-Driven Development) によるテスト実装
"""

import pytest
from datetime import timedelta
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.schemas.terms_agreement import TermsAgreementCreate
from app.core.security import create_access_token
from app.core.config import settings

pytestmark = pytest.mark.asyncio


# ========================================
# POST /api/v1/terms/agree
# ========================================

async def test_agree_to_terms_success(
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory
):
    """正常系: 利用規約・プライバシーポリシーに同意"""
    # Arrange
    employee = await employee_user_factory()
    access_token = create_access_token(
        str(employee.id),
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    # Act
    response = await async_client.post(
        "/api/v1/terms/agree",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "agree_to_terms": True,
            "agree_to_privacy": True,
            "terms_version": "1.0",
            "privacy_version": "1.0"
        }
    )

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "利用規約とプライバシーポリシーへの同意が記録されました"
    assert data["terms_version"] == "1.0"
    assert data["privacy_version"] == "1.0"
    assert "agreed_at" in data

    # データベースに保存されているか確認
    agreement = await crud.terms_agreement.get_by_staff_id(
        db_session,
        staff_id=employee.id
    )
    assert agreement is not None
    assert agreement.terms_of_service_agreed_at is not None
    assert agreement.privacy_policy_agreed_at is not None
    assert agreement.terms_version == "1.0"
    assert agreement.privacy_version == "1.0"


async def test_agree_to_terms_partial_agreement_fails(
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory
):
    """異常系: 利用規約のみ同意（プライバシーポリシー未同意）"""
    # Arrange
    employee = await employee_user_factory()
    access_token = create_access_token(
        str(employee.id),
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    # Act
    response = await async_client.post(
        "/api/v1/terms/agree",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "agree_to_terms": True,
            "agree_to_privacy": False,
            "terms_version": "1.0",
            "privacy_version": "1.0"
        }
    )

    # Assert
    assert response.status_code == 400
    data = response.json()
    assert "利用規約とプライバシーポリシーの両方に同意する必要があります" in data["detail"]


async def test_agree_to_terms_unauthorized(
    async_client: AsyncClient,
    db_session: AsyncSession
):
    """異常系: 認証なしでリクエスト"""
    # Act
    response = await async_client.post(
        "/api/v1/terms/agree",
        json={
            "agree_to_terms": True,
            "agree_to_privacy": True,
            "terms_version": "1.0",
            "privacy_version": "1.0"
        }
    )

    # Assert
    assert response.status_code == 401


async def test_agree_to_terms_updates_existing_record(
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory
):
    """正常系: 既存の同意履歴を更新"""
    # Arrange
    employee = await employee_user_factory()

    # 既存の同意履歴を作成（古いバージョン）
    await crud.terms_agreement.create(
        db_session,
        obj_in=TermsAgreementCreate(
            staff_id=employee.id,
            terms_version="0.9",
            privacy_version="0.9"
        )
    )
    await db_session.commit()

    access_token = create_access_token(
        str(employee.id),
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    # Act
    response = await async_client.post(
        "/api/v1/terms/agree",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "agree_to_terms": True,
            "agree_to_privacy": True,
            "terms_version": "1.0",
            "privacy_version": "1.0"
        }
    )

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["terms_version"] == "1.0"
    assert data["privacy_version"] == "1.0"

    # データベースで確認（レコードは1つのみ）
    agreement = await crud.terms_agreement.get_by_staff_id(
        db_session,
        staff_id=employee.id
    )
    assert agreement.terms_version == "1.0"
    assert agreement.privacy_version == "1.0"


async def test_agree_to_terms_records_ip_and_user_agent(
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory
):
    """正常系: IPアドレスとユーザーエージェントが記録される"""
    # Arrange
    employee = await employee_user_factory()
    access_token = create_access_token(
        str(employee.id),
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    # Act
    response = await async_client.post(
        "/api/v1/terms/agree",
        headers={
            "Authorization": f"Bearer {access_token}",
            "User-Agent": "TestAgent/1.0"
        },
        json={
            "agree_to_terms": True,
            "agree_to_privacy": True,
            "terms_version": "1.0",
            "privacy_version": "1.0"
        }
    )

    # Assert
    assert response.status_code == 200

    # データベースで確認
    agreement = await crud.terms_agreement.get_by_staff_id(
        db_session,
        staff_id=employee.id
    )
    assert agreement.ip_address is not None
    assert agreement.user_agent == "TestAgent/1.0"


# ========================================
# GET /api/v1/terms/status
# ========================================

async def test_get_agreement_status_success(
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory
):
    """正常系: 同意状態を取得"""
    # Arrange
    employee = await employee_user_factory()

    # 同意履歴を作成
    await crud.terms_agreement.agree_to_terms(
        db_session,
        staff_id=employee.id,
        terms_version="1.0",
        privacy_version="1.0",
        ip_address="192.168.1.1",
        user_agent="TestAgent/1.0"
    )
    await db_session.commit()

    access_token = create_access_token(
        str(employee.id),
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    # Act
    response = await async_client.get(
        "/api/v1/terms/status",
        headers={"Authorization": f"Bearer {access_token}"}
    )

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["staff_id"] == str(employee.id)
    assert data["terms_version"] == "1.0"
    assert data["privacy_version"] == "1.0"
    assert data["terms_of_service_agreed_at"] is not None
    assert data["privacy_policy_agreed_at"] is not None


async def test_get_agreement_status_not_found(
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory
):
    """異常系: 同意履歴が存在しない"""
    # Arrange
    employee = await employee_user_factory()
    access_token = create_access_token(
        str(employee.id),
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    # Act
    response = await async_client.get(
        "/api/v1/terms/status",
        headers={"Authorization": f"Bearer {access_token}"}
    )

    # Assert
    assert response.status_code == 404
    data = response.json()
    assert "同意履歴が見つかりません" in data["detail"]


async def test_get_agreement_status_unauthorized(
    async_client: AsyncClient,
    db_session: AsyncSession
):
    """異常系: 認証なしでリクエスト"""
    # Act
    response = await async_client.get("/api/v1/terms/status")

    # Assert
    assert response.status_code == 401


# ========================================
# GET /api/v1/terms/required
# ========================================

async def test_check_agreement_required_not_agreed(
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory
):
    """正常系: 未同意の場合、requiredがTrueになる"""
    # Arrange
    employee = await employee_user_factory()
    access_token = create_access_token(
        str(employee.id),
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    # Act
    response = await async_client.get(
        "/api/v1/terms/required",
        headers={"Authorization": f"Bearer {access_token}"}
    )

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["required"] is True
    assert data["reason"] == "未同意"
    assert "current_terms_version" in data
    assert "current_privacy_version" in data


async def test_check_agreement_required_already_agreed(
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory
):
    """正常系: 最新バージョンに同意済みの場合、requiredがFalseになる"""
    # Arrange
    employee = await employee_user_factory()

    # 最新バージョンに同意
    await crud.terms_agreement.agree_to_terms(
        db_session,
        staff_id=employee.id,
        terms_version="1.0",
        privacy_version="1.0"
    )
    await db_session.commit()

    access_token = create_access_token(
        str(employee.id),
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    # Act
    response = await async_client.get(
        "/api/v1/terms/required",
        headers={"Authorization": f"Bearer {access_token}"}
    )

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["required"] is False
    assert data["terms_version"] == "1.0"
    assert data["privacy_version"] == "1.0"


async def test_check_agreement_required_old_version(
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory
):
    """正常系: 古いバージョンに同意している場合、requiredがTrueになる"""
    # Arrange
    employee = await employee_user_factory()

    # 古いバージョンに同意
    await crud.terms_agreement.agree_to_terms(
        db_session,
        staff_id=employee.id,
        terms_version="0.9",
        privacy_version="0.9"
    )
    await db_session.commit()

    access_token = create_access_token(
        str(employee.id),
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    # Act
    response = await async_client.get(
        "/api/v1/terms/required",
        headers={"Authorization": f"Bearer {access_token}"}
    )

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["required"] is True
    assert data["reason"] == "規約が更新されました"
    assert data["needs_terms_update"] is True
    assert data["needs_privacy_update"] is True
    assert data["agreed_terms_version"] == "0.9"
    assert data["agreed_privacy_version"] == "0.9"


async def test_check_agreement_required_unauthorized(
    async_client: AsyncClient,
    db_session: AsyncSession
):
    """異常系: 認証なしでリクエスト"""
    # Act
    response = await async_client.get("/api/v1/terms/required")

    # Assert
    assert response.status_code == 401


# ========================================
# エッジケース
# ========================================

async def test_agree_to_terms_with_custom_version(
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory
):
    """正常系: カスタムバージョンで同意"""
    # Arrange
    employee = await employee_user_factory()
    access_token = create_access_token(
        str(employee.id),
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    # Act
    response = await async_client.post(
        "/api/v1/terms/agree",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "agree_to_terms": True,
            "agree_to_privacy": True,
            "terms_version": "2.0",
            "privacy_version": "2.5"
        }
    )

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["terms_version"] == "2.0"
    assert data["privacy_version"] == "2.5"

    # データベースで確認
    agreement = await crud.terms_agreement.get_by_staff_id(
        db_session,
        staff_id=employee.id
    )
    assert agreement.terms_version == "2.0"
    assert agreement.privacy_version == "2.5"
