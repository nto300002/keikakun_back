# tests/services/test_dashboard_service.py

import pytest
from unittest.mock import Mock, AsyncMock, patch
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, date, timedelta
import uuid

from app.services.dashboard_service import DashboardService
from app.models.staff import Staff
from app.models.office import Office
from app.models.welfare_recipient import WelfareRecipient
from app.models.support_plan_cycle import SupportPlanCycle, SupportPlanStatus
from app.models.enums import StaffRole, OfficeType, GenderType, SupportPlanStep, BillingStatus
from app.schemas.dashboard import DashboardData, DashboardRecipient
from app.core.exceptions import OfficeNotFoundError, DatabaseError

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


@pytest.fixture
def sample_staff():
    """サンプルスタッフデータ"""
    return Staff(
        id=uuid.uuid4(),
        name="テストスタッフ",
        email="test@example.com",
        role=StaffRole.owner,
        hashed_password="hashed_password",
        is_email_verified=True,
        is_mfa_enabled=False
    )


@pytest.fixture
def sample_office():
    """サンプル事業所データ"""
    return Office(
        id=uuid.uuid4(),
        name="テスト事業所",
        type=OfficeType.type_A_office,
        billing_status=BillingStatus.free,
        created_by=uuid.uuid4(),
        last_modified_by=uuid.uuid4()
    )


@pytest.fixture
def sample_recipients():
    """サンプル利用者データリスト"""
    recipients = []
    for i in range(3):
        recipient = WelfareRecipient(
            id=uuid.uuid4(),
            first_name=f"太郎{i+1}",
            last_name="田中",
            furigana=f"たなか たろう{i+1}",
            birth_day=date(1990, 1, 1),
            gender=GenderType.male
        )
        recipients.append(recipient)
    return recipients


class TestDashboardServiceCore:
    """DashboardServiceの中核機能テスト"""

    async def test_get_dashboard_data_success(self, dashboard_service, sample_staff, sample_office, sample_recipients):
        """正常系: ダッシュボードデータの取得が成功する"""
        # 各CRUDメソッドをAsyncMockで個別にパッチ
        with patch.object(dashboard_service.crud.dashboard, 'get_staff_office', new_callable=AsyncMock, return_value=(sample_staff, sample_office)) as mock_get_office, \
             patch.object(dashboard_service.crud.dashboard, 'get_office_recipients', new_callable=AsyncMock, return_value=sample_recipients) as mock_get_recipients, \
             patch.object(dashboard_service, '_create_recipient_summary', new_callable=AsyncMock) as mock_create_summary:

            # _create_recipient_summary の戻り値を設定
            mock_summaries = [
                DashboardRecipient(
                    id=str(r.id), full_name=f"{r.last_name} {r.first_name}", furigana=r.furigana, 
                    current_cycle_number=1, latest_step=SupportPlanStep.assessment, 
                    next_renewal_deadline=date.today(), monitoring_due_date=None
                ) for r in sample_recipients
            ]
            mock_create_summary.side_effect = mock_summaries

            # テスト実行
            result = await dashboard_service.get_dashboard_data(sample_staff.id)

            # 検証
            assert isinstance(result, DashboardData)
            assert result.staff_name == sample_staff.name
            assert result.office_name == sample_office.name
            assert result.current_user_count == 3
            mock_get_office.assert_awaited_once_with(db=dashboard_service.db, staff_id=sample_staff.id)
            mock_get_recipients.assert_awaited_once_with(db=dashboard_service.db, office_id=sample_office.id)
            assert mock_create_summary.call_count == 3

    async def test_get_dashboard_data_no_office(self, dashboard_service, sample_staff):
        """異常系: スタッフが事業所に所属していない場合"""
        with patch.object(dashboard_service.crud.dashboard, 'get_staff_office', new_callable=AsyncMock, return_value=None) as mock_get_office:
            result = await dashboard_service.get_dashboard_data(sample_staff.id)
            assert result is None
            mock_get_office.assert_awaited_once_with(db=dashboard_service.db, staff_id=sample_staff.id)

    async def test_get_dashboard_data_empty_recipients(self, dashboard_service, sample_staff, sample_office):
        """正常系: 利用者が0人の場合"""
        with patch.object(dashboard_service.crud.dashboard, 'get_staff_office', new_callable=AsyncMock, return_value=(sample_staff, sample_office)) as mock_get_office, \
             patch.object(dashboard_service.crud.dashboard, 'get_office_recipients', new_callable=AsyncMock, return_value=[]) as mock_get_recipients:
            
            result = await dashboard_service.get_dashboard_data(sample_staff.id)

            assert result.current_user_count == 0
            assert result.recipients == []
            mock_get_office.assert_awaited_once_with(db=dashboard_service.db, staff_id=sample_staff.id)
            mock_get_recipients.assert_awaited_once_with(db=dashboard_service.db, office_id=sample_office.id)


class TestDashboardServicePrivateMethods:
    """DashboardServiceのプライベートメソッドテスト"""

    async def test_create_recipient_summary_with_cycle(self, dashboard_service):
        """利用者サマリー作成テスト（サイクルあり）"""
        recipient = WelfareRecipient(id=uuid.uuid4(), last_name="田中", first_name="太郎", furigana="たなか たろう")
        cycle = SupportPlanCycle(id=1, statuses=[], next_renewal_deadline=date.today() + timedelta(days=150))
        
        # AsyncMockを使用して非同期メソッドをモック
        with patch.object(dashboard_service.crud.dashboard, 'get_latest_cycle', new_callable=AsyncMock, return_value=cycle) as mock_get_cycle, \
             patch.object(dashboard_service.crud.dashboard, 'get_cycle_count_for_recipient', new_callable=AsyncMock, return_value=2) as mock_get_count:

            result = await dashboard_service._create_recipient_summary(recipient)

            assert result.id == str(recipient.id)
            assert result.full_name == "田中 太郎"
            assert result.current_cycle_number == 2
            assert result.next_renewal_deadline == cycle.next_renewal_deadline
            mock_get_cycle.assert_awaited_once_with(db=dashboard_service.db, welfare_recipient_id=recipient.id)
            mock_get_count.assert_awaited_once_with(db=dashboard_service.db, welfare_recipient_id=recipient.id)

    async def test_create_recipient_summary_no_cycle(self, dashboard_service):
        """利用者サマリー作成テスト（サイクルなし）"""
        recipient = WelfareRecipient(id=uuid.uuid4(), last_name="山田", first_name="花子", furigana="やまだ はなこ")
        
        with patch.object(dashboard_service.crud.dashboard, 'get_latest_cycle', new_callable=AsyncMock) as mock_get_latest_cycle, \
             patch.object(dashboard_service.crud.dashboard, 'get_cycle_count_for_recipient', new_callable=AsyncMock) as mock_count_cycles:
            
            mock_get_latest_cycle.return_value = None
            mock_count_cycles.return_value = 0
            
            result = await dashboard_service._create_recipient_summary(recipient)

            assert result.full_name == "山田 花子"
            assert result.current_cycle_number == 0
            assert result.latest_step is None

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
        assert result == SupportPlanStep.assessment

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
        """モニタring期限日計算テスト（期限設定なし）"""
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
        """モニタring期限日計算テスト（前ステップ未完了）"""
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
