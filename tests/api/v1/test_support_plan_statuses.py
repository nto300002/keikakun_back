import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date, timedelta
import uuid

from app.core.config import settings
from app.core.security import create_access_token
from app.models.support_plan_cycle import SupportPlanCycle, SupportPlanStatus
from app.models.enums import SupportPlanStep
from app.models.office import OfficeStaff

# ヘルパー関数やフィクスチャをインポート（実際のパスはプロジェクト構成に合わせる）
from tests.utils import create_welfare_recipient

pytestmark = pytest.mark.asyncio


async def create_cycle_with_monitoring_status(db_session: AsyncSession, recipient_id: uuid.UUID) -> int:
    """最終計画書まで完了し、モニタリングステータスを持つサイクルを作成するヘルパー"""
    # 1. 完了済みのサイクルを作成
    final_plan_completed_at = date.today() - timedelta(days=10)
    completed_cycle = SupportPlanCycle(
        welfare_recipient_id=recipient_id,
        plan_cycle_start_date=date.today() - timedelta(days=200),
        next_renewal_deadline=date.today() - timedelta(days=20),
        is_latest_cycle=False,
        cycle_number=1
    )
    db_session.add(completed_cycle)
    await db_session.flush()

    # 1b. 前のサイクルのfinal_plan_signedステータスを作成
    from datetime import datetime
    final_plan_status = SupportPlanStatus(
        plan_cycle_id=completed_cycle.id,
        step_type=SupportPlanStep.final_plan_signed,
        is_latest_status=False,
        completed=True,
        completed_at=datetime.combine(final_plan_completed_at, datetime.min.time())
    )
    db_session.add(final_plan_status)
    await db_session.flush()

    # 2. 新しいサイクル（モニタリングから開始）を作成
    new_cycle = SupportPlanCycle(
        welfare_recipient_id=recipient_id,
        is_latest_cycle=True,
        cycle_number=2
    )
    db_session.add(new_cycle)
    await db_session.flush()

    monitoring_status = SupportPlanStatus(
        plan_cycle_id=new_cycle.id,
        step_type=SupportPlanStep.monitoring,
        is_latest_status=True,
        due_date=final_plan_completed_at + timedelta(days=7) # 初期期限
    )
    db_session.add(monitoring_status)
    await db_session.commit()
    await db_session.refresh(monitoring_status)
    return monitoring_status.id


async def test_update_monitoring_deadline(
    async_client: AsyncClient, 
    db_session: AsyncSession, 
    manager_user_factory,
    office_factory
):
    """【正常系】モニタリング期限の日数を更新できること"""
    # 1. Setup
    # 1a. マネージャーと事業所を作成
    manager = await manager_user_factory(with_office=False)
    office = await office_factory(creator=manager)
    association = OfficeStaff(staff_id=manager.id, office_id=office.id)
    db_session.add(association)
    await db_session.commit()

    # 1b. 認証ヘッダーを作成
    access_token = create_access_token(str(manager.id))
    headers = {"Authorization": f"Bearer {access_token}"}

    # 1c. 事業所に関連付けられた利用者を作成
    recipient = await create_welfare_recipient(db_session, office_id=office.id)
    
    # 1d. モニタリングステータスを持つサイクルを作成
    status_id = await create_cycle_with_monitoring_status(db_session, recipient.id)

    # 2. API呼び出し
    update_data = {"monitoring_deadline": 14}
    response = await async_client.patch(
        f"{settings.API_V1_STR}/support-plan-statuses/{status_id}",
        headers=headers,
        json=update_data,
    )

    # 3. アサーション
    assert response.status_code == 200
    updated_status = response.json()
    assert updated_status["monitoring_deadline"] == 14

    # due_date が再計算されていることを確認
    # final_plan_completed_at が today - 10 days なので
    expected_due_date = (date.today() - timedelta(days=10) + timedelta(days=14)).strftime("%Y-%m-%d")
    assert updated_status["due_date"] == expected_due_date
