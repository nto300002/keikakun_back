"""
app_admin用監査ログAPIのテスト

テスト対象:
- GET /api/v1/admin/audit-logs
  - 正常系: 監査ログ一覧取得
  - 正常系: target_typeによるフィルタリング
  - 正常系: ページネーション
  - 異常系: app_admin以外のアクセス（403）
"""
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.staff_profile import AuditLog
from app.models.enums import AuditLogTargetType

pytestmark = pytest.mark.asyncio


async def test_get_audit_logs_success(
    async_client: AsyncClient,
    db_session: AsyncSession,
    app_admin_user_factory,
    office_factory
):
    """正常系: app_adminが監査ログ一覧を取得できる"""
    # Arrange
    app_admin = await app_admin_user_factory()
    passphrase = "secret123!"
    from app.core.security import get_password_hash
    app_admin.hashed_passphrase = get_password_hash(passphrase)

    office = await office_factory(name="Test Office")
    await db_session.commit()

    # サンプル監査ログを作成
    now = datetime.now(timezone.utc)
    logs = [
        AuditLog(
            staff_id=app_admin.id,
            actor_role="app_admin",
            action="staff.deleted",
            target_type=AuditLogTargetType.staff.value,
            target_id=uuid.uuid4(),
            office_id=office.id,
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
            details={"reason": "test deletion"},
            timestamp=now - timedelta(minutes=10),
            is_test_data=False
        ),
        AuditLog(
            staff_id=app_admin.id,
            actor_role="app_admin",
            action="office.updated",
            target_type=AuditLogTargetType.office.value,
            target_id=office.id,
            office_id=office.id,
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
            details={"changes": {"name": "Updated Name"}},
            timestamp=now - timedelta(minutes=20),
            is_test_data=False
        ),
    ]

    for log in logs:
        db_session.add(log)
    await db_session.commit()

    # Act: ログイン
    login_response = await async_client.post(
        "/api/v1/auth/token",
        data={
            "username": app_admin.email,
            "password": "a-very-secure-password",
            "passphrase": passphrase
        }
    )
    assert login_response.status_code == 200

    # Act: 監査ログ一覧取得
    response = await async_client.get(
        "/api/v1/admin/audit-logs",
        params={"skip": 0, "limit": 50}
    )

    # Assert
    assert response.status_code == 200
    data = response.json()

    assert "logs" in data
    assert "total" in data
    assert len(data["logs"]) >= 2  # 最低2件
    assert data["total"] >= 2

    # 最新のログが最初に来る（降順）
    assert data["logs"][0]["action"] == "staff.deleted"


async def test_filter_by_target_type_staff(
    async_client: AsyncClient,
    db_session: AsyncSession,
    app_admin_user_factory,
    office_factory
):
    """正常系: target_type=staffでフィルタリング"""
    # Arrange
    app_admin = await app_admin_user_factory()
    passphrase = "secret123!"
    from app.core.security import get_password_hash
    app_admin.hashed_passphrase = get_password_hash(passphrase)

    office = await office_factory(name="Test Office")
    await db_session.commit()

    # サンプル監査ログを作成
    now = datetime.now(timezone.utc)
    logs = [
        AuditLog(
            staff_id=app_admin.id,
            actor_role="app_admin",
            action="staff.deleted",
            target_type=AuditLogTargetType.staff.value,
            target_id=uuid.uuid4(),
            office_id=office.id,
            timestamp=now - timedelta(minutes=10),
            is_test_data=False
        ),
        AuditLog(
            staff_id=app_admin.id,
            actor_role="app_admin",
            action="office.updated",
            target_type=AuditLogTargetType.office.value,
            target_id=office.id,
            office_id=office.id,
            timestamp=now - timedelta(minutes=20),
            is_test_data=False
        ),
    ]

    for log in logs:
        db_session.add(log)
    await db_session.commit()

    # Act: ログイン
    await async_client.post(
        "/api/v1/auth/token",
        data={
            "username": app_admin.email,
            "password": "a-very-secure-password",
            "passphrase": passphrase
        }
    )

    # Act: target_type=staffでフィルタリング
    response = await async_client.get(
        "/api/v1/admin/audit-logs",
        params={"target_type": "staff", "skip": 0, "limit": 50}
    )

    # Assert
    assert response.status_code == 200
    data = response.json()

    assert len(data["logs"]) >= 1
    for item in data["logs"]:
        assert item["target_type"] == "staff"


async def test_pagination(
    async_client: AsyncClient,
    db_session: AsyncSession,
    app_admin_user_factory,
    office_factory
):
    """正常系: ページネーション"""
    # Arrange
    app_admin = await app_admin_user_factory()
    passphrase = "secret123!"
    from app.core.security import get_password_hash
    app_admin.hashed_passphrase = get_password_hash(passphrase)

    office = await office_factory(name="Test Office")
    await db_session.commit()

    # 4件のサンプル監査ログを作成
    now = datetime.now(timezone.utc)
    for i in range(4):
        log = AuditLog(
            staff_id=app_admin.id,
            actor_role="app_admin",
            action=f"test.action{i}",
            target_type=AuditLogTargetType.staff.value,
            target_id=uuid.uuid4(),
            office_id=office.id,
            timestamp=now - timedelta(minutes=i*10),
            is_test_data=False
        )
        db_session.add(log)
    await db_session.commit()

    # Act: ログイン
    await async_client.post(
        "/api/v1/auth/token",
        data={
            "username": app_admin.email,
            "password": "a-very-secure-password",
            "passphrase": passphrase
        }
    )

    # Act: 1ページ目（2件取得）
    response1 = await async_client.get(
        "/api/v1/admin/audit-logs",
        params={"skip": 0, "limit": 2}
    )

    # Assert
    assert response1.status_code == 200
    data1 = response1.json()

    assert len(data1["logs"]) == 2
    assert data1["total"] >= 4
    assert data1["skip"] == 0
    assert data1["limit"] == 2

    # Act: 2ページ目（2件取得）
    response2 = await async_client.get(
        "/api/v1/admin/audit-logs",
        params={"skip": 2, "limit": 2}
    )

    # Assert
    assert response2.status_code == 200
    data2 = response2.json()

    assert len(data2["logs"]) >= 2
    assert data2["total"] >= 4
    assert data2["skip"] == 2
    assert data2["limit"] == 2


async def test_forbidden_non_app_admin(
    async_client: AsyncClient,
    db_session: AsyncSession,
    owner_user_factory
):
    """異常系: app_admin以外のアクセスは403エラー"""
    # Arrange
    owner = await owner_user_factory()
    await db_session.commit()

    # Act: ログイン
    await async_client.post(
        "/api/v1/auth/token",
        data={
            "username": owner.email,
            "password": "a-very-secure-password"
        }
    )

    # Act: 監査ログ一覧取得を試みる
    response = await async_client.get(
        "/api/v1/admin/audit-logs",
        params={"skip": 0, "limit": 50}
    )

    # Assert
    assert response.status_code == 403
    data = response.json()
    assert "権限" in data["detail"]


async def test_unauthorized_no_token(
    async_client: AsyncClient
):
    """異常系: トークンなしのアクセスは401エラー"""
    # Act: 認証なしでアクセス
    response = await async_client.get(
        "/api/v1/admin/audit-logs",
        params={"skip": 0, "limit": 50}
    )

    # Assert
    assert response.status_code == 401
