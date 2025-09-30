# tests/services/test_dashboard_service.py

import pytest
from unittest.mock import Mock
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, date, timedelta

from app.services.dashboard_service import DashboardService
from app.models.support_plan_cycle import SupportPlanCycle, SupportPlanStatus
from app.models.enums import SupportPlanStep, BillingStatus

# Pytestに非同期テストであることを認識させる
pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_db_session():
    """モックDBセッション"""
    return Mock(spec=AsyncSession)


@pytest.fixture
def dashboard_service(mock_db_session):
    """DashboardServiceインスタンス"""
    return DashboardService(mock_db_session)


class TestDashboardServiceHelpers:
    """DashboardServiceのヘルパーメソッドテスト"""

    def test_get_latest_step_from_statuses(self, dashboard_service):
        """最新ステップ取得テスト"""
        statuses = [
            SupportPlanStatus(step_type=SupportPlanStep.assessment, completed=True),
            SupportPlanStatus(step_type=SupportPlanStep.draft_plan, completed=True),
        ]
        cycle = SupportPlanCycle(id=1, statuses=statuses)
        result = dashboard_service._get_latest_step(cycle)
        assert result == SupportPlanStep.staff_meeting

    def test_get_latest_step_no_statuses(self, dashboard_service):
        """最新ステップ取得テスト（ステータスなし）"""
        cycle = SupportPlanCycle(id=1, statuses=[])
        result = dashboard_service._get_latest_step(cycle)
        assert result is None # サイクルはあるがステータスがない場合

    def test_get_latest_step_no_cycle(self, dashboard_service):
        """最新ステップ取得テスト（サイクル自体がない）"""
        result = dashboard_service._get_latest_step(None)
        assert result is None

    def test_calculate_monitoring_due_date(self, dashboard_service):
        """モニタリング期限日計算テスト"""
        final_plan_status = SupportPlanStatus(
            step_type=SupportPlanStep.final_plan_signed,
            completed=True,
            completed_at=datetime.utcnow()
        )
        monitoring_status = SupportPlanStatus(
            step_type=SupportPlanStep.monitoring,
            completed=False,
            monitoring_deadline=7
        )
        cycle = SupportPlanCycle(id=1, statuses=[final_plan_status, monitoring_status])

        result = dashboard_service._calculate_monitoring_due_date(cycle)
        expected_date = (final_plan_status.completed_at + timedelta(days=7)).date()
        assert result == expected_date

    def test_calculate_monitoring_due_date_no_deadline(self, dashboard_service):
        """モニタリング期限日計算テスト（期限設定なし）"""
        final_plan_status = SupportPlanStatus(
            step_type=SupportPlanStep.final_plan_signed,
            completed=True,
            completed_at=datetime.utcnow()
        )
        monitoring_status = SupportPlanStatus(
            step_type=SupportPlanStep.monitoring,
            completed=False,
            monitoring_deadline=None
        )
        cycle = SupportPlanCycle(id=1, statuses=[final_plan_status, monitoring_status])

        result = dashboard_service._calculate_monitoring_due_date(cycle)
        expected_date = (final_plan_status.completed_at + timedelta(days=7)).date()
        assert result == expected_date

    def test_calculate_monitoring_due_date_completed(self, dashboard_service):
        """モニタリング期限日計算テスト（完了済み）"""
        monitoring_status = SupportPlanStatus(
            step_type=SupportPlanStep.monitoring,
            completed=True,
            completed_at=datetime.utcnow(),
            monitoring_deadline=7
        )
        cycle = SupportPlanCycle(id=1, statuses=[monitoring_status])
        
        result = dashboard_service._calculate_monitoring_due_date(cycle)
        assert result is None

    def test_calculate_monitoring_due_date_no_previous_step(self, dashboard_service):
        """モニタリング期限日計算テスト（前ステップ未完了）"""
        monitoring_status = SupportPlanStatus(
            step_type=SupportPlanStep.monitoring,
            completed=False,
            monitoring_deadline=7
        )
        cycle = SupportPlanCycle(id=1, statuses=[monitoring_status])

        result = dashboard_service._calculate_monitoring_due_date(cycle)
        assert result is None

    def test_get_max_user_count(self, dashboard_service):
        """最大利用者数取得テスト"""
        assert dashboard_service._get_max_user_count(BillingStatus.free) == 5
        assert dashboard_service._get_max_user_count(BillingStatus.active) == 100
        assert dashboard_service._get_max_user_count(BillingStatus.canceled) == 0
