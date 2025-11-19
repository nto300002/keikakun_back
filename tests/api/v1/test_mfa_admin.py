import pytest
import pytest_asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.models.staff import Staff
from app.models.enums import StaffRole
from app.models.office import OfficeStaff
from app.core.security import create_access_token, verify_totp, generate_totp_secret, get_password_hash
from tests.utils import (
    random_email,
    random_string,
    create_random_staff,
    create_admin_staff,
)


class TestAdminMFAToggle:
    """管理者によるMFA切り替え機能のテスト（TDD）"""

    @pytest.mark.asyncio
    async def test_admin_enable_staff_mfa_success(self, async_client: AsyncClient, db_session: AsyncSession):
        """
        正常系: 管理者が他のスタッフのMFAを有効化できることをテスト

        前提条件:
        - 管理者ユーザー（owner）が存在する
        - 対象スタッフ（employee）のMFAが無効

        期待される結果:
        - ステータスコード: 200
        - 対象スタッフのis_mfa_enabledがTrueになる
        - MFAシークレットが設定される
        """
        # Arrange: 管理者ユーザーと対象スタッフを作成
        admin = await create_admin_staff(db_session, is_mfa_enabled=False)
        target_staff = await create_random_staff(
            db_session,
            role=StaffRole.employee,
            is_mfa_enabled=False
        )
        # 一度だけcommit
        await db_session.commit()

        # Arrange: 管理者のアクセストークンを作成
        admin_token = create_access_token(subject=str(admin.id))
        headers = {"Authorization": f"Bearer {admin_token}"}

        # Act: MFA有効化エンドポイントを呼び出し
        response = await async_client.post(
            f"/api/v1/auth/admin/staff/{target_staff.id}/mfa/enable",
            headers=headers
        )

        # Assert: レスポンス検証
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "message" in data
        assert "多要素認証を有効にしました" in data["message"]

        # Assert: DBの状態を検証
        await db_session.refresh(target_staff)
        assert target_staff.is_mfa_enabled is True
        assert target_staff.mfa_secret is not None

    @pytest.mark.asyncio
    async def test_admin_disable_staff_mfa_success(self, async_client: AsyncClient, db_session: AsyncSession):
        """
        正常系: 管理者が他のスタッフのMFAを無効化できることをテスト

        前提条件:
        - 管理者ユーザー（owner）が存在する
        - 対象スタッフ（employee）のMFAが有効

        期待される結果:
        - ステータスコード: 200
        - 対象スタッフのis_mfa_enabledがFalseになる
        - MFAシークレットがNullになる
        """
        # Arrange: 管理者ユーザーと対象スタッフを作成
        admin = await create_admin_staff(db_session, is_mfa_enabled=False)
        target_staff = await create_random_staff(
            db_session,
            role=StaffRole.employee,
            is_mfa_enabled=True
        )
        target_staff.mfa_secret = generate_totp_secret()
        # 一度だけcommit
        await db_session.commit()

        # Arrange: 管理者のアクセストークンを作成
        admin_token = create_access_token(subject=str(admin.id))
        headers = {"Authorization": f"Bearer {admin_token}"}

        # Act: MFA無効化エンドポイントを呼び出し
        response = await async_client.post(
            f"/api/v1/auth/admin/staff/{target_staff.id}/mfa/disable",
            headers=headers
        )

        # Assert: レスポンス検証
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "message" in data
        assert "多要素認証を無効にしました" in data["message"]

        # Assert: DBの状態を検証
        await db_session.refresh(target_staff)
        assert target_staff.is_mfa_enabled is False
        assert target_staff.mfa_secret is None

    @pytest.mark.asyncio
    async def test_admin_enable_mfa_non_admin_forbidden(self, async_client: AsyncClient, db_session: AsyncSession):
        """
        異常系: 管理者権限がないユーザーがMFA切り替えを試みた場合はエラー

        前提条件:
        - 一般スタッフ（employee）が存在する
        - 対象スタッフ（employee）のMFAが無効

        期待される結果:
        - ステータスコード: 403 Forbidden
        - エラーメッセージ: 管理者権限が必要
        """
        # Arrange: 一般スタッフと対象スタッフを作成
        employee = await create_random_staff(
            db_session,
            role=StaffRole.employee,
            is_mfa_enabled=False
        )
        target_staff = await create_random_staff(
            db_session,
            role=StaffRole.employee,
            is_mfa_enabled=False
        )
        # 一度だけcommit
        await db_session.commit()

        # Arrange: 一般スタッフのアクセストークンを作成
        employee_token = create_access_token(subject=str(employee.id))
        headers = {"Authorization": f"Bearer {employee_token}"}

        # Act: MFA有効化エンドポイントを呼び出し
        response = await async_client.post(
            f"/api/v1/auth/admin/staff/{target_staff.id}/mfa/enable",
            headers=headers
        )

        # Assert: レスポンス検証
        assert response.status_code == status.HTTP_403_FORBIDDEN
        detail = response.json()["detail"]
        assert "管理者" in detail or "権限" in detail

    @pytest.mark.asyncio
    async def test_admin_enable_mfa_staff_not_found(self, async_client: AsyncClient, db_session: AsyncSession):
        """
        異常系: 存在しないスタッフIDに対してMFA切り替えを試みた場合はエラー

        前提条件:
        - 管理者ユーザー（owner）が存在する
        - 存在しないスタッフID

        期待される結果:
        - ステータスコード: 404 Not Found
        - エラーメッセージ: スタッフが見つからない
        """
        # Arrange: 管理者ユーザーを作成
        admin = await create_admin_staff(db_session, is_mfa_enabled=False)
        await db_session.commit()

        # Arrange: 管理者のアクセストークンと存在しないスタッフIDを作成
        admin_token = create_access_token(subject=str(admin.id))
        headers = {"Authorization": f"Bearer {admin_token}"}
        non_existent_staff_id = uuid.uuid4()

        # Act: MFA有効化エンドポイントを呼び出し
        response = await async_client.post(
            f"/api/v1/auth/admin/staff/{non_existent_staff_id}/mfa/enable",
            headers=headers
        )

        # Assert: レスポンス検証
        assert response.status_code == status.HTTP_404_NOT_FOUND
        detail = response.json()["detail"]
        assert "見つかりません" in detail or "存在しません" in detail

    @pytest.mark.asyncio
    async def test_admin_enable_mfa_already_enabled(self, async_client: AsyncClient, db_session: AsyncSession):
        """
        異常系: 既にMFAが有効なスタッフに対して有効化を試みた場合はエラー

        前提条件:
        - 管理者ユーザー（owner）が存在する
        - 対象スタッフ（employee）のMFAが既に有効

        期待される結果:
        - ステータスコード: 400 Bad Request
        - エラーメッセージ: 既にMFAが有効
        """
        # Arrange: 管理者ユーザーと対象スタッフを作成
        admin = await create_admin_staff(db_session, is_mfa_enabled=False)
        target_staff = await create_random_staff(
            db_session,
            role=StaffRole.employee,
            is_mfa_enabled=True
        )
        target_staff.mfa_secret = generate_totp_secret()
        # 一度だけcommit
        await db_session.commit()

        # Arrange: 管理者のアクセストークンを作成
        admin_token = create_access_token(subject=str(admin.id))
        headers = {"Authorization": f"Bearer {admin_token}"}

        # Act: MFA有効化エンドポイントを呼び出し
        response = await async_client.post(
            f"/api/v1/auth/admin/staff/{target_staff.id}/mfa/enable",
            headers=headers
        )

        # Assert: レスポンス検証
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        detail = response.json()["detail"]
        assert "既に" in detail or "有効" in detail

    @pytest.mark.asyncio
    async def test_admin_disable_mfa_already_disabled(self, async_client: AsyncClient, db_session: AsyncSession):
        """
        異常系: 既にMFAが無効なスタッフに対して無効化を試みた場合はエラー

        前提条件:
        - 管理者ユーザー（owner）が存在する
        - 対象スタッフ（employee）のMFAが既に無効

        期待される結果:
        - ステータスコード: 400 Bad Request
        - エラーメッセージ: 既にMFAが無効
        """
        # Arrange: 管理者ユーザーと対象スタッフを作成
        admin = await create_admin_staff(db_session, is_mfa_enabled=False)
        target_staff = await create_random_staff(
            db_session,
            role=StaffRole.employee,
            is_mfa_enabled=False
        )
        # 一度だけcommit
        await db_session.commit()

        # Arrange: 管理者のアクセストークンを作成
        admin_token = create_access_token(subject=str(admin.id))
        headers = {"Authorization": f"Bearer {admin_token}"}

        # Act: MFA無効化エンドポイントを呼び出し
        response = await async_client.post(
            f"/api/v1/auth/admin/staff/{target_staff.id}/mfa/disable",
            headers=headers
        )

        # Assert: レスポンス検証
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        detail = response.json()["detail"]
        assert "有効になっていません" in detail or "無効" in detail or "設定されていません" in detail

    @pytest.mark.asyncio
    async def test_admin_enable_mfa_unauthorized(self, async_client: AsyncClient, db_session: AsyncSession):
        """
        異常系: 認証なしでMFA切り替えを試みた場合はエラー

        前提条件:
        - 認証トークンなし

        期待される結果:
        - ステータスコード: 401 Unauthorized
        """
        # Arrange: 対象スタッフを作成
        target_staff = await create_random_staff(
            db_session,
            role=StaffRole.employee,
            is_mfa_enabled=False
        )
        await db_session.commit()

        # Act: 認証なしでMFA有効化エンドポイントを呼び出し
        response = await async_client.post(
            f"/api/v1/auth/admin/staff/{target_staff.id}/mfa/enable"
        )

        # Assert: レスポンス検証
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestAdminMFABulkOperations:
    """管理者によるMFA一括操作機能のテスト（TDD）"""

    @pytest_asyncio.fixture
    async def office_with_multiple_staffs(self, db_session: AsyncSession, service_admin_user_factory, office_factory):
        """複数のスタッフが所属する事務所を作成するフィクスチャ"""
        # Owner を作成
        owner = await service_admin_user_factory(
            email=f"owner.{uuid.uuid4().hex[:6]}@example.com",
            name="事務所オーナー",
            role=StaffRole.owner,
            is_mfa_enabled=True
        )

        # 事務所を作成
        office = await office_factory(creator=owner, name=f"テスト事務所 {uuid.uuid4().hex[:6]}")

        # Owner と事務所を紐付け
        owner_association = OfficeStaff(staff_id=owner.id, office_id=office.id, is_primary=True)
        db_session.add(owner_association)

        # Manager を作成
        manager = await service_admin_user_factory(
            email=f"manager.{uuid.uuid4().hex[:6]}@example.com",
            name="マネージャー",
            role=StaffRole.manager,
            is_mfa_enabled=True
        )
        manager_association = OfficeStaff(staff_id=manager.id, office_id=office.id, is_primary=False)
        db_session.add(manager_association)

        # Employee (MFA有効) を作成
        employee1 = await service_admin_user_factory(
            email=f"employee1.{uuid.uuid4().hex[:6]}@example.com",
            name="従業員1",
            role=StaffRole.employee,
            is_mfa_enabled=True
        )
        employee1_association = OfficeStaff(staff_id=employee1.id, office_id=office.id, is_primary=False)
        db_session.add(employee1_association)

        # Employee (MFA無効) を作成
        employee2 = await service_admin_user_factory(
            email=f"employee2.{uuid.uuid4().hex[:6]}@example.com",
            name="従業員2",
            role=StaffRole.employee,
            is_mfa_enabled=False
        )
        employee2_association = OfficeStaff(staff_id=employee2.id, office_id=office.id, is_primary=False)
        db_session.add(employee2_association)

        await db_session.commit()

        # リレーションシップをロード
        await db_session.refresh(owner, attribute_names=["office_associations"])
        await db_session.refresh(manager, attribute_names=["office_associations"])
        await db_session.refresh(employee1, attribute_names=["office_associations"])
        await db_session.refresh(employee2, attribute_names=["office_associations"])

        return {
            "office": office,
            "owner": owner,
            "manager": manager,
            "employee1": employee1,
            "employee2": employee2,
        }

    @pytest.mark.asyncio
    async def test_admin_disable_all_office_mfa_success(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        office_with_multiple_staffs
    ):
        """
        正常系: 管理者が事務所の全スタッフのMFAを一括無効化できることをテスト

        前提条件:
        - 管理者ユーザー（owner）が存在する
        - 事務所に複数のスタッフが所属している
        - 一部のスタッフのMFAが有効

        期待される結果:
        - ステータスコード: 200
        - 全スタッフのis_mfa_enabledがFalseになる
        - 無効化されたスタッフ数が返される
        """
        # Arrange: 事務所とスタッフは fixture で作成される
        owner = office_with_multiple_staffs["owner"]
        manager = office_with_multiple_staffs["manager"]
        employee1 = office_with_multiple_staffs["employee1"]
        employee2 = office_with_multiple_staffs["employee2"]

        # Arrange: 管理者のアクセストークンを作成
        admin_token = create_access_token(subject=str(owner.id))
        headers = {"Authorization": f"Bearer {admin_token}"}

        # Act: MFA一括無効化エンドポイントを呼び出し
        response = await async_client.post(
            "/api/v1/auth/admin/office/mfa/disable-all",
            headers=headers
        )

        # Assert: レスポンス検証
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "message" in data
        assert "disabled_count" in data
        assert data["disabled_count"] == 3  # owner, manager, employee1 (employee2は元々無効)

        # Assert: DB検証 - 全スタッフのMFAが無効化されていることを確認
        await db_session.refresh(owner)
        await db_session.refresh(manager)
        await db_session.refresh(employee1)
        await db_session.refresh(employee2)

        assert owner.is_mfa_enabled is False
        assert manager.is_mfa_enabled is False
        assert employee1.is_mfa_enabled is False
        assert employee2.is_mfa_enabled is False

    @pytest.mark.asyncio
    async def test_admin_disable_all_office_mfa_as_manager_success(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        office_with_multiple_staffs
    ):
        """
        正常系: Manager が事務所の全スタッフのMFAを一括無効化できることをテスト
        """
        # Arrange
        manager = office_with_multiple_staffs["manager"]
        admin_token = create_access_token(subject=str(manager.id))
        headers = {"Authorization": f"Bearer {admin_token}"}

        # Act
        response = await async_client.post(
            "/api/v1/auth/admin/office/mfa/disable-all",
            headers=headers
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_admin_disable_all_office_mfa_as_employee_forbidden(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        office_with_multiple_staffs
    ):
        """
        異常系: Employee は一括無効化できない (403 Forbidden)
        """
        # Arrange
        employee1 = office_with_multiple_staffs["employee1"]
        employee_token = create_access_token(subject=str(employee1.id))
        headers = {"Authorization": f"Bearer {employee_token}"}

        # Act
        response = await async_client.post(
            "/api/v1/auth/admin/office/mfa/disable-all",
            headers=headers
        )

        # Assert
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_admin_disable_all_office_mfa_unauthorized(
        self,
        async_client: AsyncClient
    ):
        """
        異常系: 未認証ユーザーは一括無効化できない (401 Unauthorized)
        """
        # Act
        response = await async_client.post(
            "/api/v1/auth/admin/office/mfa/disable-all"
        )

        # Assert
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_admin_enable_all_office_mfa_success(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        office_with_multiple_staffs
    ):
        """
        正常系: 管理者が事務所の全スタッフのMFAを一括有効化できることをテスト

        前提条件:
        - 管理者ユーザー（owner）が存在する
        - 事務所に複数のスタッフが所属している
        - 一部のスタッフのMFAが無効

        期待される結果:
        - ステータスコード: 200
        - 全スタッフのis_mfa_enabledがTrueになる
        - 各スタッフのQRコード、シークレットキー、リカバリーコードが返される
        """
        # Arrange
        owner = office_with_multiple_staffs["owner"]
        manager = office_with_multiple_staffs["manager"]
        employee1 = office_with_multiple_staffs["employee1"]
        employee2 = office_with_multiple_staffs["employee2"]

        # 全員のMFAを無効化
        await owner.disable_mfa(db_session)
        await manager.disable_mfa(db_session)
        await employee1.disable_mfa(db_session)
        # employee2は既にMFA無効なのでスキップ
        await db_session.commit()

        admin_token = create_access_token(subject=str(owner.id))
        headers = {"Authorization": f"Bearer {admin_token}"}

        # Act
        response = await async_client.post(
            "/api/v1/auth/admin/office/mfa/enable-all",
            headers=headers
        )

        # Assert: レスポンス検証
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "message" in data
        assert "enabled_count" in data
        assert "staff_mfa_data" in data
        assert data["enabled_count"] == 4  # 全員有効化

        # スタッフごとのMFA設定情報が含まれているか確認
        staff_mfa_data = data["staff_mfa_data"]
        assert len(staff_mfa_data) == 4

        for staff_data in staff_mfa_data:
            assert "staff_id" in staff_data
            assert "staff_name" in staff_data
            assert "qr_code_uri" in staff_data
            assert "secret_key" in staff_data
            assert "recovery_codes" in staff_data
            assert len(staff_data["recovery_codes"]) == 10

        # Assert: DB検証
        await db_session.refresh(owner)
        await db_session.refresh(manager)
        await db_session.refresh(employee1)
        await db_session.refresh(employee2)
        assert owner.is_mfa_enabled is True
        assert manager.is_mfa_enabled is True
        assert employee1.is_mfa_enabled is True
        assert employee2.is_mfa_enabled is True

    @pytest.mark.asyncio
    async def test_admin_enable_all_office_mfa_as_employee_forbidden(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        office_with_multiple_staffs
    ):
        """
        異常系: Employee は一括有効化できない (403 Forbidden)
        """
        # Arrange
        employee1 = office_with_multiple_staffs["employee1"]
        employee_token = create_access_token(subject=str(employee1.id))
        headers = {"Authorization": f"Bearer {employee_token}"}

        # Act
        response = await async_client.post(
            "/api/v1/auth/admin/office/mfa/enable-all",
            headers=headers
        )

        # Assert
        assert response.status_code == status.HTTP_403_FORBIDDEN
