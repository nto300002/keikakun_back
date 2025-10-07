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
        """最新ステップ取得テスト - is_latest_statusがない場合はassessmentを返す"""
        statuses = [
            SupportPlanStatus(step_type=SupportPlanStep.assessment, completed=True, is_latest_status=False),
            SupportPlanStatus(step_type=SupportPlanStep.draft_plan, completed=True, is_latest_status=False),
        ]
        cycle = SupportPlanCycle(id=1, statuses=statuses)
        result = dashboard_service._get_latest_step(cycle)
        # is_latest_statusがない場合はフォールバックでassessmentを返す
        assert result == SupportPlanStep.assessment

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
        """モニタリング期限日計算テスト - is_latest_status=True かつ due_dateが設定されている場合"""
        expected_date = (datetime.utcnow() + timedelta(days=7)).date()
        final_plan_status = SupportPlanStatus(
            step_type=SupportPlanStep.final_plan_signed,
            completed=True,
            completed_at=datetime.utcnow(),
            is_latest_status=False
        )
        monitoring_status = SupportPlanStatus(
            step_type=SupportPlanStep.monitoring,
            completed=False,
            due_date=expected_date,
            is_latest_status=True
        )
        cycle = SupportPlanCycle(id=1, monitoring_deadline=7, statuses=[final_plan_status, monitoring_status])

        result = dashboard_service._calculate_monitoring_due_date(cycle)
        assert result == expected_date

    def test_calculate_monitoring_due_date_no_deadline(self, dashboard_service):
        """モニタリング期限日計算テスト（due_date未設定の場合はNoneを返す）"""
        final_plan_status = SupportPlanStatus(
            step_type=SupportPlanStep.final_plan_signed,
            completed=True,
            completed_at=datetime.utcnow(),
            is_latest_status=False
        )
        monitoring_status = SupportPlanStatus(
            step_type=SupportPlanStep.monitoring,
            completed=False,
            due_date=None,
            is_latest_status=True
        )
        cycle = SupportPlanCycle(id=1, monitoring_deadline=None, statuses=[final_plan_status, monitoring_status])

        result = dashboard_service._calculate_monitoring_due_date(cycle)
        # due_dateが設定されていない場合はNoneを返す
        assert result is None

    def test_calculate_monitoring_due_date_completed(self, dashboard_service):
        """モニタリング期限日計算テスト（完了済み）"""
        monitoring_status = SupportPlanStatus(
            step_type=SupportPlanStep.monitoring,
            completed=True,
            completed_at=datetime.utcnow()
        )
        cycle = SupportPlanCycle(id=1, monitoring_deadline=7, statuses=[monitoring_status])
        
        result = dashboard_service._calculate_monitoring_due_date(cycle)
        assert result is None

    def test_calculate_monitoring_due_date_no_previous_step(self, dashboard_service):
        """モニタリング期限日計算テスト（前ステップ未完了）"""
        monitoring_status = SupportPlanStatus(
            step_type=SupportPlanStep.monitoring,
            completed=False
        )
        cycle = SupportPlanCycle(id=1, monitoring_deadline=7, statuses=[monitoring_status])

        result = dashboard_service._calculate_monitoring_due_date(cycle)
        assert result is None

    def test_get_max_user_count(self, dashboard_service):
        """最大利用者数取得テスト"""
        assert dashboard_service._get_max_user_count(BillingStatus.free) == 5
        assert dashboard_service._get_max_user_count(BillingStatus.active) == 100
        assert dashboard_service._get_max_user_count(BillingStatus.canceled) == 0

    def test_get_latest_step_uses_is_latest_status_flag(self, dashboard_service):
        """is_latest_statusフラグを使って最新ステップを取得するテスト"""
        statuses = [
            SupportPlanStatus(step_type=SupportPlanStep.assessment, completed=True, is_latest_status=False),
            SupportPlanStatus(step_type=SupportPlanStep.draft_plan, completed=True, is_latest_status=False),
            SupportPlanStatus(step_type=SupportPlanStep.staff_meeting, completed=True, is_latest_status=False),
            SupportPlanStatus(step_type=SupportPlanStep.final_plan_signed, completed=True, is_latest_status=False),
            SupportPlanStatus(step_type=SupportPlanStep.monitoring, completed=False, is_latest_status=True),
        ]
        cycle = SupportPlanCycle(id=1, statuses=statuses)
        result = dashboard_service._get_latest_step(cycle)
        assert result == SupportPlanStep.monitoring

    def test_get_latest_step_defaults_to_assessment_when_no_completed(self, dashboard_service):
        """completedが何もない時はassessmentを返すテスト"""
        statuses = [
            SupportPlanStatus(step_type=SupportPlanStep.assessment, completed=False, is_latest_status=True),
            SupportPlanStatus(step_type=SupportPlanStep.draft_plan, completed=False, is_latest_status=False),
            SupportPlanStatus(step_type=SupportPlanStep.staff_meeting, completed=False, is_latest_status=False),
            SupportPlanStatus(step_type=SupportPlanStep.final_plan_signed, completed=False, is_latest_status=False),
        ]
        cycle = SupportPlanCycle(id=1, statuses=statuses)
        result = dashboard_service._get_latest_step(cycle)
        assert result == SupportPlanStep.assessment

    def test_get_latest_step_prioritizes_is_latest_status_over_completed(self, dashboard_service):
        """is_latest_statusがTrueのものを優先的に返すテスト"""
        statuses = [
            SupportPlanStatus(step_type=SupportPlanStep.assessment, completed=True, is_latest_status=False),
            SupportPlanStatus(step_type=SupportPlanStep.draft_plan, completed=False, is_latest_status=True),
            SupportPlanStatus(step_type=SupportPlanStep.staff_meeting, completed=False, is_latest_status=False),
        ]
        cycle = SupportPlanCycle(id=1, statuses=statuses)
        result = dashboard_service._get_latest_step(cycle)
        assert result == SupportPlanStep.draft_plan
