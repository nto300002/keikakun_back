"""
TDD: PDF一覧取得エンドポイントのテスト

Test Cases:
1. 正常系: PDF一覧を取得できる
2. 正常系: 検索キーワードでフィルタリングできる
3. 正常系: 利用者IDでフィルタリングできる
4. 正常系: deliverable_typeでフィルタリングできる
5. 正常系: ページネーションが機能する
6. 正常系: ソート機能が動作する
7. エラー系: 事業所へのアクセス権がない
8. エラー系: 認証なしでアクセスできない
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date, datetime
from uuid import uuid4

from app.models.welfare_recipient import WelfareRecipient, OfficeWelfareRecipient
from app.models.support_plan_cycle import SupportPlanCycle, SupportPlanStatus, PlanDeliverable
from app.models.office import Office, OfficeStaff
from app.models.staff import Staff
from app.models.enums import GenderType, SupportPlanStep, DeliverableType


@pytest.mark.asyncio
async def test_get_plan_deliverables_list_success(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_admin_user: Staff,
    office_factory
):
    """
    正常系: PDF一覧を取得できる

    Given: 事業所に3件のPDFがアップロード済み
    When: GET /api/v1/support-plans/plan-deliverables を呼び出す
    Then: 3件のPDFリストが返される
    """
    # 1. テストデータの準備
    office = await office_factory(creator=test_admin_user)
    db_session.add(OfficeStaff(staff_id=test_admin_user.id, office_id=office.id, is_primary=True))
    await db_session.flush()

    # 利用者を作成
    recipient = WelfareRecipient(
        first_name="太郎",
        last_name="山田",
        first_name_furigana="たろう",
        last_name_furigana="やまだ",
        birth_day=date(1990, 1, 1),
        gender=GenderType.male,
    )
    db_session.add(recipient)
    await db_session.flush()

    # 事業所と利用者の関連
    association = OfficeWelfareRecipient(office_id=office.id, welfare_recipient_id=recipient.id)
    db_session.add(association)
    await db_session.flush()

    # サイクルを作成
    cycle = SupportPlanCycle(
        welfare_recipient_id=recipient.id,
        office_id=office.id,
        plan_cycle_start_date=date(2025, 1, 1),
        is_latest_cycle=True,
        cycle_number=1,
    )
    db_session.add(cycle)
    await db_session.flush()

    # PDF成果物を3件作成
    deliverables = [
        PlanDeliverable(
            plan_cycle_id=cycle.id,
            deliverable_type=DeliverableType.assessment_sheet,
            file_path=f"s3://test-bucket/assessment_{uuid4()}.pdf",
            original_filename="アセスメント.pdf",
            uploaded_by=test_admin_user.id,
            uploaded_at=datetime(2025, 1, 10, 10, 0, 0),
        ),
        PlanDeliverable(
            plan_cycle_id=cycle.id,
            deliverable_type=DeliverableType.draft_plan_pdf,
            file_path=f"s3://test-bucket/draft_{uuid4()}.pdf",
            original_filename="計画書原案.pdf",
            uploaded_by=test_admin_user.id,
            uploaded_at=datetime(2025, 1, 15, 10, 0, 0),
        ),
        PlanDeliverable(
            plan_cycle_id=cycle.id,
            deliverable_type=DeliverableType.final_plan_signed_pdf,
            file_path=f"s3://test-bucket/final_{uuid4()}.pdf",
            original_filename="署名済み計画書.pdf",
            uploaded_by=test_admin_user.id,
            uploaded_at=datetime(2025, 1, 20, 10, 0, 0),
        ),
    ]
    for d in deliverables:
        db_session.add(d)
    await db_session.commit()

    # 2. APIリクエスト
    response = await async_client.get(
        "/api/v1/support-plans/plan-deliverables",
        params={"office_id": str(office.id)},
    )

    # 3. レスポンス検証
    assert response.status_code == 200
    data = response.json()

    assert "items" in data
    assert "total" in data
    assert "skip" in data
    assert "limit" in data
    assert "has_more" in data

    assert data["total"] == 3
    assert len(data["items"]) == 3
    assert data["skip"] == 0
    assert data["limit"] == 20
    assert data["has_more"] is False

    # アイテムの詳細検証（最新のものが最初に来る: uploaded_at desc）
    first_item = data["items"][0]
    assert first_item["original_filename"] == "署名済み計画書.pdf"
    assert first_item["deliverable_type"] == "final_plan_signed_pdf"
    assert "welfare_recipient" in first_item
    assert first_item["welfare_recipient"]["full_name"] == "山田 太郎"
    assert "uploaded_by" in first_item
    assert "uploaded_at" in first_item
    assert "download_url" in first_item


@pytest.mark.asyncio
async def test_get_plan_deliverables_list_with_search(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_admin_user: Staff,
    office_factory
):
    """
    正常系: 検索キーワードでフィルタリングできる

    Given: 事業所に複数のPDFがアップロード済み
    When: searchパラメータを指定してAPIを呼び出す
    Then: 検索条件に一致するPDFのみが返される
    """
    # テストデータの準備
    office = await office_factory(creator=test_admin_user)
    db_session.add(OfficeStaff(staff_id=test_admin_user.id, office_id=office.id, is_primary=True))
    await db_session.flush()

    # 利用者を2人作成
    recipient1 = WelfareRecipient(
        first_name="太郎",
        last_name="山田",
        first_name_furigana="たろう",
        last_name_furigana="やまだ",
        birth_day=date(1990, 1, 1),
        gender=GenderType.male,
    )
    recipient2 = WelfareRecipient(
        first_name="花子",
        last_name="佐藤",
        first_name_furigana="はなこ",
        last_name_furigana="さとう",
        birth_day=date(1992, 3, 15),
        gender=GenderType.female,
    )
    db_session.add_all([recipient1, recipient2])
    await db_session.flush()

    # 事業所との関連
    db_session.add_all([
        OfficeWelfareRecipient(office_id=office.id, welfare_recipient_id=recipient1.id),
        OfficeWelfareRecipient(office_id=office.id, welfare_recipient_id=recipient2.id),
    ])
    await db_session.flush()

    # サイクルを作成
    cycle1 = SupportPlanCycle(
        welfare_recipient_id=recipient1.id,
        office_id=office.id,
        plan_cycle_start_date=date(2025, 1, 1),
        is_latest_cycle=True,
        cycle_number=1,
    )
    cycle2 = SupportPlanCycle(
        welfare_recipient_id=recipient2.id,
        office_id=office.id,
        plan_cycle_start_date=date(2025, 1, 1),
        is_latest_cycle=True,
        cycle_number=1,
    )
    db_session.add_all([cycle1, cycle2])
    await db_session.flush()

    # PDFを作成（recipient1: 山田太郎）
    db_session.add(PlanDeliverable(
        plan_cycle_id=cycle1.id,
        deliverable_type=DeliverableType.assessment_sheet,
        file_path=f"s3://test-bucket/yamada_assessment.pdf",
        original_filename="山田太郎_アセスメント.pdf",
        uploaded_by=test_admin_user.id,
        uploaded_at=datetime(2025, 1, 10, 10, 0, 0),
    ))

    # PDFを作成（recipient2: 佐藤花子）
    db_session.add(PlanDeliverable(
        plan_cycle_id=cycle2.id,
        deliverable_type=DeliverableType.assessment_sheet,
        file_path=f"s3://test-bucket/sato_assessment.pdf",
        original_filename="佐藤花子_アセスメント.pdf",
        uploaded_by=test_admin_user.id,
        uploaded_at=datetime(2025, 1, 10, 10, 0, 0),
    ))
    await db_session.commit()

    # APIリクエスト（"山田"で検索）
    response = await async_client.get(
        "/api/v1/support-plans/plan-deliverables",
        params={
            "office_id": str(office.id),
            "search": "山田",
        },
    )

    # レスポンス検証
    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert "山田" in data["items"][0]["original_filename"] or \
           data["items"][0]["welfare_recipient"]["full_name"] == "山田 太郎"


@pytest.mark.asyncio
async def test_get_plan_deliverables_list_with_recipient_filter(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_admin_user: Staff,
    office_factory
):
    """
    正常系: 利用者IDでフィルタリングできる

    Given: 複数の利用者のPDFがアップロード済み
    When: recipient_idsパラメータを指定してAPIを呼び出す
    Then: 指定した利用者のPDFのみが返される
    """
    # テストデータの準備
    office = await office_factory(creator=test_admin_user)
    db_session.add(OfficeStaff(staff_id=test_admin_user.id, office_id=office.id, is_primary=True))
    await db_session.flush()

    # 利用者を2人作成
    recipient1 = WelfareRecipient(
        first_name="太郎",
        last_name="山田",
        first_name_furigana="たろう",
        last_name_furigana="やまだ",
        birth_day=date(1990, 1, 1),
        gender=GenderType.male,
    )
    recipient2 = WelfareRecipient(
        first_name="花子",
        last_name="佐藤",
        first_name_furigana="はなこ",
        last_name_furigana="さとう",
        birth_day=date(1992, 3, 15),
        gender=GenderType.female,
    )
    db_session.add_all([recipient1, recipient2])
    await db_session.flush()

    # 事業所との関連
    db_session.add_all([
        OfficeWelfareRecipient(office_id=office.id, welfare_recipient_id=recipient1.id),
        OfficeWelfareRecipient(office_id=office.id, welfare_recipient_id=recipient2.id),
    ])
    await db_session.flush()

    # サイクルとPDFを作成
    cycle1 = SupportPlanCycle(
        welfare_recipient_id=recipient1.id,
        office_id=office.id,
        plan_cycle_start_date=date(2025, 1, 1),
        is_latest_cycle=True,
        cycle_number=1,
    )
    cycle2 = SupportPlanCycle(
        welfare_recipient_id=recipient2.id,
        office_id=office.id,
        plan_cycle_start_date=date(2025, 1, 1),
        is_latest_cycle=True,
        cycle_number=1,
    )
    db_session.add_all([cycle1, cycle2])
    await db_session.flush()

    # recipient1のPDFを2件
    db_session.add_all([
        PlanDeliverable(
            plan_cycle_id=cycle1.id,
            deliverable_type=DeliverableType.assessment_sheet,
            file_path=f"s3://test-bucket/file1.pdf",
            original_filename="file1.pdf",
            uploaded_by=test_admin_user.id,
            uploaded_at=datetime(2025, 1, 10),
        ),
        PlanDeliverable(
            plan_cycle_id=cycle1.id,
            deliverable_type=DeliverableType.draft_plan_pdf,
            file_path=f"s3://test-bucket/file2.pdf",
            original_filename="file2.pdf",
            uploaded_by=test_admin_user.id,
            uploaded_at=datetime(2025, 1, 15),
        ),
    ])

    # recipient2のPDFを1件
    db_session.add(PlanDeliverable(
        plan_cycle_id=cycle2.id,
        deliverable_type=DeliverableType.assessment_sheet,
        file_path=f"s3://test-bucket/file3.pdf",
        original_filename="file3.pdf",
        uploaded_by=test_admin_user.id,
        uploaded_at=datetime(2025, 1, 10),
    ))
    await db_session.commit()

    # APIリクエスト（recipient1のみ取得）
    response = await async_client.get(
        "/api/v1/support-plans/plan-deliverables",
        params={
            "office_id": str(office.id),
            "recipient_ids": str(recipient1.id),
        },
    )

    # レスポンス検証
    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 2
    assert len(data["items"]) == 2
    for item in data["items"]:
        assert item["welfare_recipient"]["id"] == str(recipient1.id)


@pytest.mark.asyncio
async def test_get_plan_deliverables_list_pagination(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_admin_user: Staff,
    office_factory
):
    """
    正常系: ページネーションが機能する

    Given: 事業所に25件のPDFがアップロード済み
    When: limit=10, skip=10でAPIを呼び出す
    Then: 11件目から20件目のPDFが返される
    """
    # テストデータの準備
    office = await office_factory(creator=test_admin_user)
    db_session.add(OfficeStaff(staff_id=test_admin_user.id, office_id=office.id, is_primary=True))
    await db_session.flush()

    recipient = WelfareRecipient(
        first_name="太郎",
        last_name="テスト",
        first_name_furigana="たろう",
        last_name_furigana="てすと",
        birth_day=date(1990, 1, 1),
        gender=GenderType.male,
    )
    db_session.add(recipient)
    await db_session.flush()

    db_session.add(OfficeWelfareRecipient(office_id=office.id, welfare_recipient_id=recipient.id))
    await db_session.flush()

    cycle = SupportPlanCycle(
        welfare_recipient_id=recipient.id,
        office_id=office.id,
        plan_cycle_start_date=date(2025, 1, 1),
        is_latest_cycle=True,
        cycle_number=1,
    )
    db_session.add(cycle)
    await db_session.flush()

    # 25件のPDFを作成
    for i in range(25):
        db_session.add(PlanDeliverable(
            plan_cycle_id=cycle.id,
            deliverable_type=DeliverableType.assessment_sheet,
            file_path=f"s3://test-bucket/file_{i}.pdf",
            original_filename=f"file_{i:02d}.pdf",
            uploaded_by=test_admin_user.id,
            uploaded_at=datetime(2025, 1, 1, 10, i, 0),
        ))
    await db_session.commit()

    # APIリクエスト（2ページ目を取得）
    response = await async_client.get(
        "/api/v1/support-plans/plan-deliverables",
        params={
            "office_id": str(office.id),
            "skip": 10,
            "limit": 10,
        },
    )

    # レスポンス検証
    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 25
    assert len(data["items"]) == 10
    assert data["skip"] == 10
    assert data["limit"] == 10
    assert data["has_more"] is True


@pytest.mark.asyncio
async def test_get_plan_deliverables_list_forbidden(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_admin_user: Staff,
    office_factory
):
    """
    エラー系: 事業所へのアクセス権がない

    Given: ユーザーが所属していない事業所
    When: その事業所のPDF一覧を取得しようとする
    Then: 403 Forbiddenエラーが返される
    """
    # 別の事業所を作成
    from app.models.enums import OfficeType

    other_office = Office(
        name="別の事業所",
        type=OfficeType.type_B_office,
        created_by=test_admin_user.id,
        last_modified_by=test_admin_user.id,
    )
    db_session.add(other_office)
    await db_session.commit()

    # APIリクエスト（アクセス権のない事業所）
    response = await async_client.get(
        "/api/v1/support-plans/plan-deliverables",
        params={"office_id": str(other_office.id)},
    )

    # レスポンス検証
    assert response.status_code == 403
    assert "権限" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_plan_deliverables_list_unauthorized(
    async_client: AsyncClient,
):
    """
    エラー系: 認証なしでアクセスできない

    Given: 未認証のユーザー
    When: PDF一覧APIにアクセスする
    Then: 401 Unauthorizedエラーが返される
    """
    # 認証ヘッダーなしでリクエスト
    from app.main import app
    from httpx import AsyncClient as BaseAsyncClient, ASGITransport

    async with BaseAsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/v1/support-plans/plan-deliverables",
            params={"office_id": str(uuid4())},
        )

    # レスポンス検証
    assert response.status_code == 401
