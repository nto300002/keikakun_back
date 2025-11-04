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
from unittest.mock import patch, AsyncMock

logging.basicConfig()
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)

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

        # monkeypatchでsettings.S3_BUCKET_NAMEを設定
        monkeypatch.setattr(settings, "S3_BUCKET_NAME", bucket_name)
        monkeypatch.setattr(settings, "S3_ENDPOINT_URL", None)

        # デバッグ: S3_BUCKET_NAMEが正しく設定されているか確認
        print(f"\n=== S3 Mock Setup ===")
        print(f"DEBUG: bucket_name = {bucket_name}")
        print(f"DEBUG: settings.S3_BUCKET_NAME = {settings.S3_BUCKET_NAME}")
        print(f"=== S3 Mock Setup Complete ===\n")

        yield s3_client


@pytest.mark.asyncio
async def test_upload_pdf_with_s3_integration(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_admin_user: Staff,
    office_factory,
    s3_mock
):
    """
    POST /api/v1/support-plans/plan-deliverables
    S3統合: PDFアップロードが実際にS3に保存されることを確認
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

    # ステータスを作成
    statuses = [
        SupportPlanStatus(
            plan_cycle_id=cycle.id,
            welfare_recipient_id=recipient.id,
            office_id=office.id,
            step_type=SupportPlanStep.assessment,
            is_latest_status=True,
            completed=False,
        ),
        SupportPlanStatus(
            plan_cycle_id=cycle.id,
            welfare_recipient_id=recipient.id,
            office_id=office.id,
            step_type=SupportPlanStep.draft_plan,
            is_latest_status=False,
            completed=False,
        ),
        SupportPlanStatus(
            plan_cycle_id=cycle.id,
            welfare_recipient_id=recipient.id,
            office_id=office.id,
            step_type=SupportPlanStep.staff_meeting,
            is_latest_status=False,
            completed=False,
        ),
        SupportPlanStatus(
            plan_cycle_id=cycle.id,
            welfare_recipient_id=recipient.id,
            office_id=office.id,
            step_type=SupportPlanStep.final_plan_signed,
            is_latest_status=False,
            completed=False,
        ),
    ]
    db_session.add_all(statuses)
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

    # 3. PDFファイルのアップロード
    pdf_content = b"%PDF-1.4 mock content for S3 test"
    files = {
        "file": ("assessment.pdf", io.BytesIO(pdf_content), "application/pdf")
    }
    data = {
        "plan_cycle_id": cycle.id,
        "deliverable_type": DeliverableType.assessment_sheet.value,
    }

    response = await async_client.post("/api/v1/support-plans/plan-deliverables", files=files, data=data)

    # 4. レスポンスの検証
    assert response.status_code == 201
    response_data = response.json()
    assert "id" in response_data
    assert response_data["deliverable_type"] == DeliverableType.assessment_sheet.value
    assert response_data["plan_cycle_id"] == cycle.id

    # 5. DBに保存されたfile_pathを確認
    stmt = select(PlanDeliverable).where(PlanDeliverable.plan_cycle_id == cycle.id)
    result = await db_session.execute(stmt)
    deliverable = result.scalar_one()

    # file_pathがS3 URLの形式であることを確認
    assert deliverable.file_path.startswith("s3://")
    assert settings.S3_BUCKET_NAME in deliverable.file_path

    # 6. S3に実際にファイルがアップロードされたことを確認
    # file_pathから object_name を抽出 (s3://bucket-name/object-name)
    object_name = deliverable.file_path.replace(f"s3://{settings.S3_BUCKET_NAME}/", "")

    s3_response = s3_mock.get_object(Bucket=settings.S3_BUCKET_NAME, Key=object_name)
    s3_data = s3_response["Body"].read()
    assert s3_data == pdf_content

    # クリーンアップ
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_download_pdf_deliverable(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_admin_user: Staff,
    office_factory,
    s3_mock
):
    """
    GET /api/v1/support-plans/deliverables/{deliverable_id}/download
    S3から署名付きURLを生成してPDFダウンロードができることを確認
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

    # S3にファイルをアップロード（テストデータとして）
    object_name = f"plan-deliverables/{cycle.id}/assessment/test-assessment.pdf"
    pdf_content = b"%PDF-1.4 test download content"
    s3_mock.put_object(
        Bucket=settings.S3_BUCKET_NAME,
        Key=object_name,
        Body=pdf_content
    )

    # PlanDeliverableレコードを作成
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

    # 3. ダウンロードエンドポイントを呼び出す
    response = await async_client.get(f"/api/v1/support-plans/deliverables/{deliverable.id}/download")

    # 4. レスポンスの検証
    assert response.status_code == 200
    response_data = response.json()

    # 署名付きURLが返されることを確認
    assert "presigned_url" in response_data
    assert response_data["presigned_url"] is not None
    assert isinstance(response_data["presigned_url"], str)

    # URLにS3署名パラメータが含まれていることを確認
    presigned_url = response_data["presigned_url"]
    assert "X-Amz-Algorithm=AWS4-HMAC-SHA256" in presigned_url
    assert "X-Amz-Signature=" in presigned_url
    assert settings.S3_BUCKET_NAME in presigned_url

    # クリーンアップ
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_download_pdf_deliverable_not_found(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_admin_user: Staff,
    s3_mock
):
    """
    GET /api/v1/support-plans/deliverables/{deliverable_id}/download
    存在しないdeliverable_idの場合、404エラーを返すことを確認
    """
    # 依存関係のオーバーライド（get_dbは async_client fixture で既にオーバーライド済み）
    async def override_get_current_user_with_relations():
        stmt = select(Staff).where(Staff.id == test_admin_user.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        ).execution_options(populate_existing=True)
        result = await db_session.execute(stmt)
        user = result.scalars().first()
        return user

    app.dependency_overrides[get_current_user] = override_get_current_user_with_relations

    # 存在しないIDでリクエスト
    response = await async_client.get("/api/v1/support-plans/deliverables/99999/download")

    # 404エラーを期待
    assert response.status_code == 404

    # クリーンアップ
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_download_pdf_deliverable_unauthorized(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_admin_user: Staff,
    office_factory,
    s3_mock
):
    """
    GET /api/v1/support-plans/deliverables/{deliverable_id}/download
    他の事業所のdeliverableにアクセスしようとした場合、403エラーを返すことを確認
    """
    # 事業所1（test_admin_userが所属）
    office1 = await office_factory(creator=test_admin_user)
    db_session.add(OfficeStaff(staff_id=test_admin_user.id, office_id=office1.id, is_primary=True))
    await db_session.flush()  # OfficeStaffを先にflush

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

    # サイクルを作成（office2に関連）
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

    # 他の事業所のdeliverableにアクセス試行
    response = await async_client.get(f"/api/v1/support-plans/deliverables/{deliverable.id}/download")

    # 403エラーを期待
    assert response.status_code == 403

    # クリーンアップ
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_download_pdf_with_inline_content_disposition(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_admin_user: Staff,
    office_factory,
    s3_mock
):
    """
    GET /api/v1/support-plans/deliverables/{deliverable_id}/download
    署名付きURLがContent-Disposition: inlineを含むことを確認（プレビュー用、ダウンロードではない）

    要件: @xmemo/3memox.md - ダウンロードは必要ないのでプレビューできるように
    """
    # 1. テストデータの準備
    office = await office_factory(creator=test_admin_user)
    db_session.add(OfficeStaff(staff_id=test_admin_user.id, office_id=office.id, is_primary=True))
    await db_session.flush()

    # 利用者を作成
    recipient = WelfareRecipient(
        first_name="プレビュー",
        last_name="テスト",
        first_name_furigana="プレビュー",
        last_name_furigana="テスト",
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

    # S3にファイルをアップロード（テストデータとして）
    object_name = f"plan-deliverables/{cycle.id}/assessment/preview-test.pdf"
    pdf_content = b"%PDF-1.4 preview test content"
    s3_mock.put_object(
        Bucket=settings.S3_BUCKET_NAME,
        Key=object_name,
        Body=pdf_content,
        ContentType='application/pdf',
        ContentDisposition='inline'  # プレビュー用に inline を設定
    )

    # PlanDeliverableレコードを作成
    deliverable = PlanDeliverable(
        plan_cycle_id=cycle.id,
        deliverable_type=DeliverableType.assessment_sheet,
        file_path=f"s3://{settings.S3_BUCKET_NAME}/{object_name}",
        original_filename="preview-test.pdf",
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

    # 3. ダウンロードエンドポイントを呼び出す
    response = await async_client.get(f"/api/v1/support-plans/deliverables/{deliverable.id}/download")

    # 4. レスポンスの検証
    assert response.status_code == 200
    response_data = response.json()

    # 署名付きURLが返されることを確認
    assert "presigned_url" in response_data
    presigned_url = response_data["presigned_url"]
    assert presigned_url is not None

    # 5. 重要: 署名付きURLにResponseContentDisposition=inlineパラメータが含まれることを確認
    # これにより、ブラウザはPDFをダウンロードせずにプレビュー表示する
    assert "ResponseContentDisposition" in presigned_url or "response-content-disposition" in presigned_url.lower()
    assert "inline" in presigned_url.lower()

    # attachmentが含まれていないことを確認（ダウンロードではなくプレビュー）
    assert "attachment" not in presigned_url.lower()

    # 6. S3署名パラメータが含まれていることを確認
    assert "X-Amz-Algorithm=AWS4-HMAC-SHA256" in presigned_url
    assert "X-Amz-Signature=" in presigned_url

    # クリーンアップ
    app.dependency_overrides.clear()
