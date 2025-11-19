# k_back/tests/api/v1/test_office.py

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid
from datetime import timedelta

from app.models.office import Office, OfficeStaff
from app.models.staff import Staff
from app.models.enums import StaffRole, OfficeType
from app import crud
from app.core.security import create_access_token

# Pytestに非同期テストであることを認識させる
pytestmark = pytest.mark.asyncio

# --- フィクスチャの準備 ---

@pytest_asyncio.fixture
async def owner_user_without_office(service_admin_user_factory):
    """事務所に所属していないownerユーザーを作成するフィクスチャ"""
    return await service_admin_user_factory(email=f"owner.no.office.{uuid.uuid4().hex[:6]}@example.com", name="Owner Without Office")

@pytest_asyncio.fixture
async def owner_user_with_office(db_session: AsyncSession, service_admin_user_factory, office_factory):
    """既に事務所に所属しているownerユーザーを作成するフィクスチャ"""
    user = await service_admin_user_factory(email=f"owner.with.office.{uuid.uuid4().hex[:6]}@example.com", name="Owner With Office")
    office = await office_factory(creator=user, name=f"Existing Office {uuid.uuid4().hex[:6]}")
    
    # ユーザーと事務所を紐付け
    association = OfficeStaff(staff_id=user.id, office_id=office.id, is_primary=True)
    db_session.add(association)
    await db_session.commit()
    await db_session.refresh(user, attribute_names=["office_associations"])
    return user

@pytest_asyncio.fixture
async def employee_user(service_admin_user_factory):
    """employeeロールのユーザーを作成するフィクスチャ"""
    return await service_admin_user_factory(
        email=f"employee.{uuid.uuid4().hex[:6]}@example.com",
        name="Normal Employee",
        role=StaffRole.employee
    )


# --- 事務所登録API (/offices/setup) のテスト ---

class TestSetupOffice:
    """
    POST /api/v1/offices/setup
    """

    @pytest.mark.parametrize("mock_current_user", ["owner_user_without_office"], indirect=True)
    async def test_setup_office_success(self, async_client: AsyncClient, db_session: AsyncSession, mock_current_user: Staff):
        """正常系: ownerが正常に事務所を登録できる"""
        # Arrange
        payload = {"name": "新しい訪問看護ステーション", "office_type": "type_A_office"}
        access_token = create_access_token(str(mock_current_user.id), timedelta(minutes=30))
        headers = {"Authorization": f"Bearer {access_token}"}

        # Act
        # この時点ではエンドポイントが存在しないため404が返るが、実装後は200になることを期待
        response = await async_client.post("/api/v1/offices/setup", json=payload, headers=headers)
        print("Status Code:", response.status_code)
        try:
            print("Response JSON:", response.json())
        except Exception as e:
            print("Response Text:", response.text)
            print("JSON Decode Error:", e)


        # Assert: レスポンスの検証
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == payload["name"]
        assert data["office_type"] == payload["office_type"]
        assert "id" in data
        print(f"Response data: {data}")

        # Assert: DBの状態の検証
        # 1. Officeが作成されたか
        office_in_db = await db_session.get(Office, uuid.UUID(data["id"]))
        assert office_in_db is not None
        assert office_in_db.name == payload["name"]
        assert office_in_db.created_by == mock_current_user.id

        # 2. ユーザーとOfficeが紐付いたか
        stmt = select(OfficeStaff).where(OfficeStaff.office_id == office_in_db.id)
        association_result = await db_session.execute(stmt)
        association = association_result.scalar_one_or_none()
        
        assert association is not None
        assert association.staff_id == mock_current_user.id
        assert association.is_primary is True

    @pytest.mark.parametrize("mock_current_user", ["employee_user"], indirect=True)
    async def test_setup_office_forbidden_for_employee(self, async_client: AsyncClient, mock_current_user: Staff):
        """異常系: employeeロールでは事務所登録ができない (403 Forbidden)"""
        # Arrange
        payload = {"name": "従業員が作ろうとする事務所", "office_type": "type_A_office"}
        access_token = create_access_token(str(mock_current_user.id), timedelta(minutes=30))
        headers = {"Authorization": f"Bearer {access_token}"}

        # Act
        response = await async_client.post("/api/v1/offices/setup", json=payload, headers=headers)

        # Assert
        assert response.status_code == 403
        assert "権限がありません" in response.json()["detail"]

    @pytest.mark.parametrize("mock_current_user", ["owner_user_with_office"], indirect=True)
    async def test_setup_office_fail_if_already_associated(self, async_client: AsyncClient, mock_current_user: Staff):
        """異常系: 既に事務所に所属しているownerは新しい事務所を登録できない (400 Bad Request)"""
        # Arrange
        payload = {"name": "二つ目の事務所", "office_type": "type_A_office"}
        access_token = create_access_token(str(mock_current_user.id), timedelta(minutes=30))
        headers = {"Authorization": f"Bearer {access_token}"}

        # Act
        response = await async_client.post("/api/v1/offices/setup", json=payload, headers=headers)

        # Assert
        assert response.status_code == 400
        assert "既に事業所に所属しています" in response.json()["detail"]

    @pytest.mark.parametrize("mock_current_user", ["owner_user_without_office"], indirect=True)
    async def test_setup_office_duplicate_name(self, async_client: AsyncClient, office_factory, owner_user_without_office: Staff, mock_current_user):
        """異常系: 既に存在する事務所名で登録しようとすると失敗する (409 Conflict)"""
        # Arrange
        existing_office_name = f"既存の事務所_{uuid.uuid4().hex[:6]}"
        await office_factory(creator=owner_user_without_office, name=existing_office_name)
        
        payload = {"name": existing_office_name, "office_type": "type_A_office"}
        access_token = create_access_token(str(mock_current_user.id), timedelta(minutes=30))
        headers = {"Authorization": f"Bearer {access_token}"}

        # Act
        response = await async_client.post("/api/v1/offices/setup", json=payload, headers=headers)

        # Assert
        assert response.status_code == 409
        assert "すでにその名前の事務所は登録されています" in response.json()["detail"]

    @pytest.mark.parametrize("mock_current_user", ["owner_user_without_office"], indirect=True)
    @pytest.mark.parametrize(
        "invalid_payload, expected_detail_part",
        [
            ({"name": "短"}, "String should have at least 5 characters"),
            ({"office_type": "invalid_type"}, "Input should be"),
            ({"name": "a" * 101}, "String should have at most 100 characters"),
            ({}, "Field required"),
        ]
    )
    async def test_setup_office_invalid_data(self, async_client: AsyncClient, mock_current_user: Staff, invalid_payload, expected_detail_part):
        """異常系: 不正なデータでの事務所登録が失敗する (422 Unprocessable Entity)"""
        # Arrange
        payload = {"name": "有効な事務所名", "office_type": "type_A_office"}
        
        temp_payload = payload.copy()
        temp_payload.update(invalid_payload)
        if not invalid_payload:
             del temp_payload["name"]

        access_token = create_access_token(str(mock_current_user.id), timedelta(minutes=30))
        headers = {"Authorization": f"Bearer {access_token}"}

        # Act
        response = await async_client.post("/api/v1/offices/setup", json=temp_payload, headers=headers)

        # Assert
        assert response.status_code == 422
        assert expected_detail_part in str(response.json()["detail"])

    async def test_setup_office_unauthorized(self, async_client: AsyncClient):
        """異常系: 認証なしで事務所登録ができない (401 Unauthorized)"""
        # Arrange
        payload = {"name": "認証なしの事務所", "office_type": "type_A_office"}

        # Act
        response = await async_client.post("/api/v1/offices/setup", json=payload)

        # Assert
        assert response.status_code == 401


# --- 事務所一覧取得API (/offices/) のテスト ---

class TestGetOffices:
    """
    GET /api/v1/offices/
    """

    @pytest.mark.parametrize("mock_current_user", ["employee_user"], indirect=True)
    async def test_get_all_offices_success(self, async_client: AsyncClient, db_session: AsyncSession, office_factory, owner_user_with_office, mock_current_user: Staff):
        """正常系: 認証済みユーザーが全ての事業所一覧を取得できる"""
        # Arrange
        # 事前に複数の事業所を作成
        await office_factory(name="事業所A", creator=owner_user_with_office, session=db_session)
        await office_factory(name="事業所B", creator=owner_user_with_office, session=db_session)
        await db_session.commit()  # 作成した事業所をコミットして他のセッションから見えるようにする

        access_token = create_access_token(str(mock_current_user.id), timedelta(minutes=30))
        headers = {"Authorization": f"Bearer {access_token}"}

        # Act
        response = await async_client.get("/api/v1/offices/", headers=headers)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 2
        office_names = [office["name"] for office in data]
        assert "事業所A" in office_names
        assert "事業所B" in office_names

    async def test_get_all_offices_unauthorized(self, async_client: AsyncClient):
        """異常系: 認証なしで事業所一覧を取得できない (401 Unauthorized)"""
        # Arrange
        # Act
        response = await async_client.get("/api/v1/offices/")

        # Assert
        assert response.status_code == 401


# --- 事務所スタッフ一覧取得API (/offices/me/staffs) のテスト ---

class TestGetOfficeStaffs:
    """
    GET /api/v1/offices/me/staffs
    管理者が所属事務所の全スタッフを取得する
    """

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

    async def test_get_office_staffs_as_owner_success(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        office_with_multiple_staffs
    ):
        """正常系: Owner が自事務所の全スタッフ一覧を取得できる"""
        # Arrange
        owner = office_with_multiple_staffs["owner"]
        access_token = create_access_token(str(owner.id), timedelta(minutes=30))
        headers = {"Authorization": f"Bearer {access_token}"}

        # Act
        response = await async_client.get("/api/v1/offices/me/staffs", headers=headers)

        # Assert
        assert response.status_code == 200
        data = response.json()

        # 4名のスタッフが返される（Owner, Manager, Employee1, Employee2）
        assert len(data) == 4

        # 各スタッフの必須フィールドが含まれる
        for staff in data:
            assert "id" in staff
            assert "full_name" in staff
            assert "email" in staff
            assert "role" in staff
            assert "is_mfa_enabled" in staff

        # スタッフ名が含まれる
        staff_names = [s["full_name"] for s in data]
        assert "テスト 事務所オーナー" in staff_names
        assert "テスト マネージャー" in staff_names
        assert "テスト 従業員1" in staff_names
        assert "テスト 従業員2" in staff_names

    async def test_get_office_staffs_as_manager_success(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        office_with_multiple_staffs
    ):
        """正常系: Manager が自事務所の全スタッフ一覧を取得できる"""
        # Arrange
        manager = office_with_multiple_staffs["manager"]
        access_token = create_access_token(str(manager.id), timedelta(minutes=30))
        headers = {"Authorization": f"Bearer {access_token}"}

        # Act
        response = await async_client.get("/api/v1/offices/me/staffs", headers=headers)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 4

    async def test_get_office_staffs_mfa_status_correct(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        office_with_multiple_staffs
    ):
        """正常系: MFA状態が正しく返される"""
        # Arrange
        owner = office_with_multiple_staffs["owner"]
        employee2 = office_with_multiple_staffs["employee2"]
        access_token = create_access_token(str(owner.id), timedelta(minutes=30))
        headers = {"Authorization": f"Bearer {access_token}"}

        # Act
        response = await async_client.get("/api/v1/offices/me/staffs", headers=headers)

        # Assert
        assert response.status_code == 200
        data = response.json()

        # 従業員2のMFAが無効であることを確認
        employee2_data = next((s for s in data if s["email"] == employee2.email), None)
        assert employee2_data is not None
        assert employee2_data["is_mfa_enabled"] is False

        # Ownerを含む他のスタッフのMFAが有効であることを確認
        owner_data = next((s for s in data if s["email"] == owner.email), None)
        assert owner_data is not None
        assert owner_data["is_mfa_enabled"] is True

    async def test_get_office_staffs_as_employee_forbidden(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        office_with_multiple_staffs
    ):
        """異常系: Employee は事務所スタッフ一覧を取得できない (403 Forbidden)"""
        # Arrange
        employee1 = office_with_multiple_staffs["employee1"]
        access_token = create_access_token(str(employee1.id), timedelta(minutes=30))
        headers = {"Authorization": f"Bearer {access_token}"}

        # Act
        response = await async_client.get("/api/v1/offices/me/staffs", headers=headers)

        # Assert
        assert response.status_code == 403
        detail = response.json()["detail"]
        assert "権限" in detail or "管理者" in detail

    async def test_get_office_staffs_unauthorized(self, async_client: AsyncClient):
        """異常系: 未認証ユーザーは事務所スタッフ一覧を取得できない (401 Unauthorized)"""
        # Arrange
        # Act
        response = await async_client.get("/api/v1/offices/me/staffs")

        # Assert
        assert response.status_code == 401

    async def test_get_office_staffs_no_office_association(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        service_admin_user_factory
    ):
        """異常系: 事務所未所属のユーザーは404 Not Found"""
        # Arrange
        # 事務所に所属していないOwnerを作成
        owner_no_office = await service_admin_user_factory(
            email=f"owner.no.office.{uuid.uuid4().hex[:6]}@example.com",
            name="事務所なしオーナー",
            role=StaffRole.owner
        )
        await db_session.commit()

        access_token = create_access_token(str(owner_no_office.id), timedelta(minutes=30))
        headers = {"Authorization": f"Bearer {access_token}"}

        # Act
        response = await async_client.get("/api/v1/offices/me/staffs", headers=headers)

        # Assert
        assert response.status_code == 404
        detail = response.json()["detail"]
        assert "事務所" in detail or "所属" in detail
