# tests/api/v1/test_support_plan_statuses_employee_restriction.py

"""
SupportPlanStatuses API の Employee 制限機能のテスト

このテストは、Employee が SupportPlanStatus の UPDATE (モニタリング期限更新) を実行しようとした場合に、
EmployeeActionRequest が作成されることを確認します。

また、Manager/Owner は制限なく直接実行できることも確認します。
"""

import pytest
import uuid
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from datetime import date, timedelta, datetime

from app.models.staff import Staff
from app.models.office import OfficeStaff
from app.models.welfare_recipient import WelfareRecipient, OfficeWelfareRecipient
from app.models.support_plan_cycle import SupportPlanCycle, SupportPlanStatus
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


async def create_monitoring_status(db_session, office_id):
    """モニタリングステータスを持つサイクルを作成"""
    # 利用者を作成
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

    # 完了済みのサイクル（cycle 1）を作成
    final_plan_completed_at = date.today() - timedelta(days=10)
    completed_cycle = SupportPlanCycle(
        welfare_recipient_id=recipient.id,
        office_id=office_id,
        plan_cycle_start_date=date.today() - timedelta(days=200),
        is_latest_cycle=False,
        cycle_number=1
    )
    db_session.add(completed_cycle)
    await db_session.flush()

    # 前のサイクルのfinal_plan_signedステータスを作成
    final_plan_status = SupportPlanStatus(
        plan_cycle_id=completed_cycle.id,
        welfare_recipient_id=recipient.id,
        office_id=office_id,
        step_type=SupportPlanStep.final_plan_signed,
        is_latest_status=False,
        completed=True,
        completed_at=datetime.combine(final_plan_completed_at, datetime.min.time())
    )
    db_session.add(final_plan_status)
    await db_session.flush()

    # 新しいサイクル（cycle 2 - モニタリングから開始）を作成
    new_cycle = SupportPlanCycle(
        welfare_recipient_id=recipient.id,
        office_id=office_id,
        is_latest_cycle=True,
        cycle_number=2
    )
    db_session.add(new_cycle)
    await db_session.flush()

    # モニタリングステータスを作成
    monitoring_status = SupportPlanStatus(
        plan_cycle_id=new_cycle.id,
        welfare_recipient_id=recipient.id,
        office_id=office_id,
        step_type=SupportPlanStep.monitoring,
        is_latest_status=True,
        due_date=final_plan_completed_at + timedelta(days=7)  # 初期期限
    )
    db_session.add(monitoring_status)
    await db_session.flush()

    return monitoring_status.id


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


# ============================================================================
# PATCH /{status_id} (UPDATE - モニタリング期限更新) のテスト
# ============================================================================

async def test_employee_update_monitoring_deadline_creates_request(
    async_client: AsyncClient,
    db_session: AsyncSession,
    service_admin_user_factory,
    office_factory
):
    """Employee がモニタリング期限更新を試みると、EmployeeActionRequest が作成される"""
    # Arrange
    employee, office_id = await setup_staff_with_office(
        db_session, service_admin_user_factory, office_factory, StaffRole.employee
    )
    await override_current_user(db_session, employee)

    status_id = await create_monitoring_status(db_session, office_id)
    await db_session.commit()

    # Act
    update_data = {"monitoring_deadline": 14}
    response = await async_client.patch(
        f"/api/v1/support-plan-statuses/{status_id}",
        json=update_data
    )

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
    assert request.resource_type == ResourceType.support_plan_status
    assert request.action_type == ActionType.update
    assert request.status == RequestStatus.pending
    assert request.request_data["monitoring_deadline"] == 14

    # モニタリング期限は更新されていないことを確認（承認待ち）
    status = await db_session.get(SupportPlanStatus, status_id)
    await db_session.refresh(status, ["plan_cycle"])
    # 初期値のまま（Noneまたは設定されていない）
    assert status.plan_cycle.monitoring_deadline is None or status.plan_cycle.monitoring_deadline != 14

    # Cleanup
    app.dependency_overrides.clear()


async def test_manager_update_monitoring_deadline_direct(
    async_client: AsyncClient,
    db_session: AsyncSession,
    service_admin_user_factory,
    office_factory
):
    """Manager はモニタリング期限を直接更新できる"""
    # Arrange
    manager, office_id = await setup_staff_with_office(
        db_session, service_admin_user_factory, office_factory, StaffRole.manager
    )
    await override_current_user(db_session, manager)

    status_id = await create_monitoring_status(db_session, office_id)
    await db_session.commit()

    # Act
    update_data = {"monitoring_deadline": 21}
    response = await async_client.patch(
        f"/api/v1/support-plan-statuses/{status_id}",
        json=update_data
    )

    # Assert
    assert response.status_code == 200  # OK
    response_data = response.json()
    assert response_data["monitoring_deadline"] == 21

    # due_date が再計算されていることを確認
    expected_due_date = (date.today() - timedelta(days=10) + timedelta(days=21)).strftime("%Y-%m-%d")
    assert response_data["due_date"] == expected_due_date

    # Cleanup
    app.dependency_overrides.clear()


async def test_owner_update_monitoring_deadline_direct(
    async_client: AsyncClient,
    db_session: AsyncSession,
    service_admin_user_factory,
    office_factory
):
    """Owner はモニタリング期限を直接更新できる"""
    # Arrange
    owner, office_id = await setup_staff_with_office(
        db_session, service_admin_user_factory, office_factory, StaffRole.owner
    )
    await override_current_user(db_session, owner)

    status_id = await create_monitoring_status(db_session, office_id)
    await db_session.commit()

    # Act
    update_data = {"monitoring_deadline": 28}
    response = await async_client.patch(
        f"/api/v1/support-plan-statuses/{status_id}",
        json=update_data
    )

    # Assert
    assert response.status_code == 200  # OK
    response_data = response.json()
    assert response_data["monitoring_deadline"] == 28

    # Cleanup
    app.dependency_overrides.clear()
