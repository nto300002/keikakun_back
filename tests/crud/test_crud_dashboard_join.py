"""
Test 1.3: JOIN戦略統一のテスト

TDDアプローチ:
1. Red: テストを実装し、失敗することを確認
2. Green: OUTER JOIN統一を実装してテストをパス
3. Refactor: コードをリファクタリング
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from tests.utils import (
    create_test_office,
    create_test_recipient,
    create_test_cycle
)


class TestJoinStrategy:
    """JOIN戦略統一のテスト"""

    @pytest.mark.asyncio
    async def test_outer_join_includes_no_cycle_recipients(
        self,
        db_session: AsyncSession
    ):
        """
        Test 1.3.1: 最新サイクルがない利用者も表示される

        要件:
        - OUTER JOIN により、サイクルがない利用者も結果に含まれる

        TDD: Red → Green → Refactor
        """
        # Setup
        office = await create_test_office(db_session)

        # サイクルありの利用者
        recipient_with_cycle = await create_test_recipient(
            db_session,
            office_id=office.id,
            last_name="山田",
            first_name="太郎",
            last_name_furigana="やまだ",
            first_name_furigana="たろう"
        )
        await create_test_cycle(
            db_session,
            welfare_recipient_id=recipient_with_cycle.id,
            office_id=office.id,
            cycle_number=1,
            is_latest_cycle=True
        )

        # サイクルなしの利用者
        recipient_without_cycle = await create_test_recipient(
            db_session,
            office_id=office.id,
            last_name="佐藤",
            first_name="花子",
            last_name_furigana="さとう",
            first_name_furigana="はなこ"
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
        assert len(results) == 2, "2件の利用者が表示されること"

        # サイクルなしの利用者（さとう）
        recipient1, cycle_count1, latest_cycle1 = results[0]
        assert recipient1.last_name == "佐藤"
        assert cycle_count1 == 0
        assert latest_cycle1 is None

        # サイクルありの利用者（やまだ）
        recipient2, cycle_count2, latest_cycle2 = results[1]
        assert recipient2.last_name == "山田"
        assert cycle_count2 == 1
        assert latest_cycle2 is not None

    @pytest.mark.asyncio
    async def test_sort_by_next_renewal_deadline_with_nulls(
        self,
        db_session: AsyncSession
    ):
        """
        Test 1.3.2: 期限ソート時のNULLハンドリング

        要件:
        - sort_by='next_renewal_deadline' でもOUTER JOIN
        - NULLは最後にソート（nullslast）

        TDD: Red → Green → Refactor
        """
        # Setup: 期限あり・なしの利用者
        office = await create_test_office(db_session)

        # 期限あり（2026-03-01）
        recipient_with_deadline = await create_test_recipient(
            db_session,
            office_id=office.id,
            last_name="山田",
            first_name="太郎"
        )
        cycle_with_deadline = await create_test_cycle(
            db_session,
            welfare_recipient_id=recipient_with_deadline.id,
            office_id=office.id,
            cycle_number=1,
            is_latest_cycle=True,
            next_renewal_deadline="2026-03-01"
        )

        # 期限なし（最新サイクルなし）
        recipient_without_deadline = await create_test_recipient(
            db_session,
            office_id=office.id,
            last_name="佐藤",
            first_name="花子"
        )

        await db_session.commit()

        # Execute: 期限昇順でソート
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

        # Assert: 期限ありが先、期限なし（NULL）が後
        assert len(results) == 2

        first_recipient, _, first_cycle = results[0]
        assert first_cycle is not None, "1番目は期限ありの利用者"
        assert first_cycle.next_renewal_deadline is not None
        assert first_recipient.last_name == "山田"

        second_recipient, _, second_cycle = results[1]
        assert second_cycle is None, "2番目は期限なし（NULL）の利用者"
        assert second_recipient.last_name == "佐藤"

    @pytest.mark.asyncio
    async def test_sort_by_next_renewal_deadline_desc_with_nulls(
        self,
        db_session: AsyncSession
    ):
        """
        Test 1.3.3: 期限降順ソート時のNULLハンドリング

        要件:
        - sort_order='desc' でもNULLは最後
        - 期限が遠い順にソート

        TDD: Red → Green → Refactor
        """
        # Setup: 複数の期限
        office = await create_test_office(db_session)

        # 期限A: 2026-02-01（近い）
        recipient_a = await create_test_recipient(
            db_session,
            office_id=office.id,
            last_name="A",
            first_name="太郎"
        )
        await create_test_cycle(
            db_session,
            welfare_recipient_id=recipient_a.id,
            office_id=office.id,
            cycle_number=1,
            is_latest_cycle=True,
            next_renewal_deadline="2026-02-01"
        )

        # 期限B: 2026-03-01（遠い）
        recipient_b = await create_test_recipient(
            db_session,
            office_id=office.id,
            last_name="B",
            first_name="次郎"
        )
        await create_test_cycle(
            db_session,
            welfare_recipient_id=recipient_b.id,
            office_id=office.id,
            cycle_number=1,
            is_latest_cycle=True,
            next_renewal_deadline="2026-03-01"
        )

        # 期限なし
        recipient_null = await create_test_recipient(
            db_session,
            office_id=office.id,
            last_name="NULL",
            first_name="三郎"
        )

        await db_session.commit()

        # Execute: 期限降順でソート
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

        # Assert: B(遠い) → A(近い) → NULL(最後)
        assert len(results) == 3

        # 1番目: B（2026-03-01）
        assert results[0][0].last_name == "B"
        assert results[0][2].next_renewal_deadline.strftime("%Y-%m-%d") == "2026-03-01"

        # 2番目: A（2026-02-01）
        assert results[1][0].last_name == "A"
        assert results[1][2].next_renewal_deadline.strftime("%Y-%m-%d") == "2026-02-01"

        # 3番目: NULL（最後）
        assert results[2][0].last_name == "NULL"
        assert results[2][2] is None

    @pytest.mark.asyncio
    async def test_inner_join_regression_check(self, db_session: AsyncSession):
        """
        Test 1.3.4: INNER JOIN への回帰がないことを確認

        要件:
        - 旧実装（INNER JOIN）ではサイクルなし利用者が除外されていた
        - 新実装（OUTER JOIN）では含まれることを確認

        TDD: Red → Green → Refactor
        """
        # Setup
        office = await create_test_office(db_session)

        # 10人の利用者（半分はサイクルなし）
        for i in range(10):
            recipient = await create_test_recipient(
                db_session,
                office_id=office.id,
                last_name=f"テスト{i:02d}",
                first_name="太郎"
            )

            # 偶数のみサイクル作成
            if i % 2 == 0:
                await create_test_cycle(
                    db_session,
                    welfare_recipient_id=recipient.id,
                    office_id=office.id,
                    cycle_number=1,
                    is_latest_cycle=True
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

        # Assert: 全10人が含まれる（INNER JOINなら5人のみ）
        assert len(results) == 10, \
            "サイクルなし利用者も含めて全員が表示されること（OUTER JOIN）"

        # サイクルありの数を確認
        with_cycle = sum(1 for _, _, cycle in results if cycle is not None)
        without_cycle = sum(1 for _, _, cycle in results if cycle is None)

        assert with_cycle == 5, "サイクルありは5人"
        assert without_cycle == 5, "サイクルなしは5人"
