# tests/api/v1/test_welfare_recipients_employee_restriction.py

"""
WelfareRecipient API の Employee 制限機能のテスト

このテストは、Employee が WelfareRecipient の CREATE/UPDATE/DELETE を実行しようとした場合に、
EmployeeActionRequest が作成されることを確認します。

また、Manager/Owner は制限なく直接実行できることも確認します。
"""

import pytest
import uuid
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.staff import Staff
from app.models.office import OfficeStaff
from app.models.welfare_recipient import WelfareRecipient
from app.models.employee_action_request import EmployeeActionRequest
from app.models.enums import StaffRole, ResourceType, ActionType, RequestStatus
from app.main import app
from app.api.deps import get_current_user

pytestmark = pytest.mark.asyncio


# テストデータ用のヘルパー関数
def create_registration_data(first_name: str = "テスト", last_name: str = "利用者") -> dict:
    """WelfareRecipient 作成用のテストデータを生成"""
    return {
        "basic_info": {
            "firstName": first_name,
            "lastName": last_name,
            "firstNameFurigana": "てすと",
            "lastNameFurigana": "りようしゃ",
            "birthDay": "1990-01-01",
            "gender": "male"
        },
        "contact_address": {
            "address": "東京都テスト区1-2-3",
            "formOfResidence": "home_with_family",
            "meansOfTransportation": "public_transport",
            "tel": "0312345678"
        },
        "emergency_contacts": [],
        "disability_info": {
            "disabilityOrDiseaseName": "テスト障害",
            "livelihoodProtection": "not_receiving"
        },
        "disability_details": []
    }


async def setup_staff_with_office(
    db_session: AsyncSession,
    service_admin_user_factory,
    office_factory,
    role: StaffRole
) -> tuple[Staff, uuid.UUID]:
    """スタッフと事業所を作成し、関連付ける"""
    staff = await service_admin_user_factory(
        email=f"staff_{role.value}_{uuid.uuid4().hex[:8]}@example.com",
        role=role
    )
    office = await office_factory(creator=staff)

    # スタッフを事業所に関連付け
    association = OfficeStaff(
        staff_id=staff.id,
        office_id=office.id,
        is_primary=True
    )
    db_session.add(association)
    await db_session.flush()

    return staff, office.id


async def override_current_user(db_session: AsyncSession, staff: Staff):
    """get_current_user を上書きしてスタッフを返す"""
    async def _override():
        stmt = select(Staff).where(Staff.id == staff.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        ).execution_options(populate_existing=True)
        result = await db_session.execute(stmt)
        return result.scalars().first()

    app.dependency_overrides[get_current_user] = _override


# --- CREATE のテスト ---

async def test_employee_create_welfare_recipient_creates_request(
    async_client: AsyncClient,
    db_session: AsyncSession,
    service_admin_user_factory,
    office_factory
):
    """Employee が WelfareRecipient 作成を試みると、EmployeeActionRequest が作成される"""
    # Arrange
    employee, office_id = await setup_staff_with_office(
        db_session, service_admin_user_factory, office_factory, StaffRole.employee
    )
    await override_current_user(db_session, employee)

    registration_data = create_registration_data("従業員", "作成")

    # Act
    response = await async_client.post("/api/v1/welfare-recipients/", json=registration_data)

    # Assert
    assert response.status_code == 202  # Accepted
    response_data = response.json()
    assert "message" in response_data
    assert "Request created and pending approval" in response_data["message"]
    assert "request_id" in response_data

    # EmployeeActionRequest が作成されていることを確認
    request_id = uuid.UUID(response_data["request_id"])
    request = await db_session.get(EmployeeActionRequest, request_id)
    assert request is not None
    assert request.requester_staff_id == employee.id
    assert request.office_id == office_id
    assert request.resource_type == ResourceType.welfare_recipient
    assert request.action_type == ActionType.create
    assert request.status == RequestStatus.pending
    assert request.request_data is not None

    # WelfareRecipient は作成されていないことを確認（承認待ち）
    # 特定の名前で検索して、このテストで作成されたものが存在しないことを確認
    result = await db_session.execute(
        select(WelfareRecipient).where(
            WelfareRecipient.first_name == "作成",
            WelfareRecipient.last_name == "従業員"
        )
    )
    recipients = result.scalars().all()
    assert len(recipients) == 0


async def test_manager_create_welfare_recipient_direct(
    async_client: AsyncClient,
    db_session: AsyncSession,
    service_admin_user_factory,
    office_factory
):
    """Manager は WelfareRecipient を直接作成できる"""
    # Arrange
    manager, office_id = await setup_staff_with_office(
        db_session, service_admin_user_factory, office_factory, StaffRole.manager
    )
    await override_current_user(db_session, manager)

    registration_data = create_registration_data("マネージャー", "作成")

    # Act
    response = await async_client.post("/api/v1/welfare-recipients/", json=registration_data)

    # Assert
    assert response.status_code == 201  # Created
    response_data = response.json()
    assert response_data["success"] is True
    assert "recipient_id" in response_data

    # WelfareRecipient が作成されていることを確認
    recipient_id = uuid.UUID(response_data["recipient_id"])
    recipient = await db_session.get(WelfareRecipient, recipient_id)
    assert recipient is not None
    assert recipient.first_name == "マネージャー"
    assert recipient.last_name == "作成"


async def test_owner_create_welfare_recipient_direct(
    async_client: AsyncClient,
    db_session: AsyncSession,
    service_admin_user_factory,
    office_factory
):
    """Owner は WelfareRecipient を直接作成できる"""
    # Arrange
    owner, office_id = await setup_staff_with_office(
        db_session, service_admin_user_factory, office_factory, StaffRole.owner
    )
    await override_current_user(db_session, owner)

    registration_data = create_registration_data("オーナー", "作成")

    # Act
    response = await async_client.post("/api/v1/welfare-recipients/", json=registration_data)

    # Assert
    assert response.status_code == 201  # Created
    response_data = response.json()
    assert response_data["success"] is True
    assert "recipient_id" in response_data

    # WelfareRecipient が作成されていることを確認
    recipient_id = uuid.UUID(response_data["recipient_id"])
    recipient = await db_session.get(WelfareRecipient, recipient_id)
    assert recipient is not None
    assert recipient.first_name == "オーナー"
    assert recipient.last_name == "作成"


# --- UPDATE のテスト ---

async def test_employee_update_welfare_recipient_creates_request(
    async_client: AsyncClient,
    db_session: AsyncSession,
    service_admin_user_factory,
    office_factory
):
    """Employee が WelfareRecipient 更新を試みると、EmployeeActionRequest が作成される"""
    # Arrange
    # まず Manager で WelfareRecipient を作成
    manager, office_id = await setup_staff_with_office(
        db_session, service_admin_user_factory, office_factory, StaffRole.manager
    )
    await override_current_user(db_session, manager)

    registration_data = create_registration_data("更新前", "データ")
    response = await async_client.post("/api/v1/welfare-recipients/", json=registration_data)
    assert response.status_code == 201
    recipient_id = uuid.UUID(response.json()["recipient_id"])

    # Employee に切り替え
    employee = await service_admin_user_factory(
        email=f"employee_update_{uuid.uuid4().hex[:8]}@example.com",
        role=StaffRole.employee
    )
    association = OfficeStaff(staff_id=employee.id, office_id=office_id, is_primary=True)
    db_session.add(association)
    await db_session.flush()
    await override_current_user(db_session, employee)

    # 更新データ
    update_data = create_registration_data("更新後", "データ")

    # Act
    response = await async_client.put(f"/api/v1/welfare-recipients/{recipient_id}", json=update_data)

    # Assert
    assert response.status_code == 202  # Accepted
    response_data = response.json()
    assert "Request created and pending approval" in response_data["message"]
    assert "request_id" in response_data

    # EmployeeActionRequest が作成されていることを確認
    request_id = uuid.UUID(response_data["request_id"])
    request = await db_session.get(EmployeeActionRequest, request_id)
    assert request is not None
    assert request.resource_type == ResourceType.welfare_recipient
    assert request.action_type == ActionType.update
    assert request.resource_id == recipient_id
    assert request.status == RequestStatus.pending


async def test_manager_update_welfare_recipient_direct(
    async_client: AsyncClient,
    db_session: AsyncSession,
    service_admin_user_factory,
    office_factory
):
    """Manager は WelfareRecipient を直接更新できる"""
    # Arrange
    manager, office_id = await setup_staff_with_office(
        db_session, service_admin_user_factory, office_factory, StaffRole.manager
    )
    await override_current_user(db_session, manager)

    # WelfareRecipient を作成
    registration_data = create_registration_data("更新前", "マネージャー")
    response = await async_client.post("/api/v1/welfare-recipients/", json=registration_data)
    recipient_id = uuid.UUID(response.json()["recipient_id"])

    # 更新データ
    update_data = create_registration_data("更新後", "マネージャー")

    # Act
    response = await async_client.put(f"/api/v1/welfare-recipients/{recipient_id}", json=update_data)

    # Assert
    assert response.status_code == 200  # OK
    response_data = response.json()
    assert response_data["first_name"] == "更新後"


# --- DELETE のテスト ---

async def test_employee_delete_welfare_recipient_creates_request(
    async_client: AsyncClient,
    db_session: AsyncSession,
    service_admin_user_factory,
    office_factory
):
    """Employee が WelfareRecipient 削除を試みると、EmployeeActionRequest が作成される"""
    # Arrange
    # まず Manager で WelfareRecipient を作成
    manager, office_id = await setup_staff_with_office(
        db_session, service_admin_user_factory, office_factory, StaffRole.manager
    )
    await override_current_user(db_session, manager)

    registration_data = create_registration_data("削除対象", "データ")
    response = await async_client.post("/api/v1/welfare-recipients/", json=registration_data)
    recipient_id = uuid.UUID(response.json()["recipient_id"])

    # Employee に切り替え
    employee = await service_admin_user_factory(
        email=f"employee_delete_{uuid.uuid4().hex[:8]}@example.com",
        role=StaffRole.employee
    )
    association = OfficeStaff(staff_id=employee.id, office_id=office_id, is_primary=True)
    db_session.add(association)
    await db_session.flush()
    await override_current_user(db_session, employee)

    # Act
    response = await async_client.delete(f"/api/v1/welfare-recipients/{recipient_id}")

    # Assert
    assert response.status_code == 202  # Accepted
    response_data = response.json()
    assert "Request created and pending approval" in response_data["message"]

    # EmployeeActionRequest が作成されていることを確認
    request_id = uuid.UUID(response_data["request_id"])
    request = await db_session.get(EmployeeActionRequest, request_id)
    assert request is not None
    assert request.resource_type == ResourceType.welfare_recipient
    assert request.action_type == ActionType.delete
    assert request.resource_id == recipient_id

    # WelfareRecipient はまだ削除されていないことを確認
    recipient = await db_session.get(WelfareRecipient, recipient_id)
    assert recipient is not None


async def test_manager_delete_welfare_recipient_direct(
    async_client: AsyncClient,
    db_session: AsyncSession,
    service_admin_user_factory,
    office_factory
):
    """Manager は WelfareRecipient を直接削除できる"""
    # Arrange
    manager, office_id = await setup_staff_with_office(
        db_session, service_admin_user_factory, office_factory, StaffRole.manager
    )
    await override_current_user(db_session, manager)

    # WelfareRecipient を作成
    registration_data = create_registration_data("削除対象", "マネージャー")
    response = await async_client.post("/api/v1/welfare-recipients/", json=registration_data)
    recipient_id = uuid.UUID(response.json()["recipient_id"])

    # Act
    response = await async_client.delete(f"/api/v1/welfare-recipients/{recipient_id}")

    # Assert
    assert response.status_code == 200  # OK
    response_data = response.json()
    assert response_data["message"] == "Welfare recipient deleted successfully"

    # WelfareRecipient が削除されていることを確認
    recipient = await db_session.get(WelfareRecipient, recipient_id)
    assert recipient is None


# --- READ のテスト ---

async def test_employee_read_welfare_recipient_no_restriction(
    async_client: AsyncClient,
    db_session: AsyncSession,
    service_admin_user_factory,
    office_factory
):
    """Employee も WelfareRecipient を読み取れる（制限なし）"""
    # Arrange
    # Manager で WelfareRecipient を作成
    manager, office_id = await setup_staff_with_office(
        db_session, service_admin_user_factory, office_factory, StaffRole.manager
    )
    await override_current_user(db_session, manager)

    registration_data = create_registration_data("読取", "テスト")
    response = await async_client.post("/api/v1/welfare-recipients/", json=registration_data)
    recipient_id = uuid.UUID(response.json()["recipient_id"])

    # Employee に切り替え
    employee = await service_admin_user_factory(
        email=f"employee_read_{uuid.uuid4().hex[:8]}@example.com",
        role=StaffRole.employee
    )
    association = OfficeStaff(staff_id=employee.id, office_id=office_id, is_primary=True)
    db_session.add(association)
    await db_session.flush()
    await override_current_user(db_session, employee)

    # Act
    response = await async_client.get(f"/api/v1/welfare-recipients/{recipient_id}")

    # Assert
    assert response.status_code == 200  # OK
    response_data = response.json()
    assert response_data["first_name"] == "読取"
    assert response_data["last_name"] == "テスト"
