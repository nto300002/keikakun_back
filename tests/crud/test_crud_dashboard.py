# tests/crud/test_crud_dashboard.py

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, date, timedelta
import uuid

# 修正: dashboard_crudインスタンスを直接インポート
from app.crud.crud_dashboard import dashboard_crud
from app.models.staff import Staff
from app.models.office import Office, OfficeStaff
from app.models.welfare_recipient import WelfareRecipient, OfficeWelfareRecipient
from app.models.support_plan_cycle import SupportPlanCycle, SupportPlanStatus
from app.models.enums import StaffRole, OfficeType, GenderType, SupportPlanStep

# Pytestに非同期テストであることを認識させる
pytestmark = pytest.mark.asyncio


@pytest.fixture
async def crud_dashboard_fixtures(
    db_session: AsyncSession,
    service_admin_user_factory,
    office_factory
):
    """CRUDダッシュボードテスト用の基本フィクスチャ"""
    staff = await service_admin_user_factory(
        name="CRUD テスト管理者",
        email="crud-dashboard@example.com",
        role=StaffRole.manager
    )
    office = await office_factory(
        creator=staff,
        name="CRUD テスト事業所",
        type=OfficeType.type_B_office
    )
    office_staff = OfficeStaff(staff_id=staff.id, office_id=office.id, is_primary=True)
    db_session.add(office_staff)
    
    recipients = []
    for i in range(5):
        recipient = WelfareRecipient(
            first_name=f"CRUD{i+1}",
            last_name="テスト",
            furigana=f"てすと crud{i+1}",
            birth_day=date(1985 + i, 1, 1),
            gender=GenderType.male if i % 2 == 0 else GenderType.female
        )
        db_session.add(recipient)
        recipients.append(recipient)
    
    await db_session.flush()
    
    for recipient in recipients:
        office_recipient = OfficeWelfareRecipient(welfare_recipient_id=recipient.id, office_id=office.id)
        db_session.add(office_recipient)
    
    cycles = []
    for i, recipient in enumerate(recipients[:3]):
        old_cycle = SupportPlanCycle(welfare_recipient_id=recipient.id, plan_cycle_start_date=date.today() - timedelta(days=200), next_renewal_deadline=date.today() - timedelta(days=20), is_latest_cycle=False)
        db_session.add(old_cycle)
        await db_session.flush()

        latest_cycle = SupportPlanCycle(welfare_recipient_id=recipient.id, plan_cycle_start_date=date.today() - timedelta(days=30), next_renewal_deadline=date.today() + timedelta(days=150), is_latest_cycle=True)
        db_session.add(latest_cycle)
        await db_session.flush()
        cycles.append(latest_cycle)
    
    for i, cycle in enumerate(cycles):
        if i == 0:
            status = SupportPlanStatus(plan_cycle_id=cycle.id, step_type=SupportPlanStep.assessment, completed=True, completed_at=datetime.utcnow())
            db_session.add(status)
        elif i == 1:
            status = SupportPlanStatus(plan_cycle_id=cycle.id, step_type=SupportPlanStep.monitoring, completed=False, monitoring_deadline=7)
            db_session.add(status)
    
    await db_session.commit()
    
    # Ensure module-level dashboard_crud has the test db_session available
    # so tests that call dashboard_crud.get_*(...) without passing db= can work.
    dashboard_crud.db = db_session

    return {
        'staff': staff,
        'office': office,
        'recipients': recipients,
        'cycles': cycles
    }


class TestCRUDDashboardCore:
    """CRUDDashboardの中核機能テスト"""
    
    async def test_get_staff_office_success(self, db_session: AsyncSession, crud_dashboard_fixtures):
        staff = crud_dashboard_fixtures['staff']
        office = crud_dashboard_fixtures['office']
        result = await dashboard_crud.get_staff_office(db=db_session, staff_id=staff.id)
        assert result is not None
        staff_result, office_result = result
        assert office_result.id == office.id

    async def test_get_office_recipients_success(self, db_session: AsyncSession, crud_dashboard_fixtures):
        office = crud_dashboard_fixtures['office']
        expected_recipients = crud_dashboard_fixtures['recipients']
        result = await dashboard_crud.get_office_recipients(db=db_session, office_id=office.id)
        assert len(result) == 5
        assert {r.id for r in result} == {r.id for r in expected_recipients}

    async def test_get_latest_cycle_success(self, db_session: AsyncSession, crud_dashboard_fixtures):
        recipient = crud_dashboard_fixtures['recipients'][0]
        result = await dashboard_crud.get_latest_cycle(db=db_session, welfare_recipient_id=recipient.id)
        assert result is not None
        assert result.welfare_recipient_id == recipient.id
        assert result.is_latest_cycle is True

    async def test_get_latest_cycle_not_found(self, db_session: AsyncSession, crud_dashboard_fixtures):
        recipient = crud_dashboard_fixtures['recipients'][3]
        result = await dashboard_crud.get_latest_cycle(db=db_session, welfare_recipient_id=recipient.id)
        assert result is None

    async def test_count_office_recipients_success(self, db_session: AsyncSession, crud_dashboard_fixtures):
        office = crud_dashboard_fixtures['office']
        result = await dashboard_crud.count_office_recipients(db=db_session, office_id=office.id)
        assert result == 5

    async def test_get_cycle_count_for_recipient_success(self, db_session: AsyncSession, crud_dashboard_fixtures):
        recipient = crud_dashboard_fixtures['recipients'][0]
        result = await dashboard_crud.get_cycle_count_for_recipient(db=db_session, welfare_recipient_id=recipient.id)
        assert result == 2

class TestCRUDDashboardDataConsistency:
    """CRUDDashboardのデータ整合性テスト"""

    async def test_recipient_cycle_relationship_consistency(self, db_session: AsyncSession, crud_dashboard_fixtures):
        recipient = crud_dashboard_fixtures['recipients'][0]
        latest_cycle = await dashboard_crud.get_latest_cycle(db=db_session, welfare_recipient_id=recipient.id)
        assert latest_cycle is not None
        assert latest_cycle.welfare_recipient_id == recipient.id
        
        cycle_count = await dashboard_crud.get_cycle_count_for_recipient(db=db_session, welfare_recipient_id=recipient.id)
        assert cycle_count == 2
        
        query = select(func.count()).select_from(SupportPlanCycle).filter(
            SupportPlanCycle.welfare_recipient_id == recipient.id,
            SupportPlanCycle.is_latest_cycle == True
        )
        result = await db_session.execute(query)
        assert result.scalar() == 1
