import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import patch
from uuid import uuid4
from typing import Tuple
from datetime import date, timedelta

from app.db.session import AsyncSessionLocal
from app.services.welfare_recipient_service import welfare_recipient_service
from app.models.welfare_recipient import WelfareRecipient, OfficeWelfareRecipient
from app.models.support_plan_cycle import SupportPlanCycle, SupportPlanStatus
from app.models.staff import Staff
from app.models.office import Office
from app.models.enums import StaffRole, OfficeType, GenderType, SupportPlanStep
from app.core.security import get_password_hash

pytestmark = pytest.mark.asyncio

@pytest.fixture(scope="function")
async def db() -> AsyncSession:
    """テスト用の非同期DBセッションを提供するフィクスチャ"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            try:
                await session.rollback()
            except Exception:
                pass

@pytest.fixture(scope="function")
async def setup_staff_and_office(db: AsyncSession) -> Tuple[Staff, Office]:
    """テスト用のスタッフと事業所を作成して返すフィクスチャ（非同期）"""
    staff = Staff(
        name="テスト管理者",
        email=f"test_admin_{uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash("password"),
        role=StaffRole.owner,
    )
    db.add(staff)
    await db.flush()

    office = Office(
        name="テスト事業所",
        type=OfficeType.type_A_office,
        created_by=staff.id,
        last_modified_by=staff.id,
    )
    db.add(office)
    await db.flush()

    await db.refresh(staff)
    await db.refresh(office)
    return staff, office

async def test_repair_creates_missing_cycle(db: AsyncSession, setup_staff_and_office):
    """初期サイクルが無い利用者に対してサイクルと初期ステータスを作成する"""
    staff, office = setup_staff_and_office

    recipient = WelfareRecipient(first_name="修復対象", last_name="一", birth_day=date(1990, 1, 1), gender=GenderType.male)
    db.add(recipient)
    await db.flush()

    # 利用者と事業所を関連付け
    office_recipient = OfficeWelfareRecipient(office_id=office.id, welfare_recipient_id=recipient.id)
    db.add(office_recipient)
    await db.commit()
    await db.refresh(recipient) # commit後にrefreshしてセッションに再アタッチ
    await db.refresh(staff)

    repaired, msg = await welfare_recipient_service.repair_recipient_support_plan(db=db, welfare_recipient_id=recipient.id, performed_by=staff.id)
    
    # サービス内でcommitが走るため、オブジェクトの状態をリフレッシュする
    await db.refresh(recipient)

    assert repaired is True
    assert "初期支援計画サイクルとステータスを作成しました" in msg
    res = await db.execute(select(func.count()).select_from(SupportPlanCycle).where(SupportPlanCycle.welfare_recipient_id == recipient.id))
    assert res.scalar_one() == 1

    res2 = await db.execute(select(func.count()).select_from(SupportPlanStatus).where(SupportPlanStatus.plan_cycle_id == select(SupportPlanCycle.id).where(SupportPlanCycle.welfare_recipient_id == recipient.id).scalar_subquery()))
    assert res2.scalar_one() >= 3


async def test_repair_adds_missing_statuses(db: AsyncSession, setup_staff_and_office):
    """サイクルはあるがステータスが不足している場合に不足分を作成する"""
    staff, office = setup_staff_and_office

    recipient = WelfareRecipient(first_name="部分修復", last_name="二", birth_day=date(1990, 1, 1), gender=GenderType.female)
    db.add(recipient)
    await db.flush()

    # 利用者と事業所を関連付け
    office_recipient = OfficeWelfareRecipient(office_id=office.id, welfare_recipient_id=recipient.id)
    db.add(office_recipient)
    await db.flush()

    cycle = SupportPlanCycle(welfare_recipient_id=recipient.id, office_id=office.id, is_latest_cycle=True, plan_cycle_start_date=date.today(), next_renewal_deadline=date.today() + timedelta(days=180))
    db.add(cycle)
    await db.flush()

    st = SupportPlanStatus(plan_cycle_id=cycle.id, welfare_recipient_id=recipient.id, office_id=office.id, step_type=SupportPlanStep.assessment, completed=False)
    db.add(st)
    await db.commit()
    await db.refresh(recipient)
    await db.refresh(staff)

    repaired, msg = await welfare_recipient_service.repair_recipient_support_plan(db=db, welfare_recipient_id=recipient.id, performed_by=staff.id)

    # サービス内でcommitが走るため、オブジェクトの状態をリフレッシュする
    await db.refresh(recipient)
    await db.refresh(cycle)

    assert repaired is True    
    assert "不足していた" in msg

    res = await db.execute(select(func.count()).select_from(SupportPlanStatus).where(SupportPlanStatus.plan_cycle_id == cycle.id))
    assert res.scalar_one() >= 3


async def test_repair_returns_false_on_internal_error(db: AsyncSession, setup_staff_and_office):
    """内部エラーが起きた場合は False を返しロールバックされること"""
    staff, office = setup_staff_and_office

    # サイクルが存在する状態を作る
    recipient = WelfareRecipient(first_name="エラー", last_name="三", birth_day=date(1990, 1, 1), gender=GenderType.other)
    db.add(recipient)
    await db.flush()

    # 利用者と事業所を関連付け
    office_recipient = OfficeWelfareRecipient(office_id=office.id, welfare_recipient_id=recipient.id)
    db.add(office_recipient)
    await db.flush()

    cycle = SupportPlanCycle(welfare_recipient_id=recipient.id, office_id=office.id, is_latest_cycle=True, plan_cycle_start_date=date.today(), next_renewal_deadline=date.today() + timedelta(days=180))
    db.add(cycle)
    await db.commit()
    await db.refresh(recipient)
    await db.refresh(staff)
    await db.refresh(cycle)

    # _repair_missing_statuses_async が呼ばれるパスでエラーを発生させる
    with patch.object(welfare_recipient_service, "_repair_missing_statuses_async", side_effect=Exception("boom")) as mock_repair:
        repaired, msg = await welfare_recipient_service.repair_recipient_support_plan(db=db, welfare_recipient_id=recipient.id, performed_by=staff.id)
        assert repaired is False
        assert "修復中にエラー" in msg
        mock_repair.assert_awaited_once()

    # サービス内でrollbackが走るため、オブジェクトの状態をリフレッシュする
    await db.refresh(cycle)

    # ロールバックされていることを確認 (ステータスが追加されていない)
    res = await db.execute(select(func.count()).select_from(SupportPlanStatus).where(SupportPlanStatus.plan_cycle_id == cycle.id))
    assert res.scalar_one() == 0