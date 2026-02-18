"""
Test 1.2: サブクエリ統合の正しさテスト

TDDアプローチ:
1. Red: テストを実装し、失敗することを確認
2. Green: cycle_info_sq サブクエリ統合を実装してテストをパス
3. Refactor: コードをリファクタリング
"""

import pytest
import pytest_asyncio
import time
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from tests.utils import (
    create_test_office,
    create_test_recipient,
    create_test_cycle
)


class TestSubqueryIntegration:
    """統合サブクエリ(cycle_info_sq)の正しさテスト"""

    @pytest_asyncio.fixture
    async def setup_recipient_with_cycles(self, db_session: AsyncSession):
        """利用者 + 複数サイクルのテストデータ作成"""
        # 事業所作成
        office = await create_test_office(db_session)

        # 利用者作成
        recipient = await create_test_recipient(
            db_session,
            office_id=office.id,
            last_name="山田",
            first_name="太郎",
            last_name_furigana="やまだ",
            first_name_furigana="たろう"
        )

        # サイクルを3つ作成（1,2は過去、3が最新）
        cycle1 = await create_test_cycle(
            db_session,
            welfare_recipient_id=recipient.id,
            office_id=office.id,
            cycle_number=1,
            is_latest_cycle=False
        )
        cycle2 = await create_test_cycle(
            db_session,
            welfare_recipient_id=recipient.id,
            office_id=office.id,
            cycle_number=2,
            is_latest_cycle=False
        )
        cycle3 = await create_test_cycle(
            db_session,
            welfare_recipient_id=recipient.id,
            office_id=office.id,
            cycle_number=3,
            is_latest_cycle=True
        )

        await db_session.commit()
        return {
            "office": office,
            "recipient": recipient,
            "cycles": [cycle1, cycle2, cycle3],
            "latest_cycle": cycle3
        }

    @pytest.mark.asyncio
    async def test_cycle_count_is_correct(
        self,
        db_session: AsyncSession,
        setup_recipient_with_cycles
    ):
        """
        Test 1.2.1: サイクル数が正しくカウントされる

        要件:
        - cycle_count = 実際のサイクル数
        - GROUP BY が正しく機能

        TDD: Red → Green → Refactor
        """
        data = setup_recipient_with_cycles
        office = data["office"]

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
        assert len(results) == 1, "結果が1件であること"
        recipient, cycle_count, latest_cycle = results[0]
        assert cycle_count == 3, \
            f"サイクル数が不正です: expected=3, actual={cycle_count}"

    @pytest.mark.asyncio
    async def test_latest_cycle_id_is_correct(
        self,
        db_session: AsyncSession,
        setup_recipient_with_cycles
    ):
        """
        Test 1.2.2: 最新サイクルIDが正しく取得される

        要件:
        - latest_cycle_id = is_latest_cycle=true のサイクルID
        - CASE式が正しく機能

        TDD: Red → Green → Refactor
        """
        data = setup_recipient_with_cycles
        office = data["office"]
        expected_latest_cycle = data["latest_cycle"]

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
        recipient, cycle_count, latest_cycle = results[0]
        assert latest_cycle is not None, "最新サイクルが取得できません"
        assert latest_cycle.id == expected_latest_cycle.id, \
            "最新サイクルIDが不正です"
        assert latest_cycle.is_latest_cycle == True, \
            "is_latest_cycle=trueではありません"
        assert latest_cycle.cycle_number == 3, \
            "最新サイクルのcycle_numberが不正です"

    @pytest.mark.asyncio
    async def test_no_latest_cycle_returns_null(self, db_session: AsyncSession):
        """
        Test 1.2.3: 最新サイクルがない場合NULLを返す

        要件:
        - 全サイクルが is_latest_cycle=false の場合、latest_cycle=NULL
        - OUTER JOIN が正しく機能

        TDD: Red → Green → Refactor
        """
        # Setup: 最新サイクルなしの利用者
        office = await create_test_office(db_session)
        recipient = await create_test_recipient(
            db_session,
            office_id=office.id,
            last_name="佐藤",
            first_name="花子"
        )
        # 過去サイクルのみ
        await create_test_cycle(
            db_session,
            welfare_recipient_id=recipient.id,
            office_id=office.id,
            cycle_number=1,
            is_latest_cycle=False
        )
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
        recipient, cycle_count, latest_cycle = results[0]
        assert cycle_count == 1, "サイクル数が不正です"
        assert latest_cycle is None, \
            "最新サイクルがNULLであること（is_latest_cycle=falseのみの場合）"

    @pytest.mark.asyncio
    async def test_subquery_performance(self, db_session: AsyncSession):
        """
        Test 1.2.4: サブクエリ統合のパフォーマンス

        要件:
        - 統合サブクエリが2つの独立サブクエリより高速
        - クエリ時間 < 200ms（100利用者）

        TDD: Red → Green → Refactor
        """
        # Setup: 100利用者 × 各3サイクル
        office = await create_test_office(db_session)
        for i in range(100):
            recipient = await create_test_recipient(
                db_session,
                office_id=office.id,
                last_name=f"テスト{i:03d}",
                first_name="太郎",
                last_name_furigana=f"てすと{i:03d}",
                first_name_furigana="たろう"
            )
            for j in range(3):
                await create_test_cycle(
                    db_session,
                    welfare_recipient_id=recipient.id,
            office_id=office.id,
                    cycle_number=j + 1,
                    is_latest_cycle=(j == 2)
                )
        await db_session.commit()

        # Execute: クエリ時間測定
        start_time = time.time()
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
        elapsed_time = time.time() - start_time

        # Assert
        assert len(results) == 100, "結果が100件であること"
        assert elapsed_time < 0.2, \
            f"クエリ時間が200msを超えました: {elapsed_time:.3f}s"

        # デバッグ情報を出力
        print(f"\n100利用者のクエリ時間: {elapsed_time:.3f}s")

    @pytest.mark.asyncio
    async def test_multiple_recipients_with_different_cycle_counts(
        self,
        db_session: AsyncSession
    ):
        """
        Test 1.2.5: 異なるサイクル数の利用者が正しくカウントされる

        要件:
        - 各利用者のサイクル数が独立してカウントされる
        - GROUP BY が正しく機能

        TDD: Red → Green → Refactor
        """
        # Setup: 3人の利用者（サイクル数が異なる）
        office = await create_test_office(db_session)

        # 利用者A: 1サイクル
        recipient_a = await create_test_recipient(
            db_session,
            office_id=office.id,
            last_name="あいうえお",
            first_name="A"
        )
        await create_test_cycle(
            db_session,
            welfare_recipient_id=recipient_a.id,
            office_id=office.id,
            cycle_number=1,
            is_latest_cycle=True
        )

        # 利用者B: 3サイクル
        recipient_b = await create_test_recipient(
            db_session,
            office_id=office.id,
            last_name="かきくけこ",
            first_name="B"
        )
        for j in range(3):
            await create_test_cycle(
                db_session,
                welfare_recipient_id=recipient_b.id,
            office_id=office.id,
                cycle_number=j + 1,
                is_latest_cycle=(j == 2)
            )

        # 利用者C: 5サイクル
        recipient_c = await create_test_recipient(
            db_session,
            office_id=office.id,
            last_name="さしすせそ",
            first_name="C"
        )
        for j in range(5):
            await create_test_cycle(
                db_session,
                welfare_recipient_id=recipient_c.id,
            office_id=office.id,
                cycle_number=j + 1,
                is_latest_cycle=(j == 4)
            )

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

        # Assert: サイクル数が正しい
        assert len(results) == 3, "3人の利用者が取得されること"

        # A: 1サイクル
        _, cycle_count_a, latest_a = results[0]
        assert cycle_count_a == 1
        assert latest_a.cycle_number == 1

        # B: 3サイクル
        _, cycle_count_b, latest_b = results[1]
        assert cycle_count_b == 3
        assert latest_b.cycle_number == 3

        # C: 5サイクル
        _, cycle_count_c, latest_c = results[2]
        assert cycle_count_c == 5
        assert latest_c.cycle_number == 5
