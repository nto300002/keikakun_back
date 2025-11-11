# tests/api/v1/test_support_plans_employee_restriction.py

"""
SupportPlans (PlanDeliverable) API の Employee 制限機能のテスト

このテストは、Employee が PlanDeliverable の CREATE/UPDATE/DELETE を実行しようとした場合に、
EmployeeActionRequest が作成されることを確認します。

また、Manager/Owner は制限なく直接実行できることも確認します。
"""

import pytest
import uuid
import io
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from datetime import date

from app.models.staff import Staff
from app.models.office import OfficeStaff
from app.models.welfare_recipient import WelfareRecipient, OfficeWelfareRecipient
from app.models.support_plan_cycle import SupportPlanCycle, PlanDeliverable, SupportPlanStatus
from app.models.employee_action_request import EmployeeActionRequest
from app.models.enums import StaffRole, ResourceType, ActionType, RequestStatus, GenderType, SupportPlanStep
from app.main import app
from app.api.deps import get_current_user

pytestmark = pytest.mark.asyncio


# テストデータ用のヘルパー関数

async def setup_staff_with_office(db_session, service_admin_user_factory, office_factory, role):
    """スタッフと事業所をセットアップ"""
    staff = await service_admin_user_factory(
        email=f"{role.value}_{uuid.uuid4().hex[:8]}@example.com",
        role=role
    )
    office = await office_factory(creator=staff)
    association = OfficeStaff(staff_id=staff.id, office_id=office.id, is_primary=True)
    db_session.add(association)
    await db_session.flush()
    return staff, office.id


async def create_welfare_recipient_with_cycle(db_session, office_id):
    """利用者とサイクルを作成"""
    recipient = WelfareRecipient(
        first_name="テスト",
        last_name="太郎",
        first_name_furigana="テスト",
        last_name_furigana="タロウ",
        birth_day=date(1990, 1, 1),
        gender=GenderType.male,
    )
    db_session.add(recipient)
    await db_session.flush()

    # Office と Recipient の関連
    office_assoc = OfficeWelfareRecipient(office_id=office_id, welfare_recipient_id=recipient.id)
    db_session.add(office_assoc)
    await db_session.flush()

    # Cycle を作成
    cycle = SupportPlanCycle(
        welfare_recipient_id=recipient.id,
        office_id=office_id,
        plan_cycle_start_date=date(2024, 1, 1),
        is_latest_cycle=True,
        cycle_number=1,
    )
    db_session.add(cycle)
    await db_session.flush()

    # 初期ステータス（assessment）を作成
    status = SupportPlanStatus(
        plan_cycle_id=cycle.id,
        welfare_recipient_id=recipient.id,
        office_id=office_id,
        step_type=SupportPlanStep.assessment,
        is_latest_status=True,
        completed=False
    )
    db_session.add(status)
    await db_session.flush()

    return recipient, cycle


async def override_current_user(db_session, staff):
    """get_current_user をオーバーライド"""
    async def override():
        stmt = (
            select(Staff)
            .where(Staff.id == staff.id)
            .options(
                selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
            )
            .execution_options(populate_existing=True)
        )
        result = await db_session.execute(stmt)
        return result.scalars().first()

    app.dependency_overrides[get_current_user] = override


def create_mock_pdf_file():
    """モックPDFファイルを作成"""
    # シンプルなPDFヘッダーのみ
    pdf_content = b"%PDF-1.4\n%Mock PDF content\n%%EOF"
    return io.BytesIO(pdf_content)


# ============================================================================
# POST /plan-deliverables (CREATE) のテスト
# ============================================================================

async def test_employee_upload_plan_deliverable_creates_request(
    async_client: AsyncClient,
    db_session: AsyncSession,
    service_admin_user_factory,
    office_factory
):
    """Employee が PlanDeliverable アップロードを試みると、EmployeeActionRequest が作成される"""
    # Arrange
    employee, office_id = await setup_staff_with_office(
        db_session, service_admin_user_factory, office_factory, StaffRole.employee
    )
    await override_current_user(db_session, employee)

    recipient, cycle = await create_welfare_recipient_with_cycle(db_session, office_id)
    await db_session.commit()

    # Act
    files = {"file": ("test.pdf", create_mock_pdf_file(), "application/pdf")}
    data = {
        "plan_cycle_id": cycle.id,
        "deliverable_type": "assessment_sheet"
    }
    response = await async_client.post("/api/v1/support-plans/plan-deliverables", files=files, data=data)

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
    assert request.resource_type == ResourceType.support_plan_cycle
    assert request.action_type == ActionType.create
    assert request.status == RequestStatus.pending

    # PlanDeliverable は作成されていないことを確認（承認待ち）
    result = await db_session.execute(
        select(PlanDeliverable).where(PlanDeliverable.plan_cycle_id == cycle.id)
    )
    deliverables = result.scalars().all()
    assert len(deliverables) == 0

    # Cleanup
    app.dependency_overrides.clear()


async def test_manager_upload_plan_deliverable_direct(
    async_client: AsyncClient,
    db_session: AsyncSession,
    service_admin_user_factory,
    office_factory,
    mocker
):
    """Manager は PlanDeliverable を直接アップロードできる"""
    # S3アップロードをモック
    mock_upload = mocker.patch("app.core.storage.upload_file")
    mock_upload.return_value = "s3://test-bucket/test-file.pdf"

    # Arrange
    manager, office_id = await setup_staff_with_office(
        db_session, service_admin_user_factory, office_factory, StaffRole.manager
    )
    await override_current_user(db_session, manager)

    recipient, cycle = await create_welfare_recipient_with_cycle(db_session, office_id)
    await db_session.commit()

    # Act
    files = {"file": ("test.pdf", create_mock_pdf_file(), "application/pdf")}
    data = {
        "plan_cycle_id": cycle.id,
        "deliverable_type": "assessment_sheet"
    }
    response = await async_client.post("/api/v1/support-plans/plan-deliverables", files=files, data=data)

    # Assert
    assert response.status_code == 201  # Created
    response_data = response.json()
    assert response_data["plan_cycle_id"] == cycle.id
    assert response_data["deliverable_type"] == "assessment_sheet"

    # PlanDeliverable が作成されていることを確認
    result = await db_session.execute(
        select(PlanDeliverable).where(PlanDeliverable.plan_cycle_id == cycle.id)
    )
    deliverables = result.scalars().all()
    assert len(deliverables) == 1

    # Cleanup
    app.dependency_overrides.clear()


async def test_owner_upload_plan_deliverable_direct(
    async_client: AsyncClient,
    db_session: AsyncSession,
    service_admin_user_factory,
    office_factory,
    mocker
):
    """Owner は PlanDeliverable を直接アップロードできる"""
    # S3アップロードをモック
    mock_upload = mocker.patch("app.core.storage.upload_file")
    mock_upload.return_value = "s3://test-bucket/test-file.pdf"

    # Arrange
    owner, office_id = await setup_staff_with_office(
        db_session, service_admin_user_factory, office_factory, StaffRole.owner
    )
    await override_current_user(db_session, owner)

    recipient, cycle = await create_welfare_recipient_with_cycle(db_session, office_id)
    await db_session.commit()

    # Act
    files = {"file": ("test.pdf", create_mock_pdf_file(), "application/pdf")}
    data = {
        "plan_cycle_id": cycle.id,
        "deliverable_type": "assessment_sheet"  # 初期ステータスに合わせて変更
    }
    response = await async_client.post("/api/v1/support-plans/plan-deliverables", files=files, data=data)

    # Assert
    assert response.status_code == 201  # Created

    # Cleanup
    app.dependency_overrides.clear()


# ============================================================================
# PUT /deliverables/{deliverable_id} (UPDATE) のテスト
# ============================================================================

async def test_employee_update_plan_deliverable_creates_request(
    async_client: AsyncClient,
    db_session: AsyncSession,
    service_admin_user_factory,
    office_factory,
    mocker
):
    """Employee が PlanDeliverable 更新を試みると、EmployeeActionRequest が作成される"""
    # S3アップロードをモック
    mock_upload = mocker.patch("app.core.storage.upload_file")
    mock_upload.return_value = "s3://test-bucket/test-file.pdf"

    # Arrange: まず Manager で Deliverable を作成
    manager, office_id = await setup_staff_with_office(
        db_session, service_admin_user_factory, office_factory, StaffRole.manager
    )
    await override_current_user(db_session, manager)

    recipient, cycle = await create_welfare_recipient_with_cycle(db_session, office_id)

    # Deliverable を作成
    files = {"file": ("original.pdf", create_mock_pdf_file(), "application/pdf")}
    data = {
        "plan_cycle_id": cycle.id,
        "deliverable_type": "assessment_sheet"
    }
    create_response = await async_client.post("/api/v1/support-plans/plan-deliverables", files=files, data=data)
    assert create_response.status_code == 201
    deliverable_id = create_response.json()["id"]

    # Employee に切り替え
    employee = await service_admin_user_factory(
        email=f"employee_update_{uuid.uuid4().hex[:8]}@example.com",
        role=StaffRole.employee
    )
    association = OfficeStaff(staff_id=employee.id, office_id=office_id, is_primary=True)
    db_session.add(association)
    await db_session.flush()
    await override_current_user(db_session, employee)

    # Act
    update_files = {"file": ("updated.pdf", create_mock_pdf_file(), "application/pdf")}
    response = await async_client.put(f"/api/v1/support-plans/deliverables/{deliverable_id}", files=update_files)

    # Assert
    assert response.status_code == 202  # Accepted
    response_data = response.json()
    assert "Request created and pending approval" in response_data["message"]
    assert "request_id" in response_data

    # EmployeeActionRequest が作成されていることを確認
    request_id = uuid.UUID(response_data["request_id"])
    request = await db_session.get(EmployeeActionRequest, request_id)
    assert request is not None
    assert request.resource_type == ResourceType.support_plan_cycle
    assert request.action_type == ActionType.update

    # Cleanup
    app.dependency_overrides.clear()


async def test_manager_update_plan_deliverable_direct(
    async_client: AsyncClient,
    db_session: AsyncSession,
    service_admin_user_factory,
    office_factory,
    mocker
):
    """Manager は PlanDeliverable を直接更新できる"""
    # S3アップロードをモック
    mock_upload = mocker.patch("app.core.storage.upload_file")
    mock_upload.return_value = "s3://test-bucket/updated-file.pdf"

    # Arrange
    manager, office_id = await setup_staff_with_office(
        db_session, service_admin_user_factory, office_factory, StaffRole.manager
    )
    await override_current_user(db_session, manager)

    recipient, cycle = await create_welfare_recipient_with_cycle(db_session, office_id)

    # Deliverable を作成
    files = {"file": ("original.pdf", create_mock_pdf_file(), "application/pdf")}
    data = {
        "plan_cycle_id": cycle.id,
        "deliverable_type": "assessment_sheet"
    }
    create_response = await async_client.post("/api/v1/support-plans/plan-deliverables", files=files, data=data)
    deliverable_id = create_response.json()["id"]

    # Act - 更新
    update_files = {"file": ("updated.pdf", create_mock_pdf_file(), "application/pdf")}
    response = await async_client.put(f"/api/v1/support-plans/deliverables/{deliverable_id}", files=update_files)

    # Assert
    assert response.status_code == 200  # OK

    # Cleanup
    app.dependency_overrides.clear()


# ============================================================================
# DELETE /deliverables/{deliverable_id} (DELETE) のテスト
# ============================================================================

async def test_employee_delete_plan_deliverable_creates_request(
    async_client: AsyncClient,
    db_session: AsyncSession,
    service_admin_user_factory,
    office_factory,
    mocker
):
    """Employee が PlanDeliverable 削除を試みると、EmployeeActionRequest が作成される"""
    # S3アップロードをモック
    mock_upload = mocker.patch("app.core.storage.upload_file")
    mock_upload.return_value = "s3://test-bucket/test-file.pdf"

    # Arrange: まず Manager で Deliverable を作成
    manager, office_id = await setup_staff_with_office(
        db_session, service_admin_user_factory, office_factory, StaffRole.manager
    )
    await override_current_user(db_session, manager)

    recipient, cycle = await create_welfare_recipient_with_cycle(db_session, office_id)

    # Deliverable を作成
    files = {"file": ("test.pdf", create_mock_pdf_file(), "application/pdf")}
    data = {
        "plan_cycle_id": cycle.id,
        "deliverable_type": "assessment_sheet"
    }
    create_response = await async_client.post("/api/v1/support-plans/plan-deliverables", files=files, data=data)
    deliverable_id = create_response.json()["id"]

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
    response = await async_client.delete(f"/api/v1/support-plans/deliverables/{deliverable_id}")

    # Assert
    assert response.status_code == 202  # Accepted
    response_data = response.json()
    assert "Request created and pending approval" in response_data["message"]

    # EmployeeActionRequest が作成されていることを確認
    request_id = uuid.UUID(response_data["request_id"])
    request = await db_session.get(EmployeeActionRequest, request_id)
    assert request is not None
    assert request.action_type == ActionType.delete

    # Deliverable は削除されていないことを確認（承認待ち）
    deliverable = await db_session.get(PlanDeliverable, deliverable_id)
    assert deliverable is not None

    # Cleanup
    app.dependency_overrides.clear()


async def test_manager_delete_plan_deliverable_direct(
    async_client: AsyncClient,
    db_session: AsyncSession,
    service_admin_user_factory,
    office_factory,
    mocker
):
    """Manager は PlanDeliverable を直接削除できる"""
    # S3アップロードをモック
    mock_upload = mocker.patch("app.core.storage.upload_file")
    mock_upload.return_value = "s3://test-bucket/test-file.pdf"

    # Arrange
    manager, office_id = await setup_staff_with_office(
        db_session, service_admin_user_factory, office_factory, StaffRole.manager
    )
    await override_current_user(db_session, manager)

    recipient, cycle = await create_welfare_recipient_with_cycle(db_session, office_id)

    # Deliverable を作成
    files = {"file": ("test.pdf", create_mock_pdf_file(), "application/pdf")}
    data = {
        "plan_cycle_id": cycle.id,
        "deliverable_type": "assessment_sheet"
    }
    create_response = await async_client.post("/api/v1/support-plans/plan-deliverables", files=files, data=data)
    deliverable_id = create_response.json()["id"]

    # Act - 削除
    response = await async_client.delete(f"/api/v1/support-plans/deliverables/{deliverable_id}")

    # Assert
    assert response.status_code == 204  # No Content

    # Deliverable が削除されていることを確認
    deliverable = await db_session.get(PlanDeliverable, deliverable_id)
    assert deliverable is None

    # Cleanup
    app.dependency_overrides.clear()
