# k_back/tests/crud/test_crud_dashboard_summary.py

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date, timedelta, datetime, timezone
import uuid

from app.crud.crud_dashboard import CRUDDashboard
from app.models import (
    Staff, Office, OfficeStaff, WelfareRecipient, OfficeWelfareRecipient,
    SupportPlanCycle, SupportPlanStatus
)
from app.models.enums import (
    StaffRole, OfficeType, GenderType, SupportPlanStep
)

# Pytestに非同期テストであることを認識させる
pytestmark = pytest.mark.asyncio

# テスト対象のCRUDインスタンス
crud_dashboard = CRUDDashboard(WelfareRecipient)

@pytest.fixture(scope="function")
async def search_sort_filter_fixtures(db_session: AsyncSession, service_admin_user_factory, office_factory):
    """検索・ソート・フィルター機能のテスト用フィクスチャ"""
    # 1. スタッフと事業所の作成
    staff = await service_admin_user_factory(email="summary_test@example.com")
    office = await office_factory(creator=staff, name="サマリーテスト事業所")
    db_session.add(OfficeStaff(staff_id=staff.id, office_id=office.id, is_primary=True))

    # 2. 利用者データの定義
    recipients_data = [
        {"last_name": "佐藤", "first_name": "愛", "last_name_furigana": "さとう", "first_name_furigana": "あい", "created_at_delta": 30},
        {"last_name": "鈴木", "first_name": "次郎", "last_name_furigana": "すずき", "first_name_furigana": "じろう", "created_at_delta": 20},
        {"last_name": "高橋", "first_name": "学", "last_name_furigana": "たかはし", "first_name_furigana": "まなぶ", "created_at_delta": 5},
        {"last_name": "田中", "first_name": "太郎", "last_name_furigana": "たなか", "first_name_furigana": "たろう", "created_at_delta": 10},
        {"last_name": "伊藤", "first_name": "健太", "last_name_furigana": "いとう", "first_name_furigana": "けんた", "created_at_delta": 1},
    ]
    
    recipients = []
    for i, data in enumerate(recipients_data):
        recipient = WelfareRecipient(
            last_name=data["last_name"], first_name=data["first_name"],
            last_name_furigana=data["last_name_furigana"], first_name_furigana=data["first_name_furigana"],
            birth_day=date(1990, 1, 1), gender=GenderType.male,
            created_at=datetime.now(timezone.utc) - timedelta(days=data["created_at_delta"])
        )
        db_session.add(recipient)

        try:
            await db_session.flush()
        except Exception as e:
            raise

        db_session.add(OfficeWelfareRecipient(welfare_recipient_id=recipient.id, office_id=office.id))
        recipients.append(recipient)

    sato, suzuki, takahashi, tanaka, ito = recipients

    # 3. 支援計画サイクルとステータスの作成
    # 佐藤 愛 (期限切れ)
    cycle_sato = SupportPlanCycle(welfare_recipient_id=sato.id, plan_cycle_start_date=date.today() - timedelta(days=375), cycle_number=1, is_latest_cycle=True, next_renewal_deadline=date.today() - timedelta(days=10))
    db_session.add(cycle_sato)
    await db_session.flush()
    db_session.add(SupportPlanStatus(plan_cycle_id=cycle_sato.id, step_type=SupportPlanStep.assessment, completed=False))

    # 鈴木 次郎 (更新間近)
    cycle_suzuki = SupportPlanCycle(welfare_recipient_id=suzuki.id, plan_cycle_start_date=date.today() - timedelta(days=350), cycle_number=1, is_latest_cycle=True, next_renewal_deadline=date.today() + timedelta(days=15))
    db_session.add(cycle_suzuki)
    await db_session.flush()
    db_session.add(SupportPlanStatus(plan_cycle_id=cycle_suzuki.id, step_type=SupportPlanStep.monitoring, completed=False))

    # 高橋 学 (通常)
    cycle_takahashi = SupportPlanCycle(welfare_recipient_id=takahashi.id, plan_cycle_start_date=date.today() - timedelta(days=275), cycle_number=1, is_latest_cycle=True, next_renewal_deadline=date.today() + timedelta(days=90))
    db_session.add(cycle_takahashi)
    await db_session.flush()
    db_session.add(SupportPlanStatus(plan_cycle_id=cycle_takahashi.id, step_type=SupportPlanStep.monitoring, completed=False))

    # 田中 太郎 (通常)
    new_plan_start_date = date.today() - timedelta(days=305)
    cycle_tanaka_old = SupportPlanCycle(welfare_recipient_id=tanaka.id, plan_cycle_start_date=new_plan_start_date - timedelta(days=365), cycle_number=1, is_latest_cycle=False)
    cycle_tanaka_new = SupportPlanCycle(welfare_recipient_id=tanaka.id, plan_cycle_start_date=new_plan_start_date, cycle_number=2, is_latest_cycle=True, next_renewal_deadline=date.today() + timedelta(days=60))
    db_session.add_all([cycle_tanaka_old, cycle_tanaka_new])
    await db_session.flush()
    db_session.add(SupportPlanStatus(plan_cycle_id=cycle_tanaka_new.id, step_type=SupportPlanStep.draft_plan, completed=False))

    # 伊藤 健太 (サイクルなし)

    await db_session.commit()
    
    return {"office_id": office.id, "recipients": {r.last_name: r for r in recipients}}


class TestCRUDDashboardGetFilteredSummaries:
    """crud.dashboard.get_filtered_summaries のテスト"""

    async def test_no_filters_or_search(self, db_session: AsyncSession, search_sort_filter_fixtures):
        """検索・フィルターなし: 全件がデフォルトソート順で返される"""
        office_id = search_sort_filter_fixtures["office_id"]
        
        results = await crud_dashboard.get_filtered_summaries(
            db=db_session, office_ids=[office_id],
            sort_by="name_phonetic", sort_order="asc",
            filters={}, search_term=None, skip=0, limit=10
        )
        
        assert len(results) == 5
        # デフォルトはフリガナ昇順
        assert [r.last_name for r in results] == ["伊藤", "佐藤", "鈴木", "高橋", "田中"]

    # --- 検索機能のテスト ---
    async def test_search_by_last_name(self, db_session: AsyncSession, search_sort_filter_fixtures):
        """検索: 姓での部分一致検索"""
        office_id = search_sort_filter_fixtures["office_id"]
        
        results = await crud_dashboard.get_filtered_summaries(
            db=db_session, office_ids=[office_id],
            sort_by="name_phonetic", sort_order="asc",
            filters={}, search_term="田", skip=0, limit=10
        )
        
        assert len(results) == 1
        assert results[0].last_name == "田中"

    async def test_search_by_full_name(self, db_session: AsyncSession, search_sort_filter_fixtures):
        """検索: フルネームでの検索"""
        office_id = search_sort_filter_fixtures["office_id"]
        
        results = await crud_dashboard.get_filtered_summaries(
            db=db_session, office_ids=[office_id],
            sort_by="name_phonetic", sort_order="asc",
            filters={}, search_term="鈴木 次郎", skip=0, limit=10
        )
        
        assert len(results) == 1
        assert results[0].last_name == "鈴木"

    async def test_search_by_furigana(self, db_session: AsyncSession, search_sort_filter_fixtures):
        """検索: フリガナでの検索"""
        office_id = search_sort_filter_fixtures["office_id"]
        
        results = await crud_dashboard.get_filtered_summaries(
            db=db_session, office_ids=[office_id],
            sort_by="name_phonetic", sort_order="asc",
            filters={}, search_term="さとう", skip=0, limit=10
        )
        
        assert len(results) == 1
        assert results[0].last_name == "佐藤"

    async def test_search_no_results(self, db_session: AsyncSession, search_sort_filter_fixtures):
        """検索: 該当なしの場合"""
        office_id = search_sort_filter_fixtures["office_id"]
        
        results = await crud_dashboard.get_filtered_summaries(
            db=db_session, office_ids=[office_id],
            sort_by="name_phonetic", sort_order="asc",
            filters={}, search_term="山田", skip=0, limit=10
        )
        
        assert len(results) == 0

    # --- ソート機能のテスト ---
    async def test_sort_by_created_at_desc(self, db_session: AsyncSession, search_sort_filter_fixtures):
        """ソート: 作成日時の降順"""
        office_id = search_sort_filter_fixtures["office_id"]
        
        results = await crud_dashboard.get_filtered_summaries(
            db=db_session, office_ids=[office_id],
            sort_by="created_at", sort_order="desc",
            filters={}, search_term=None, skip=0, limit=10
        )
        
        assert len(results) == 5
        assert [r.last_name for r in results] == ["伊藤", "高橋", "田中", "鈴木", "佐藤"]

    async def test_sort_by_next_renewal_deadline_asc(self, db_session: AsyncSession, search_sort_filter_fixtures):
        """ソート: 次回更新日の昇順（サイクルがない利用者は含まれない）"""
        office_id = search_sort_filter_fixtures["office_id"]
        
        results = await crud_dashboard.get_filtered_summaries(
            db=db_session, office_ids=[office_id],
            sort_by="next_renewal_deadline", sort_order="asc",
            filters={}, search_term=None, skip=0, limit=10
        )
        
        # サイクルを持つ4人のみ
        assert len(results) == 4
        assert [r.last_name for r in results] == ["佐藤", "鈴木", "田中", "高橋"]

    # --- フィルター機能のテスト ---
    async def test_filter_is_overdue(self, db_session: AsyncSession, search_sort_filter_fixtures):
        """フィルター: 期限切れ"""
        office_id = search_sort_filter_fixtures["office_id"]
        
        results = await crud_dashboard.get_filtered_summaries(
            db=db_session, office_ids=[office_id],
            sort_by="name_phonetic", sort_order="asc",
            filters={"is_overdue": True}, search_term=None, skip=0, limit=10
        )
        
        assert len(results) == 1
        assert results[0].last_name == "佐藤"

    async def test_filter_is_upcoming(self, db_session: AsyncSession, search_sort_filter_fixtures):
        """フィルター: 更新間近"""
        office_id = search_sort_filter_fixtures["office_id"]
        
        results = await crud_dashboard.get_filtered_summaries(
            db=db_session, office_ids=[office_id],
            sort_by="name_phonetic", sort_order="asc",
            filters={"is_upcoming": True}, search_term=None, skip=0, limit=10
        )
        
        assert len(results) == 1
        assert results[0].last_name == "鈴木"

    async def test_filter_by_status(self, db_session: AsyncSession, search_sort_filter_fixtures):
        """フィルター: ステータス"""
        office_id = search_sort_filter_fixtures["office_id"]
        
        results = await crud_dashboard.get_filtered_summaries(
            db=db_session, office_ids=[office_id],
            sort_by="name_phonetic", sort_order="asc",
            filters={"status": SupportPlanStep.draft_plan}, search_term=None, skip=0, limit=10
        )
        
        assert len(results) == 1
        assert results[0].last_name == "田中"

    async def test_filter_by_cycle_number(self, db_session: AsyncSession, search_sort_filter_fixtures):
        """フィルター: サイクル番号"""
        office_id = search_sort_filter_fixtures["office_id"]
        
        results = await crud_dashboard.get_filtered_summaries(
            db=db_session, office_ids=[office_id],
            sort_by="name_phonetic", sort_order="asc",
            filters={"cycle_number": 2}, search_term=None, skip=0, limit=10
        )
        
        assert len(results) == 1
        assert results[0].last_name == "田中"

    # --- 複合条件のテスト ---
    async def test_search_with_overdue_filter(self, db_session: AsyncSession, search_sort_filter_fixtures):
        """複合: 検索 + 期限切れフィルター"""
        office_id = search_sort_filter_fixtures["office_id"]
        
        results = await crud_dashboard.get_filtered_summaries(
            db=db_session,
            office_ids=[office_id],
            sort_by="name_phonetic",
            sort_order="asc",
            filters={"is_overdue": True},
            search_term="佐藤",
            skip=0,
            limit=50
        )
        assert len(results) == 1
        assert results[0].last_name == "佐藤"

    async def test_contradictory_filters(self, db_session: AsyncSession, search_sort_filter_fixtures):
        """複合: 矛盾するフィルター条件 (期限切れ AND 更新間近)"""
        office_id = search_sort_filter_fixtures["office_id"]
        
        results = await crud_dashboard.get_filtered_summaries(
            db=db_session,
            office_ids=[office_id],
            sort_by="name_phonetic",
            sort_order="asc",
            filters={
                "is_overdue": True,
                "is_upcoming": True
            },
            search_term=None,
            skip=0,
            limit=50
        )
        # 矛盾する条件なので結果は0件になる
        assert len(results) == 0

    async def test_all_conditions_combined(self, db_session: AsyncSession, search_sort_filter_fixtures):
        """複合: 全条件の組み合わせ"""
        office_id = search_sort_filter_fixtures["office_id"]
        
        results = await crud_dashboard.get_filtered_summaries(
            db=db_session,
            office_ids=[office_id],
            sort_by="next_renewal_deadline",
            sort_order="asc",
            filters={
                "is_upcoming": True,
                "status": SupportPlanStep.monitoring,
                "cycle_number": 1
            },
            search_term="すずき",
            skip=0,
            limit=50
        )
        assert len(results) == 1
        assert results[0].last_name == "鈴木"
