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
    # アプリケーションが必要とするS3関連の環境変数
    monkeypatch.setenv("S3_ACCESS_KEY", "testing")
    monkeypatch.setenv("S3_SECRET_KEY", "testing")
    monkeypatch.setenv("S3_REGION", "us-east-1")
    monkeypatch.setenv("S3_BUCKET_NAME", "test-plan-deliverables-bucket")
    # S3_ENDPOINT_URLを削除してmotoのデフォルトモックを使用
    monkeypatch.delenv("S3_ENDPOINT_URL", raising=False)


@pytest.fixture(scope="function")
def s3_mock(aws_credentials):
    """S3 mock context manager."""
    with mock_aws():
        # S3クライアントを作成してバケットを作成
        # region_name=Noneを使用してsettings.S3_REGIONと一致させる
        s3_client = boto3.client(
            "s3",
            region_name="us-east-1",
            aws_access_key_id="testing",
            aws_secret_access_key="testing"
        )
        bucket_name = "test-plan-deliverables-bucket"
        s3_client.create_bucket(Bucket=bucket_name)

        # バケットが作成されたことを確認
        buckets = s3_client.list_buckets()
        print(f"\n=== S3 Mock Setup ===")
        print(f"DEBUG: Created buckets: {[b['Name'] for b in buckets['Buckets']]}")

        yield s3_client


@pytest.mark.asyncio
async def test_upload_assessment_pdf(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_admin_user: Staff,
    office_factory,
    s3_mock,
    monkeypatch
):
    """
    POST /api/v1/plan-deliverables
    アセスメントPDFのアップロードが正常に完了することを確認
    """
    # S3アップロード関数をモック
    from unittest.mock import AsyncMock
    async def mock_upload_file(file, object_name: str):
        """S3アップロードをモック"""
        return f"s3://test-plan-deliverables-bucket/{object_name}"

    from app.core import storage
    monkeypatch.setattr(storage, "upload_file", mock_upload_file)

    # 1. テストデータの準備
    print(f"\n=== DEBUG: Test data preparation ===")
    print(f"DEBUG: test_admin_user.id = {test_admin_user.id}")
    print(f"DEBUG: db_session object id (test data prep) = {id(db_session)}")

    office = await office_factory(creator=test_admin_user)
    print(f"DEBUG: office.id = {office.id}")

    db_session.add(OfficeStaff(staff_id=test_admin_user.id, office_id=office.id, is_primary=True))
    await db_session.flush()  # OfficeStaffを先にflush

    # OfficeStaffが保存されたか確認
    office_staff_check = await db_session.execute(
        select(OfficeStaff).where(OfficeStaff.staff_id == test_admin_user.id)
    )
    saved_office_staff = office_staff_check.scalars().all()
    print(f"DEBUG: OfficeStaff records saved = {len(saved_office_staff)}")
    for idx, os in enumerate(saved_office_staff):
        print(f"DEBUG: OfficeStaff[{idx}].staff_id = {os.staff_id}, office_id = {os.office_id}")

    recipient = WelfareRecipient(first_name="テスト", last_name="太郎", first_name_furigana="テスト", last_name_furigana="タロウ", birth_day=date(1990, 1, 1), gender=GenderType.male)
    db_session.add(recipient)
    await db_session.flush()
    association = OfficeWelfareRecipient(office_id=office.id, welfare_recipient_id=recipient.id)
    db_session.add(association)
    cycle = SupportPlanCycle(welfare_recipient_id=recipient.id, office_id=office.id, is_latest_cycle=True, cycle_number=1)
    db_session.add(cycle)
    await db_session.flush()
    statuses = [SupportPlanStatus(plan_cycle_id=cycle.id, welfare_recipient_id=recipient.id, office_id=office.id, step_type=s, is_latest_status=(s==SupportPlanStep.assessment)) for s in [SupportPlanStep.assessment, SupportPlanStep.draft_plan, SupportPlanStep.staff_meeting, SupportPlanStep.final_plan_signed]]
    db_session.add_all(statuses)
    await db_session.commit()
    print(f"=== DEBUG: Test data preparation complete ===\n")

    # 2. 依存関係のオーバーライド（get_current_userのみ）
    async def override_get_current_user_with_relations():
        print(f"\n=== DEBUG test_upload_assessment_pdf: override_get_current_user_with_relations called ===")
        print(f"DEBUG: test_admin_user.id = {test_admin_user.id}")
        print(f"DEBUG: db_session object id = {id(db_session)}")

        # SQLAlchemyのSQLログを一時的に有効化
        import logging
        logging.basicConfig()
        logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

        # SQL レベルでの確認: OfficeStaff が存在するか生SQLで確認
        from sqlalchemy import text
        print("\n--- Raw SQL Query ---")
        raw_sql_result = await db_session.execute(
            text("SELECT id, staff_id, office_id, is_primary FROM office_staffs WHERE staff_id = :staff_id"),
            {"staff_id": str(test_admin_user.id)}
        )
        raw_rows = raw_sql_result.fetchall()
        print(f"DEBUG: Raw SQL - OfficeStaff records = {len(raw_rows)}")
        for idx, row in enumerate(raw_rows):
            print(f"DEBUG: Raw SQL - OfficeStaff[{idx}]: id={row[0]}, staff_id={row[1]}, office_id={row[2]}, is_primary={row[3]}")

        # OfficeStaffを直接クエリしてみる
        print("\n--- Direct OfficeStaff Query ---")
        office_staff_stmt = select(OfficeStaff).where(OfficeStaff.staff_id == test_admin_user.id)
        office_staff_result = await db_session.execute(office_staff_stmt)
        office_staff_records = office_staff_result.scalars().all()
        print(f"DEBUG: Direct OfficeStaff query - records found = {len(office_staff_records)}")
        for idx, os in enumerate(office_staff_records):
            print(f"DEBUG: OfficeStaff[{idx}]: id={os.id}, staff_id={os.staff_id}, office_id={os.office_id}")
            # Staffオブジェクトにアクセスしてみる
            try:
                print(f"DEBUG: OfficeStaff[{idx}].staff = {os.staff}")
                print(f"DEBUG: OfficeStaff[{idx}].staff.id = {os.staff.id if os.staff else None}")
            except Exception as e:
                print(f"DEBUG: Error accessing OfficeStaff[{idx}].staff: {e}")

        # selectinloadなしで取得してみる
        print("\n--- Staff Query Without selectinload ---")
        stmt_no_load = select(Staff).where(Staff.id == test_admin_user.id)
        result_no_load = await db_session.execute(stmt_no_load)
        user_no_load = result_no_load.scalars().first()
        print(f"DEBUG: Without selectinload - user found = {user_no_load is not None}")
        if user_no_load:
            print(f"DEBUG: user_no_load object state: {user_no_load.__dict__}")
            try:
                print(f"DEBUG: Without selectinload - office_associations length = {len(user_no_load.office_associations)}")
            except Exception as e:
                print(f"DEBUG: Without selectinload - Error accessing office_associations: {type(e).__name__}: {e}")

        # キャッシュをバイパスして強制的にDBから再ロード
        print("\n--- Staff Query With selectinload (populate_existing=True) ---")
        stmt = select(Staff).where(Staff.id == test_admin_user.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        ).execution_options(populate_existing=True)
        result = await db_session.execute(stmt)
        user = result.scalars().first()

        print(f"DEBUG: With selectinload - user found = {user is not None}")
        if user:
            print(f"DEBUG: user.id = {user.id}")
            print(f"DEBUG: user object state: {user.__dict__}")
            print(f"DEBUG: user.office_associations = {user.office_associations}")
            print(f"DEBUG: len(office_associations) = {len(user.office_associations)}")
            for idx, assoc in enumerate(user.office_associations):
                print(f"DEBUG: association[{idx}].staff_id = {assoc.staff_id}")
                print(f"DEBUG: association[{idx}].office_id = {assoc.office_id}")
                print(f"DEBUG: association[{idx}].office = {assoc.office}")
                if assoc.office:
                    print(f"DEBUG: association[{idx}].office.id = {assoc.office.id}")
                    print(f"DEBUG: association[{idx}].office.name = {assoc.office.name}")

        # リレーションシップのメタデータを確認
        print("\n--- Relationship Metadata ---")
        print(f"DEBUG: Staff.office_associations.property = {Staff.office_associations.property}")
        print(f"DEBUG: Staff.office_associations.property.mapper = {Staff.office_associations.property.mapper}")

        print(f"=== DEBUG END ===\n")

        # SQLログを元に戻す
        logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)

        return user

    app.dependency_overrides[get_current_user] = override_get_current_user_with_relations

    # 3. API呼び出し
    pdf_content = b"%PDF-1.4 mock content"
    files = {"file": ("assessment.pdf", io.BytesIO(pdf_content), "application/pdf")}
    data = {"plan_cycle_id": cycle.id, "deliverable_type": DeliverableType.assessment_sheet.value}

    response = await async_client.post("/api/v1/support-plans/plan-deliverables", files=files, data=data)

    # 4. レスポンスを検証
    assert response.status_code == 201
    response_data = response.json()
    assert response_data["plan_cycle_id"] == cycle.id
    assert response_data["deliverable_type"] == DeliverableType.assessment_sheet.value

    # 5. DBの状態を確認（アセスメントが完了している）
    # cycleとstatusesを再取得
    stmt = select(SupportPlanCycle).where(SupportPlanCycle.id == cycle.id).options(selectinload(SupportPlanCycle.statuses))
    result = await db_session.execute(stmt)
    refreshed_cycle = result.scalar_one()

    assessment_status = next((s for s in refreshed_cycle.statuses if s.step_type == SupportPlanStep.assessment), None)
    assert assessment_status.completed is True
    assert assessment_status.is_latest_status is False

    # 次のステップ（draft_plan）が最新になっている
    draft_plan_status = next((s for s in refreshed_cycle.statuses if s.step_type == SupportPlanStep.draft_plan), None)
    assert draft_plan_status.is_latest_status is True

    # クリーンアップ
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_upload_final_plan_creates_new_cycle(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_admin_user: Staff,
    office_factory,
    s3_mock,
    monkeypatch
):
    """
    POST /api/v1/plan-deliverables
    最終計画書(署名済み)のアップロードで新しいサイクルが自動生成されることを確認
    """
    # S3アップロード関数をモック
    async def mock_upload_file(file, object_name: str):
        return f"s3://test-plan-deliverables-bucket/{object_name}"

    from app.core import storage
    monkeypatch.setattr(storage, "upload_file", mock_upload_file)

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

    # サイクル1を作成（すべてのステップが完了直前）
    cycle1 = SupportPlanCycle(
        welfare_recipient_id=recipient.id,
        office_id=office.id,
        plan_cycle_start_date=date(2024, 1, 1),
        is_latest_cycle=True,
        cycle_number=1,
    )
    db_session.add(cycle1)
    await db_session.flush()

    # サイクル1のステータスを作成（final_plan_signedが最新ステップ）
    statuses = [
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
            is_latest_status=True,
            completed=False,
        ),
    ]
    db_session.add_all(statuses)
    await db_session.commit()

    # 2. 依存関係のオーバーライド（get_current_userのみ）
    async def override_get_current_user_with_relations():
        stmt = select(Staff).where(Staff.id == test_admin_user.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        ).execution_options(populate_existing=True)
        result = await db_session.execute(stmt)
        user = result.scalars().first()
        return user

    app.dependency_overrides[get_current_user] = override_get_current_user_with_relations

    # 3. 最終計画書PDFをアップロード
    pdf_content = b"%PDF-1.4 final plan signed mock content"
    files = {
        "file": ("final_plan_signed.pdf", io.BytesIO(pdf_content), "application/pdf")
    }
    data = {
        "plan_cycle_id": cycle1.id,
        "deliverable_type": DeliverableType.final_plan_signed_pdf.value,
    }

    response = await async_client.post("/api/v1/support-plans/plan-deliverables", files=files, data=data)

    # 4. レスポンスの検証
    assert response.status_code == 201

    # 5. DBの状態を検証
    # サイクル1が最新でなくなっていることを確認
    await db_session.refresh(cycle1)
    assert cycle1.is_latest_cycle is False

    # 新しいサイクル（cycle_number=2）が作成されていることを確認
    stmt = select(SupportPlanCycle).where(
        SupportPlanCycle.welfare_recipient_id == recipient.id,
        SupportPlanCycle.cycle_number == 2
    ).options(selectinload(SupportPlanCycle.statuses))
    result = await db_session.execute(stmt)
    cycle2 = result.scalar_one()

    assert cycle2.is_latest_cycle is True
    assert cycle2.cycle_number == 2

    # 新サイクルの最初のステップがmonitoringであることを確認
    monitoring_status = next((s for s in cycle2.statuses if s.step_type == SupportPlanStep.monitoring), None)
    assert monitoring_status is not None
    assert monitoring_status.is_latest_status is True
    assert monitoring_status.completed is False

    # クリーンアップ
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_upload_wrong_step_order(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_admin_user: Staff,
    office_factory,
    s3_mock,
    monkeypatch
):
    """
    POST /api/v1/plan-deliverables
    ステップの順序を守らずにアップロードしようとした場合、エラーになることを確認
    """
    # S3アップロード関数をモック
    async def mock_upload_file(file, object_name: str):
        return f"s3://test-plan-deliverables-bucket/{object_name}"

    from app.core import storage
    monkeypatch.setattr(storage, "upload_file", mock_upload_file)

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

    # サイクルを作成（最新ステップはassessment）
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
            is_latest_status=True,  # 現在のステップ
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

    # 2. 依存関係のオーバーライド（get_current_userのみ）
    async def override_get_current_user_with_relations():
        stmt = select(Staff).where(Staff.id == test_admin_user.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        ).execution_options(populate_existing=True)
        result = await db_session.execute(stmt)
        user = result.scalars().first()
        return user

    app.dependency_overrides[get_current_user] = override_get_current_user_with_relations

    # 3. アセスメントをスキップして、draft_planをアップロードしようとする
    pdf_content = b"%PDF-1.4 draft plan mock content"
    files = {
        "file": ("draft_plan.pdf", io.BytesIO(pdf_content), "application/pdf")
    }
    data = {
        "plan_cycle_id": cycle.id,
        "deliverable_type": DeliverableType.draft_plan_pdf.value,  # 順序違反
    }

    response = await async_client.post("/api/v1/support-plans/plan-deliverables", files=files, data=data)

    # 4. レスポンスの検証（400 Bad Request または 422 Unprocessable Entity）
    assert response.status_code in [400, 422]
    detail = response.json()["detail"]
    assert "step" in detail.lower() or "順序" in detail or "ステップ" in detail

    # 5. DBの状態が変更されていないことを確認
    stmt = select(SupportPlanStatus).where(SupportPlanStatus.plan_cycle_id == cycle.id)
    result = await db_session.execute(stmt)
    all_statuses = result.scalars().all()

    # アセスメントがまだ未完了のはず
    assessment_status = next((s for s in all_statuses if s.step_type == SupportPlanStep.assessment), None)
    assert assessment_status.completed is False
    assert assessment_status.is_latest_status is True

    # クリーンアップ
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_upload_unauthorized_office(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_admin_user: Staff,
    office_factory,
    s3_mock,
    monkeypatch
):
    """
    POST /api/v1/plan-deliverables
    他の事業所の利用者の計画にアップロードしようとした場合、403エラーになることを確認
    """
    # S3アップロード関数をモック
    async def mock_upload_file(file, object_name: str):
        return f"s3://test-plan-deliverables-bucket/{object_name}"

    from app.core import storage
    monkeypatch.setattr(storage, "upload_file", mock_upload_file)

    # 1. テストデータの準備
    # 事業所1（test_admin_userが所属）
    office1 = await office_factory(creator=test_admin_user)
    db_session.add(OfficeStaff(staff_id=test_admin_user.id, office_id=office1.id, is_primary=True))
    await db_session.flush()  # OfficeStaffを先にflush

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

    # ステータスを作成
    statuses = [
        SupportPlanStatus(
            plan_cycle_id=cycle.id,
            welfare_recipient_id=recipient.id,
            office_id=office2.id,
            step_type=SupportPlanStep.assessment,
            is_latest_status=True,
            completed=False,
        ),
    ]
    db_session.add_all(statuses)
    await db_session.commit()

    # 2. 依存関係のオーバーライド（test_admin_userでログイン）
    async def override_get_current_user_with_relations():
        stmt = select(Staff).where(Staff.id == test_admin_user.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        ).execution_options(populate_existing=True)
        result = await db_session.execute(stmt)
        user = result.scalars().first()
        return user

    app.dependency_overrides[get_current_user] = override_get_current_user_with_relations

    # 3. 他の事業所の利用者の計画にアップロード試行
    pdf_content = b"%PDF-1.4 assessment mock content"
    files = {
        "file": ("assessment.pdf", io.BytesIO(pdf_content), "application/pdf")
    }
    data = {
        "plan_cycle_id": cycle.id,
        "deliverable_type": DeliverableType.assessment_sheet.value,
    }

    response = await async_client.post("/api/v1/support-plans/plan-deliverables", files=files, data=data)

    # 4. 403エラーを期待
    assert response.status_code == 403
    detail = response.json()["detail"]
    assert "permission" in detail.lower() or "access" in detail.lower() or "権限" in detail or "アクセス" in detail

    # クリーンアップ
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_upload_monitoring_then_draft_plan_in_cycle2(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_admin_user: Staff,
    office_factory,
    s3_mock,
    monkeypatch
):
    """
    POST /api/v1/plan-deliverables
    サイクル2でmonitoringを完了した後、draft_planをアップロードできることを確認
    """
    # S3アップロード関数をモック
    async def mock_upload_file(file, object_name: str):
        return f"s3://test-plan-deliverables-bucket/{object_name}"

    from app.core import storage
    monkeypatch.setattr(storage, "upload_file", mock_upload_file)

    # 1. テストデータの準備
    office = await office_factory(creator=test_admin_user)
    db_session.add(OfficeStaff(staff_id=test_admin_user.id, office_id=office.id, is_primary=True))
    await db_session.flush()

    # 利用者を作成
    recipient = WelfareRecipient(
        first_name="テスト",
        last_name="三郎",
        first_name_furigana="テスト",
        last_name_furigana="サブロウ",
        birth_day=date(1993, 7, 15),
        gender=GenderType.male,
    )
    db_session.add(recipient)
    await db_session.flush()

    # 事業所と利用者の関連を作成
    association = OfficeWelfareRecipient(office_id=office.id, welfare_recipient_id=recipient.id)
    db_session.add(association)
    await db_session.flush()

    # サイクル2を作成（monitoringが最新ステップ）
    cycle2 = SupportPlanCycle(
        welfare_recipient_id=recipient.id,
        office_id=office.id,
        plan_cycle_start_date=date(2024, 7, 1),
        is_latest_cycle=True,
        cycle_number=2,
    )
    db_session.add(cycle2)
    await db_session.flush()

    # サイクル2のステータスを作成（monitoringが最新ステップ）
    statuses = [
        SupportPlanStatus(
            plan_cycle_id=cycle2.id,
            welfare_recipient_id=recipient.id,
            office_id=office.id,
            step_type=SupportPlanStep.monitoring,
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
    db_session.add_all(statuses)
    await db_session.commit()

    # 2. 依存関係のオーバーライド（get_current_userのみ）
    async def override_get_current_user_with_relations():
        stmt = select(Staff).where(Staff.id == test_admin_user.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        ).execution_options(populate_existing=True)
        result = await db_session.execute(stmt)
        user = result.scalars().first()
        return user

    app.dependency_overrides[get_current_user] = override_get_current_user_with_relations

    # 3. monitoringのPDFをアップロード
    pdf_content = b"%PDF-1.4 monitoring report mock content"
    files = {
        "file": ("monitoring_report.pdf", io.BytesIO(pdf_content), "application/pdf")
    }
    data = {
        "plan_cycle_id": cycle2.id,
        "deliverable_type": DeliverableType.monitoring_report_pdf.value,
    }

    response = await async_client.post("/api/v1/support-plans/plan-deliverables", files=files, data=data)

    # 4. monitoringのアップロード成功を確認
    assert response.status_code == 201

    # 5. DBの状態を確認（monitoringが完了し、draft_planが最新になっている）
    stmt = select(SupportPlanCycle).where(SupportPlanCycle.id == cycle2.id).options(selectinload(SupportPlanCycle.statuses))
    result = await db_session.execute(stmt)
    refreshed_cycle = result.scalar_one()

    monitoring_status = next((s for s in refreshed_cycle.statuses if s.step_type == SupportPlanStep.monitoring), None)
    assert monitoring_status.completed is True
    assert monitoring_status.is_latest_status is False

    draft_plan_status = next((s for s in refreshed_cycle.statuses if s.step_type == SupportPlanStep.draft_plan), None)
    assert draft_plan_status.is_latest_status is True
    assert draft_plan_status.completed is False

    # 6. 続けてdraft_planのPDFをアップロード
    pdf_content2 = b"%PDF-1.4 draft plan mock content"
    files2 = {
        "file": ("draft_plan.pdf", io.BytesIO(pdf_content2), "application/pdf")
    }
    data2 = {
        "plan_cycle_id": cycle2.id,
        "deliverable_type": DeliverableType.draft_plan_pdf.value,
    }

    response2 = await async_client.post("/api/v1/support-plans/plan-deliverables", files=files2, data=data2)

    # 7. draft_planのアップロード成功を確認
    assert response2.status_code == 201
    response_data = response2.json()
    assert response_data["plan_cycle_id"] == cycle2.id
    assert response_data["deliverable_type"] == DeliverableType.draft_plan_pdf.value

    # 8. DBの状態を再確認（draft_planが完了し、staff_meetingが最新になっている）
    stmt2 = select(SupportPlanCycle).where(SupportPlanCycle.id == cycle2.id).options(selectinload(SupportPlanCycle.statuses))
    result2 = await db_session.execute(stmt2)
    final_cycle = result2.scalar_one()

    final_draft_plan_status = next((s for s in final_cycle.statuses if s.step_type == SupportPlanStep.draft_plan), None)
    assert final_draft_plan_status.completed is True
    assert final_draft_plan_status.is_latest_status is False

    staff_meeting_status = next((s for s in final_cycle.statuses if s.step_type == SupportPlanStep.staff_meeting), None)
    assert staff_meeting_status.is_latest_status is True
    assert staff_meeting_status.completed is False

    # クリーンアップ
    app.dependency_overrides.clear()
