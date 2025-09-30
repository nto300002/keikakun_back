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
