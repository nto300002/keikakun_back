import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date
import uuid
import logging

# SQLAlchemyのロギングを有効化してクエリをデバッグ
logging.basicConfig()
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

from app.models.welfare_recipient import WelfareRecipient
from app.models.support_plan_cycle import SupportPlanCycle, SupportPlanStatus
from app.models.office import Office, OfficeStaff
from app.models.staff import Staff
from app.main import app


@pytest.mark.asyncio
async def test_create_welfare_recipient_integration(
    async_client: AsyncClient,
    db_session: AsyncSession,
    service_admin_user_factory,
    office_factory,
    test_admin_user: Staff
):
    """
    POST /api/v1/recipients 統合テスト
    利用者、関連データ、支援計画が正常に作成されることを確認
    """
    # 1. テストデータの準備
    # ログインユーザーと事業所を作成
    office = await office_factory(creator=test_admin_user)
    db_session.add(OfficeStaff(staff_id=test_admin_user.id, office_id=office.id, is_primary=True))
    await db_session.flush()

    # 2. APIエンドポイントの呼び出し
    # ログイン状態を模倣するために、get_current_userをオーバーライド
    from app.api.deps import get_current_user
    from sqlalchemy.orm import selectinload
    from sqlalchemy import select
    from app.models.staff import Staff

    async def override_get_current_user_with_relations():
        stmt = select(Staff).where(Staff.id == test_admin_user.id).options(selectinload(Staff.office_associations))
        result = await db_session.execute(stmt)
        user = result.scalars().first()
        return user

    app.dependency_overrides[get_current_user] = override_get_current_user_with_relations

    # APIに渡すデータ
    registration_data = {
        "basic_info": {
            "firstName": "統合", "lastName": "テスト",
            "firstNameFurigana": "とうごう", "lastNameFurigana": "てすと",
            "birthDay": "1995-05-10", "gender": "female"
        },
        "contact_address": {
            "address": "統合テスト住所", "formOfResidence": "home_alone",
            "meansOfTransportation": "car_transport", "tel": "111222333"
        },
        "emergency_contacts": [],
        "disability_info": {
            "disabilityOrDiseaseName": "統合テスト障害", "livelihoodProtection": "receiving_with_allowance"
        },
        "disability_details": []
    }

    response = await async_client.post("/api/v1/welfare-recipients/", json=registration_data)
    
    # 3. レスポンスの検証
    assert response.status_code == 201
    response_data = response.json()
    assert response_data["success"] is True
    assert "recipient_id" in response_data
    recipient_id = uuid.UUID(response_data["recipient_id"])

    # 4. DBの状態を検証
    db_recipient = await db_session.get(WelfareRecipient, recipient_id)
    assert db_recipient is not None
    assert db_recipient.first_name == "統合"
    
    # 関連データもロードして確認
    await db_session.refresh(db_recipient, ["detail", "disability_status", "support_plan_cycles"])
    
    assert db_recipient.detail.address == "統合テスト住所"
    assert db_recipient.disability_status.disability_or_disease_name == "統合テスト障害"
    
    # 支援計画サイクルとステータスの検証
    assert len(db_recipient.support_plan_cycles) == 1
    cycle = db_recipient.support_plan_cycles[0]
    assert cycle.is_latest_cycle is True
    
    await db_session.refresh(cycle, ["statuses"])
    assert len(cycle.statuses) == 4

    # クリーンアップ
    del app.dependency_overrides[get_current_user]


@pytest.mark.asyncio
async def test_delete_welfare_recipient(
    async_client: AsyncClient,
    db_session: AsyncSession,
    office_factory,
    test_admin_user: Staff
):
    """
    DELETE /api/v1/welfare-recipients/{recipient_id} テスト
    利用者と関連データが正常に削除されることを確認
    """
    # 1. テストデータの準備
    office = await office_factory(creator=test_admin_user)
    db_session.add(OfficeStaff(staff_id=test_admin_user.id, office_id=office.id, is_primary=True))
    await db_session.flush()

    # 利用者を作成
    from app.api.deps import get_current_user
    from sqlalchemy.orm import selectinload
    from sqlalchemy import select

    async def override_get_current_user_with_relations():
        stmt = select(Staff).where(Staff.id == test_admin_user.id).options(selectinload(Staff.office_associations))
        result = await db_session.execute(stmt)
        user = result.scalars().first()
        return user

    app.dependency_overrides[get_current_user] = override_get_current_user_with_relations

    # 利用者を作成
    registration_data = {
        "basic_info": {
            "firstName": "削除", "lastName": "テスト",
            "firstNameFurigana": "さくじょ", "lastNameFurigana": "てすと",
            "birthDay": "1990-01-01", "gender": "male"
        },
        "contact_address": {
            "address": "削除テスト住所", "formOfResidence": "home_alone",
            "meansOfTransportation": "car_transport", "tel": "999888777"
        },
        "emergency_contacts": [],
        "disability_info": {
            "disabilityOrDiseaseName": "削除テスト障害", "livelihoodProtection": "receiving_with_allowance"
        },
        "disability_details": []
    }

    create_response = await async_client.post("/api/v1/welfare-recipients/", json=registration_data)
    assert create_response.status_code == 201
    recipient_id = create_response.json()["recipient_id"]

    # 2. 削除APIを呼び出し
    delete_response = await async_client.delete(f"/api/v1/welfare-recipients/{recipient_id}")

    # 3. レスポンスの検証
    assert delete_response.status_code == 200
    assert delete_response.json()["message"] == "Welfare recipient deleted successfully"

    # 4. DBから削除されたことを確認
    db_recipient = await db_session.get(WelfareRecipient, uuid.UUID(recipient_id))
    assert db_recipient is None

    # クリーンアップ
    del app.dependency_overrides[get_current_user]


@pytest.mark.asyncio
async def test_delete_welfare_recipient_with_deliverables(
    async_client: AsyncClient,
    db_session: AsyncSession,
    office_factory,
    test_admin_user: Staff
):
    """
    DELETE /api/v1/welfare-recipients/{recipient_id} テスト（成果物あり）
    成果物を持つ利用者も正常に削除されることを確認
    """
    # 1. テストデータの準備
    office = await office_factory(creator=test_admin_user)
    db_session.add(OfficeStaff(staff_id=test_admin_user.id, office_id=office.id, is_primary=True))
    await db_session.flush()

    from app.api.deps import get_current_user
    from sqlalchemy.orm import selectinload
    from sqlalchemy import select

    async def override_get_current_user_with_relations():
        stmt = select(Staff).where(Staff.id == test_admin_user.id).options(selectinload(Staff.office_associations))
        result = await db_session.execute(stmt)
        user = result.scalars().first()
        return user

    app.dependency_overrides[get_current_user] = override_get_current_user_with_relations

    # 利用者を作成
    registration_data = {
        "basic_info": {
            "firstName": "成果物", "lastName": "テスト",
            "firstNameFurigana": "せいかぶつ", "lastNameFurigana": "てすと",
            "birthDay": "1990-01-01", "gender": "male"
        },
        "contact_address": {
            "address": "成果物テスト住所", "formOfResidence": "home_alone",
            "meansOfTransportation": "car_transport", "tel": "999888777"
        },
        "emergency_contacts": [],
        "disability_info": {
            "disabilityOrDiseaseName": "成果物テスト障害", "livelihoodProtection": "receiving_with_allowance"
        },
        "disability_details": []
    }

    create_response = await async_client.post("/api/v1/welfare-recipients/", json=registration_data)
    assert create_response.status_code == 201
    recipient_id = create_response.json()["recipient_id"]

    # 成果物を追加
    from app.models.support_plan_cycle import PlanDeliverable
    from app.models.enums import DeliverableType

    # サイクルを取得
    cycles_stmt = select(SupportPlanCycle).where(SupportPlanCycle.welfare_recipient_id == uuid.UUID(recipient_id))
    cycles_result = await db_session.execute(cycles_stmt)
    cycle = cycles_result.scalars().first()

    # 成果物を作成
    deliverable = PlanDeliverable(
        plan_cycle_id=cycle.id,
        deliverable_type=DeliverableType.assessment_sheet,
        file_path="/test/path/assessment.pdf",
        original_filename="assessment.pdf",
        uploaded_by=test_admin_user.id
    )
    db_session.add(deliverable)
    await db_session.commit()

    # 2. 削除APIを呼び出し
    delete_response = await async_client.delete(f"/api/v1/welfare-recipients/{recipient_id}")

    # 3. レスポンスの検証
    assert delete_response.status_code == 200
    assert delete_response.json()["message"] == "Welfare recipient deleted successfully"

    # 4. DBから削除されたことを確認
    db_recipient = await db_session.get(WelfareRecipient, uuid.UUID(recipient_id))
    assert db_recipient is None

    # 成果物も削除されたことを確認
    deliverable_stmt = select(PlanDeliverable).where(PlanDeliverable.id == deliverable.id)
    deliverable_result = await db_session.execute(deliverable_stmt)
    assert deliverable_result.scalars().first() is None

    # クリーンアップ
    del app.dependency_overrides[get_current_user]
