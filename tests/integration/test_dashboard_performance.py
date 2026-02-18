"""
Test 4: ダッシュボード統合パフォーマンステスト

TDDアプローチ:
1. Red: テストを実装し、失敗することを確認
2. Green: Phase 1-3の実装を完了してテストをパス
3. Refactor: コードをリファクタリング
"""

import pytest
import pytest_asyncio
import asyncio
import time
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from tests.utils import (
    create_test_offices,
    create_test_recipients,
    create_test_cycles
)


class TestDashboardPerformance:
    """ダッシュボード統合パフォーマンステスト"""

    @pytest_asyncio.fixture(scope="function")
    async def setup_large_dataset(self, db_session: AsyncSession):
        """
        大規模データセット作成

        Note: 500事業所は時間がかかるため、50事業所でテスト
        """
        # 50事業所作成
        offices = await create_test_offices(db_session, count=50)

        # 各事業所に100利用者 + 各利用者に3サイクル
        for office in offices:
            recipients = await create_test_recipients(
                db_session,
                office_id=office.id,
                count=100
            )
            for recipient in recipients:
                await create_test_cycles(
                    db_session,
                    welfare_recipient_id=recipient.id,
                    count=3
                )

        await db_session.commit()
        return offices

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_initial_dashboard_load_performance(
        self,
        db_session: AsyncSession,
        setup_large_dataset
    ):
        """
        Test 4.1.1: ダッシュボード初期表示パフォーマンス

        要件:
        - 10事業所同時表示でレスポンス時間 < 500ms
        - メモリ使用量 < 10MB

        TDD: Red → Green → Refactor
        """
        offices = setup_large_dataset
        office_ids = [office.id for office in offices[:10]]  # 10事業所を同時表示

        # Execute: 初期表示
        start_time = time.time()
        results = await crud.dashboard.get_filtered_summaries(
            db=db_session,
            office_ids=office_ids,
            sort_by="furigana",
            sort_order="asc",
            filters={},
            search_term=None,
            skip=0,
            limit=100
        )
        elapsed_time = time.time() - start_time

        # Assert: パフォーマンス目標
        assert elapsed_time < 0.5, \
            f"初期表示が500msを超えました: {elapsed_time:.3f}s"
        assert len(results) <= 100, "ページネーションが機能していません"

        # デバッグ情報を出力
        print(f"\n初期表示時間（10事業所、100件取得）: {elapsed_time:.3f}s")

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_filter_performance(
        self,
        db_session: AsyncSession,
        setup_large_dataset
    ):
        """
        Test 4.1.2: フィルタリングパフォーマンス

        要件:
        - フィルタリング応答 < 300ms

        TDD: Red → Green → Refactor
        """
        offices = setup_large_dataset
        office_ids = [office.id for office in offices[:10]]

        # Execute: ステータスフィルター
        start_time = time.time()
        results = await crud.dashboard.get_filtered_summaries(
            db=db_session,
            office_ids=office_ids,
            sort_by="next_renewal_deadline",
            sort_order="asc",
            filters={"status": "assessment"},
            search_term=None,
            skip=0,
            limit=100
        )
        elapsed_time = time.time() - start_time

        # Assert
        assert elapsed_time < 0.3, \
            f"フィルタリングが300msを超えました: {elapsed_time:.3f}s"

        # デバッグ情報を出力
        print(f"\nフィルタリング時間: {elapsed_time:.3f}s")

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_pagination_performance(
        self,
        db_session: AsyncSession,
        setup_large_dataset
    ):
        """
        Test 4.1.3: ページネーションパフォーマンス

        要件:
        - 2ページ目以降も < 500ms
        - OFFSET が大きくても安定

        TDD: Red → Green → Refactor
        """
        offices = setup_large_dataset
        office_ids = [office.id for office in offices[:10]]

        # Execute: 5ページ目（OFFSET=400）
        start_time = time.time()
        results = await crud.dashboard.get_filtered_summaries(
            db=db_session,
            office_ids=office_ids,
            sort_by="furigana",
            sort_order="asc",
            filters={},
            search_term=None,
            skip=400,
            limit=100
        )
        elapsed_time = time.time() - start_time

        # Assert
        assert elapsed_time < 0.5, \
            f"ページネーションが500msを超えました: {elapsed_time:.3f}s (OFFSET=400)"

        # デバッグ情報を出力
        print(f"\nページネーション時間（OFFSET=400）: {elapsed_time:.3f}s")


class TestDashboardConcurrency:
    """同時実行負荷テスト"""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_concurrent_requests(self, db_session: AsyncSession):
        """
        Test 4.2.1: 同時10リクエストで安定動作

        要件:
        - 10リクエスト同時実行
        - すべて500ms以内
        - エラーが発生しない

        TDD: Red → Green → Refactor
        """
        # Setup: 50事業所作成
        offices = await create_test_offices(db_session, count=50)
        for office in offices:
            await create_test_recipients(
                db_session,
                office_id=office.id,
                count=100
            )
        await db_session.commit()

        # Execute: 10リクエストを同時実行
        async def single_request(office_id):
            start = time.time()
            results = await crud.dashboard.get_filtered_summaries(
                db=db_session,
                office_ids=[office_id],
                sort_by="furigana",
                sort_order="asc",
                filters={},
                search_term=None,
                skip=0,
                limit=100
            )
            elapsed = time.time() - start
            return (elapsed, len(results))

        # 10リクエストを並列実行
        tasks = [single_request(office.id) for office in offices[:10]]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Assert: すべて成功 & 500ms以内
        assert all(not isinstance(r, Exception) for r in results), \
            f"一部のリクエストでエラーが発生しました: {[r for r in results if isinstance(r, Exception)]}"

        elapsed_times = [r[0] for r in results if not isinstance(r, Exception)]
        max_time = max(elapsed_times) if elapsed_times else 0
        avg_time = sum(elapsed_times) / len(elapsed_times) if elapsed_times else 0

        assert all(t < 0.5 for t in elapsed_times), \
            f"一部のリクエストが500msを超えました: max={max_time:.3f}s"

        # デバッグ情報を出力
        print(f"\n同時10リクエスト:")
        print(f"  最大時間: {max_time:.3f}s")
        print(f"  平均時間: {avg_time:.3f}s")

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_database_connection_pool_not_exhausted(
        self,
        db_session: AsyncSession
    ):
        """
        Test 4.2.2: DBコネクションプールが枯渇しない

        要件:
        - 100リクエスト連続実行
        - 「connection pool exhausted」エラーが発生しない

        TDD: Red → Green → Refactor
        """
        # Setup
        offices = await create_test_offices(db_session, count=1)
        await create_test_recipients(
            db_session,
            office_id=offices[0].id,
            count=100
        )
        await db_session.commit()

        # Execute: 100リクエスト連続実行
        async def single_request():
            results = await crud.dashboard.get_filtered_summaries(
                db=db_session,
                office_ids=[offices[0].id],
                sort_by="furigana",
                sort_order="asc",
                filters={},
                search_term=None,
                skip=0,
                limit=100
            )
            return len(results)

        tasks = [single_request() for _ in range(100)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Assert: すべて成功
        errors = [r for r in results if isinstance(r, Exception)]
        assert len(errors) == 0, \
            f"コネクションプールが枯渇した可能性があります: {errors[:5]}"

        # デバッグ情報を出力
        print(f"\n100リクエスト連続実行: すべて成功")
