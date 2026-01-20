"""
期限切れアラートのテスト

期限が過ぎた（days_remaining <= 0）利用者の
特別な警告メッセージ表示をテストする
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date, timedelta
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.welfare_recipient import WelfareRecipient
from app.models.support_plan_cycle import SupportPlanCycle
from app.models.office import Office, OfficeStaff
from app.models.staff import Staff
from app.main import app


@pytest.mark.asyncio
async def test_get_deadline_alerts_overdue(
    async_client: AsyncClient,
    db_session: AsyncSession,
    office_factory,
    welfare_recipient_factory,
    test_admin_user: Staff
):
    """
    期限切れ（days_remaining <= 0）の利用者が
    特別なメッセージで表示されることを確認

    期待:
    - alert_type="renewal_overdue"
    - message="!{full_name}の更新期限が過ぎています!"
    - days_remaining <= 0
    """
    # 1. テストデータの準備
    office = await office_factory(creator=test_admin_user)
    db_session.add(OfficeStaff(staff_id=test_admin_user.id, office_id=office.id, is_primary=True))
    await db_session.flush()

    # 2. 利用者を作成（期限切れ3パターン）

    # 利用者A: 期限切れ（3日前）
    recipient_a = await welfare_recipient_factory(
        office_id=office.id,
        last_name="山田",
        first_name="太郎"
    )
    cycle_a = SupportPlanCycle(
        welfare_recipient_id=recipient_a.id,
        office_id=office.id,
        next_renewal_deadline=date.today() - timedelta(days=3),
        is_latest_cycle=True,
        cycle_number=2,
        next_plan_start_date=7
    )
    db_session.add(cycle_a)

    # 利用者B: 期限当日（0日）
    recipient_b = await welfare_recipient_factory(
        office_id=office.id,
        last_name="佐藤",
        first_name="花子"
    )
    cycle_b = SupportPlanCycle(
        welfare_recipient_id=recipient_b.id,
        office_id=office.id,
        next_renewal_deadline=date.today(),
        is_latest_cycle=True,
        cycle_number=1,
        next_plan_start_date=7
    )
    db_session.add(cycle_b)

    # 利用者C: 期限内（残り5日）- 比較用
    recipient_c = await welfare_recipient_factory(
        office_id=office.id,
        last_name="鈴木",
        first_name="次郎"
    )
    cycle_c = SupportPlanCycle(
        welfare_recipient_id=recipient_c.id,
        office_id=office.id,
        next_renewal_deadline=date.today() + timedelta(days=5),
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

    # 期限切れアラートを抽出
    overdue_alerts = [a for a in data["alerts"] if a.get("alert_type") == "renewal_overdue"]
    assert len(overdue_alerts) >= 2, "期限切れアラートは山田さんと佐藤さんの2件以上"

    # 利用者A（3日前に期限切れ）の検証
    alert_a = next((a for a in overdue_alerts if a["id"] == str(recipient_a.id)), None)
    assert alert_a is not None, "山田 太郎さんの期限切れアラートが存在する"
    assert alert_a["alert_type"] == "renewal_overdue"
    assert alert_a["message"] == "!山田 太郎の更新期限が過ぎています!"
    assert alert_a["days_remaining"] == -3
    assert alert_a["full_name"] == "山田 太郎"

    # 利用者B（当日期限切れ）の検証
    alert_b = next((a for a in overdue_alerts if a["id"] == str(recipient_b.id)), None)
    assert alert_b is not None, "佐藤 花子さんの期限切れアラートが存在する"
    assert alert_b["alert_type"] == "renewal_overdue"
    assert alert_b["message"] == "!佐藤 花子の更新期限が過ぎています!"
    assert alert_b["days_remaining"] == 0
    assert alert_b["full_name"] == "佐藤 花子"

    # 利用者C（期限内）の検証
    renewal_alerts = [a for a in data["alerts"] if a.get("alert_type") == "renewal_deadline"]
    alert_c = next((a for a in renewal_alerts if a["id"] == str(recipient_c.id)), None)
    assert alert_c is not None, "鈴木 次郎さんの通常アラートが存在する"
    assert alert_c["alert_type"] == "renewal_deadline"
    assert alert_c["message"] == "鈴木 次郎の更新期限まで残り5日"
    assert alert_c["days_remaining"] == 5

    # クリーンアップ
    del app.dependency_overrides[get_current_user]


@pytest.mark.asyncio
async def test_get_deadline_alerts_overdue_sorting(
    async_client: AsyncClient,
    db_session: AsyncSession,
    office_factory,
    welfare_recipient_factory,
    test_admin_user: Staff
):
    """
    期限切れアラートが期限日順（古い順）にソートされることを確認
    """
    # 1. テストデータの準備
    office = await office_factory(creator=test_admin_user)
    db_session.add(OfficeStaff(staff_id=test_admin_user.id, office_id=office.id, is_primary=True))
    await db_session.flush()

    # 2. 利用者を作成（期限切れ日が異なる3人）

    # 利用者A: 10日前に期限切れ（最も古い）
    recipient_a = await welfare_recipient_factory(
        office_id=office.id,
        last_name="Aさん",
        first_name="一"
    )
    cycle_a = SupportPlanCycle(
        welfare_recipient_id=recipient_a.id,
        office_id=office.id,
        next_renewal_deadline=date.today() - timedelta(days=10),
        is_latest_cycle=True,
        cycle_number=1,
        next_plan_start_date=7
    )
    db_session.add(cycle_a)

    # 利用者B: 5日前に期限切れ
    recipient_b = await welfare_recipient_factory(
        office_id=office.id,
        last_name="Bさん",
        first_name="二"
    )
    cycle_b = SupportPlanCycle(
        welfare_recipient_id=recipient_b.id,
        office_id=office.id,
        next_renewal_deadline=date.today() - timedelta(days=5),
        is_latest_cycle=True,
        cycle_number=1,
        next_plan_start_date=7
    )
    db_session.add(cycle_b)

    # 利用者C: 当日期限切れ（最も新しい）
    recipient_c = await welfare_recipient_factory(
        office_id=office.id,
        last_name="Cさん",
        first_name="三"
    )
    cycle_c = SupportPlanCycle(
        welfare_recipient_id=recipient_c.id,
        office_id=office.id,
        next_renewal_deadline=date.today(),
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

    # 期限切れアラートを抽出
    overdue_alerts = [a for a in data["alerts"] if a.get("alert_type") == "renewal_overdue"]
    assert len(overdue_alerts) >= 3, "期限切れアラートは3件以上"

    # ソート順の検証: 期限日が古い順（days_remainingが最も負の値が先頭）
    overdue_ids = [a["id"] for a in overdue_alerts]

    # AさんBさんCさんの順に並んでいることを確認
    a_index = next((i for i, id in enumerate(overdue_ids) if id == str(recipient_a.id)), None)
    b_index = next((i for i, id in enumerate(overdue_ids) if id == str(recipient_b.id)), None)
    c_index = next((i for i, id in enumerate(overdue_ids) if id == str(recipient_c.id)), None)

    assert a_index is not None, "Aさんが含まれている"
    assert b_index is not None, "Bさんが含まれている"
    assert c_index is not None, "Cさんが含まれている"
    assert a_index < b_index < c_index, "期限日が古い順にソートされている"

    # クリーンアップ
    del app.dependency_overrides[get_current_user]
