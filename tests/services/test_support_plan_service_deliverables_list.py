"""
TDD: サービス層のテスト - get_deliverables_list

Test Cases:
1. 正常系: PDF一覧を取得し、正しくレスポンスが整形される
2. 正常系: フィルター条件が正しくCRUD層に渡される
3. 正常系: ページネーション情報が正確に計算される
4. 異常系: S3 presigned URL生成エラー時のハンドリング
5. 正常系: レスポンスデータの構造が正しい
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from uuid import UUID, uuid4
from datetime import datetime, date
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.support_plan_service import support_plan_service
from app.models.enums import DeliverableType, StaffRole
from app.models.support_plan_cycle import PlanDeliverable
from app.models.welfare_recipient import WelfareRecipient
from app.models.support_plan_cycle import SupportPlanCycle
from app.models.staff import Staff


pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_db_session():
    """モックDBセッション"""
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def mock_current_user():
    """モックカレントユーザー"""
    user = Mock(spec=Staff)
    user.id = uuid4()
    user.full_name = "テストユーザー"
    user.role = StaffRole.owner
    return user


@pytest.fixture
def sample_deliverables_data():
    """サンプルのdeliverableデータ"""
    office_id = uuid4()
    staff_id = uuid4()
    recipient_id = uuid4()
    cycle_id = 1  # SupportPlanCycle.idはint型

    # モックWelfareRecipient
    mock_recipient = Mock(spec=WelfareRecipient)
    mock_recipient.id = recipient_id
    mock_recipient.full_name = "山田 太郎"
    mock_recipient.full_name_furigana = "やまだ たろう"

    # モックSupportPlanCycle
    mock_cycle = Mock(spec=SupportPlanCycle)
    mock_cycle.id = cycle_id
    mock_cycle.cycle_number = 1
    mock_cycle.plan_cycle_start_date = date(2025, 1, 1)
    mock_cycle.next_renewal_deadline = date(2025, 7, 1)
    mock_cycle.is_latest_cycle = True
    mock_cycle.welfare_recipient = mock_recipient

    # モックStaff
    mock_staff = Mock(spec=Staff)
    mock_staff.id = staff_id
    mock_staff.full_name = "アップロード者"
    mock_staff.role = StaffRole.employee

    # モックPlanDeliverable
    deliverable1 = Mock(spec=PlanDeliverable)
    deliverable1.id = 1
    deliverable1.original_filename = "アセスメント.pdf"
    deliverable1.file_path = "s3://test-bucket/assessment.pdf"
    deliverable1.deliverable_type = DeliverableType.assessment_sheet
    deliverable1.plan_cycle = mock_cycle
    deliverable1.uploaded_by_staff = mock_staff
    deliverable1.uploaded_at = datetime(2025, 1, 10, 10, 0, 0)

    deliverable2 = Mock(spec=PlanDeliverable)
    deliverable2.id = 2
    deliverable2.original_filename = "計画書.pdf"
    deliverable2.file_path = "s3://test-bucket/plan.pdf"
    deliverable2.deliverable_type = DeliverableType.draft_plan_pdf
    deliverable2.plan_cycle = mock_cycle
    deliverable2.uploaded_by_staff = mock_staff
    deliverable2.uploaded_at = datetime(2025, 1, 15, 10, 0, 0)

    return [deliverable1, deliverable2], office_id


class TestGetDeliverablesList:
    """get_deliverables_list メソッドのテスト"""

    async def test_get_deliverables_list_success(
        self,
        mock_db_session,
        mock_current_user,
        sample_deliverables_data
    ):
        """
        正常系: PDF一覧を取得し、正しくレスポンスが整形される

        Given: 2件のPDFデータが存在
        When: get_deliverables_listを呼び出す
        Then: 正しく整形されたレスポンスが返される
        """
        deliverables, office_id = sample_deliverables_data

        # CRUD層のモック
        with patch('app.services.support_plan_service.crud.support_plan.get_multi_deliverables_with_relations') as mock_get_multi:
            with patch('app.services.support_plan_service.crud.support_plan.count_deliverables_with_filters') as mock_count:
                with patch('app.core.storage.create_presigned_url') as mock_presigned:
                    # モックの戻り値を設定
                    mock_get_multi.return_value = deliverables
                    mock_count.return_value = 2
                    mock_presigned.return_value = "https://s3.amazonaws.com/test-bucket/signed-url"

                    # テスト実行
                    result = await support_plan_service.get_deliverables_list(
                        db=mock_db_session,
                        current_user=mock_current_user,
                        office_id=office_id,
                        search=None,
                        recipient_ids=None,
                        deliverable_types=None,
                        date_from=None,
                        date_to=None,
                        sort_by="uploaded_at",
                        sort_order="desc",
                        skip=0,
                        limit=20
                    )

                    # 検証
                    assert result.total == 2
                    assert len(result.items) == 2
                    assert result.skip == 0
                    assert result.limit == 20
                    assert result.has_more is False

                    # 1件目のデータ検証
                    item1 = result.items[0]
                    assert item1.id == 1
                    assert item1.original_filename == "アセスメント.pdf"
                    assert item1.deliverable_type == DeliverableType.assessment_sheet
                    assert item1.deliverable_type_display == "アセスメントシート"
                    assert item1.welfare_recipient.full_name == "山田 太郎"
                    assert item1.plan_cycle.cycle_number == 1
                    assert item1.uploaded_by.name == "アップロード者"
                    assert item1.download_url == "https://s3.amazonaws.com/test-bucket/signed-url"

                    # CRUD層が正しく呼ばれたか確認
                    mock_get_multi.assert_called_once()
                    mock_count.assert_called_once()

    async def test_get_deliverables_list_with_filters(
        self,
        mock_db_session,
        mock_current_user,
        sample_deliverables_data
    ):
        """
        正常系: フィルター条件が正しくCRUD層に渡される

        Given: フィルター条件を指定
        When: get_deliverables_listを呼び出す
        Then: フィルター条件が正しくCRUD層に渡される
        """
        deliverables, office_id = sample_deliverables_data
        recipient_id = uuid4()
        date_from = datetime(2025, 1, 1, 0, 0, 0)
        date_to = datetime(2025, 1, 31, 23, 59, 59)

        with patch('app.services.support_plan_service.crud.support_plan.get_multi_deliverables_with_relations') as mock_get_multi:
            with patch('app.services.support_plan_service.crud.support_plan.count_deliverables_with_filters') as mock_count:
                with patch('app.core.storage.create_presigned_url') as mock_presigned:
                    mock_get_multi.return_value = deliverables
                    mock_count.return_value = 2
                    mock_presigned.return_value = "https://signed-url"

                    # フィルター条件付きで実行
                    await support_plan_service.get_deliverables_list(
                        db=mock_db_session,
                        current_user=mock_current_user,
                        office_id=office_id,
                        search="テスト",
                        recipient_ids=[recipient_id],
                        deliverable_types=[DeliverableType.assessment_sheet],
                        date_from=date_from,
                        date_to=date_to,
                        sort_by="recipient_name",
                        sort_order="asc",
                        skip=0,
                        limit=10
                    )

                    # CRUD層の呼び出しを検証
                    call_args = mock_get_multi.call_args
                    assert call_args is not None

                    # フィルター条件が正しく渡されているか確認
                    filters = call_args.kwargs['filters']
                    assert filters['search'] == "テスト"
                    assert filters['recipient_ids'] == [recipient_id]
                    assert filters['deliverable_types'] == [DeliverableType.assessment_sheet]
                    assert filters['date_from'] == date_from
                    assert filters['date_to'] == date_to

                    # ソート条件が正しく渡されているか確認
                    assert call_args.kwargs['sort_by'] == "recipient_name"
                    assert call_args.kwargs['sort_order'] == "asc"
                    assert call_args.kwargs['skip'] == 0
                    assert call_args.kwargs['limit'] == 10

    async def test_pagination_has_more_calculation(
        self,
        mock_db_session,
        mock_current_user,
        sample_deliverables_data
    ):
        """
        正常系: ページネーション情報が正確に計算される

        Given: 合計100件のデータが存在し、20件ずつ取得
        When: 各ページでget_deliverables_listを呼び出す
        Then: has_moreが正しく計算される
        """
        deliverables, office_id = sample_deliverables_data

        with patch('app.services.support_plan_service.crud.support_plan.get_multi_deliverables_with_relations') as mock_get_multi:
            with patch('app.services.support_plan_service.crud.support_plan.count_deliverables_with_filters') as mock_count:
                with patch('app.core.storage.create_presigned_url') as mock_presigned:
                    mock_get_multi.return_value = deliverables
                    mock_count.return_value = 100  # 合計100件
                    mock_presigned.return_value = "https://signed-url"

                    # 1ページ目（0-19）: has_more = True
                    result1 = await support_plan_service.get_deliverables_list(
                        db=mock_db_session,
                        current_user=mock_current_user,
                        office_id=office_id,
                        skip=0,
                        limit=20
                    )
                    assert result1.has_more is True

                    # 4ページ目（60-79）: has_more = True
                    result2 = await support_plan_service.get_deliverables_list(
                        db=mock_db_session,
                        current_user=mock_current_user,
                        office_id=office_id,
                        skip=60,
                        limit=20
                    )
                    assert result2.has_more is True

                    # 5ページ目（80-99）: has_more = False
                    result3 = await support_plan_service.get_deliverables_list(
                        db=mock_db_session,
                        current_user=mock_current_user,
                        office_id=office_id,
                        skip=80,
                        limit=20
                    )
                    assert result3.has_more is False

    async def test_s3_presigned_url_error_handling(
        self,
        mock_db_session,
        mock_current_user,
        sample_deliverables_data
    ):
        """
        異常系: S3 presigned URL生成エラー時のハンドリング

        Given: S3 URL生成でエラーが発生
        When: get_deliverables_listを呼び出す
        Then: download_urlがNoneになり、処理は続行される
        """
        deliverables, office_id = sample_deliverables_data

        with patch('app.services.support_plan_service.crud.support_plan.get_multi_deliverables_with_relations') as mock_get_multi:
            with patch('app.services.support_plan_service.crud.support_plan.count_deliverables_with_filters') as mock_count:
                with patch('app.core.storage.create_presigned_url') as mock_presigned:
                    mock_get_multi.return_value = deliverables
                    mock_count.return_value = 2
                    # S3エラーをシミュレート
                    mock_presigned.side_effect = Exception("S3 connection error")

                    # テスト実行
                    result = await support_plan_service.get_deliverables_list(
                        db=mock_db_session,
                        current_user=mock_current_user,
                        office_id=office_id,
                        skip=0,
                        limit=20
                    )

                    # エラーが発生してもレスポンスは返される
                    assert result.total == 2
                    assert len(result.items) == 2

                    # download_urlがNoneになっている
                    assert result.items[0].download_url is None
                    assert result.items[1].download_url is None

    async def test_deliverable_type_display_mapping(
        self,
        mock_db_session,
        mock_current_user
    ):
        """
        正常系: deliverable_type_displayが正しくマッピングされる

        Given: 各種deliverable_typeのPDFが存在
        When: get_deliverables_listを呼び出す
        Then: 日本語の表示名が正しく設定される
        """
        office_id = uuid4()

        # 各種タイプのdeliverableを作成
        deliverable_types_mapping = [
            (DeliverableType.assessment_sheet, "アセスメントシート"),
            (DeliverableType.draft_plan_pdf, "計画書（原案）"),
            (DeliverableType.final_plan_signed_pdf, "計画書（署名済）"),
            (DeliverableType.staff_meeting_minutes, "担当者会議議事録"),
            (DeliverableType.monitoring_report_pdf, "モニタリング報告書"),
        ]

        for deliverable_type, expected_display in deliverable_types_mapping:
            # モックデータ作成
            mock_recipient = Mock(spec=WelfareRecipient)
            mock_recipient.id = uuid4()
            mock_recipient.full_name = "テスト 太郎"
            mock_recipient.full_name_furigana = "てすと たろう"

            mock_cycle = Mock(spec=SupportPlanCycle)
            mock_cycle.id = 1  # SupportPlanCycle.idはint型
            mock_cycle.cycle_number = 1
            mock_cycle.plan_cycle_start_date = date(2025, 1, 1)
            mock_cycle.next_renewal_deadline = date(2025, 7, 1)
            mock_cycle.is_latest_cycle = True
            mock_cycle.welfare_recipient = mock_recipient

            mock_staff = Mock(spec=Staff)
            mock_staff.id = uuid4()
            mock_staff.full_name = "スタッフ"
            mock_staff.role = StaffRole.employee

            deliverable = Mock(spec=PlanDeliverable)
            deliverable.id = 1
            deliverable.original_filename = f"{expected_display}.pdf"
            deliverable.file_path = "s3://test-bucket/file.pdf"
            deliverable.deliverable_type = deliverable_type
            deliverable.plan_cycle = mock_cycle
            deliverable.uploaded_by_staff = mock_staff
            deliverable.uploaded_at = datetime(2025, 1, 10, 10, 0, 0)

            with patch('app.services.support_plan_service.crud.support_plan.get_multi_deliverables_with_relations') as mock_get_multi:
                with patch('app.services.support_plan_service.crud.support_plan.count_deliverables_with_filters') as mock_count:
                    with patch('app.core.storage.create_presigned_url') as mock_presigned:
                        mock_get_multi.return_value = [deliverable]
                        mock_count.return_value = 1
                        mock_presigned.return_value = "https://signed-url"

                        # テスト実行
                        result = await support_plan_service.get_deliverables_list(
                            db=mock_db_session,
                            current_user=mock_current_user,
                            office_id=office_id,
                            skip=0,
                            limit=20
                        )

                        # deliverable_type_displayの検証
                        assert result.items[0].deliverable_type_display == expected_display
