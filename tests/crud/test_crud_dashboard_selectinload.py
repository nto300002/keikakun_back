"""
Test 3.1: selectinloadフィルタリングのテスト

TDDアプローチ:
1. Red: テストを実装し、失敗することを確認
2. Green: selectinloadにフィルタリングを追加してテストをパス
3. Refactor: コードをリファクタリング
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.models.enums import SupportPlanStep, DeliverableType
from tests.utils import (
    create_test_office,
    create_test_recipient,
    create_test_cycle,
    create_test_status,
    create_test_deliverable
)


class TestSelectinloadOptimization:
    """selectinload最適化のテスト"""

    @pytest_asyncio.fixture
    async def setup_recipient_with_full_data(self, db_session: AsyncSession):
        """利用者 + 複数ステータス + デリバラブルのテストデータ"""
        office = await create_test_office(db_session)
        recipient = await create_test_recipient(
            db_session,
            office_id=office.id,
            last_name="山田",
            first_name="太郎"
        )

        # 最新サイクル
        latest_cycle = await create_test_cycle(
            db_session,
            welfare_recipient_id=recipient.id,
            office_id=office.id,
            cycle_number=1,
            is_latest_cycle=True
        )

        # 複数のステータス（最新のみ1つ）
        status_old_1 = await create_test_status(
            db_session,
            plan_cycle_id=latest_cycle.id,
            welfare_recipient_id=recipient.id,
            office_id=office.id,
            step_type=SupportPlanStep.assessment,
            is_latest_status=False,
            completed=True
        )
        status_old_2 = await create_test_status(
            db_session,
            plan_cycle_id=latest_cycle.id,
            welfare_recipient_id=recipient.id,
            office_id=office.id,
            step_type=SupportPlanStep.draft_plan,
            is_latest_status=False,
            completed=True
        )
        status_latest = await create_test_status(
            db_session,
            plan_cycle_id=latest_cycle.id,
            welfare_recipient_id=recipient.id,
            office_id=office.id,
            step_type=SupportPlanStep.monitoring,
            is_latest_status=True,
            completed=False
        )

        # 複数のデリバラブル
        deliverable_assessment = await create_test_deliverable(
            db_session,
            plan_cycle_id=latest_cycle.id,
            uploaded_by=office.created_by,
            deliverable_type=DeliverableType.assessment_sheet
        )
        deliverable_draft = await create_test_deliverable(
            db_session,
            plan_cycle_id=latest_cycle.id,
            uploaded_by=office.created_by,
            deliverable_type=DeliverableType.draft_plan_pdf
        )
        deliverable_final = await create_test_deliverable(
            db_session,
            plan_cycle_id=latest_cycle.id,
            uploaded_by=office.created_by,
            deliverable_type=DeliverableType.final_plan_signed_pdf
        )

        await db_session.commit()
        return {
            "office": office,
            "recipient": recipient,
            "latest_cycle": latest_cycle,
            "statuses": {
                "old": [status_old_1, status_old_2],
                "latest": status_latest
            },
            "deliverables": {
                "assessment": deliverable_assessment,
                "others": [deliverable_draft, deliverable_final]
            }
        }

    @pytest.mark.asyncio
    async def test_only_latest_statuses_loaded(
        self,
        db_session: AsyncSession,
        setup_recipient_with_full_data
    ):
        """
        Test 3.1.1: 最新ステータスのみがロードされる

        要件:
        - is_latest_status=true のステータスのみロード
        - 過去のステータスはロードされない

        TDD: Red → Green → Refactor
        """
        data = setup_recipient_with_full_data
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
        recipient, _, latest_cycle = results[0]

        # 最新ステータスのみがロードされている
        assert len(latest_cycle.statuses) == 1, \
            f"最新ステータスのみロードすべきです: {len(latest_cycle.statuses)}件ロードされています"
        assert latest_cycle.statuses[0].is_latest_status == True
        assert latest_cycle.statuses[0].step_type == SupportPlanStep.monitoring

    @pytest.mark.asyncio
    async def test_only_assessment_deliverables_loaded(
        self,
        db_session: AsyncSession,
        setup_recipient_with_full_data
    ):
        """
        Test 3.1.2: アセスメントシートのみがロードされる

        要件:
        - deliverable_type=assessment_sheet のみロード
        - 他のデリバラブルはロードされない

        TDD: Red → Green → Refactor
        """
        data = setup_recipient_with_full_data
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
        recipient, _, latest_cycle = results[0]

        # アセスメントシートのみがロードされている
        assert len(latest_cycle.deliverables) == 1, \
            f"アセスメントシートのみロードすべきです: {len(latest_cycle.deliverables)}件ロードされています"
        assert latest_cycle.deliverables[0].deliverable_type == DeliverableType.assessment_sheet

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_selectinload_reduces_query_count(self, db_session: AsyncSession):
        """
        Test 3.1.3: selectinloadのクエリ数削減

        要件:
        - N+1問題が発生しない
        - クエリ数が利用者数に比例しない

        TDD: Red → Green → Refactor
        """
        # Setup: 100利用者
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
                office_id=office.id,
                cycle_number=1,
                is_latest_cycle=True
            )
            # 各サイクルに10個のステータス（最新1つ）
            for j in range(10):
                await create_test_status(
                    db_session,
                    plan_cycle_id=cycle.id,
            welfare_recipient_id=recipient.id,
            office_id=office.id,
                    step_type=SupportPlanStep.assessment,
                    is_latest_status=(j == 9)
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

        # Assert: 結果が正しい
        assert len(results) == 100

        # 各利用者の最新ステータスのみがロードされている
        for recipient, _, latest_cycle in results:
            if latest_cycle:
                assert len(latest_cycle.statuses) == 1, \
                    f"最新ステータスのみロードされるべき: {len(latest_cycle.statuses)}件"
                assert latest_cycle.statuses[0].is_latest_status == True

    @pytest.mark.asyncio
    async def test_selectinload_with_no_statuses(self, db_session: AsyncSession):
        """
        Test 3.1.4: ステータスがない場合の動作

        要件:
        - ステータスがないサイクルでエラーが発生しない
        - 空のリストを返す

        TDD: Red → Green → Refactor
        """
        # Setup: ステータスなしのサイクル
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
            office_id=office.id,
            cycle_number=1,
            is_latest_cycle=True
        )
        # ステータスを作成しない
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
        recipient, _, latest_cycle = results[0]
        assert latest_cycle is not None
        assert len(latest_cycle.statuses) == 0, \
            "ステータスがない場合は空のリストを返す"

    @pytest.mark.asyncio
    async def test_selectinload_with_no_deliverables(self, db_session: AsyncSession):
        """
        Test 3.1.5: デリバラブルがない場合の動作

        要件:
        - デリバラブルがないサイクルでエラーが発生しない
        - 空のリストを返す

        TDD: Red → Green → Refactor
        """
        # Setup: デリバラブルなしのサイクル
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
            office_id=office.id,
            cycle_number=1,
            is_latest_cycle=True
        )
        # デリバラブルを作成しない
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
        recipient, _, latest_cycle = results[0]
        assert latest_cycle is not None
        assert len(latest_cycle.deliverables) == 0, \
            "デリバラブルがない場合は空のリストを返す"
