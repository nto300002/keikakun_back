"""Employee制限API統合テスト（Phase 7 - 高優先度）

APIエンドポイント経由でのEmployee制限機能のE2Eテスト

このテストは以下を検証します:
1. EmployeeがCREATE/UPDATE/DELETEを実行すると202 Acceptedを返す
2. Manager/OwnerがCREATE/UPDATE/DELETEを実行すると直接実行される
3. Employeeは自分のリクエストを承認できない（403 Forbidden）
4. Managerは同じ事業所のリクエストのみ承認可能
5. Managerは他の事業所のリクエストを承認できない

実行コマンド:
pytest tests/integration/test_employee_restriction_api.py -v -s --tb=short
"""

import pytest
from datetime import date
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import StaffRole, GenderType
from app.models.welfare_recipient import WelfareRecipient


@pytest.mark.asyncio
async def test_employee_api_create_welfare_recipient_returns_202_accepted(
    async_client: AsyncClient,
    db_session: AsyncSession,
    office_factory,
    staff_factory
):
    """
    Employee が API 経由で WelfareRecipient を作成すると 202 Accepted を返す

    テスト内容:
    - Employee が POST /api/v1/welfare-recipients を実行
    - 202 Accepted が返される
    - レスポンスにrequest_idが含まれる
    - 実際にはWelfareRecipientは作成されない（承認待ち）
    """
    # Arrange
    office = await office_factory(session=db_session)
    employee = await staff_factory(
        session=db_session,
        office_id=office.id,
        role=StaffRole.employee
    )

    # get_current_userをオーバーライド
    from app.main import app
    from app.api.deps import get_current_user
    from app.models.staff import Staff
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.office import OfficeStaff

    async def override_get_current_user():
        stmt = select(Staff).where(Staff.id == employee.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        ).execution_options(populate_existing=True)
        result = await db_session.execute(stmt)
        return result.scalars().first()

    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        # Act: Employee が WelfareRecipient 作成をリクエスト
        create_data = {
            "basic_info": {
                "firstName": "太郎",
                "lastName": "山田",
                "firstNameFurigana": "たろう",
                "lastNameFurigana": "やまだ",
                "birthDay": "1990-01-01",
                "gender": "male"
            },
            "contact_address": {
                "address": "東京都渋谷区1-1-1",
                "formOfResidence": "home_with_family",
                "meansOfTransportation": "walk",
                "tel": "03-1234-5678"
            },
            "disability_info": {
                "disabilityOrDiseaseName": "テスト障害",
                "livelihoodProtection": "not_receiving"
            },
            "emergency_contacts": [],
            "disability_details": []
        }

        response = await async_client.post(
            "/api/v1/welfare-recipients/",
            json=create_data
        )

        # Assert: 202 Accepted が返される
        assert response.status_code == 202, f"Expected 202, got {response.status_code}: {response.text}"
        response_data = response.json()

        assert "message" in response_data
        assert "request_id" in response_data
        assert "pending approval" in response_data["message"].lower()

        print(f"\n✅ Employee API: 202 Accepted")
        print(f"   Request ID: {response_data['request_id']}")
        print(f"   Message: {response_data['message']}")

        # WelfareRecipientが作成されていないことを確認
        from sqlalchemy import select
        result = await db_session.execute(
            select(WelfareRecipient).where(
                WelfareRecipient.first_name == "太郎",
                WelfareRecipient.last_name == "山田"
            )
        )
        recipient = result.scalar_one_or_none()
        assert recipient is None, "WelfareRecipientが承認前に作成されてしまった"

    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_manager_api_create_welfare_recipient_returns_201_created(
    async_client: AsyncClient,
    db_session: AsyncSession,
    office_factory,
    staff_factory
):
    """
    Manager が API 経由で WelfareRecipient を作成すると 201 Created を返す

    テスト内容:
    - Manager が POST /api/v1/welfare-recipients を実行
    - 201 Created が返される
    - 実際にWelfareRecipientが作成される
    """
    # Arrange
    office = await office_factory(session=db_session)
    manager = await staff_factory(
        session=db_session,
        office_id=office.id,
        role=StaffRole.manager
    )

    # Manager用の認証設定
    from app.main import app
    from app.api.deps import get_current_user
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.office import OfficeStaff
    from app.models.staff import Staff

    async def override_get_current_user():
        stmt = select(Staff).where(Staff.id == manager.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        ).execution_options(populate_existing=True)
        result = await db_session.execute(stmt)
        return result.scalars().first()

    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        # Act: Manager が WelfareRecipient を作成
        create_data = {
            "basic_info": {
                "firstName": "花子",
                "lastName": "田中",
                "firstNameFurigana": "はなこ",
                "lastNameFurigana": "たなか",
                "birthDay": "1995-05-15",
                "gender": "female"
            },
            "contact_address": {
                "address": "東京都新宿区2-2-2",
                "formOfResidence": "home_alone",
                "meansOfTransportation": "public_transport",
                "tel": "03-9876-5432"
            },
            "disability_info": {
                "disabilityOrDiseaseName": "テスト障害2",
                "livelihoodProtection": "receiving_with_allowance"
            },
            "emergency_contacts": [],
            "disability_details": []
        }

        response = await async_client.post(
            "/api/v1/welfare-recipients/",
            json=create_data
        )

        # Assert: 201 Created が返される
        assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.text}"
        response_data = response.json()

        assert "success" in response_data
        assert response_data["success"] is True
        assert "recipient_id" in response_data
        assert response_data["recipient_id"] is not None

        print(f"\n✅ Manager API: 201 Created")
        print(f"   WelfareRecipient ID: {response_data['recipient_id']}")
        print(f"   Message: {response_data.get('message', 'N/A')}")

        # WelfareRecipientが実際に作成されたことを確認
        from sqlalchemy import select
        result = await db_session.execute(
            select(WelfareRecipient).where(
                WelfareRecipient.first_name == "花子",
                WelfareRecipient.last_name == "田中"
            )
        )
        recipient = result.scalar_one_or_none()
        assert recipient is not None, "WelfareRecipientが作成されていない"

    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_employee_cannot_approve_request_via_api_403_forbidden(
    async_client: AsyncClient,
    db_session: AsyncSession,
    office_factory,
    staff_factory
):
    """
    Employee が API 経由でリクエストを承認しようとすると 403 Forbidden を返す

    テスト内容:
    - Employee1 がリクエストを作成
    - Employee2 が承認しようとする
    - 403 Forbidden が返される
    """
    # Arrange
    office = await office_factory(session=db_session)
    employee1 = await staff_factory(
        session=db_session,
        office_id=office.id,
        role=StaffRole.employee,
        first_name="従業員1"
    )
    employee2 = await staff_factory(
        session=db_session,
        office_id=office.id,
        role=StaffRole.employee,
        first_name="従業員2"
    )

    # Employee1 がリクエストを作成
    from app.services.employee_action_service import employee_action_service
    from app.schemas.employee_action_request import EmployeeActionRequestCreate
    from app.models.enums import ResourceType, ActionType
    from app.schemas.welfare_recipient import WelfareRecipientCreate

    welfare_recipient_data = WelfareRecipientCreate(
        first_name="太郎",
        last_name="山田",
        first_name_furigana="たろう",
        last_name_furigana="やまだ",
        birth_day=date(1990, 1, 1),
        gender=GenderType.male
    )

    request_create = EmployeeActionRequestCreate(
        resource_type=ResourceType.welfare_recipient,
        action_type=ActionType.create,
        resource_id=None,
        request_data=welfare_recipient_data.model_dump(mode='json')
    )

    request = await employee_action_service.create_request(
        db=db_session,
        requester_staff_id=employee1.id,
        office_id=office.id,
        obj_in=request_create
    )
    await db_session.commit()

    # Employee2 用の認証設定
    from app.core.security import create_access_token
    from datetime import timedelta
    from app.core.config import settings
    from app.main import app
    from app.api.deps import get_current_user
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.office import OfficeStaff
    from app.models.staff import Staff

    access_token = create_access_token(str(employee2.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    headers = {"Authorization": f"Bearer {access_token}"}

    async def override_get_current_user():
        stmt = select(Staff).where(Staff.id == employee2.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        )
        result = await db_session.execute(stmt)
        return result.scalars().first()

    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        # Act: Employee2 がリクエストを承認しようとする
        response = await async_client.patch(
            f"/api/v1/employee-action-requests/{request.id}/approve",
            json={"approver_notes": "承認します"},
            headers=headers
        )

        # Assert: 403 Forbidden が返される
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        response_data = response.json()

        assert "detail" in response_data
        assert "manager" in response_data["detail"].lower() or "owner" in response_data["detail"].lower()

        print(f"\n✅ Employee2 が承認を試みる: 403 Forbidden")
        print(f"   Error Message: {response_data['detail']}")

    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_manager_can_approve_request_from_same_office(
    async_client: AsyncClient,
    db_session: AsyncSession,
    office_factory,
    staff_factory
):
    """
    Manager が同じ事業所のリクエストを API 経由で承認できる

    テスト内容:
    - Employee がリクエストを作成
    - 同じ事業所の Manager が承認
    - 200 OK が返される
    - リクエストが承認される
    """
    # Arrange
    office = await office_factory(session=db_session)
    employee = await staff_factory(
        session=db_session,
        office_id=office.id,
        role=StaffRole.employee
    )
    manager = await staff_factory(
        session=db_session,
        office_id=office.id,
        role=StaffRole.manager
    )

    # Employee がリクエストを作成
    from app.services.employee_action_service import employee_action_service
    from app.schemas.employee_action_request import EmployeeActionRequestCreate
    from app.models.enums import ResourceType, ActionType
    from app.schemas.welfare_recipient import WelfareRecipientCreate

    welfare_recipient_data = WelfareRecipientCreate(
        first_name="太郎",
        last_name="山田",
        first_name_furigana="たろう",
        last_name_furigana="やまだ",
        birth_day=date(1990, 1, 1),
        gender=GenderType.male
    )

    request_create = EmployeeActionRequestCreate(
        resource_type=ResourceType.welfare_recipient,
        action_type=ActionType.create,
        resource_id=None,
        request_data=welfare_recipient_data.model_dump(mode='json')
    )

    request = await employee_action_service.create_request(
        db=db_session,
        requester_staff_id=employee.id,
        office_id=office.id,
        obj_in=request_create
    )
    await db_session.commit()

    # Manager 用の認証設定
    from app.core.security import create_access_token
    from datetime import timedelta
    from app.core.config import settings
    from app.main import app
    from app.api.deps import get_current_user
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.office import OfficeStaff
    from app.models.staff import Staff

    access_token = create_access_token(str(manager.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    headers = {"Authorization": f"Bearer {access_token}"}

    async def override_get_current_user():
        stmt = select(Staff).where(Staff.id == manager.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        )
        result = await db_session.execute(stmt)
        return result.scalars().first()

    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        # Act: Manager がリクエストを承認
        response = await async_client.patch(
            f"/api/v1/employee-action-requests/{request.id}/approve",
            json={"approver_notes": "承認します"},
            headers=headers
        )

        # Assert: 200 OK が返される
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        response_data = response.json()

        assert response_data["status"] == "approved"
        assert response_data["approved_by_staff_id"] == str(manager.id)

        print(f"\n✅ Manager が同じ事業所のリクエストを承認: 200 OK")
        print(f"   Request ID: {response_data['id']}")
        print(f"   Status: {response_data['status']}")

    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_manager_cannot_approve_request_from_other_office(
    async_client: AsyncClient,
    db_session: AsyncSession,
    office_factory,
    staff_factory
):
    """
    Manager が他の事業所のリクエストを API 経由で承認できない

    テスト内容:
    - Office1 の Employee がリクエストを作成
    - Office2 の Manager が承認しようとする
    - 403 Forbidden が返される
    """
    # Arrange
    office1 = await office_factory(session=db_session)
    office2 = await office_factory(session=db_session)

    employee_office1 = await staff_factory(
        session=db_session,
        office_id=office1.id,
        role=StaffRole.employee
    )
    manager_office2 = await staff_factory(
        session=db_session,
        office_id=office2.id,
        role=StaffRole.manager
    )

    # Office1 の Employee がリクエストを作成
    from app.services.employee_action_service import employee_action_service
    from app.schemas.employee_action_request import EmployeeActionRequestCreate
    from app.models.enums import ResourceType, ActionType
    from app.schemas.welfare_recipient import WelfareRecipientCreate

    welfare_recipient_data = WelfareRecipientCreate(
        first_name="太郎",
        last_name="山田",
        first_name_furigana="たろう",
        last_name_furigana="やまだ",
        birth_day=date(1990, 1, 1),
        gender=GenderType.male
    )

    request_create = EmployeeActionRequestCreate(
        resource_type=ResourceType.welfare_recipient,
        action_type=ActionType.create,
        resource_id=None,
        request_data=welfare_recipient_data.model_dump(mode='json')
    )

    request = await employee_action_service.create_request(
        db=db_session,
        requester_staff_id=employee_office1.id,
        office_id=office1.id,
        obj_in=request_create
    )
    await db_session.commit()

    # Office2 の Manager 用の認証設定
    from app.core.security import create_access_token
    from datetime import timedelta
    from app.core.config import settings
    from app.main import app
    from app.api.deps import get_current_user
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.office import OfficeStaff
    from app.models.staff import Staff

    access_token = create_access_token(str(manager_office2.id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    headers = {"Authorization": f"Bearer {access_token}"}

    async def override_get_current_user():
        stmt = select(Staff).where(Staff.id == manager_office2.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        )
        result = await db_session.execute(stmt)
        return result.scalars().first()

    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        # Act: Office2 の Manager がリクエストを承認しようとする
        response = await async_client.patch(
            f"/api/v1/employee-action-requests/{request.id}/approve",
            json={"approver_notes": "承認します"},
            headers=headers
        )

        # Assert: 403 Forbidden が返される
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        response_data = response.json()

        assert "detail" in response_data
        assert "office" in response_data["detail"].lower()

        print(f"\n✅ 他の事業所の Manager が承認を試みる: 403 Forbidden")
        print(f"   Error Message: {response_data['detail']}")

    finally:
        app.dependency_overrides.pop(get_current_user, None)
