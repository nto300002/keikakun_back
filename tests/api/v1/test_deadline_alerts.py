import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date, timedelta
from sqlalchemy import select
from sqlalchemy.orm import selectinload
import uuid

from app.models.welfare_recipient import WelfareRecipient
from app.models.support_plan_cycle import SupportPlanCycle
from app.models.office import Office, OfficeStaff
from app.models.staff import Staff
from app.main import app


@pytest.mark.asyncio
async def test_get_deadline_alerts_basic(
    async_client: AsyncClient,
    db_session: AsyncSession,
    office_factory,
    welfare_recipient_factory,
    test_admin_user: Staff
):
    """
    GET /api/v1/welfare-recipients/deadline-alerts 基本テスト
    30日以内に期限が迫っている利用者を取得できることを確認
    """
    # 1. テストデータの準備
    office = await office_factory(creator=test_admin_user)
    db_session.add(OfficeStaff(staff_id=test_admin_user.id, office_id=office.id, is_primary=True))
    await db_session.flush()

    # 2. 利用者を作成（期限が異なる3人）
    # 利用者A: 残り15日
    recipient_a = await welfare_recipient_factory(office_id=office.id)
    cycle_a = SupportPlanCycle(
        welfare_recipient_id=recipient_a.id,
        office_id=office.id,
        next_renewal_deadline=date.today() + timedelta(days=15),
        is_latest_cycle=True,
        cycle_number=1,
        next_plan_start_date=7
    )
    db_session.add(cycle_a)

    # 利用者B: 残り25日
    recipient_b = await welfare_recipient_factory(office_id=office.id)
    cycle_b = SupportPlanCycle(
        welfare_recipient_id=recipient_b.id,
        office_id=office.id,
        next_renewal_deadline=date.today() + timedelta(days=25),
        is_latest_cycle=True,
        cycle_number=2,
        next_plan_start_date=7
    )
    db_session.add(cycle_b)

    # 利用者C: 残り50日（30日を超えているので対象外）
    recipient_c = await welfare_recipient_factory(office_id=office.id)
    cycle_c = SupportPlanCycle(
        welfare_recipient_id=recipient_c.id,
        office_id=office.id,
        next_renewal_deadline=date.today() + timedelta(days=50),
        is_latest_cycle=True,
        cycle_number=1,
        next_plan_start_date=7
    )
    db_session.add(cycle_c)

    await db_session.commit()

    # 3. 依存性オーバーライド
    from app.api.deps import get_current_user

    async def override_get_current_user_with_relations():
        stmt = select(Staff).where(Staff.id == test_admin_user.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        ).execution_options(populate_existing=True)
        result = await db_session.execute(stmt)
        user = result.scalars().first()
        return user

    app.dependency_overrides[get_current_user] = override_get_current_user_with_relations

    # 4. APIエンドポイントの呼び出し
    response = await async_client.get("/api/v1/welfare-recipients/deadline-alerts")

    # 5. レスポンスの検証
    assert response.status_code == 200
    data = response.json()

    assert "alerts" in data
    assert "total" in data

    # renewal_deadline タイプのアラートのみを抽出
    renewal_alerts = [a for a in data["alerts"] if a.get("alert_type") == "renewal_deadline"]
    assert len(renewal_alerts) == 2, "更新期限アラートはAとBの2件"

    # ソート順: 残り日数が少ない順
    assert renewal_alerts[0]["days_remaining"] == 15  # 利用者A
    assert renewal_alerts[1]["days_remaining"] == 25  # 利用者B

    # フィールドの検証
    assert "id" in renewal_alerts[0]
    assert "full_name" in renewal_alerts[0]
    assert "alert_type" in renewal_alerts[0]
    assert "message" in renewal_alerts[0]
    assert "next_renewal_deadline" in renewal_alerts[0]
    assert "days_remaining" in renewal_alerts[0]
    assert "current_cycle_number" in renewal_alerts[0]

    # クリーンアップ
    del app.dependency_overrides[get_current_user]


@pytest.mark.asyncio
async def test_get_deadline_alerts_with_limit(
    async_client: AsyncClient,
    db_session: AsyncSession,
    office_factory,
    welfare_recipient_factory,
    test_admin_user: Staff
):
    """
    GET /api/v1/welfare-recipients/deadline-alerts?limit=3
    limit パラメータが機能することを確認
    """
    # 1. テストデータの準備
    office = await office_factory(creator=test_admin_user)
    db_session.add(OfficeStaff(staff_id=test_admin_user.id, office_id=office.id, is_primary=True))
    await db_session.flush()

    # 5人の利用者を作成（すべて30日以内）
    for i in range(5):
        recipient = await welfare_recipient_factory(office_id=office.id)
        cycle = SupportPlanCycle(
            welfare_recipient_id=recipient.id,
            office_id=office.id,
            next_renewal_deadline=date.today() + timedelta(days=10 + i * 2),
            is_latest_cycle=True,
            cycle_number=1,
            next_plan_start_date=7
        )
        db_session.add(cycle)

    await db_session.commit()

    # 2. 依存性オーバーライド
    from app.api.deps import get_current_user

    async def override_get_current_user_with_relations():
        stmt = select(Staff).where(Staff.id == test_admin_user.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        ).execution_options(populate_existing=True)
        result = await db_session.execute(stmt)
        user = result.scalars().first()
        return user

    app.dependency_overrides[get_current_user] = override_get_current_user_with_relations

    # 3. APIエンドポイントの呼び出し（limit=3）
    response = await async_client.get("/api/v1/welfare-recipients/deadline-alerts?limit=3")

    # 4. レスポンスの検証
    assert response.status_code == 200
    data = response.json()

    assert len(data["alerts"]) == 3  # limitが効いている
    # 全体数はrenewal_deadline (5人) + assessment_incomplete (5人)
    assert data["total"] >= 5  # 全体数は5人以上（アセスメント未完了含む）

    # クリーンアップ
    del app.dependency_overrides[get_current_user]


@pytest.mark.asyncio
async def test_get_deadline_alerts_with_threshold(
    async_client: AsyncClient,
    db_session: AsyncSession,
    office_factory,
    welfare_recipient_factory,
    test_admin_user: Staff
):
    """
    GET /api/v1/welfare-recipients/deadline-alerts?threshold_days=15
    threshold_days パラメータが機能することを確認
    """
    # 1. テストデータの準備
    office = await office_factory(creator=test_admin_user)
    db_session.add(OfficeStaff(staff_id=test_admin_user.id, office_id=office.id, is_primary=True))
    await db_session.flush()

    # 利用者A: 残り10日
    recipient_a = await welfare_recipient_factory(office_id=office.id)
    cycle_a = SupportPlanCycle(
        welfare_recipient_id=recipient_a.id,
        office_id=office.id,
        next_renewal_deadline=date.today() + timedelta(days=10),
        is_latest_cycle=True,
        cycle_number=1,
        next_plan_start_date=7
    )
    db_session.add(cycle_a)

    # 利用者B: 残り20日（15日を超えているので対象外）
    recipient_b = await welfare_recipient_factory(office_id=office.id)
    cycle_b = SupportPlanCycle(
        welfare_recipient_id=recipient_b.id,
        office_id=office.id,
        next_renewal_deadline=date.today() + timedelta(days=20),
        is_latest_cycle=True,
        cycle_number=1,
        next_plan_start_date=7
    )
    db_session.add(cycle_b)

    await db_session.commit()

    # 2. 依存性オーバーライド
    from app.api.deps import get_current_user

    async def override_get_current_user_with_relations():
        stmt = select(Staff).where(Staff.id == test_admin_user.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        ).execution_options(populate_existing=True)
        result = await db_session.execute(stmt)
        user = result.scalars().first()
        return user

    app.dependency_overrides[get_current_user] = override_get_current_user_with_relations

    # 3. APIエンドポイントの呼び出し（threshold_days=15）
    response = await async_client.get("/api/v1/welfare-recipients/deadline-alerts?threshold_days=15")

    # 4. レスポンスの検証
    assert response.status_code == 200
    data = response.json()

    # renewal_deadline タイプのアラートのみを抽出
    renewal_alerts = [a for a in data["alerts"] if a.get("alert_type") == "renewal_deadline"]
    assert len(renewal_alerts) == 1, "更新期限アラートはAのみ"
    assert renewal_alerts[0]["days_remaining"] == 10

    # クリーンアップ
    del app.dependency_overrides[get_current_user]


@pytest.mark.asyncio
async def test_get_deadline_alerts_empty(
    async_client: AsyncClient,
    db_session: AsyncSession,
    office_factory,
    welfare_recipient_factory,
    test_admin_user: Staff
):
    """
    GET /api/v1/welfare-recipients/deadline-alerts
    期限が近い利用者がいない場合、空のリストを返すことを確認
    """
    from app.models.support_plan_cycle import PlanDeliverable
    from app.models.enums import DeliverableType

    # 1. テストデータの準備
    office = await office_factory(creator=test_admin_user)
    db_session.add(OfficeStaff(staff_id=test_admin_user.id, office_id=office.id, is_primary=True))
    await db_session.flush()

    # 利用者作成（期限が100日後、アセスメントPDF済み）
    recipient = await welfare_recipient_factory(office_id=office.id)
    cycle = SupportPlanCycle(
        welfare_recipient_id=recipient.id,
        office_id=office.id,
        next_renewal_deadline=date.today() + timedelta(days=100),
        is_latest_cycle=True,
        cycle_number=1
    )
    db_session.add(cycle)
    await db_session.flush()

    # アセスメントPDFを追加（アセスメント未完了アラートに含まれないようにする）
    deliverable = PlanDeliverable(
        plan_cycle_id=cycle.id,
        deliverable_type=DeliverableType.assessment_sheet,
        file_path="test-bucket/test_assessment.pdf",
        original_filename="assessment.pdf",
        uploaded_by=test_admin_user.id
    )
    db_session.add(deliverable)
    await db_session.commit()

    # 2. 依存性オーバーライド
    from app.api.deps import get_current_user

    async def override_get_current_user_with_relations():
        stmt = select(Staff).where(Staff.id == test_admin_user.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        ).execution_options(populate_existing=True)
        result = await db_session.execute(stmt)
        user = result.scalars().first()
        return user

    app.dependency_overrides[get_current_user] = override_get_current_user_with_relations

    # 3. APIエンドポイントの呼び出し
    response = await async_client.get("/api/v1/welfare-recipients/deadline-alerts")

    # 4. レスポンスの検証
    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 0
    assert len(data["alerts"]) == 0

    # クリーンアップ
    del app.dependency_overrides[get_current_user]


@pytest.mark.asyncio
async def test_get_deadline_alerts_requires_auth(
    async_client: AsyncClient,
):
    """
    GET /api/v1/welfare-recipients/deadline-alerts
    認証が必要であることを確認
    """
    response = await async_client.get("/api/v1/welfare-recipients/deadline-alerts")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_deadline_alerts_assessment_incomplete(
    async_client: AsyncClient,
    db_session: AsyncSession,
    office_factory,
    welfare_recipient_factory,
    test_admin_user: Staff
):
    """
    GET /api/v1/welfare-recipients/deadline-alerts
    アセスメント未完了の利用者がアラートに含まれることを確認

    条件:
    - is_latest_cycle=true
    - next_plan_start_dateが設定されている
    - アセスメントPDFがアップロードされていない

    期待:
    - アラートリストにアセスメント未完了の利用者が含まれる
    - alert_type="assessment_incomplete"
    - messageに「のアセスメントが完了していません」が含まれる
    """
    # 1. テストデータの準備
    office = await office_factory(creator=test_admin_user)
    db_session.add(OfficeStaff(staff_id=test_admin_user.id, office_id=office.id, is_primary=True))
    await db_session.flush()

    # 2. アセスメント未完了の利用者を作成
    recipient_incomplete = await welfare_recipient_factory(office_id=office.id)
    cycle_incomplete = SupportPlanCycle(
        welfare_recipient_id=recipient_incomplete.id,
        office_id=office.id,
        plan_cycle_start_date=date.today() - timedelta(days=10),
        is_latest_cycle=True,
        cycle_number=1,
        next_plan_start_date=7  # 7日後にアセスメント開始
    )
    db_session.add(cycle_incomplete)
    await db_session.flush()

    # アセスメントPDFはアップロードされていない状態（deliverablesを追加しない）

    await db_session.commit()

    # 3. 依存性オーバーライド
    from app.api.deps import get_current_user

    async def override_get_current_user_with_relations():
        stmt = select(Staff).where(Staff.id == test_admin_user.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        ).execution_options(populate_existing=True)
        result = await db_session.execute(stmt)
        user = result.scalars().first()
        return user

    app.dependency_overrides[get_current_user] = override_get_current_user_with_relations

    # 4. APIエンドポイントの呼び出し
    response = await async_client.get("/api/v1/welfare-recipients/deadline-alerts")

    # 5. レスポンスの検証
    assert response.status_code == 200
    data = response.json()

    assert "alerts" in data
    assert data["total"] >= 1, "アセスメント未完了の利用者が1人以上含まれるべき"

    # アセスメント未完了アラートを検索
    assessment_alerts = [
        alert for alert in data["alerts"]
        if alert.get("alert_type") == "assessment_incomplete"
    ]

    assert len(assessment_alerts) >= 1, "アセスメント未完了アラートが含まれるべき"

    # 最初のアセスメント未完了アラートを検証
    alert = assessment_alerts[0]
    assert "id" in alert
    assert "full_name" in alert
    assert "alert_type" in alert
    assert alert["alert_type"] == "assessment_incomplete"
    assert "message" in alert
    assert "アセスメントが完了していません" in alert["message"], \
        f"メッセージに「アセスメントが完了していません」が含まれるべき。実際: {alert['message']}"

    # クリーンアップ
    del app.dependency_overrides[get_current_user]


@pytest.mark.asyncio
async def test_get_deadline_alerts_cycle_number_1_assessment_incomplete(
    async_client: AsyncClient,
    db_session: AsyncSession,
    office_factory,
    welfare_recipient_factory,
    test_admin_user: Staff
):
    """
    GET /api/v1/welfare-recipients/deadline-alerts
    cycle_number=1のアセスメント未完了アラートが正しく含まれることを確認

    受け入れ要件 (AC2):
    - cycle_number = 1
    - is_latest_cycle = true
    - next_plan_start_date = NULL（または任意の値）
    - アセスメントPDF未アップロード

    期待:
    - アラートリストに含まれる
    - alert_type = "assessment_incomplete"
    - message = "{姓} {名}のアセスメントが完了していません"
    - current_cycle_number = 1
    """
    # 1. テストデータの準備
    office = await office_factory(creator=test_admin_user)
    db_session.add(OfficeStaff(staff_id=test_admin_user.id, office_id=office.id, is_primary=True))
    await db_session.flush()

    # 2. cycle_number=1、next_plan_start_date=NULLの利用者を作成
    recipient = await welfare_recipient_factory(
        office_id=office.id,
        last_name="テスト",
        first_name="太郎"
    )
    cycle = SupportPlanCycle(
        welfare_recipient_id=recipient.id,
        office_id=office.id,
        plan_cycle_start_date=date.today() - timedelta(days=5),
        is_latest_cycle=True,
        cycle_number=1,
        next_plan_start_date=None  # NULL
    )
    db_session.add(cycle)
    await db_session.flush()

    # アセスメントPDFはアップロードされていない状態（deliverablesを追加しない）

    await db_session.commit()

    # 3. 依存性オーバーライド
    from app.api.deps import get_current_user

    async def override_get_current_user_with_relations():
        stmt = select(Staff).where(Staff.id == test_admin_user.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        ).execution_options(populate_existing=True)
        result = await db_session.execute(stmt)
        user = result.scalars().first()
        return user

    app.dependency_overrides[get_current_user] = override_get_current_user_with_relations

    # 4. APIエンドポイントの呼び出し
    response = await async_client.get("/api/v1/welfare-recipients/deadline-alerts")

    # 5. レスポンスの検証
    assert response.status_code == 200
    data = response.json()

    assert "alerts" in data
    assert data["total"] >= 1, "cycle_number=1のアセスメント未完了アラートが含まれるべき"

    # アセスメント未完了アラートを検索
    assessment_alerts = [
        alert for alert in data["alerts"]
        if alert.get("alert_type") == "assessment_incomplete" and alert.get("current_cycle_number") == 1
    ]

    assert len(assessment_alerts) >= 1, "cycle_number=1のアセスメント未完了アラートが含まれるべき"

    # 最初のcycle_number=1アラートを検証
    alert = assessment_alerts[0]
    assert alert["id"] == str(recipient.id)
    assert alert["full_name"] == "テスト 太郎"
    assert alert["alert_type"] == "assessment_incomplete"
    assert alert["message"] == "テスト 太郎のアセスメントが完了していません"
    assert alert["current_cycle_number"] == 1
    assert alert["next_renewal_deadline"] is None
    assert alert["days_remaining"] is None

    # クリーンアップ
    del app.dependency_overrides[get_current_user]
