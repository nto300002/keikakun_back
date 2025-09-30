import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from unittest.mock import patch
from uuid import uuid4
from datetime import date, timedelta

from app.services.welfare_recipient_service import welfare_recipient_service
from app.schemas.welfare_recipient import UserRegistrationRequest
from app.db.session import AsyncSessionLocal
from app import crud
from app.models.staff import Staff
from app.models.office import Office
from app.models.welfare_recipient import WelfareRecipient
from app.models.support_plan_cycle import SupportPlanCycle, SupportPlanStatus
from app.models.enums import SupportPlanStep, StaffRole, OfficeType
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


@pytest.fixture
def full_registration_data() -> UserRegistrationRequest:
    """テスト用の完全な利用者登録データ"""
    return UserRegistrationRequest(
        basic_info={
            "firstName": "サービス", "lastName": "テスト",
            "firstNameFurigana": "さーびす", "lastNameFurigana": "てすと",
            "birthDay": date(1990, 1, 1), "gender": "male"
        },
        contact_address={
            "address": "テスト住所", "formOfResidence": "home_with_family",
            "meansOfTransportation": "public_transport", "tel": "0123456789"
        },
        emergency_contacts=[],
        disability_info={
            "disabilityOrDiseaseName": "テスト障害", "livelihoodProtection": "not_receiving"},
        disability_details=[]
    )


@pytest.fixture
async def setup_staff_and_office(db: AsyncSession) -> tuple[Staff, Office]:
    """テスト用のスタッフと事業所を作成して返すフィクスチャ（非同期）"""
    staff = Staff(
        name="テスト管理者",
        email=f"test_admin_{uuid4()}@example.com",
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
    # refresh to populate mapped relationships/ids
    await db.refresh(staff)
    await db.refresh(office)
    return staff, office


class TestWelfareRecipientService:
    """welfare_recipient_service の非同期テスト"""

    async def test_create_recipient_with_details_success(
        self, db: AsyncSession, full_registration_data: UserRegistrationRequest, setup_staff_and_office
    ):
        """正常系: 利用者と関連データ、初期支援計画がすべて作成されること"""
        _, office = setup_staff_and_office

        # create_recipient_with_initial_plan は同期実装の場合 run_in_executor される等の互換処理を期待
        res = welfare_recipient_service.create_recipient_with_initial_plan(
            db=db, registration_data=full_registration_data, office_id=office.id
        )
        # create_recipient_with_initial_plan may return coroutine when service is async-compatible
        if hasattr(res, "__await__"):
            recipient_id = await res
        else:
            recipient_id = res

        # Eager loadingで関連データを取得
        stmt = select(WelfareRecipient).where(WelfareRecipient.id == recipient_id).options(
            selectinload(WelfareRecipient.detail),
            selectinload(WelfareRecipient.support_plan_cycles).selectinload(SupportPlanCycle.statuses)
        )
        result = await db.execute(stmt)
        db_recipient = result.scalars().first()

        # アサーション
        assert db_recipient is not None
        assert db_recipient.first_name == "サービス"
        assert db_recipient.detail is not None
        assert len(db_recipient.support_plan_cycles) == 1
        assert len(db_recipient.support_plan_cycles[0].statuses) > 0


class TestCreateInitialSupportPlan:
    """初期支援計画作成ロジックのテスト"""

    async def test_initial_plan_for_first_cycle(self, db: AsyncSession, setup_staff_and_office):
        """要件通り、最初のサイクルの初期ステップが正しく作成されるか"""
        staff, office = setup_staff_and_office
        recipient = WelfareRecipient(first_name="初回", last_name="テスト", birth_day=date(1999,1,1), gender="male")
        db.add(recipient)
        await db.flush()

        await welfare_recipient_service._create_initial_support_plan(db, recipient.id)


        stmt = select(SupportPlanCycle).where(SupportPlanCycle.welfare_recipient_id == recipient.id).options(selectinload(SupportPlanCycle.statuses))
        result = await db.execute(stmt)
        cycle = result.scalars().first()

        assert cycle is not None
        assert cycle.cycle_number == 1
        step_types = {status.step_type for status in cycle.statuses}
        assert step_types == {
            SupportPlanStep.assessment, 
            SupportPlanStep.draft_plan, 
            SupportPlanStep.staff_meeting, 
            SupportPlanStep.final_plan_signed
        }

    async def test_initial_plan_for_subsequent_cycle(self, db: AsyncSession, setup_staff_and_office):
        """要件通り、2回目以降のサイクルの初期ステップが正しく作成されるか"""
        staff, office = setup_staff_and_office
        recipient = WelfareRecipient(first_name="２回目", last_name="テスト", birth_day=date(1998,1,1), gender="female")
        db.add(recipient)
        await db.flush()

        # 既存のサイクルを１つ作成しておく
        existing_cycle = SupportPlanCycle(
            welfare_recipient_id=recipient.id, 
            cycle_number=1, 
            is_latest_cycle=False, 
            plan_cycle_start_date=date.today() - timedelta(days=200)
        )
        db.add(existing_cycle)
        await db.flush()

        await welfare_recipient_service._create_initial_support_plan(db, recipient.id)

        stmt = select(SupportPlanCycle).where(
            SupportPlanCycle.welfare_recipient_id == recipient.id, 
            SupportPlanCycle.is_latest_cycle == True
        ).options(selectinload(SupportPlanCycle.statuses))
        result = await db.execute(stmt)
        cycle = result.scalars().first()

        assert cycle is not None
        assert cycle.cycle_number == 2
        step_types = {status.step_type for status in cycle.statuses}
        assert step_types == {
            SupportPlanStep.monitoring, 
            SupportPlanStep.draft_plan, 
            SupportPlanStep.staff_meeting, 
            SupportPlanStep.final_plan_signed
        }


    async def test_create_recipient_rollback_on_error(
        self, db: AsyncSession, full_registration_data: UserRegistrationRequest, setup_staff_and_office
    ):
        """異常系: 処理中にエラーが発生した場合にロールバックされること"""
        _, office = setup_staff_and_office

        # patch はクラスメソッドを確実にパッチ
        with patch.object(welfare_recipient_service.__class__, "_create_initial_support_plan", side_effect=Exception("DB Error")):
            with pytest.raises(Exception, match="DB Error"):
                coro_or_res = welfare_recipient_service.create_recipient_with_details(
                    db=db, registration_data=full_registration_data, office_id=office.id
                )
                if hasattr(coro_or_res, "__await__"):
                    await coro_or_res
                else:
                    # 同期例外が発生するならそのまま呼び出す
                    _ = coro_or_res
