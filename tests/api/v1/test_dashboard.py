# tests/api/v1/test_dashboard.py

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date, timedelta

# 修正: 依存性オーバーライドのためにappとget_current_userをインポート
from app.main import app
from app.api.deps import get_current_user

from app.models.staff import Staff
from app.models.office import Office, OfficeStaff
from app.models.welfare_recipient import WelfareRecipient, OfficeWelfareRecipient
from app.models.support_plan_cycle import SupportPlanCycle, SupportPlanStatus
from app.models.enums import StaffRole, OfficeType, GenderType, SupportPlanStep, BillingStatus

# Pytestに非同期テストであることを認識させる
pytestmark = pytest.mark.asyncio


@pytest.fixture
async def dashboard_fixtures(db_session: AsyncSession, service_admin_user_factory, office_factory):
    """ダッシュボードテスト用の基本フィクスチャ"""
    staff = await service_admin_user_factory(name="ダッシュボードテスト管理者", email="dashboard@example.com", role=StaffRole.owner)
    office = await office_factory(creator=staff, name="テストダッシュボード事業所", type=OfficeType.type_A_office)
    office_staff = OfficeStaff(staff_id=staff.id, office_id=office.id, is_primary=True)
    db_session.add(office_staff)
    
    recipients = []
    for i in range(3):
        recipient = WelfareRecipient(
            first_name=f"太郎{i+1}", 
            last_name="田中", 
            first_name_furigana=f"たろう{i+1}",
            last_name_furigana="たなか",
            birth_day=date(1990, 1, 1), 
            gender=GenderType.male
        )
        db_session.add(recipient)
        await db_session.flush()
        office_recipient = OfficeWelfareRecipient(welfare_recipient_id=recipient.id, office_id=office.id)
        db_session.add(office_recipient)
        recipients.append(recipient)
    
    for i, recipient in enumerate(recipients):
        cycle = SupportPlanCycle(welfare_recipient_id=recipient.id, plan_cycle_start_date=date.today() - timedelta(days=30), next_renewal_deadline=date.today() + timedelta(days=150), is_latest_cycle=True)
        db_session.add(cycle)
        await db_session.flush()
        if i == 0:
            status1 = SupportPlanStatus(plan_cycle_id=cycle.id, step_type=SupportPlanStep.assessment, completed=True)
            status2 = SupportPlanStatus(plan_cycle_id=cycle.id, step_type=SupportPlanStep.draft_plan, completed=False)
            db_session.add_all([status1, status2])
        elif i == 1:
            cycle.monitoring_deadline = 7
            status = SupportPlanStatus(plan_cycle_id=cycle.id, step_type=SupportPlanStep.monitoring, completed=False)
            db_session.add(status)
    
    await db_session.commit()
    return {'staff': staff, 'office': office, 'recipients': recipients}


class TestDashboardAPI:
    """ダッシュボードAPIのテストクラス"""
    
    async def test_get_dashboard_success(self, async_client: AsyncClient, dashboard_fixtures):
        staff = dashboard_fixtures['staff']
        app.dependency_overrides[get_current_user] = lambda: staff

        response = await async_client.get("/api/v1/dashboard/")

        del app.dependency_overrides[get_current_user]

        assert response.status_code == 200
        data = response.json()
        assert data["staff_name"] == staff.name
        assert data["office_name"] == dashboard_fixtures['office'].name
        assert data["current_user_count"] == 3
        assert len(data["recipients"]) == 3

        # monitoring_deadline が設定されている利用者を確認
        recipient_with_monitoring = next(
            (r for r in data["recipients"] if r.get("monitoring_deadline") is not None),
            None
        )
        assert recipient_with_monitoring is not None
        assert recipient_with_monitoring["monitoring_deadline"] == 7

    async def test_get_dashboard_empty_recipients(self, async_client: AsyncClient, db_session: AsyncSession, service_admin_user_factory, office_factory):
        staff = await service_admin_user_factory(name="空の事業所管理者", email="empty@example.com")
        office = await office_factory(creator=staff, name="空のテスト事業所")
        office_staff = OfficeStaff(staff_id=staff.id, office_id=office.id, is_primary=True)
        db_session.add(office_staff)
        await db_session.commit()
        
        app.dependency_overrides[get_current_user] = lambda: staff
        response = await async_client.get("/api/v1/dashboard/")
        del app.dependency_overrides[get_current_user]
        
        assert response.status_code == 200
        data = response.json()
        assert data["current_user_count"] == 0
        assert data["recipients"] == []

    async def test_get_dashboard_unauthorized(self, async_client: AsyncClient):
        # 認証オーバーライドなしでアクセス
        response = await async_client.get("/api/v1/dashboard/")
        assert response.status_code == 401

    async def test_get_dashboard_no_office_association(self, async_client: AsyncClient, db_session: AsyncSession, service_admin_user_factory):
        staff = await service_admin_user_factory(name="無所属スタッフ", email="nooffice@example.com")
        await db_session.commit()
        
        app.dependency_overrides[get_current_user] = lambda: staff
        response = await async_client.get("/api/v1/dashboard/")
        del app.dependency_overrides[get_current_user]
        
        assert response.status_code == 404
        assert "事業所情報が見つかりません" in response.json()["detail"]
