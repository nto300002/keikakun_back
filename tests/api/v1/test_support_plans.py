import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from datetime import date, datetime
import uuid

from app.models.welfare_recipient import WelfareRecipient
from app.models.support_plan_cycle import SupportPlanCycle, SupportPlanStatus, PlanDeliverable
from app.models.office import Office, OfficeStaff
from app.models.staff import Staff
from app.models.enums import GenderType, SupportPlanStep, DeliverableType
from app.main import app
from app.api.deps import get_current_user, get_db
from tests.utils import load_staff_with_office


@pytest.mark.asyncio
async def test_get_support_plan_cycles(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_admin_user: Staff,
    office_factory
):
    """
    GET /api/v1/support-plans/{recipient_id}/cycles
    利用者の個別支援計画サイクル一覧を取得できることを確認
    """
    # 1. テストデータの準備
    office = await office_factory(creator=test_admin_user)
    db_session.add(OfficeStaff(staff_id=test_admin_user.id, office_id=office.id, is_primary=True))
    await db_session.flush()

    # 利用者を作成
    recipient = WelfareRecipient(
        first_name="テスト",
        last_name="太郎",
        first_name_furigana="テスト",
        last_name_furigana="タロウ",
        birth_day=date(1990, 1, 1),
        gender=GenderType.male,
    )
    db_session.add(recipient)
    await db_session.flush()

    # 事業所と利用者の関連を作成
    from app.models.welfare_recipient import OfficeWelfareRecipient
    association = OfficeWelfareRecipient(office_id=office.id, welfare_recipient_id=recipient.id)
    db_session.add(association)
    await db_session.flush()

    # サイクル1を作成（is_latest_cycle=False）
    cycle1 = SupportPlanCycle(
        welfare_recipient_id=recipient.id,
        office_id=office.id,
        plan_cycle_start_date=date(2024, 1, 1),
        is_latest_cycle=False,
        cycle_number=1,
    )
    db_session.add(cycle1)
    await db_session.flush()

    # サイクル1のステータスを作成
    statuses1 = [
        SupportPlanStatus(
            plan_cycle_id=cycle1.id,
            welfare_recipient_id=recipient.id,
            office_id=office.id,
            step_type=SupportPlanStep.assessment,
            is_latest_status=False,
            completed=True,
            completed_at=datetime(2024, 1, 15),
        ),
        SupportPlanStatus(
            plan_cycle_id=cycle1.id,
            welfare_recipient_id=recipient.id,
            office_id=office.id,
            step_type=SupportPlanStep.draft_plan,
            is_latest_status=False,
            completed=True,
            completed_at=datetime(2024, 2, 1),
        ),
        SupportPlanStatus(
            plan_cycle_id=cycle1.id,
            welfare_recipient_id=recipient.id,
            office_id=office.id,
            step_type=SupportPlanStep.staff_meeting,
            is_latest_status=False,
            completed=True,
            completed_at=datetime(2024, 2, 15),
        ),
        SupportPlanStatus(
            plan_cycle_id=cycle1.id,
            welfare_recipient_id=recipient.id,
            office_id=office.id,
            step_type=SupportPlanStep.final_plan_signed,
            is_latest_status=False,
            completed=True,
            completed_at=datetime(2024, 3, 1),
        ),
    ]
    db_session.add_all(statuses1)

    # サイクル2を作成（最新サイクル）
    cycle2 = SupportPlanCycle(
        welfare_recipient_id=recipient.id,
        office_id=office.id,
        plan_cycle_start_date=date(2024, 7, 1),
        is_latest_cycle=True,
        cycle_number=2,
    )
    db_session.add(cycle2)
    await db_session.flush()

    # サイクル2のステータスを作成
    statuses2 = [
        SupportPlanStatus(
            plan_cycle_id=cycle2.id,
            welfare_recipient_id=recipient.id,
            office_id=office.id,
            step_type=SupportPlanStep.assessment,
            is_latest_status=True,
            completed=False,
        ),
        SupportPlanStatus(
            plan_cycle_id=cycle2.id,
            welfare_recipient_id=recipient.id,
            office_id=office.id,
            step_type=SupportPlanStep.draft_plan,
            is_latest_status=False,
            completed=False,
        ),
        SupportPlanStatus(
            plan_cycle_id=cycle2.id,
            welfare_recipient_id=recipient.id,
            office_id=office.id,
            step_type=SupportPlanStep.staff_meeting,
            is_latest_status=False,
            completed=False,
        ),
        SupportPlanStatus(
            plan_cycle_id=cycle2.id,
            welfare_recipient_id=recipient.id,
            office_id=office.id,
            step_type=SupportPlanStep.final_plan_signed,
            is_latest_status=False,
            completed=False,
        ),
    ]
    db_session.add_all(statuses2)
    await db_session.commit()

    # 2. 依存関係のオーバーライド（get_dbは async_client fixture で既にオーバーライド済み）
    async def override_get_current_user_with_relations():
        # Reload test_admin_user with office_associations
        return await load_staff_with_office(db_session, test_admin_user)

    app.dependency_overrides[get_current_user] = override_get_current_user_with_relations

    # 3. APIエンドポイントの呼び出し
    response = await async_client.get(f"/api/v1/support-plans/{recipient.id}/cycles")

    # 4. レスポンスの検証
    assert response.status_code == 200
    data = response.json()

    assert "cycles" in data
    assert len(data["cycles"]) == 2

    # サイクルの順序を確認（cycle_numberの降順）
    assert data["cycles"][0]["cycle_number"] == 2
    assert data["cycles"][1]["cycle_number"] == 1

    # 降順になったので、最初がサイクル2
    cycle2_data = data["cycles"][0]
    assert cycle2_data["is_latest_cycle"] is True
    assert len(cycle2_data["statuses"]) == 4

    # 2番目がサイクル1
    cycle1_data = data["cycles"][1]
    assert cycle1_data["is_latest_cycle"] is False
    assert len(cycle1_data["statuses"]) == 4

    # ステータスの詳細を確認
    assessment_status = next(s for s in cycle2_data["statuses"] if s["step_type"] == "assessment")
    assert assessment_status["completed"] is False
    assert assessment_status["is_latest_status"] is True

    # クリーンアップ
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_support_plan_cycles_not_found(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_admin_user: Staff,
):
    """
    GET /api/v1/support-plans/{recipient_id}/cycles
    存在しない利用者IDの場合404を返すことを確認
    """
    # 依存関係のオーバーライド
    async def override_get_current_user_with_relations():
        stmt = select(Staff).where(Staff.id == test_admin_user.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        ).execution_options(populate_existing=True)
        result = await db_session.execute(stmt)
        user = result.scalars().first()
        return user

    app.dependency_overrides[get_current_user] = override_get_current_user_with_relations

    # 存在しないUUIDでリクエスト
    non_existent_id = uuid.uuid4()
    response = await async_client.get(f"/api/v1/support-plans/{non_existent_id}/cycles")

    # 404エラーを期待
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()

    # クリーンアップ
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_support_plan_cycles_unauthorized_office(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_admin_user: Staff,
    office_factory
):
    """
    GET /api/v1/support-plans/{recipient_id}/cycles
    他の事業所の利用者にアクセスしようとした場合、403を返すことを確認
    """
    # 事業所1と事業所2を作成
    office1 = await office_factory(creator=test_admin_user)
    db_session.add(OfficeStaff(staff_id=test_admin_user.id, office_id=office1.id, is_primary=True))

    # 別のスタッフと事業所2を作成
    other_staff = Staff(
        email="other@example.com",
        hashed_password="hashed",
        last_name="他の",
        first_name="スタッフ",
        full_name="他の スタッフ",
        role="employee",
    )
    db_session.add(other_staff)
    await db_session.flush()

    office2 = await office_factory(creator=other_staff)

    # 事業所2に属する利用者を作成
    recipient = WelfareRecipient(
        first_name="テスト",
        last_name="花子",
        first_name_furigana="テスト",
        last_name_furigana="ハナコ",
        birth_day=date(1992, 5, 10),
        gender=GenderType.female,
    )
    db_session.add(recipient)
    await db_session.flush()

    # 事業所2と利用者の関連を作成
    from app.models.welfare_recipient import OfficeWelfareRecipient
    association2 = OfficeWelfareRecipient(office_id=office2.id, welfare_recipient_id=recipient.id)
    db_session.add(association2)
    await db_session.commit()

    # 依存関係のオーバーライド（test_admin_userでログイン）
    async def override_get_current_user_with_relations():
        stmt = select(Staff).where(Staff.id == test_admin_user.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        ).execution_options(populate_existing=True)
        result = await db_session.execute(stmt)
        user = result.scalars().first()
        return user

    app.dependency_overrides[get_current_user] = override_get_current_user_with_relations

    # 他の事業所の利用者にアクセス
    response = await async_client.get(f"/api/v1/support-plans/{recipient.id}/cycles")

    # 403エラーを期待
    assert response.status_code == 403
    assert "permission" in response.json()["detail"].lower() or "access" in response.json()["detail"].lower()

    # クリーンアップ
    app.dependency_overrides.clear()
