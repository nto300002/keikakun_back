"""
Test 5: 既存機能の回帰テスト

TDDアプローチ:
1. Red: テストを実装し、失敗することを確認
2. Green: 実装を修正してテストをパス
3. Refactor: リファクタリング後も回帰がないことを確認
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.models.enums import SupportPlanStep
from tests.utils import (
    create_test_office,
    create_test_recipient,
    create_test_cycle,
    create_test_status
)


class TestDashboardRegression:
    """既存機能の回帰テスト"""

    @pytest.mark.asyncio
    async def test_all_filters_work_correctly(self, db_session: AsyncSession):
        """
        Test 5.1.1: すべてのフィルターが正しく動作

        要件:
        - status フィルター
        - cycle_number フィルター
        - search_term（氏名検索）
        - 複合条件（AND）

        TDD: Red → Green → Refactor
        """
        # Setup: 様々な条件の利用者
        office = await create_test_office(db_session)

        # 利用者1: assessment, cycle=1, 名前="山田太郎"
        recipient1 = await create_test_recipient(
            db_session,
            office_id=office.id,
            last_name="山田",
            first_name="太郎",
            last_name_furigana="やまだ",
            first_name_furigana="たろう"
        )
        cycle1 = await create_test_cycle(
            db_session,
            welfare_recipient_id=recipient1.id,
            office_id=office.id,
            cycle_number=1,
            is_latest_cycle=True
        )
        await create_test_status(
            db_session,
            plan_cycle_id=cycle1.id,
            welfare_recipient_id=recipient1.id,
            office_id=office.id,
            step_type=SupportPlanStep.assessment,
            is_latest_status=True
        )

        # 利用者2: monitoring, cycle=2, 名前="佐藤花子"
        recipient2 = await create_test_recipient(
            db_session,
            office_id=office.id,
            last_name="佐藤",
            first_name="花子",
            last_name_furigana="さとう",
            first_name_furigana="はなこ"
        )
        # cycle 1（過去）
        await create_test_cycle(
            db_session,
            welfare_recipient_id=recipient2.id,
            office_id=office.id,
            cycle_number=1,
            is_latest_cycle=False
        )
        # cycle 2（最新）
        cycle2 = await create_test_cycle(
            db_session,
            welfare_recipient_id=recipient2.id,
            office_id=office.id,
            cycle_number=2,
            is_latest_cycle=True
        )
        await create_test_status(
            db_session,
            plan_cycle_id=cycle2.id,
            welfare_recipient_id=recipient2.id,
            office_id=office.id,
            step_type=SupportPlanStep.monitoring,
            is_latest_status=True
        )

        await db_session.commit()

        # Test 1: status フィルター
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
        assert len(results) == 1
        assert results[0][0].last_name == "山田"

        # Test 2: cycle_number フィルター
        results = await crud.dashboard.get_filtered_summaries(
            db=db_session,
            office_ids=[office.id],
            sort_by="furigana",
            sort_order="asc",
            filters={"cycle_number": 2},
            search_term=None,
            skip=0,
            limit=100
        )
        assert len(results) == 1
        assert results[0][0].last_name == "佐藤"

        # Test 3: search_term（氏名検索）
        results = await crud.dashboard.get_filtered_summaries(
            db=db_session,
            office_ids=[office.id],
            sort_by="furigana",
            sort_order="asc",
            filters={},
            search_term="山田",
            skip=0,
            limit=100
        )
        assert len(results) == 1
        assert results[0][0].last_name == "山田"

        # Test 4: 複合条件（status + cycle_number）
        results = await crud.dashboard.get_filtered_summaries(
            db=db_session,
            office_ids=[office.id],
            sort_by="furigana",
            sort_order="asc",
            filters={
                "status": "monitoring",
                "cycle_number": 2
            },
            search_term=None,
            skip=0,
            limit=100
        )
        assert len(results) == 1
        assert results[0][0].last_name == "佐藤"

    @pytest.mark.asyncio
    async def test_all_sort_options_work_correctly(self, db_session: AsyncSession):
        """
        Test 5.1.2: すべてのソートオプションが正しく動作

        要件:
        - furigana（ふりがな昇順・降順）
        - next_renewal_deadline（期限昇順・降順）
        - NULLハンドリング

        TDD: Red → Green → Refactor
        """
        # Setup: 異なるふりがな・期限の利用者
        office = await create_test_office(db_session)

        # 利用者A: あ, 期限=2026-03-01
        recipient_a = await create_test_recipient(
            db_session,
            office_id=office.id,
            last_name_furigana="あいうえお",
            first_name_furigana="あ",
            last_name="アイウエオ",
            first_name="A"
        )
        cycle_a = await create_test_cycle(
            db_session,
            welfare_recipient_id=recipient_a.id,
            office_id=office.id,
            cycle_number=1,
            is_latest_cycle=True,
            next_renewal_deadline="2026-03-01"
        )

        # 利用者B: か, 期限=2026-02-01
        recipient_b = await create_test_recipient(
            db_session,
            office_id=office.id,
            last_name_furigana="かきくけこ",
            first_name_furigana="か",
            last_name="カキクケコ",
            first_name="B"
        )
        cycle_b = await create_test_cycle(
            db_session,
            welfare_recipient_id=recipient_b.id,
            office_id=office.id,
            cycle_number=1,
            is_latest_cycle=True,
            next_renewal_deadline="2026-02-01"
        )

        # 利用者C: さ, 期限なし
        recipient_c = await create_test_recipient(
            db_session,
            office_id=office.id,
            last_name_furigana="さしすせそ",
            first_name_furigana="さ",
            last_name="サシスセソ",
            first_name="C"
        )
        # サイクルなし（期限なし）

        await db_session.commit()

        # Test 1: ふりがな昇順
        results = await crud.dashboard.get_filtered_summaries(
            db=db_session,
            office_ids=[office.id],
            sort_by="furigana",
            sort_order="asc",
            filters={},
            search_term=None,
            skip=0,
            limit=100
        )
        assert len(results) == 3
        assert results[0][0].last_name_furigana.startswith("あ")
        assert results[1][0].last_name_furigana.startswith("か")
        assert results[2][0].last_name_furigana.startswith("さ")

        # Test 2: ふりがな降順
        results = await crud.dashboard.get_filtered_summaries(
            db=db_session,
            office_ids=[office.id],
            sort_by="furigana",
            sort_order="desc",
            filters={},
            search_term=None,
            skip=0,
            limit=100
        )
        assert len(results) == 3
        assert results[0][0].last_name_furigana.startswith("さ")
        assert results[1][0].last_name_furigana.startswith("か")
        assert results[2][0].last_name_furigana.startswith("あ")

        # Test 3: 期限昇順（早い順、NULLは最後）
        results = await crud.dashboard.get_filtered_summaries(
            db=db_session,
            office_ids=[office.id],
            sort_by="next_renewal_deadline",
            sort_order="asc",
            filters={},
            search_term=None,
            skip=0,
            limit=100
        )
        assert len(results) == 3
        # B(2026-02-01) → A(2026-03-01) → C(NULL)
        assert results[0][2] is not None
        assert results[0][2].next_renewal_deadline.strftime("%Y-%m-%d") == "2026-02-01"
        assert results[1][2] is not None
        assert results[1][2].next_renewal_deadline.strftime("%Y-%m-%d") == "2026-03-01"
        assert results[2][2] is None  # NULLは最後

        # Test 4: 期限降順（遠い順、NULLは最後）
        results = await crud.dashboard.get_filtered_summaries(
            db=db_session,
            office_ids=[office.id],
            sort_by="next_renewal_deadline",
            sort_order="desc",
            filters={},
            search_term=None,
            skip=0,
            limit=100
        )
        assert len(results) == 3
        # A(2026-03-01) → B(2026-02-01) → C(NULL)
        assert results[0][2] is not None
        assert results[0][2].next_renewal_deadline.strftime("%Y-%m-%d") == "2026-03-01"
        assert results[1][2] is not None
        assert results[1][2].next_renewal_deadline.strftime("%Y-%m-%d") == "2026-02-01"
        assert results[2][2] is None  # NULLは最後

    @pytest.mark.asyncio
    async def test_pagination_works_correctly(self, db_session: AsyncSession):
        """
        Test 5.1.3: ページネーションが正しく動作

        要件:
        - skip/limit が正しく機能
        - 総件数が正確

        TDD: Red → Green → Refactor
        """
        # Setup: 150利用者
        office = await create_test_office(db_session)
        for i in range(150):
            await create_test_recipient(
                db_session,
                office_id=office.id,
                last_name=f"テスト{i:03d}",
                first_name="太郎",
                last_name_furigana=f"てすと{i:03d}",
                first_name_furigana="たろう"
            )
        await db_session.commit()

        # Test 1: 1ページ目（0-99）
        results_page1 = await crud.dashboard.get_filtered_summaries(
            db=db_session,
            office_ids=[office.id],
            sort_by="furigana",
            sort_order="asc",
            filters={},
            search_term=None,
            skip=0,
            limit=100
        )
        assert len(results_page1) == 100

        # Test 2: 2ページ目（100-149）
        results_page2 = await crud.dashboard.get_filtered_summaries(
            db=db_session,
            office_ids=[office.id],
            sort_by="furigana",
            sort_order="asc",
            filters={},
            search_term=None,
            skip=100,
            limit=100
        )
        assert len(results_page2) == 50

        # Test 3: 重複がないこと
        page1_ids = {r[0].id for r in results_page1}
        page2_ids = {r[0].id for r in results_page2}
        assert page1_ids.isdisjoint(page2_ids), "ページ間で重複があります"

    @pytest.mark.asyncio
    async def test_empty_office_returns_empty_list(self, db_session: AsyncSession):
        """
        Test 5.1.4: 利用者がいない事業所は空リストを返す

        要件:
        - 利用者0の事業所でエラーが発生しない
        - 空のリストを返す

        TDD: Red → Green → Refactor
        """
        # Setup: 利用者がいない事業所
        office = await create_test_office(db_session)
        await db_session.commit()

        # Execute
        results = await crud.dashboard.get_filtered_summaries(
            db=db_session,
            office_ids=[office.id],
            sort_by="furigana",
            sort_order="asc",
            filters={},
            search_term=None,
            skip=0,
            limit=100
        )

        # Assert
        assert len(results) == 0, \
            "利用者がいない事業所は空リストを返すこと"

    @pytest.mark.asyncio
    async def test_multiple_offices_filter(self, db_session: AsyncSession):
        """
        Test 5.1.5: 複数事業所フィルターが正しく動作

        要件:
        - office_ids で複数事業所を指定
        - 指定した事業所の利用者のみ表示

        TDD: Red → Green → Refactor
        """
        # Setup: 3つの事業所
        office_a = await create_test_office(db_session, name="事業所A")
        office_b = await create_test_office(db_session, name="事業所B")
        office_c = await create_test_office(db_session, name="事業所C")

        # 各事業所に利用者を作成
        for office, name_prefix in [
            (office_a, "A"),
            (office_b, "B"),
            (office_c, "C")
        ]:
            for i in range(10):
                await create_test_recipient(
                    db_session,
                    office_id=office.id,
                    last_name=f"{name_prefix}{i:02d}",
                    first_name="太郎"
                )

        await db_session.commit()

        # Test 1: 事業所A+Bのみ指定
        results = await crud.dashboard.get_filtered_summaries(
            db=db_session,
            office_ids=[office_a.id, office_b.id],
            sort_by="furigana",
            sort_order="asc",
            filters={},
            search_term=None,
            skip=0,
            limit=100
        )

        # Assert: 事業所A+Bの利用者のみ（20人）
        assert len(results) == 20

        # 事業所Cの利用者が含まれていないことを確認
        last_names = [r[0].last_name for r in results]
        assert all(not name.startswith("C") for name in last_names), \
            "事業所Cの利用者が含まれています"

        # Test 2: 全事業所指定
        results_all = await crud.dashboard.get_filtered_summaries(
            db=db_session,
            office_ids=[office_a.id, office_b.id, office_c.id],
            sort_by="furigana",
            sort_order="asc",
            filters={},
            search_term=None,
            skip=0,
            limit=100
        )

        # Assert: 全30人
        assert len(results_all) == 30
