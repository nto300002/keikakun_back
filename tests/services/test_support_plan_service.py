import pytest
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from uuid import UUID, uuid4
from datetime import date, timedelta, datetime, timezone
from unittest.mock import patch
from typing import Tuple

from app.db.session import AsyncSessionLocal
from app.models.welfare_recipient import WelfareRecipient, OfficeWelfareRecipient
from app.models.support_plan_cycle import SupportPlanCycle, SupportPlanStatus
from app.models.staff import Staff
from app.models.office import Office
from app.models.enums import StaffRole, OfficeType, GenderType, SupportPlanStep, DeliverableType
from app.core.security import get_password_hash
from app.services.support_plan_service import support_plan_service
from app.schemas.support_plan import PlanDeliverableCreate
from app.core.exceptions import InvalidStepOrderError

# Add basic logging config to see output
logging.basicConfig(level=logging.INFO)


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
async def setup_staff_and_office(db: AsyncSession) -> Tuple[UUID, UUID]:
    """テスト用のスタッフと事業所を作成してIDを返すフィクスチャ"""
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
    await db.flush() # Flush to assign office.id

    # Get IDs before commit, as objects may become expired after commit
    staff_id = staff.id
    office_id = office.id
    print(f"[Debug] setup_staff_and_office: staff_id={staff_id}, office_id={office_id}")

    await db.commit() # Commit to ensure objects are persisted

    return staff_id, office_id

@pytest.fixture(scope="function")
async def setup_recipient_with_initial_cycle(db: AsyncSession, setup_staff_and_office: Tuple[UUID, UUID]) -> Tuple[UUID, int, UUID]:
    """初期サイクルを持つ利用者を作成し、そのIDを返すフィクスチャ"""
    staff_id, office_id = setup_staff_and_office
    
    recipient = WelfareRecipient(
        first_name="テスト",
        last_name="太郎",
        first_name_furigana="テスト",
        last_name_furigana="タロウ",
        birth_day=date(1990, 1, 1),
        gender=GenderType.male,
    )
    db.add(recipient)
    await db.flush()

    association = OfficeWelfareRecipient(office_id=office_id, welfare_recipient_id=recipient.id)
    db.add(association)

    cycle = SupportPlanCycle(
        welfare_recipient_id=recipient.id,
        plan_cycle_start_date=None,
        next_renewal_deadline=None,
        is_latest_cycle=True,
        cycle_number=1
    )
    db.add(cycle)
    await db.flush()

    statuses = [
        SupportPlanStatus(plan_cycle_id=cycle.id, step_type=SupportPlanStep.assessment, is_latest_status=True),
        SupportPlanStatus(plan_cycle_id=cycle.id, step_type=SupportPlanStep.draft_plan, is_latest_status=False),
        SupportPlanStatus(plan_cycle_id=cycle.id, step_type=SupportPlanStep.staff_meeting, is_latest_status=False),
        SupportPlanStatus(plan_cycle_id=cycle.id, step_type=SupportPlanStep.final_plan_signed, is_latest_status=False),
    ]
    db.add_all(statuses)

    recipient_id = recipient.id
    cycle_id = cycle.id

    await db.commit()
    
    return recipient_id, cycle_id, staff_id


@pytest.mark.asyncio
async def test_upload_assessment_deliverable_completes_step(
    db: AsyncSession, 
    setup_recipient_with_initial_cycle: Tuple[UUID, int, UUID]
):
    """【正常系】アセスメントの成果物をアップロードすると、対応するステップが完了すること"""
    recipient_id, cycle_id, staff_id = setup_recipient_with_initial_cycle

    deliverable_in = PlanDeliverableCreate(
        plan_cycle_id=cycle_id,
        deliverable_type=DeliverableType.assessment_sheet,
        file_path="/path/to/dummy.pdf",
        original_filename="dummy.pdf",
    )
    await support_plan_service.handle_deliverable_upload(
        db=db, 
        deliverable_in=deliverable_in,
        uploaded_by_staff_id=staff_id
    )

    from sqlalchemy import select
    stmt = select(SupportPlanCycle).where(SupportPlanCycle.id == cycle_id).options(selectinload(SupportPlanCycle.statuses))
    result = await db.execute(stmt)
    updated_cycle = result.scalar_one()

    assessment_status = next((s for s in updated_cycle.statuses if s.step_type == SupportPlanStep.assessment), None)
    assert assessment_status is not None
    assert assessment_status.completed is True

    draft_plan_status = next((s for s in updated_cycle.statuses if s.step_type == SupportPlanStep.draft_plan), None)
    assert draft_plan_status is not None
    assert draft_plan_status.is_latest_status is True

@pytest.mark.asyncio
async def test_upload_assessment_sets_cycle_dates(
    db: AsyncSession, 
    setup_recipient_with_initial_cycle: Tuple[UUID, int, UUID]
):
    """
    【正常系】アセスメント成果物をアップロードすると、
    plan_cycle_start_date と next_renewal_deadline が設定されること
    """
    recipient_id, cycle_id, staff_id = setup_recipient_with_initial_cycle

    # 1. 初期状態の確認
    initial_cycle = await db.get(SupportPlanCycle, cycle_id)
    assert initial_cycle.plan_cycle_start_date is None
    assert initial_cycle.next_renewal_deadline is None

    # 2. `date.today()` をモックして日付を固定
    mock_today = date(2023, 10, 27)
    mock_now_utc = datetime(2023, 10, 27, 12, 0, 0, tzinfo=timezone.utc)

    with patch('app.services.support_plan_service.datetime.date') as mock_date, \
         patch('app.services.support_plan_service.datetime.datetime') as mock_datetime:

        mock_date.today.return_value = mock_today
        mock_datetime.now.return_value = mock_now_utc

        # 3. アセスメント成果物をアップロード
        deliverable_in = PlanDeliverableCreate(
            plan_cycle_id=cycle_id,
            deliverable_type=DeliverableType.assessment_sheet,
            file_path="/path/to/assessment.pdf",
            original_filename="assessment.pdf",
        )
        await support_plan_service.handle_deliverable_upload(
            db=db, 
            deliverable_in=deliverable_in,
            uploaded_by_staff_id=staff_id
        )

    # 4. 結果をDBから取得してアサート
    await db.refresh(initial_cycle)

    expected_deadline = mock_today + timedelta(days=180)
    assert initial_cycle.plan_cycle_start_date == mock_today
    assert initial_cycle.next_renewal_deadline == expected_deadline

@pytest.mark.asyncio
async def test_upload_final_plan_creates_new_cycle(
    db: AsyncSession,
    setup_recipient_with_initial_cycle: Tuple[UUID, int, UUID]
):
    """【正常系】最終計画書をアップロードすると、次サイクルが自動生成されること"""
    recipient_id, original_cycle_id, staff_id = setup_recipient_with_initial_cycle

    # 前提となるステップを完了させる
    steps_to_complete = [
        (DeliverableType.assessment_sheet, "assessment.pdf"),
        (DeliverableType.draft_plan_pdf, "draft_plan.pdf"),
        (DeliverableType.staff_meeting_minutes, "staff_meeting.pdf"),
    ]

    for deliverable_type, filename in steps_to_complete:
        # 各ステップの前提条件を整えるために、都度DBから最新の状態を取得する
        await db.refresh(await db.get(SupportPlanCycle, original_cycle_id), attribute_names=["statuses"])

        deliverable_in = PlanDeliverableCreate(
            plan_cycle_id=original_cycle_id,
            deliverable_type=deliverable_type,
            file_path=f"/path/to/{filename}",
            original_filename=filename,
        )
        await support_plan_service.handle_deliverable_upload(
            db=db,
            deliverable_in=deliverable_in,
            uploaded_by_staff_id=staff_id
        )

    # 最終計画書をアップロード
    mock_today = date(2023, 10, 27)
    mock_now_utc = datetime(2023, 10, 27, 12, 0, 0, tzinfo=timezone.utc)

    with patch('app.services.support_plan_service.datetime.date') as mock_date, \
         patch('app.services.support_plan_service.datetime.datetime') as mock_datetime:

        mock_date.today.return_value = mock_today
        mock_datetime.now.return_value = mock_now_utc

        deliverable_in = PlanDeliverableCreate(
            plan_cycle_id=original_cycle_id,
            deliverable_type=DeliverableType.final_plan_signed_pdf,
            file_path="/path/to/final_plan.pdf",
            original_filename="final_plan.pdf",
        )
        await support_plan_service.handle_deliverable_upload(
            db=db,
            deliverable_in=deliverable_in,
            uploaded_by_staff_id=staff_id
        )

        from sqlalchemy import select
        original_cycle_stmt = select(SupportPlanCycle).where(SupportPlanCycle.id == original_cycle_id)
        original_cycle = (await db.execute(original_cycle_stmt)).scalar_one()
        assert original_cycle.is_latest_cycle is False

        new_cycle_stmt = select(SupportPlanCycle).where(
            SupportPlanCycle.welfare_recipient_id == recipient_id,
            SupportPlanCycle.is_latest_cycle == True
        ).options(selectinload(SupportPlanCycle.statuses))
        new_cycle = (await db.execute(new_cycle_stmt)).scalar_one_or_none()

        assert new_cycle is not None
        assert new_cycle.plan_cycle_start_date == mock_today
        assert new_cycle.next_renewal_deadline == mock_today + timedelta(days=180)
        assert new_cycle.cycle_number == original_cycle.cycle_number + 1

        monitoring_status = next((s for s in new_cycle.statuses if s.step_type == SupportPlanStep.monitoring), None)
        assert monitoring_status is not None
        assert monitoring_status.is_latest_status is True

        # モニタリングの期限日が正しく設定されていることを確認
        expected_due_date = (mock_now_utc.date() + timedelta(days=7))
        assert monitoring_status.due_date == expected_due_date


@pytest.mark.asyncio
async def test_upload_monitoring_report_in_cycle_2(
    db: AsyncSession,
    setup_recipient_with_initial_cycle: Tuple[UUID, int, UUID]
):
    """【正常系】サイクル2以降でモニタリングレポートをアップロードできること"""
    recipient_id, original_cycle_id, staff_id = setup_recipient_with_initial_cycle

    # サイクル1を完了させて、サイクル2を作成
    steps_to_complete = [
        (DeliverableType.assessment_sheet, "assessment.pdf"),
        (DeliverableType.draft_plan_pdf, "draft_plan.pdf"),
        (DeliverableType.staff_meeting_minutes, "staff_meeting.pdf"),
        (DeliverableType.final_plan_signed_pdf, "final_plan.pdf"),
    ]

    for deliverable_type, filename in steps_to_complete:
        await db.refresh(await db.get(SupportPlanCycle, original_cycle_id), attribute_names=["statuses"])
        deliverable_in = PlanDeliverableCreate(
            plan_cycle_id=original_cycle_id,
            deliverable_type=deliverable_type,
            file_path=f"/path/to/{filename}",
            original_filename=filename,
        )
        await support_plan_service.handle_deliverable_upload(
            db=db,
            deliverable_in=deliverable_in,
            uploaded_by_staff_id=staff_id
        )

    # サイクル2を取得
    from sqlalchemy import select
    cycle_2_stmt = select(SupportPlanCycle).where(
        SupportPlanCycle.welfare_recipient_id == recipient_id,
        SupportPlanCycle.is_latest_cycle == True
    ).options(selectinload(SupportPlanCycle.statuses))
    cycle_2 = (await db.execute(cycle_2_stmt)).scalar_one()

    assert cycle_2.cycle_number == 2

    # サイクル2でモニタリングレポートをアップロード
    deliverable_in = PlanDeliverableCreate(
        plan_cycle_id=cycle_2.id,
        deliverable_type=DeliverableType.monitoring_report_pdf,
        file_path="/path/to/monitoring_report.pdf",
        original_filename="monitoring_report.pdf",
    )

    # エラーが発生しないことを確認
    await support_plan_service.handle_deliverable_upload(
        db=db,
        deliverable_in=deliverable_in,
        uploaded_by_staff_id=staff_id
    )


@pytest.mark.asyncio
async def test_upload_violates_step_order_raises_error(
    db: AsyncSession,
    setup_recipient_with_initial_cycle: Tuple[UUID, int, UUID]
):
    """【異常系】ステップの順序を守らないアップロードはエラーになること"""
    recipient_id, cycle_id, staff_id = setup_recipient_with_initial_cycle

    # アセスメント(is_latest_status=True)が未完了の状態で、次の計画書原案をアップロードしようとする
    deliverable_in = PlanDeliverableCreate(
        plan_cycle_id=cycle_id,
        deliverable_type=DeliverableType.draft_plan_pdf, # 順序違反
        file_path="/path/to/draft_plan.pdf",
        original_filename="draft_plan.pdf",
    )

    with pytest.raises(InvalidStepOrderError, match="現在のステップは assessment です。draft_plan の成果物はアップロードできません。"):
        await support_plan_service.handle_deliverable_upload(
            db=db,
            deliverable_in=deliverable_in,
            uploaded_by_staff_id=staff_id
        )


@pytest.mark.asyncio
async def test_reupload_final_plan_does_not_create_duplicate_cycle(
    db: AsyncSession,
    setup_recipient_with_initial_cycle: Tuple[UUID, int, UUID]
):
    """【正常系】final_plan_signed_pdfを削除して再アップロードしても、重複するサイクルが作成されないこと"""
    recipient_id, original_cycle_id, staff_id = setup_recipient_with_initial_cycle

    # 前提となるステップを完了させる
    steps_to_complete = [
        (DeliverableType.assessment_sheet, "assessment.pdf"),
        (DeliverableType.draft_plan_pdf, "draft_plan.pdf"),
        (DeliverableType.staff_meeting_minutes, "staff_meeting.pdf"),
    ]

    for deliverable_type, filename in steps_to_complete:
        await db.refresh(await db.get(SupportPlanCycle, original_cycle_id), attribute_names=["statuses"])
        deliverable_in = PlanDeliverableCreate(
            plan_cycle_id=original_cycle_id,
            deliverable_type=deliverable_type,
            file_path=f"/path/to/{filename}",
            original_filename=filename,
        )
        await support_plan_service.handle_deliverable_upload(
            db=db,
            deliverable_in=deliverable_in,
            uploaded_by_staff_id=staff_id
        )

    # 最初のfinal_plan_signedアップロード
    deliverable_in = PlanDeliverableCreate(
        plan_cycle_id=original_cycle_id,
        deliverable_type=DeliverableType.final_plan_signed_pdf,
        file_path="/path/to/final_plan.pdf",
        original_filename="final_plan.pdf",
    )
    await support_plan_service.handle_deliverable_upload(
        db=db,
        deliverable_in=deliverable_in,
        uploaded_by_staff_id=staff_id
    )

    # サイクル2が作成されたことを確認
    from sqlalchemy import select
    cycle_2_stmt = select(SupportPlanCycle).where(
        SupportPlanCycle.welfare_recipient_id == recipient_id,
        SupportPlanCycle.cycle_number == 2
    )
    cycle_2 = (await db.execute(cycle_2_stmt)).scalar_one()
    assert cycle_2 is not None

    # final_plan_signed_pdfを削除（PlanDeliverableレコードを削除）
    from app.models.support_plan_cycle import PlanDeliverable
    delete_stmt = select(PlanDeliverable).where(
        PlanDeliverable.plan_cycle_id == original_cycle_id,
        PlanDeliverable.deliverable_type == DeliverableType.final_plan_signed_pdf
    )
    deliverable_to_delete = (await db.execute(delete_stmt)).scalar_one()
    await db.delete(deliverable_to_delete)

    # 元のサイクルのfinal_plan_signedのis_latest_statusをTrueに戻す
    original_cycle = await db.get(SupportPlanCycle, original_cycle_id, options=[selectinload(SupportPlanCycle.statuses)])
    staff_meeting_status = next((s for s in original_cycle.statuses if s.step_type == SupportPlanStep.staff_meeting), None)
    staff_meeting_status.is_latest_status = False

    final_plan_status = next((s for s in original_cycle.statuses if s.step_type == SupportPlanStep.final_plan_signed), None)
    final_plan_status.completed = False
    final_plan_status.completed_at = None
    final_plan_status.is_latest_status = True
    await db.commit()

    # 再度final_plan_signedをアップロード
    deliverable_in_reupload = PlanDeliverableCreate(
        plan_cycle_id=original_cycle_id,
        deliverable_type=DeliverableType.final_plan_signed_pdf,
        file_path="/path/to/final_plan_reupload.pdf",
        original_filename="final_plan_reupload.pdf",
    )
    await support_plan_service.handle_deliverable_upload(
        db=db,
        deliverable_in=deliverable_in_reupload,
        uploaded_by_staff_id=staff_id
    )

    # サイクルが2つのみであることを確認（重複していないこと）
    all_cycles_stmt = select(SupportPlanCycle).where(
        SupportPlanCycle.welfare_recipient_id == recipient_id
    )
    all_cycles = (await db.execute(all_cycles_stmt)).scalars().all()

    # サイクル1とサイクル2の2つのみであることを確認
    assert len(all_cycles) == 2
    assert any(c.cycle_number == 1 for c in all_cycles)
    assert any(c.cycle_number == 2 for c in all_cycles)

    # cycle_number=2のサイクルが1つだけであることを確認
    cycle_2_count = sum(1 for c in all_cycles if c.cycle_number == 2)
    assert cycle_2_count == 1
