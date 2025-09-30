# tests/crud/test_crud_dashboard.py

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, date, timedelta
import uuid

from app.crud.crud_dashboard import crud_dashboard
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
            first_name_furigana=f"crud{i+1}",
            last_name_furigana="てすと",
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
    await db_session.flush()
    
    # Ensure module-level crud_dashboard has the test db_session available
    # so tests that call crud_dashboard.get_*(...) without passing db= can work.
    crud_dashboard.db = db_session

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
        result = await crud_dashboard.get_staff_office(db=db_session, staff_id=staff.id)
        assert result is not None
        staff_result, office_result = result
        assert office_result.id == office.id

    async def test_get_office_recipients_success(self, db_session: AsyncSession, crud_dashboard_fixtures):
        office = crud_dashboard_fixtures['office']
        expected_recipients = crud_dashboard_fixtures['recipients']
        result = await crud_dashboard.get_office_recipients(db=db_session, office_id=office.id)
        assert len(result) == 5
        assert {r.id for r in result} == {r.id for r in expected_recipients}

    async def test_count_office_recipients_success(self, db_session: AsyncSession, crud_dashboard_fixtures):
        office = crud_dashboard_fixtures['office']
        result = await crud_dashboard.count_office_recipients(db=db_session, office_id=office.id)
        assert result == 5




class TestCRUDDashboardEdgeCases:
    """CRUDDashboardのエッジケース（データが存在しない場合など）のテスト"""

    async def test_no_recipients_in_office(self, db_session: AsyncSession, office_factory, service_admin_user_factory):
        """利用者が一人もいない事業所のテスト"""
        staff = await service_admin_user_factory(email="edgecase@example.com")
        office = await office_factory(creator=staff, name="利用者ゼロ事業所")
        db_session.add(OfficeStaff(staff_id=staff.id, office_id=office.id, is_primary=True))
        await db_session.commit()

        # 利用者数カウントが0であること
        count = await crud_dashboard.count_office_recipients(db=db_session, office_id=office.id)
        assert count == 0

        # 利用者リストが空であること
        recipients = await crud_dashboard.get_office_recipients(db=db_session, office_id=office.id)
        assert recipients == []

        # サマリー取得で空の結果が返ること
        summaries = await crud_dashboard.get_filtered_summaries(
            db=db_session, office_ids=[office.id],
            sort_by="name_phonetic", sort_order="asc",
            filters={}, search_term=None, skip=0, limit=10
        )
        assert summaries == []

        # サマリーカウントがすべて0であること
        summary_counts = await crud_dashboard.get_summary_counts(db=db_session, office_ids=[office.id])
        assert summary_counts["total_recipients"] == 0
        assert summary_counts["overdue_count"] == 0
        assert summary_counts["upcoming_count"] == 0
        assert summary_counts["no_cycle_count"] == 0


class TestGetFilteredSummaries:
    """get_filtered_summaries の包括的なテスト"""

    async def test_get_filtered_summaries_success(self, db_session: AsyncSession, crud_dashboard_fixtures):
        """正常系: データが正しく取得できることを確認"""
        office = crud_dashboard_fixtures['office']
        
        results = await crud_dashboard.get_filtered_summaries(
            db=db_session,
            office_ids=[office.id],
            sort_by="name_phonetic",
            sort_order="asc",
            filters={},
            search_term=None,
            skip=0,
            limit=10
        )
        
        assert len(results) == 5
        
        # 結果を検証しやすいように辞書に変換
        result_map = {row[0].id: row for row in results} # row = (WelfareRecipient, cycle_count, SupportPlanCycle)
        
        # サイクルを持つ利用者 (recipients[0]) の検証
        recipient_with_cycle = crud_dashboard_fixtures['recipients'][0]
        res_with_cycle = result_map[recipient_with_cycle.id]
        
        assert res_with_cycle[0].id == recipient_with_cycle.id
        assert res_with_cycle[1] == 2  # cycle_count
        assert res_with_cycle[2] is not None # latest_cycle
        assert res_with_cycle[2].is_latest_cycle is True

        # サイクルを持たない利用者 (recipients[3]) の検証
        recipient_no_cycle = crud_dashboard_fixtures['recipients'][3]
        res_no_cycle = result_map[recipient_no_cycle.id]

        assert res_no_cycle[0].id == recipient_no_cycle.id
        assert res_no_cycle[1] == 0 # cycle_count
        assert res_no_cycle[2] is None # latest_cycle
