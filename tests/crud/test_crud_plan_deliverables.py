"""
TDD: CRUD層のテスト - Plan Deliverables

Test Cases:
1. get_multi_deliverables_with_relations: リレーションを含むPDF一覧を取得
2. count_deliverables_with_filters: フィルター条件での総件数取得
3. フィルター機能: 検索キーワード
4. フィルター機能: 利用者ID
5. フィルター機能: deliverable_type
6. フィルター機能: 日付範囲
7. ソート機能: uploaded_at, recipient_name, file_name
8. ページネーション機能
9. N+1問題の解決確認
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import date, datetime
from uuid import uuid4

from app.crud.crud_support_plan import crud_support_plan_cycle
from app.models.welfare_recipient import WelfareRecipient, OfficeWelfareRecipient
from app.models.support_plan_cycle import SupportPlanCycle, PlanDeliverable
from app.models.office import Office, OfficeStaff
from app.models.staff import Staff
from app.models.enums import GenderType, DeliverableType, OfficeType


@pytest.fixture
async def setup_test_data(db_session: AsyncSession, test_admin_user: Staff):
    """テストデータのセットアップ"""
    # 事業所を作成
    office = Office(
        name="テスト事業所",
        type=OfficeType.type_A_office,
        created_by=test_admin_user.id,
        last_modified_by=test_admin_user.id,
    )
    db_session.add(office)
    await db_session.flush()

    # スタッフと事業所の関連
    db_session.add(OfficeStaff(
        staff_id=test_admin_user.id,
        office_id=office.id,
        is_primary=True
    ))

    # 利用者を3人作成
    recipients = []
    for i in range(3):
        recipient = WelfareRecipient(
            first_name=f"太郎{i+1}",
            last_name=f"山田{i+1}",
            first_name_furigana=f"たろう{i+1}",
            last_name_furigana=f"やまだ{i+1}",
            birth_day=date(1990 + i, 1, 1),
            gender=GenderType.male,
        )
        db_session.add(recipient)
        await db_session.flush()

        # 事業所と利用者の関連
        db_session.add(OfficeWelfareRecipient(
            office_id=office.id,
            welfare_recipient_id=recipient.id
        ))
        recipients.append(recipient)

    await db_session.flush()

    # サイクルとPDFを作成
    deliverables = []
    for i, recipient in enumerate(recipients):
        cycle = SupportPlanCycle(
            welfare_recipient_id=recipient.id,
            office_id=office.id,
            plan_cycle_start_date=date(2025, 1, 1),
            is_latest_cycle=True,
            cycle_number=1,
        )
        db_session.add(cycle)
        await db_session.flush()

        # 各利用者に2件のPDFを作成
        for j in range(2):
            deliverable = PlanDeliverable(
                plan_cycle_id=cycle.id,
                deliverable_type=DeliverableType.assessment_sheet if j == 0 else DeliverableType.draft_plan_pdf,
                file_path=f"s3://test-bucket/file_{i}_{j}.pdf",
                original_filename=f"file_{i}_{j}.pdf",
                uploaded_by=test_admin_user.id,
                uploaded_at=datetime(2025, 1, 10 + i * 2 + j, 10, 0, 0),
            )
            db_session.add(deliverable)
            deliverables.append(deliverable)

    await db_session.commit()

    return {
        "office": office,
        "recipients": recipients,
        "deliverables": deliverables,
    }


@pytest.mark.asyncio
async def test_get_multi_deliverables_with_relations(
    db_session: AsyncSession,
    test_admin_user: Staff,
    setup_test_data
):
    """
    リレーションを含むPDF一覧を取得できる

    Given: 事業所に6件のPDFが存在
    When: get_multi_deliverables_with_relations を呼び出す
    Then: 全てのPDFがリレーション付きで取得される
    """
    data = setup_test_data
    office = data["office"]

    # CRUD実行
    deliverables = await crud_support_plan_cycle.get_multi_deliverables_with_relations(
        db_session,
        office_id=office.id,
        filters={},
        sort_by="uploaded_at",
        sort_order="desc",
        skip=0,
        limit=20,
    )

    # 検証
    assert len(deliverables) == 6

    # リレーションが正しくロードされているか確認
    first = deliverables[0]
    assert hasattr(first, 'plan_cycle')
    assert hasattr(first.plan_cycle, 'welfare_recipient')
    assert hasattr(first, 'uploaded_by_staff')

    # N+1問題が発生していないことを確認（追加のクエリが発生しない）
    # この時点でリレーションがロード済みのはず
    assert first.plan_cycle.welfare_recipient is not None
    assert first.uploaded_by_staff is not None


@pytest.mark.asyncio
async def test_count_deliverables_with_filters(
    db_session: AsyncSession,
    test_admin_user: Staff,
    setup_test_data
):
    """
    フィルター条件での総件数を取得できる

    Given: 事業所に6件のPDFが存在
    When: count_deliverables_with_filters を呼び出す
    Then: 正しい件数が返される
    """
    data = setup_test_data
    office = data["office"]

    # 全件数
    total = await crud_support_plan_cycle.count_deliverables_with_filters(
        db_session,
        office_id=office.id,
        filters={},
    )
    assert total == 6

    # フィルター適用後の件数
    total_filtered = await crud_support_plan_cycle.count_deliverables_with_filters(
        db_session,
        office_id=office.id,
        filters={"deliverable_types": [DeliverableType.assessment_sheet]},
    )
    assert total_filtered == 3


@pytest.mark.asyncio
async def test_filter_by_search_keyword(
    db_session: AsyncSession,
    test_admin_user: Staff,
    setup_test_data
):
    """
    検索キーワードでフィルタリングできる

    Given: 複数のPDFが存在
    When: searchパラメータを指定
    Then: ファイル名または利用者名に一致するPDFが返される
    """
    data = setup_test_data
    office = data["office"]

    # ファイル名で検索
    deliverables = await crud_support_plan_cycle.get_multi_deliverables_with_relations(
        db_session,
        office_id=office.id,
        filters={"search": "file_0"},
        sort_by="uploaded_at",
        sort_order="asc",
        skip=0,
        limit=20,
    )
    assert len(deliverables) == 2  # file_0_0.pdf, file_0_1.pdf

    # 利用者名で検索
    deliverables = await crud_support_plan_cycle.get_multi_deliverables_with_relations(
        db_session,
        office_id=office.id,
        filters={"search": "山田1"},
        sort_by="uploaded_at",
        sort_order="asc",
        skip=0,
        limit=20,
    )
    assert len(deliverables) == 2  # 山田1太郎1のPDF 2件


@pytest.mark.asyncio
async def test_filter_by_recipient_ids(
    db_session: AsyncSession,
    test_admin_user: Staff,
    setup_test_data
):
    """
    利用者IDでフィルタリングできる

    Given: 3人の利用者のPDFが存在
    When: 特定の利用者IDを指定
    Then: その利用者のPDFのみが返される
    """
    data = setup_test_data
    office = data["office"]
    recipients = data["recipients"]

    # 1人目の利用者のみ
    deliverables = await crud_support_plan_cycle.get_multi_deliverables_with_relations(
        db_session,
        office_id=office.id,
        filters={"recipient_ids": [recipients[0].id]},
        sort_by="uploaded_at",
        sort_order="asc",
        skip=0,
        limit=20,
    )
    assert len(deliverables) == 2
    assert all(d.plan_cycle.welfare_recipient_id == recipients[0].id for d in deliverables)


@pytest.mark.asyncio
async def test_filter_by_deliverable_types(
    db_session: AsyncSession,
    test_admin_user: Staff,
    setup_test_data
):
    """
    deliverable_typeでフィルタリングできる

    Given: 異なるタイプのPDFが存在
    When: 特定のdeliverable_typeを指定
    Then: そのタイプのPDFのみが返される
    """
    data = setup_test_data
    office = data["office"]

    # アセスメントシートのみ
    deliverables = await crud_support_plan_cycle.get_multi_deliverables_with_relations(
        db_session,
        office_id=office.id,
        filters={"deliverable_types": [DeliverableType.assessment_sheet]},
        sort_by="uploaded_at",
        sort_order="asc",
        skip=0,
        limit=20,
    )
    assert len(deliverables) == 3
    assert all(d.deliverable_type == DeliverableType.assessment_sheet for d in deliverables)


@pytest.mark.asyncio
async def test_filter_by_date_range(
    db_session: AsyncSession,
    test_admin_user: Staff,
    setup_test_data
):
    """
    日付範囲でフィルタリングできる

    Given: 異なる日付でアップロードされたPDFが存在
    When: 日付範囲を指定
    Then: その範囲内のPDFのみが返される
    """
    data = setup_test_data
    office = data["office"]

    # 1月10日から1月12日までのPDF
    deliverables = await crud_support_plan_cycle.get_multi_deliverables_with_relations(
        db_session,
        office_id=office.id,
        filters={
            "date_from": datetime(2025, 1, 10),
            "date_to": datetime(2025, 1, 12, 23, 59, 59),
        },
        sort_by="uploaded_at",
        sort_order="asc",
        skip=0,
        limit=20,
    )
    assert len(deliverables) == 3  # 1/10, 1/11, 1/12にアップロードされたもの


@pytest.mark.asyncio
async def test_sort_by_uploaded_at(
    db_session: AsyncSession,
    test_admin_user: Staff,
    setup_test_data
):
    """
    uploaded_atでソートできる

    Given: 複数のPDFが存在
    When: sort_by="uploaded_at"を指定
    Then: アップロード日時順にソートされる
    """
    data = setup_test_data
    office = data["office"]

    # 昇順
    deliverables_asc = await crud_support_plan_cycle.get_multi_deliverables_with_relations(
        db_session,
        office_id=office.id,
        filters={},
        sort_by="uploaded_at",
        sort_order="asc",
        skip=0,
        limit=20,
    )
    assert deliverables_asc[0].uploaded_at < deliverables_asc[-1].uploaded_at

    # 降順
    deliverables_desc = await crud_support_plan_cycle.get_multi_deliverables_with_relations(
        db_session,
        office_id=office.id,
        filters={},
        sort_by="uploaded_at",
        sort_order="desc",
        skip=0,
        limit=20,
    )
    assert deliverables_desc[0].uploaded_at > deliverables_desc[-1].uploaded_at


@pytest.mark.asyncio
async def test_sort_by_recipient_name(
    db_session: AsyncSession,
    test_admin_user: Staff,
    setup_test_data
):
    """
    利用者名でソートできる

    Given: 複数の利用者のPDFが存在
    When: sort_by="recipient_name"を指定
    Then: 利用者名順（フリガナ）にソートされる
    """
    data = setup_test_data
    office = data["office"]

    deliverables = await crud_support_plan_cycle.get_multi_deliverables_with_relations(
        db_session,
        office_id=office.id,
        filters={},
        sort_by="recipient_name",
        sort_order="asc",
        skip=0,
        limit=20,
    )

    # フリガナ順にソートされているか確認
    for i in range(len(deliverables) - 1):
        current_furigana = (
            deliverables[i].plan_cycle.welfare_recipient.last_name_furigana +
            deliverables[i].plan_cycle.welfare_recipient.first_name_furigana
        )
        next_furigana = (
            deliverables[i+1].plan_cycle.welfare_recipient.last_name_furigana +
            deliverables[i+1].plan_cycle.welfare_recipient.first_name_furigana
        )
        assert current_furigana <= next_furigana


@pytest.mark.asyncio
async def test_sort_by_file_name(
    db_session: AsyncSession,
    test_admin_user: Staff,
    setup_test_data
):
    """
    ファイル名でソートできる

    Given: 複数のPDFが存在
    When: sort_by="file_name"を指定
    Then: ファイル名順にソートされる
    """
    data = setup_test_data
    office = data["office"]

    deliverables = await crud_support_plan_cycle.get_multi_deliverables_with_relations(
        db_session,
        office_id=office.id,
        filters={},
        sort_by="file_name",
        sort_order="asc",
        skip=0,
        limit=20,
    )

    # ファイル名順にソートされているか確認
    for i in range(len(deliverables) - 1):
        assert deliverables[i].original_filename <= deliverables[i+1].original_filename


@pytest.mark.asyncio
async def test_pagination(
    db_session: AsyncSession,
    test_admin_user: Staff,
    setup_test_data
):
    """
    ページネーションが機能する

    Given: 6件のPDFが存在
    When: skip, limitを指定
    Then: 指定された範囲のPDFが返される
    """
    data = setup_test_data
    office = data["office"]

    # 1ページ目（0-2件目）
    page1 = await crud_support_plan_cycle.get_multi_deliverables_with_relations(
        db_session,
        office_id=office.id,
        filters={},
        sort_by="uploaded_at",
        sort_order="asc",
        skip=0,
        limit=2,
    )
    assert len(page1) == 2

    # 2ページ目（3-4件目）
    page2 = await crud_support_plan_cycle.get_multi_deliverables_with_relations(
        db_session,
        office_id=office.id,
        filters={},
        sort_by="uploaded_at",
        sort_order="asc",
        skip=2,
        limit=2,
    )
    assert len(page2) == 2

    # 重複がないことを確認
    page1_ids = {d.id for d in page1}
    page2_ids = {d.id for d in page2}
    assert page1_ids.isdisjoint(page2_ids)
