import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from datetime import date, datetime
import io
import logging
import boto3
from moto import mock_aws

logging.basicConfig()
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

from app.models.welfare_recipient import WelfareRecipient, OfficeWelfareRecipient
from app.models.support_plan_cycle import SupportPlanCycle, SupportPlanStatus, PlanDeliverable
from app.models.office import Office, OfficeStaff
from app.models.staff import Staff
from app.models.enums import GenderType, SupportPlanStep, DeliverableType
from app.main import app
from app.api.deps import get_current_user, get_db
from app.core.config import settings


@pytest.fixture(scope="function")
def aws_credentials(monkeypatch):
    """Mock AWS Credentials for moto."""
    # monkeypatchを使用して環境変数を設定（テスト終了後に自動的に元に戻る）
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


@pytest.fixture(scope="function")
def s3_mock(aws_credentials, monkeypatch):
    """S3 mock context manager."""
    with mock_aws():
        # S3クライアントを作成してバケットを作成
        s3_client = boto3.client("s3", region_name="us-east-1")
        bucket_name = "test-plan-deliverables-bucket"
        s3_client.create_bucket(Bucket=bucket_name)

        # monkeypatchを使用してsettingsを変更（テスト終了後に自動的に元に戻る）
        monkeypatch.setattr(settings, "S3_BUCKET_NAME", bucket_name)
        monkeypatch.setattr(settings, "S3_ENDPOINT_URL", None)

        yield s3_client


@pytest.mark.asyncio
async def test_reupload_deliverable_replaces_file(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_admin_user: Staff,
    office_factory,
    s3_mock
):
    """
    PUT /api/v1/support-plans/deliverables/{deliverable_id}
    既存の成果物を再アップロード（上書き）できることを確認
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
    association = OfficeWelfareRecipient(office_id=office.id, welfare_recipient_id=recipient.id)
    db_session.add(association)
    await db_session.flush()

    # サイクルを作成
    cycle = SupportPlanCycle(
        welfare_recipient_id=recipient.id,
        office_id=office.id,
        plan_cycle_start_date=date(2024, 1, 1),
        is_latest_cycle=True,
        cycle_number=1,
    )
    db_session.add(cycle)
    await db_session.flush()

    # ステータスを作成（assessmentは完了済み）
    statuses = [
        SupportPlanStatus(
            plan_cycle_id=cycle.id,
            welfare_recipient_id=recipient.id,
            office_id=office.id,
            step_type=SupportPlanStep.assessment,
            is_latest_status=False,
            completed=True,
            completed_at=datetime(2024, 1, 15),
        ),
        SupportPlanStatus(
            plan_cycle_id=cycle.id,
            welfare_recipient_id=recipient.id,
            office_id=office.id,
            step_type=SupportPlanStep.draft_plan,
            is_latest_status=True,
            completed=False,
        ),
    ]
    db_session.add_all(statuses)
    await db_session.flush()

    # 既存のdeliverableを作成
    old_object_name = f"plan-deliverables/{cycle.id}/assessment/old-assessment.pdf"
    old_pdf_content = b"%PDF-1.4 old content"
    s3_mock.put_object(
        Bucket=settings.S3_BUCKET_NAME,
        Key=old_object_name,
        Body=old_pdf_content
    )

    existing_deliverable = PlanDeliverable(
        plan_cycle_id=cycle.id,
        deliverable_type=DeliverableType.assessment_sheet,
        file_path=f"s3://{settings.S3_BUCKET_NAME}/{old_object_name}",
        original_filename="old-assessment.pdf",
        uploaded_by=test_admin_user.id
    )
    db_session.add(existing_deliverable)
    await db_session.commit()

    # 2. 依存関係のオーバーライド（get_dbは async_client fixture で既にオーバーライド済み）
    async def override_get_current_user_with_relations():
        stmt = select(Staff).where(Staff.id == test_admin_user.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        ).execution_options(populate_existing=True)
        result = await db_session.execute(stmt)
        user = result.scalars().first()
        return user

    app.dependency_overrides[get_current_user] = override_get_current_user_with_relations

    # 3. 新しいPDFで再アップロード
    new_pdf_content = b"%PDF-1.4 new updated content"
    files = {
        "file": ("new-assessment.pdf", io.BytesIO(new_pdf_content), "application/pdf")
    }

    response = await async_client.put(
        f"/api/v1/support-plans/deliverables/{existing_deliverable.id}",
        files=files
    )

    # 4. レスポンスの検証
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["id"] == existing_deliverable.id
    assert response_data["original_filename"] == "new-assessment.pdf"

    # 5. DBの状態を検証
    await db_session.refresh(existing_deliverable)

    # ファイルパスが更新されていることを確認
    assert "new-assessment.pdf" in existing_deliverable.file_path
    assert existing_deliverable.file_path != f"s3://{settings.S3_BUCKET_NAME}/{old_object_name}"

    # 6. 新しいファイルがS3にアップロードされたことを確認
    new_object_name = existing_deliverable.file_path.replace(f"s3://{settings.S3_BUCKET_NAME}/", "")
    s3_response = s3_mock.get_object(Bucket=settings.S3_BUCKET_NAME, Key=new_object_name)
    s3_data = s3_response["Body"].read()
    assert s3_data == new_pdf_content

    # 7. ステータスは変更されていないことを確認（既に完了済み）
    stmt = select(SupportPlanStatus).where(
        SupportPlanStatus.plan_cycle_id == cycle.id,
        SupportPlanStatus.step_type == SupportPlanStep.assessment
    )
    result = await db_session.execute(stmt)
    assessment_status = result.scalar_one()
    assert assessment_status.completed is True

    # クリーンアップ
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_delete_deliverable_reverts_status(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_admin_user: Staff,
    office_factory,
    s3_mock
):
    """
    DELETE /api/v1/support-plans/deliverables/{deliverable_id}
    成果物を削除すると、対応するステータスが未完了に戻ることを確認
    """
    # 1. テストデータの準備
    office = await office_factory(creator=test_admin_user)
    db_session.add(OfficeStaff(staff_id=test_admin_user.id, office_id=office.id, is_primary=True))
    await db_session.flush()

    # 利用者を作成
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

    # 事業所と利用者の関連を作成
    association = OfficeWelfareRecipient(office_id=office.id, welfare_recipient_id=recipient.id)
    db_session.add(association)
    await db_session.flush()

    # サイクルを作成
    cycle = SupportPlanCycle(
        welfare_recipient_id=recipient.id,
        office_id=office.id,
        plan_cycle_start_date=date(2024, 1, 1),
        is_latest_cycle=True,
        cycle_number=1,
    )
    db_session.add(cycle)
    await db_session.flush()

    # ステータスを作成（assessmentは完了済み）
    statuses = [
        SupportPlanStatus(
            plan_cycle_id=cycle.id,
            welfare_recipient_id=recipient.id,
            office_id=office.id,
            step_type=SupportPlanStep.assessment,
            is_latest_status=False,
            completed=True,
            completed_at=datetime(2024, 1, 15),
            completed_by=test_admin_user.id,
        ),
        SupportPlanStatus(
            plan_cycle_id=cycle.id,
            welfare_recipient_id=recipient.id,
            office_id=office.id,
            step_type=SupportPlanStep.draft_plan,
            is_latest_status=True,
            completed=False,
        ),
    ]
    db_session.add_all(statuses)
    await db_session.flush()

    # 既存のdeliverableを作成
    object_name = f"plan-deliverables/{cycle.id}/assessment/test-assessment.pdf"
    pdf_content = b"%PDF-1.4 test content"
    s3_mock.put_object(
        Bucket=settings.S3_BUCKET_NAME,
        Key=object_name,
        Body=pdf_content
    )

    deliverable = PlanDeliverable(
        plan_cycle_id=cycle.id,
        deliverable_type=DeliverableType.assessment_sheet,
        file_path=f"s3://{settings.S3_BUCKET_NAME}/{object_name}",
        original_filename="test-assessment.pdf",
        uploaded_by=test_admin_user.id
    )
    db_session.add(deliverable)
    await db_session.commit()

    # 2. 依存関係のオーバーライド（get_dbは async_client fixture で既にオーバーライド済み）
    async def override_get_current_user_with_relations():
        stmt = select(Staff).where(Staff.id == test_admin_user.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        ).execution_options(populate_existing=True)
        result = await db_session.execute(stmt)
        user = result.scalars().first()
        return user

    app.dependency_overrides[get_current_user] = override_get_current_user_with_relations

    # 3. 削除リクエスト
    response = await async_client.delete(f"/api/v1/support-plans/deliverables/{deliverable.id}")

    # 4. レスポンスの検証
    assert response.status_code == 204

    # 5. DBの状態を検証 - deliverableが削除されたことを確認
    stmt = select(PlanDeliverable).where(PlanDeliverable.id == deliverable.id)
    result = await db_session.execute(stmt)
    deleted_deliverable = result.scalar_one_or_none()
    assert deleted_deliverable is None

    # 6. ステータスが未完了に戻っていることを確認
    stmt = select(SupportPlanStatus).where(
        SupportPlanStatus.plan_cycle_id == cycle.id,
        SupportPlanStatus.step_type == SupportPlanStep.assessment
    )
    result = await db_session.execute(stmt)
    assessment_status = result.scalar_one()

    assert assessment_status.completed is False
    assert assessment_status.completed_at is None
    assert assessment_status.completed_by is None
    assert assessment_status.is_latest_status is True  # 最新ステップに戻る

    # 7. 次のステップが最新でなくなっていることを確認
    stmt = select(SupportPlanStatus).where(
        SupportPlanStatus.plan_cycle_id == cycle.id,
        SupportPlanStatus.step_type == SupportPlanStep.draft_plan
    )
    result = await db_session.execute(stmt)
    draft_plan_status = result.scalar_one()
    assert draft_plan_status.is_latest_status is False

    # クリーンアップ
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_reupload_final_plan_does_not_create_duplicate_cycle(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_admin_user: Staff,
    office_factory,
    s3_mock
):
    """
    PUT /api/v1/support-plans/deliverables/{deliverable_id}
    署名済み計画書を再アップロードしても、重複してサイクルが作成されないことを確認
    """
    # 1. テストデータの準備
    office = await office_factory(creator=test_admin_user)
    db_session.add(OfficeStaff(staff_id=test_admin_user.id, office_id=office.id, is_primary=True))
    await db_session.flush()

    # 利用者を作成
    recipient = WelfareRecipient(
        first_name="テスト",
        last_name="次郎",
        first_name_furigana="テスト",
        last_name_furigana="ジロウ",
        birth_day=date(1995, 3, 20),
        gender=GenderType.male,
    )
    db_session.add(recipient)
    await db_session.flush()

    # 事業所と利用者の関連を作成
    association = OfficeWelfareRecipient(office_id=office.id, welfare_recipient_id=recipient.id)
    db_session.add(association)
    await db_session.flush()

    # サイクル1を作成（全ステップ完了済み）
    cycle1 = SupportPlanCycle(
        welfare_recipient_id=recipient.id,
        office_id=office.id,
        plan_cycle_start_date=date(2024, 1, 1),
        is_latest_cycle=False,
        cycle_number=1,
    )
    db_session.add(cycle1)
    await db_session.flush()

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
    await db_session.flush()

    # サイクル2を作成（最新サイクル、既に存在）
    cycle2 = SupportPlanCycle(
        welfare_recipient_id=recipient.id,
        office_id=office.id,
        plan_cycle_start_date=date(2024, 7, 1),
        is_latest_cycle=True,
        cycle_number=2,
    )
    db_session.add(cycle2)
    await db_session.flush()

    statuses2 = [
        SupportPlanStatus(
            plan_cycle_id=cycle2.id,
            welfare_recipient_id=recipient.id,
            office_id=office.id,
            step_type=SupportPlanStep.monitoring,
            is_latest_status=True,
            completed=False,
        ),
    ]
    db_session.add_all(statuses2)
    await db_session.flush()

    # 既存のfinal_plan deliverableを作成
    old_object_name = f"plan-deliverables/{cycle1.id}/final_plan/old-final.pdf"
    old_pdf_content = b"%PDF-1.4 old final plan"
    s3_mock.put_object(
        Bucket=settings.S3_BUCKET_NAME,
        Key=old_object_name,
        Body=old_pdf_content
    )

    final_deliverable = PlanDeliverable(
        plan_cycle_id=cycle1.id,
        deliverable_type=DeliverableType.final_plan_signed_pdf,
        file_path=f"s3://{settings.S3_BUCKET_NAME}/{old_object_name}",
        original_filename="old-final.pdf",
        uploaded_by=test_admin_user.id
    )
    db_session.add(final_deliverable)
    await db_session.commit()

    # 2. 依存関係のオーバーライド（get_dbは async_client fixture で既にオーバーライド済み）
    async def override_get_current_user_with_relations():
        stmt = select(Staff).where(Staff.id == test_admin_user.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        ).execution_options(populate_existing=True)
        result = await db_session.execute(stmt)
        user = result.scalars().first()
        return user

    app.dependency_overrides[get_current_user] = override_get_current_user_with_relations

    # 3. 署名済み計画書を再アップロード
    new_pdf_content = b"%PDF-1.4 new final plan signed"
    files = {
        "file": ("new-final.pdf", io.BytesIO(new_pdf_content), "application/pdf")
    }

    response = await async_client.put(
        f"/api/v1/support-plans/deliverables/{final_deliverable.id}",
        files=files
    )

    # 4. レスポンスの検証
    assert response.status_code == 200

    # 5. サイクルが重複して作成されていないことを確認
    stmt = select(SupportPlanCycle).where(
        SupportPlanCycle.welfare_recipient_id == recipient.id
    ).order_by(SupportPlanCycle.cycle_number)
    result = await db_session.execute(stmt)
    all_cycles = result.scalars().all()

    # サイクルは2つのまま（cycle1とcycle2のみ）
    assert len(all_cycles) == 2
    assert all_cycles[0].cycle_number == 1
    assert all_cycles[1].cycle_number == 2

    # サイクル3が作成されていないことを確認
    cycle3_exists = any(c.cycle_number == 3 for c in all_cycles)
    assert cycle3_exists is False

    # クリーンアップ
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_delete_deliverable_unauthorized(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_admin_user: Staff,
    office_factory,
    s3_mock
):
    """
    DELETE /api/v1/support-plans/deliverables/{deliverable_id}
    他の事業所のdeliverableを削除しようとした場合、403エラーを返すことを確認
    """
    # 事業所1（test_admin_userが所属）
    office1 = await office_factory(creator=test_admin_user)
    db_session.add(OfficeStaff(staff_id=test_admin_user.id, office_id=office1.id, is_primary=True))

    # 別のスタッフと事業所2を作成
    other_staff = Staff(
        email="other@example.com",
        hashed_password="hashed",
        name="他のスタッフ",
        role="employee",
    )
    db_session.add(other_staff)
    await db_session.flush()

    office2 = await office_factory(creator=other_staff)

    # 事業所2に属する利用者を作成
    recipient = WelfareRecipient(
        first_name="別",
        last_name="利用者",
        first_name_furigana="ベツ",
        last_name_furigana="リヨウシャ",
        birth_day=date(1988, 8, 8),
        gender=GenderType.male,
    )
    db_session.add(recipient)
    await db_session.flush()

    # 事業所2と利用者の関連
    association = OfficeWelfareRecipient(office_id=office2.id, welfare_recipient_id=recipient.id)
    db_session.add(association)
    await db_session.flush()

    # サイクルを作成
    cycle = SupportPlanCycle(
        welfare_recipient_id=recipient.id,
        office_id=office2.id,
        plan_cycle_start_date=date(2024, 1, 1),
        is_latest_cycle=True,
        cycle_number=1,
    )
    db_session.add(cycle)
    await db_session.flush()

    # PlanDeliverableレコードを作成
    object_name = f"plan-deliverables/{cycle.id}/assessment/test.pdf"
    deliverable = PlanDeliverable(
        plan_cycle_id=cycle.id,
        deliverable_type=DeliverableType.assessment_sheet,
        file_path=f"s3://{settings.S3_BUCKET_NAME}/{object_name}",
        original_filename="test.pdf",
        uploaded_by=other_staff.id
    )
    db_session.add(deliverable)
    await db_session.commit()

    # 依存関係のオーバーライド（test_admin_userでログイン、get_dbは async_client fixture で既にオーバーライド済み）
    async def override_get_current_user_with_relations():
        stmt = select(Staff).where(Staff.id == test_admin_user.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        ).execution_options(populate_existing=True)
        result = await db_session.execute(stmt)
        user = result.scalars().first()
        return user

    app.dependency_overrides[get_current_user] = override_get_current_user_with_relations

    # 他の事業所のdeliverableの削除を試行
    response = await async_client.delete(f"/api/v1/support-plans/deliverables/{deliverable.id}")

    # 403エラーを期待
    assert response.status_code == 403

    # クリーンアップ
    app.dependency_overrides.clear()
