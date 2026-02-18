"""
Test 3.2: EXISTS句フィルターのテスト

TDDアプローチ:
1. Red: テストを実装し、失敗することを確認
2. Green: EXISTS句を実装してテストをパス
3. Refactor: コードをリファクタリング
"""

import pytest
import pytest_asyncio
import time
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.models.enums import SupportPlanStep
from tests.utils import (
    create_test_office,
    create_test_recipient,
    create_test_cycle,
    create_test_status
)


class TestExistsClauseFilter:
    """EXISTS句を使用したフィルターのテスト"""

    @pytest_asyncio.fixture
    async def setup_recipients_with_different_statuses(self, db_session: AsyncSession):
        """異なるステータスの利用者を作成"""
        office = await create_test_office(db_session)

        # アセスメントステップの利用者
        recipient_assessment = await create_test_recipient(
            db_session,
            office_id=office.id,
            last_name="山田",
            first_name="太郎",
            last_name_furigana="やまだ",
            first_name_furigana="たろう"
        )
        cycle_assessment = await create_test_cycle(
            db_session,
            welfare_recipient_id=recipient_assessment.id,
            cycle_number=1,
            is_latest_cycle=True
        )
        await create_test_status(
            db_session,
            plan_cycle_id=cycle_assessment.id,
            step_type=SupportPlanStep.assessment,
            is_latest_status=True
        )

        # モニタリングステップの利用者
        recipient_monitoring = await create_test_recipient(
            db_session,
            office_id=office.id,
            last_name="佐藤",
            first_name="花子",
            last_name_furigana="さとう",
            first_name_furigana="はなこ"
        )
        cycle_monitoring = await create_test_cycle(
            db_session,
            welfare_recipient_id=recipient_monitoring.id,
            cycle_number=1,
            is_latest_cycle=True
        )
        await create_test_status(
            db_session,
            plan_cycle_id=cycle_monitoring.id,
            step_type=SupportPlanStep.monitoring,
            is_latest_status=True
        )

        await db_session.commit()
        return {
            "office": office,
            "recipients": {
                "assessment": recipient_assessment,
                "monitoring": recipient_monitoring
            }
        }

    @pytest.mark.asyncio
    async def test_filter_by_assessment_status(
        self,
        db_session: AsyncSession,
        setup_recipients_with_different_statuses
    ):
        """
        Test 3.2.1: アセスメントステータスでフィルタリング

        要件:
        - status='assessment' で正しくフィルタリング
        - EXISTS句が正しく動作

        TDD: Red → Green → Refactor
        """
        data = setup_recipients_with_different_statuses
        office = data["office"]

        # Execute: assessment フィルター
        results = await crud.dashboard.get_filtered_summaries(
            db=db_session,
            office_ids=[office.id],
            sort_by="furigana",
            sort_order="asc",
            filters={"status": "assessment"},
            search_term=None,
            skip=0,
            limit=100
        )

        # Assert: assessment の利用者のみ
        assert len(results) == 1, f"1件の結果が期待されます: {len(results)}件"
        recipient, _, latest_cycle = results[0]
        assert recipient.last_name == "山田"
        assert latest_cycle.statuses[0].step_type == SupportPlanStep.assessment

    @pytest.mark.asyncio
    async def test_filter_by_monitoring_status(
        self,
        db_session: AsyncSession,
        setup_recipients_with_different_statuses
    ):
        """
        Test 3.2.2: モニタリングステータスでフィルタリング

        要件:
        - status='monitoring' で正しくフィルタリング

        TDD: Red → Green → Refactor
        """
        data = setup_recipients_with_different_statuses
        office = data["office"]

        # Execute: monitoring フィルター
        results = await crud.dashboard.get_filtered_summaries(
            db=db_session,
            office_ids=[office.id],
            sort_by="furigana",
            sort_order="asc",
            filters={"status": "monitoring"},
            search_term=None,
            skip=0,
            limit=100
        )

        # Assert: monitoring の利用者のみ
        assert len(results) == 1
        recipient, _, latest_cycle = results[0]
        assert recipient.last_name == "佐藤"
        assert latest_cycle.statuses[0].step_type == SupportPlanStep.monitoring

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_exists_clause_performance(self, db_session: AsyncSession):
        """
        Test 3.2.3: EXISTS句のパフォーマンス

        要件:
        - EXISTS句がサブクエリ+JOINより高速
        - クエリ時間 < 300ms（100利用者）

        TDD: Red → Green → Refactor
        """
        # Setup: 100利用者（50人ずつ異なるステータス）
        office = await create_test_office(db_session)
        for i in range(100):
            recipient = await create_test_recipient(
                db_session,
                office_id=office.id,
                last_name=f"テスト{i:03d}",
                first_name="太郎"
            )
            cycle = await create_test_cycle(
                db_session,
                welfare_recipient_id=recipient.id,
                cycle_number=1,
                is_latest_cycle=True
            )
            status_type = SupportPlanStep.assessment if i < 50 else SupportPlanStep.monitoring
            await create_test_status(
                db_session,
                plan_cycle_id=cycle.id,
                step_type=status_type,
                is_latest_status=True
            )
        await db_session.commit()

        # Execute: パフォーマンス測定
        start_time = time.time()
        results = await crud.dashboard.get_filtered_summaries(
            db=db_session,
            office_ids=[office.id],
            sort_by="furigana",
            sort_order="asc",
            filters={"status": "assessment"},
            search_term=None,
            skip=0,
            limit=100
        )
        elapsed_time = time.time() - start_time

        # Assert
        assert len(results) == 50, "50件の結果が期待されます"
        assert elapsed_time < 0.3, \
            f"クエリ時間が300msを超えました: {elapsed_time:.3f}s"

        # デバッグ情報を出力
        print(f"\nEXISTS句フィルター時間: {elapsed_time:.3f}s")

    @pytest.mark.asyncio
    async def test_invalid_status_filter_returns_empty(self, db_session: AsyncSession):
        """
        Test 3.2.4: 無効なステータスフィルターは無視される

        要件:
        - 存在しないステータス名でエラーが発生しない
        - フィルターが無視され、全件表示される

        TDD: Red → Green → Refactor
        """
        # Setup
        office = await create_test_office(db_session)
        recipient = await create_test_recipient(
            db_session,
            office_id=office.id,
            last_name="山田",
            first_name="太郎"
        )
        cycle = await create_test_cycle(
            db_session,
            welfare_recipient_id=recipient.id,
            cycle_number=1,
            is_latest_cycle=True
        )
        await create_test_status(
            db_session,
            plan_cycle_id=cycle.id,
            step_type=SupportPlanStep.assessment,
            is_latest_status=True
        )
        await db_session.commit()

        # Execute: 無効なステータス名
        results = await crud.dashboard.get_filtered_summaries(
            db=db_session,
            office_ids=[office.id],
            sort_by="furigana",
            sort_order="asc",
            filters={"status": "invalid_status"},
            search_term=None,
            skip=0,
            limit=100
        )

        # Assert: フィルターが無視され、全件表示
        assert len(results) == 1, \
            "無効なステータスフィルターは無視されること"

    @pytest.mark.asyncio
    async def test_filter_with_multiple_conditions(self, db_session: AsyncSession):
        """
        Test 3.2.5: 複数の条件でフィルタリング

        要件:
        - status + cycle_number の複合条件
        - AND条件で正しくフィルタリング

        TDD: Red → Green → Refactor
        """
        # Setup: 異なるステータス・サイクル数の利用者
        office = await create_test_office(db_session)

        # 利用者A: assessment, cycle=1
        recipient_a = await create_test_recipient(
            db_session,
            office_id=office.id,
            last_name="A",
            first_name="太郎"
        )
        cycle_a = await create_test_cycle(
            db_session,
            welfare_recipient_id=recipient_a.id,
            cycle_number=1,
            is_latest_cycle=True
        )
        await create_test_status(
            db_session,
            plan_cycle_id=cycle_a.id,
            step_type=SupportPlanStep.assessment,
            is_latest_status=True
        )

        # 利用者B: monitoring, cycle=2
        recipient_b = await create_test_recipient(
            db_session,
            office_id=office.id,
            last_name="B",
            first_name="次郎"
        )
        # 過去サイクル
        await create_test_cycle(
            db_session,
            welfare_recipient_id=recipient_b.id,
            cycle_number=1,
            is_latest_cycle=False
        )
        # 最新サイクル
        cycle_b = await create_test_cycle(
            db_session,
            welfare_recipient_id=recipient_b.id,
            cycle_number=2,
            is_latest_cycle=True
        )
        await create_test_status(
            db_session,
            plan_cycle_id=cycle_b.id,
            step_type=SupportPlanStep.monitoring,
            is_latest_status=True
        )

        await db_session.commit()

        # Execute: status='assessment' AND cycle_number=1
        results = await crud.dashboard.get_filtered_summaries(
            db=db_session,
            office_ids=[office.id],
            sort_by="furigana",
            sort_order="asc",
            filters={
                "status": "assessment",
                "cycle_number": 1
            },
            search_term=None,
            skip=0,
            limit=100
        )

        # Assert: 利用者Aのみ
        assert len(results) == 1
        recipient, cycle_count, _ = results[0]
        assert recipient.last_name == "A"
        assert cycle_count == 1
