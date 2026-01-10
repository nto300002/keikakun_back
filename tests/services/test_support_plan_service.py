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

# Configure logging to suppress SQL statements and show only application logs
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s:%(name)s:%(message)s'
)

# Suppress SQLAlchemy engine logs (SQL statements)
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
logging.getLogger('sqlalchemy.pool').setLevel(logging.WARNING)
logging.getLogger('sqlalchemy.dialects').setLevel(logging.WARNING)
logging.getLogger('sqlalchemy.orm').setLevel(logging.WARNING)

# Keep application logs visible
logging.getLogger('app').setLevel(logging.INFO)


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
        first_name="管理者",
        last_name="テスト",
        full_name="テスト 管理者",
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
        office_id=office_id,
        plan_cycle_start_date=None,
        next_renewal_deadline=None,
        is_latest_cycle=True,
        cycle_number=1
    )
    db.add(cycle)
    await db.flush()

    statuses = [
        SupportPlanStatus(plan_cycle_id=cycle.id, welfare_recipient_id=recipient.id, office_id=office_id, step_type=SupportPlanStep.assessment, is_latest_status=True),
        SupportPlanStatus(plan_cycle_id=cycle.id, welfare_recipient_id=recipient.id, office_id=office_id, step_type=SupportPlanStep.draft_plan, is_latest_status=False),
        SupportPlanStatus(plan_cycle_id=cycle.id, welfare_recipient_id=recipient.id, office_id=office_id, step_type=SupportPlanStep.staff_meeting, is_latest_status=False),
        SupportPlanStatus(plan_cycle_id=cycle.id, welfare_recipient_id=recipient.id, office_id=office_id, step_type=SupportPlanStep.final_plan_signed, is_latest_status=False),
        SupportPlanStatus(plan_cycle_id=cycle.id, welfare_recipient_id=recipient.id, office_id=office_id, step_type=SupportPlanStep.monitoring, is_latest_status=False),
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
async def test_upload_final_plan_does_not_create_new_cycle(
    db: AsyncSession,
    setup_recipient_with_initial_cycle: Tuple[UUID, int, UUID]
):
    """【正常系】最終計画書をアップロードしても、次サイクルは自動生成されないこと（新仕様）"""
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
        original_cycle_stmt = select(SupportPlanCycle).where(SupportPlanCycle.id == original_cycle_id).options(selectinload(SupportPlanCycle.statuses))
        original_cycle = (await db.execute(original_cycle_stmt)).scalar_one()

        # 【新仕様】final_plan_signed アップロード後も、サイクル1は最新のままであること
        assert original_cycle.is_latest_cycle is True, "final_plan_signed アップロード後も、サイクル1は最新のままであること"

        # final_plan_signedステータスが完了し、is_latest_status=Trueであることを確認
        final_plan_status = next((s for s in original_cycle.statuses if s.step_type == SupportPlanStep.final_plan_signed), None)
        assert final_plan_status is not None, "final_plan_signedステータスが存在すること"
        assert final_plan_status.completed is True, "final_plan_signedステータスが完了していること"
        assert final_plan_status.is_latest_status is False, "final_plan_signed完了後、次のステップ（monitoring）がlatest_statusになること"

        # 次のステップ（monitoring）がlatest_statusになることを確認
        monitoring_status = next((s for s in original_cycle.statuses if s.step_type == SupportPlanStep.monitoring), None)
        assert monitoring_status is not None, "monitoringステータスが存在すること"
        assert monitoring_status.is_latest_status is True, "final_plan_signed完了後、monitoringがlatest_statusになること"

        # 【新仕様】サイクル2はまだ作成されていないことを確認
        new_cycle_stmt = select(SupportPlanCycle).where(
            SupportPlanCycle.welfare_recipient_id == recipient_id,
            SupportPlanCycle.cycle_number == 2
        )
        new_cycle = (await db.execute(new_cycle_stmt)).scalar_one_or_none()
        assert new_cycle is None, "final_plan_signed アップロード後は、まだサイクル2は作成されていないこと"


@pytest.mark.asyncio
async def test_upload_monitoring_report_creates_new_cycle(
    db: AsyncSession,
    setup_recipient_with_initial_cycle: Tuple[UUID, int, UUID]
):
    """【TDD: Red Phase】モニタリング報告書をアップロードすると、次サイクルが自動生成されること

    新仕様: final_plan_signed_pdfではなく、monitoring_report_pdfアップロード時に
    次のサイクルが作成される。
    """
    recipient_id, original_cycle_id, staff_id = setup_recipient_with_initial_cycle

    # 前提となる全ステップを完了させる（モニタリングまで）
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

    # final_plan_signed_pdfアップロード後、まだサイクル2は作成されていないことを確認
    from sqlalchemy import select
    cycle_2_stmt_before = select(SupportPlanCycle).where(
        SupportPlanCycle.welfare_recipient_id == recipient_id,
        SupportPlanCycle.cycle_number == 2
    )
    cycle_2_before = (await db.execute(cycle_2_stmt_before)).scalar_one_or_none()
    assert cycle_2_before is None, "final_plan_signed_pdf アップロード後は、まだサイクル2は作成されていないこと"

    # モニタリング報告書をアップロード（ここで次サイクルが作成される）
    mock_today = date(2023, 10, 27)
    mock_now_utc = datetime(2023, 10, 27, 12, 0, 0, tzinfo=timezone.utc)

    with patch('app.services.support_plan_service.datetime.date') as mock_date, \
         patch('app.services.support_plan_service.datetime.datetime') as mock_datetime:

        mock_date.today.return_value = mock_today
        mock_datetime.now.return_value = mock_now_utc

        deliverable_in = PlanDeliverableCreate(
            plan_cycle_id=original_cycle_id,
            deliverable_type=DeliverableType.monitoring_report_pdf,
            file_path="/path/to/monitoring_report.pdf",
            original_filename="monitoring_report.pdf",
        )
        await support_plan_service.handle_deliverable_upload(
            db=db,
            deliverable_in=deliverable_in,
            uploaded_by_staff_id=staff_id
        )

        # 旧サイクルの確認
        original_cycle_stmt = select(SupportPlanCycle).where(
            SupportPlanCycle.id == original_cycle_id
        ).options(selectinload(SupportPlanCycle.statuses))
        original_cycle = (await db.execute(original_cycle_stmt)).scalar_one()
        assert original_cycle.is_latest_cycle is False, "旧サイクルはis_latest_cycle=Falseになること"

        # 旧サイクルのmonitoringステータスが完了していることを確認
        monitoring_status = next((s for s in original_cycle.statuses if s.step_type == SupportPlanStep.monitoring), None)
        assert monitoring_status is not None, "monitoringステータスが存在すること"
        assert monitoring_status.completed is True, "monitoringステータスが完了していること"
        assert monitoring_status.is_latest_status is True, "サイクル完了時、monitoringはis_latest_status=Trueであること"

        # 新サイクルの確認
        new_cycle_stmt = select(SupportPlanCycle).where(
            SupportPlanCycle.welfare_recipient_id == recipient_id,
            SupportPlanCycle.is_latest_cycle == True
        ).options(selectinload(SupportPlanCycle.statuses))
        new_cycle = (await db.execute(new_cycle_stmt)).scalar_one_or_none()

        assert new_cycle is not None, "モニタリング報告書アップロード後、新サイクルが作成されること"
        assert new_cycle.plan_cycle_start_date == mock_today
        assert new_cycle.next_renewal_deadline == mock_today + timedelta(days=180)
        assert new_cycle.cycle_number == original_cycle.cycle_number + 1

        # 全5ステップが作成されていることを確認
        step_types = {status.step_type for status in new_cycle.statuses}
        assert step_types == {
            SupportPlanStep.assessment,
            SupportPlanStep.draft_plan,
            SupportPlanStep.staff_meeting,
            SupportPlanStep.final_plan_signed,
            SupportPlanStep.monitoring
        }

        # assessmentがlatest_statusになっていることを確認
        assessment_status = next((s for s in new_cycle.statuses if s.step_type == SupportPlanStep.assessment), None)
        assert assessment_status is not None
        assert assessment_status.is_latest_status is True

        # モニタリングステータスも存在し、期限日が正しく設定されていることを確認
        new_monitoring_status = next((s for s in new_cycle.statuses if s.step_type == SupportPlanStep.monitoring), None)
        assert new_monitoring_status is not None
        expected_due_date = (mock_now_utc.date() + timedelta(days=7))
        assert new_monitoring_status.due_date == expected_due_date


@pytest.mark.asyncio
async def test_upload_monitoring_report_in_cycle_2(
    db: AsyncSession,
    setup_recipient_with_initial_cycle: Tuple[UUID, int, UUID]
):
    """【正常系】サイクル2以降でモニタリングレポートをアップロードできること（サイクル統一後）"""
    recipient_id, original_cycle_id, staff_id = setup_recipient_with_initial_cycle

    # サイクル1を完了させて、サイクル2を作成（新仕様：monitoringまで完了）
    steps_to_complete = [
        (DeliverableType.assessment_sheet, "assessment.pdf"),
        (DeliverableType.draft_plan_pdf, "draft_plan.pdf"),
        (DeliverableType.staff_meeting_minutes, "staff_meeting.pdf"),
        (DeliverableType.final_plan_signed_pdf, "final_plan.pdf"),
        (DeliverableType.monitoring_report_pdf, "monitoring.pdf"),  # 新仕様：これがサイクル2を作成
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

    # サイクル2がデータベースに確実に存在することを確認
    await db.flush()
    await db.refresh(cycle_2)

    assert cycle_2.cycle_number == 2

    # サイクル2でも全ステップを順番にアップロード（サイクル統一後はassessmentから開始）
    # 新仕様：monitoring_report_pdfアップロード時に新サイクルが作成される
    cycle_2_steps = [
        (DeliverableType.assessment_sheet, "assessment2.pdf"),
        (DeliverableType.draft_plan_pdf, "draft_plan2.pdf"),
        (DeliverableType.staff_meeting_minutes, "staff_meeting2.pdf"),
        (DeliverableType.final_plan_signed_pdf, "final_plan2.pdf"),
        (DeliverableType.monitoring_report_pdf, "monitoring2.pdf"),  # 新仕様：これがサイクル3を作成
    ]

    for deliverable_type, filename in cycle_2_steps:
        await db.refresh(cycle_2, attribute_names=["statuses"])
        deliverable_in = PlanDeliverableCreate(
            plan_cycle_id=cycle_2.id,
            deliverable_type=deliverable_type,
            file_path=f"/path/to/{filename}",
            original_filename=filename,
        )
        # エラーが発生しないことを確認
        await support_plan_service.handle_deliverable_upload(
            db=db,
            deliverable_in=deliverable_in,
            uploaded_by_staff_id=staff_id
        )

    # 最後のmonitoring_report_pdfアップロードにより、サイクル3が作成されたことを確認
    cycle_3_stmt = select(SupportPlanCycle).where(
        SupportPlanCycle.welfare_recipient_id == recipient_id,
        SupportPlanCycle.cycle_number == 3
    )
    cycle_3 = (await db.execute(cycle_3_stmt)).scalar_one_or_none()
    assert cycle_3 is not None, "monitoring_report_pdf アップロード後、新サイクルが作成されること"


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
async def test_reupload_monitoring_does_not_create_duplicate_cycle(
    db: AsyncSession,
    setup_recipient_with_initial_cycle: Tuple[UUID, int, UUID]
):
    """【正常系】monitoring_report_pdfを削除して再アップロードしても、重複するサイクルが作成されないこと（新仕様）"""
    recipient_id, original_cycle_id, staff_id = setup_recipient_with_initial_cycle

    # 前提となるステップを完了させる
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

    # 最初のmonitoring_report_pdfアップロード（新仕様：これがサイクル2を作成）
    deliverable_in = PlanDeliverableCreate(
        plan_cycle_id=original_cycle_id,
        deliverable_type=DeliverableType.monitoring_report_pdf,
        file_path="/path/to/monitoring.pdf",
        original_filename="monitoring.pdf",
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

    # monitoring_report_pdfを削除（PlanDeliverableレコードを削除）
    from app.models.support_plan_cycle import PlanDeliverable
    delete_stmt = select(PlanDeliverable).where(
        PlanDeliverable.plan_cycle_id == original_cycle_id,
        PlanDeliverable.deliverable_type == DeliverableType.monitoring_report_pdf
    )
    deliverable_to_delete = (await db.execute(delete_stmt)).scalar_one()
    await db.delete(deliverable_to_delete)

    # 元のサイクルのmonitoringのis_latest_statusをTrueに戻す
    original_cycle = await db.get(SupportPlanCycle, original_cycle_id, options=[selectinload(SupportPlanCycle.statuses)])
    final_plan_status = next((s for s in original_cycle.statuses if s.step_type == SupportPlanStep.final_plan_signed), None)
    final_plan_status.is_latest_status = False

    monitoring_status = next((s for s in original_cycle.statuses if s.step_type == SupportPlanStep.monitoring), None)
    monitoring_status.completed = False
    monitoring_status.completed_at = None
    monitoring_status.is_latest_status = True
    await db.commit()

    # 再度monitoring_report_pdfをアップロード
    deliverable_in_reupload = PlanDeliverableCreate(
        plan_cycle_id=original_cycle_id,
        deliverable_type=DeliverableType.monitoring_report_pdf,
        file_path="/path/to/monitoring_reupload.pdf",
        original_filename="monitoring_reupload.pdf",
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


# ==================== Phase 3: カレンダー連携統合テスト ====================

@pytest.mark.asyncio
async def test_monitoring_upload_creates_calendar_event(
    db: AsyncSession,
    setup_recipient_with_initial_cycle: Tuple[UUID, int, UUID]
):
    """【統合テスト】モニタリング報告書アップロード時に更新期限イベントが自動作成されること（新仕様）"""
    from app import crud
    from app.services.calendar_service import calendar_service
    from app.schemas.calendar_account import CalendarSetupRequest
    from app.models.enums import CalendarConnectionStatus, CalendarEventType
    import json

    recipient_id, original_cycle_id, staff_id = setup_recipient_with_initial_cycle

    # 事業所IDを取得
    from sqlalchemy import select
    cycle_stmt = select(SupportPlanCycle).where(SupportPlanCycle.id == original_cycle_id)
    cycle = (await db.execute(cycle_stmt)).scalar_one()
    office_id = cycle.office_id

    # カレンダーアカウントを設定
    service_account_json = json.dumps({
        "type": "service_account",
        "project_id": "test-project",
        "private_key_id": "test-key-id",
        "private_key": "-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----\n",
        "client_email": "test@test.iam.gserviceaccount.com",
        "client_id": "123456",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/test"
    })

    setup_request = CalendarSetupRequest(
        office_id=office_id,
        google_calendar_id=f"test-{uuid4().hex[:8]}@group.calendar.google.com",
        service_account_json=service_account_json,
        calendar_name="テストカレンダー"
    )
    account = await calendar_service.setup_office_calendar(db=db, request=setup_request)
    await calendar_service.update_connection_status(
        db=db,
        account_id=account.id,
        status=CalendarConnectionStatus.connected
    )

    # 前提となるステップを完了させる（新仕様：monitoringまで完了）
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

    # モニタリング報告書をアップロード（新仕様：これがサイクル2を作成）
    deliverable_in = PlanDeliverableCreate(
        plan_cycle_id=original_cycle_id,
        deliverable_type=DeliverableType.monitoring_report_pdf,
        file_path="/path/to/monitoring.pdf",
        original_filename="monitoring.pdf",
    )
    await support_plan_service.handle_deliverable_upload(
        db=db,
        deliverable_in=deliverable_in,
        uploaded_by_staff_id=staff_id
    )

    # 新しいサイクルを取得
    new_cycle_stmt = select(SupportPlanCycle).where(
        SupportPlanCycle.welfare_recipient_id == recipient_id,
        SupportPlanCycle.is_latest_cycle == True
    ).options(selectinload(SupportPlanCycle.statuses))
    new_cycle = (await db.execute(new_cycle_stmt)).scalar_one()

    # 全5ステップが作成されていることを確認
    step_types = {status.step_type for status in new_cycle.statuses}
    assert step_types == {
        SupportPlanStep.assessment,
        SupportPlanStep.draft_plan,
        SupportPlanStep.staff_meeting,
        SupportPlanStep.final_plan_signed,
        SupportPlanStep.monitoring
    }

    # 更新期限イベントが作成されたことを確認
    events = await crud.calendar_event.get_by_cycle_id(db=db, cycle_id=new_cycle.id)
    renewal_events = [e for e in events if e.event_type == CalendarEventType.renewal_deadline]

    assert len(renewal_events) == 1, "更新期限イベントが1つ作成されているべき"
    renewal_event = renewal_events[0]
    assert renewal_event.welfare_recipient_id == recipient_id
    assert renewal_event.office_id == office_id
    assert "更新期限" in renewal_event.event_title

    # モニタリング期限イベントも作成されたことを確認
    monitoring_status = next((s for s in new_cycle.statuses if s.step_type == SupportPlanStep.monitoring), None)
    assert monitoring_status is not None

    monitoring_events = await crud.calendar_event.get_by_status_id(db=db, status_id=monitoring_status.id)
    monitoring_deadline_events = [e for e in monitoring_events if e.event_type == CalendarEventType.monitoring_deadline]

    assert len(monitoring_deadline_events) == 1, "モニタリング期限イベントが1つ作成されているべき"
    monitoring_event = monitoring_deadline_events[0]
    assert monitoring_event.welfare_recipient_id == recipient_id
    assert monitoring_event.office_id == office_id
    assert "次の個別支援計画の開始期限" in monitoring_event.event_title


@pytest.mark.asyncio
async def test_monitoring_upload_without_calendar_account_succeeds(
    db: AsyncSession,
    setup_recipient_with_initial_cycle: Tuple[UUID, int, UUID]
):
    """【統合テスト】カレンダー未設定でもモニタリング報告書アップロードは成功すること（新仕様）"""
    recipient_id, original_cycle_id, staff_id = setup_recipient_with_initial_cycle

    # カレンダーアカウントを設定しない

    # 前提となるステップを完了させる（新仕様：monitoringまで完了）
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

    # deliverableアップロード後、セッションをflushして変更を確定
    await db.flush()

    # モニタリング報告書をアップロード（新仕様：これがサイクル2を作成、エラーが発生しないことを確認）
    deliverable_in = PlanDeliverableCreate(
        plan_cycle_id=original_cycle_id,
        deliverable_type=DeliverableType.monitoring_report_pdf,
        file_path="/path/to/monitoring.pdf",
        original_filename="monitoring.pdf",
    )

    # エラーが発生しないことを確認
    await support_plan_service.handle_deliverable_upload(
        db=db,
        deliverable_in=deliverable_in,
        uploaded_by_staff_id=staff_id
    )

    # 新しいサイクルが作成されたことを確認
    from sqlalchemy import select
    new_cycle_stmt = select(SupportPlanCycle).where(
        SupportPlanCycle.welfare_recipient_id == recipient_id,
        SupportPlanCycle.is_latest_cycle == True
    )
    new_cycle = (await db.execute(new_cycle_stmt)).scalar_one()
    assert new_cycle is not None
    assert new_cycle.cycle_number == 2


class TestCalendarEventDeletionHooks:
    """カレンダーイベント削除フックのテスト"""

    async def test_delete_renewal_event_on_final_plan_completion(self, db: AsyncSession):
        """final_plan_signed完了時に更新期限イベントが削除されることを確認"""
        from app.models.calendar_events import CalendarEvent
        from app.models.calendar_account import OfficeCalendarAccount
        from app.models.enums import CalendarEventType, CalendarConnectionStatus, CalendarSyncStatus
        from app.services.calendar_service import calendar_service
        import json

        # スタッフと事業所を作成
        staff = Staff(
            first_name="管理者",
            last_name="テスト",
            full_name="テスト 管理者",
            email=f"test_{uuid4()}@example.com",
            hashed_password=get_password_hash("password"),
            role=StaffRole.owner
        )
        db.add(staff)
        await db.flush()

        office = Office(
            name="テスト事業所",
            type=OfficeType.type_A_office,
            created_by=staff.id,
            last_modified_by=staff.id
        )
        db.add(office)
        await db.flush()

        # カレンダーアカウントを作成
        valid_sa_json = json.dumps({
            "type": "service_account",
            "project_id": "test",
            "private_key_id": "test-key-id",
            "private_key": "-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----\n",
            "client_email": "test@test.iam.gserviceaccount.com",
            "client_id": "123456"
        })
        from app.schemas.calendar_account import CalendarSetupRequest
        setup_req = CalendarSetupRequest(
            office_id=office.id,
            google_calendar_id=f"test-{uuid4().hex[:8]}@group.calendar.google.com",
            service_account_json=valid_sa_json,
            calendar_name="テストカレンダー"
        )
        account = await calendar_service.setup_office_calendar(db=db, request=setup_req)
        await calendar_service.update_connection_status(
            db=db,
            account_id=account.id,
            status=CalendarConnectionStatus.connected
        )

        # 利用者を作成
        recipient = WelfareRecipient(
            first_name="太郎",
            last_name="テスト",
            first_name_furigana="たろう",
            last_name_furigana="てすと",
            birth_day=date(1990, 1, 1),
            gender=GenderType.male
        )
        db.add(recipient)
        await db.flush()

        # サイクルを作成
        cycle_start = date.today()
        cycle = SupportPlanCycle(
            welfare_recipient_id=recipient.id,
            office_id=office.id,
            plan_cycle_start_date=cycle_start,
            next_renewal_deadline=cycle_start + timedelta(days=180),
            cycle_number=1,
            is_latest_cycle=True
        )
        db.add(cycle)
        await db.flush()

        # ステータスを作成
        status = SupportPlanStatus(
            welfare_recipient_id=recipient.id,
            plan_cycle_id=cycle.id,
            office_id=office.id,
            step_type=SupportPlanStep.final_plan_signed,
            completed=False,
            is_latest_status=True
        )
        db.add(status)
        await db.flush()

        # 更新期限イベントを作成
        event_ids = await calendar_service.create_renewal_deadline_events(
            db=db,
            office_id=office.id,
            welfare_recipient_id=recipient.id,
            cycle_id=cycle.id,
            next_renewal_deadline=cycle.next_renewal_deadline
        )
        assert len(event_ids) == 1

        # イベントが存在することを確認
        from sqlalchemy import select
        event_stmt = select(CalendarEvent).where(
            CalendarEvent.support_plan_cycle_id == cycle.id,
            CalendarEvent.event_type == CalendarEventType.renewal_deadline
        )
        event = (await db.execute(event_stmt)).scalar_one_or_none()
        assert event is not None

        # final_plan_signedを完了にする
        await support_plan_service.update_status_completion(
            db=db,
            status_id=status.id,
            completed=True
        )
        await db.commit()

        # イベントが削除されたことを確認
        event_after = (await db.execute(event_stmt)).scalar_one_or_none()
        assert event_after is None

    async def test_delete_monitoring_event_on_monitoring_completion(self, db: AsyncSession):
        """monitoring完了時にモニタリングイベントが削除されることを確認"""
        from app.models.calendar_events import CalendarEvent
        from app.models.calendar_account import OfficeCalendarAccount
        from app.models.enums import CalendarEventType, CalendarConnectionStatus, CalendarSyncStatus
        from app.services.calendar_service import calendar_service
        import json

        # スタッフと事業所を作成
        staff = Staff(
            first_name="管理者",
            last_name="テスト",
            full_name="テスト 管理者",
            email=f"test_{uuid4()}@example.com",
            hashed_password=get_password_hash("password"),
            role=StaffRole.owner
        )
        db.add(staff)
        await db.flush()

        office = Office(
            name="テスト事業所",
            type=OfficeType.type_A_office,
            created_by=staff.id,
            last_modified_by=staff.id
        )
        db.add(office)
        await db.flush()

        # カレンダーアカウントを作成
        valid_sa_json = json.dumps({
            "type": "service_account",
            "project_id": "test",
            "private_key_id": "test-key-id",
            "private_key": "-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----\n",
            "client_email": "test@test.iam.gserviceaccount.com",
            "client_id": "123456"
        })
        from app.schemas.calendar_account import CalendarSetupRequest
        setup_req = CalendarSetupRequest(
            office_id=office.id,
            google_calendar_id=f"test-{uuid4().hex[:8]}@group.calendar.google.com",
            service_account_json=valid_sa_json,
            calendar_name="テストカレンダー"
        )
        account = await calendar_service.setup_office_calendar(db=db, request=setup_req)
        await calendar_service.update_connection_status(
            db=db,
            account_id=account.id,
            status=CalendarConnectionStatus.connected
        )

        # 利用者を作成
        recipient = WelfareRecipient(
            first_name="次郎",
            last_name="テスト",
            first_name_furigana="じろう",
            last_name_furigana="てすと",
            birth_day=date(1992, 2, 2),
            gender=GenderType.male
        )
        db.add(recipient)
        await db.flush()

        # サイクルを作成（cycle_number=2でモニタリングイベント作成可能）
        cycle_start = date.today()
        cycle = SupportPlanCycle(
            welfare_recipient_id=recipient.id,
            office_id=office.id,
            plan_cycle_start_date=cycle_start,
            next_renewal_deadline=cycle_start + timedelta(days=180),
            cycle_number=2,
            is_latest_cycle=True
        )
        db.add(cycle)
        await db.flush()

        # monitoringステータスを作成
        status = SupportPlanStatus(
            welfare_recipient_id=recipient.id,
            plan_cycle_id=cycle.id,
            office_id=office.id,
            step_type=SupportPlanStep.monitoring,
            completed=False,
            is_latest_status=True
        )
        db.add(status)
        await db.flush()

        # モニタリングイベントを作成
        event_ids = await calendar_service.create_monitoring_deadline_events(
            db=db,
            office_id=office.id,
            welfare_recipient_id=recipient.id,
            cycle_id=cycle.id,
            cycle_start_date=cycle_start,
            cycle_number=cycle.cycle_number,
            status_id=status.id  # status_idを渡してイベントに紐付け
        )
        assert len(event_ids) == 1

        # イベントが存在することを確認
        from sqlalchemy import select
        event_stmt = select(CalendarEvent).where(
            CalendarEvent.support_plan_status_id == status.id,
            CalendarEvent.event_type == CalendarEventType.monitoring_deadline
        )
        event = (await db.execute(event_stmt)).scalar_one_or_none()
        assert event is not None

        # monitoringを完了にする
        await support_plan_service.update_status_completion(
            db=db,
            status_id=status.id,
            completed=True
        )
        await db.commit()

        # イベントが削除されたことを確認
        event_after = (await db.execute(event_stmt)).scalar_one_or_none()
        assert event_after is None
