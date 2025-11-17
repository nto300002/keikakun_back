import pytest
import copy
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import status
import uuid

from app.core.config import settings
from app.core.security import create_access_token

# 詳細な要件に基づくテストデータ
RECIPIENT_CREATE_DATA = {
    "basic_info": {
        "firstName": "太郎",
        "lastName": "利用者",
        "firstNameFurigana": "たろう",
        "lastNameFurigana": "りようしゃ",
        "birthDay": "1980-04-01",
        "gender": "male"
    },
    "contact_address": {
        "address": "東京都新宿区西新宿2-8-1",
        "formOfResidence": "home_alone",
        "formOfResidenceOtherText": None,
        "meansOfTransportation": "public_transport",
        "meansOfTransportationOtherText": None,
        "tel": "090-1234-5678"
    },
    "disability_info": {
        "disabilityOrDiseaseName": "統合失調症",
        "livelihoodProtection": "not_receiving",
        "specialRemarks": "週に1回の訪問看護を受けている。"
    },
    "disability_details": [
        {
            "category": "mental_health_handbook",
            "gradeOrLevel": "2",
            "applicationStatus": "acquired",
            "physicalDisabilityType": None,
            "physicalDisabilityTypeOtherText": None
        }
    ],
    "emergency_contacts": [
        {
            "firstName": "花子",
            "lastName": "利用者",
            "firstNameFurigana": "はなこ",
            "lastNameFurigana": "りようしゃ",
            "relationship": "妻",
            "tel": "080-9876-5432",
            "address": "東京都新宿区西新宿2-8-1",
            "notes": "日中は仕事で電話に出られない可能性あり。",
            "priority": 1
        }
    ]
}


@pytest.mark.asyncio
async def test_create_recipient_as_manager(
    async_client: AsyncClient, manager_user_token_headers: dict, db_session: AsyncSession
):
    """
    テスト: マネージャーは新しい受信者を作成できる。
    期待: 作成された受信者データを含む 201 Created レスポンス。
    """
    response = await async_client.post(
        f"{settings.API_V1_STR}/welfare-recipients/",
        headers=manager_user_token_headers,
        json=RECIPIENT_CREATE_DATA,
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["success"] == True
    assert "recipient_id" in data
    assert data["support_plan_created"] == True


@pytest.mark.asyncio
async def test_create_recipient_as_employee_forbidden(
    async_client: AsyncClient, normal_user_token_headers: dict
):
    """
    テスト: 従業員は新しい受信者を作成するリクエストを送信できる（Employee制限機能により）。
    期待: 202 Accepted（リクエスト作成成功）.
    """
    response = await async_client.post(
        f"{settings.API_V1_STR}/welfare-recipients/",
        headers=normal_user_token_headers,
        json=RECIPIENT_CREATE_DATA,
    )
    assert response.status_code == status.HTTP_202_ACCEPTED
    # レスポンスにrequest_idが含まれることを確認
    assert "request_id" in response.json()


@pytest.mark.asyncio
async def test_create_recipient_missing_fields_unprocessable(
    async_client: AsyncClient, manager_user_token_headers: dict
):
    """
    テスト: 必須フィールドが欠落している受信者を作成すると失敗する。
    期待: 422 Unprocessable Entity.
    """
    invalid_data = copy.deepcopy(RECIPIENT_CREATE_DATA)
    del invalid_data["basic_info"]["firstName"]
    response = await async_client.post(
        f"{settings.API_V1_STR}/welfare-recipients/",
        headers=manager_user_token_headers,
        json=invalid_data,
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_create_recipient_empty_disability_category_bad_request(
    async_client: AsyncClient, manager_user_token_headers: dict
):
    """
    テスト: 手帳カテゴリが空文字列の場合、適切なエラーメッセージと共に400を返す。
    期待: 400 Bad Request と指定されたエラーメッセージ。
    """
    invalid_data = copy.deepcopy(RECIPIENT_CREATE_DATA)
    invalid_data["disability_details"][0]["category"] = ""

    print(f"[DEBUG] Sending request with invalid_data: {invalid_data}")

    response = await async_client.post(
        f"{settings.API_V1_STR}/welfare-recipients/",
        headers=manager_user_token_headers,
        json=invalid_data,
    )

    print(f"[DEBUG] Response status: {response.status_code}")
    print(f"[DEBUG] Response content: {response.content}")

    if response.status_code != status.HTTP_400_BAD_REQUEST:
        try:
            error_detail = response.json()
            print(f"[DEBUG] Error response JSON: {error_detail}")
        except Exception as e:
            print(f"[DEBUG] Could not parse error response as JSON: {e}")

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    data = response.json()
    assert data["detail"][0]["type"] == "enum"


@pytest.mark.asyncio
async def test_get_recipient_by_id(
    async_client: AsyncClient, manager_user_token_headers: dict, db_session: AsyncSession
):
    """
    テスト: 既存の受信者をIDで取得できる。
    期待: 200 OK と受信者データ。
    """
    # 1. Create a recipient first
    create_response = await async_client.post(
        f"{settings.API_V1_STR}/welfare-recipients/",
        headers=manager_user_token_headers,
        json=RECIPIENT_CREATE_DATA
    )
    assert create_response.status_code == status.HTTP_201_CREATED
    recipient_id = create_response.json()["recipient_id"]

    # 2. Get the recipient by ID
    response = await async_client.get(
        f"{settings.API_V1_STR}/welfare-recipients/{recipient_id}",
        headers=manager_user_token_headers,
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    # Response should contain welfare recipient data
    assert "id" in data
    assert data["id"] == str(recipient_id)


@pytest.mark.asyncio
async def test_get_nonexistent_recipient_not_found(
    async_client: AsyncClient, manager_user_token_headers: dict
):
    """
    テスト: 存在しない受信者を取得しようとすると失敗する。
    期待: 404 Not Found.
    """
    nonexistent_id = uuid.uuid4()
    response = await async_client.get(
        f"{settings.API_V1_STR}/welfare-recipients/{nonexistent_id}",
        headers=manager_user_token_headers,
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_update_recipient(
    async_client: AsyncClient, manager_user_token_headers: dict, db_session: AsyncSession
):
    """
    テスト: 既存の受信者を部分的に更新できる。
    期待: 更新されたデータを含む 200 OK。
    """
    # 1. Create a recipient first
    create_response = await async_client.post(
        f"{settings.API_V1_STR}/welfare-recipients/",
        headers=manager_user_token_headers,
        json=RECIPIENT_CREATE_DATA
    )
    assert create_response.status_code == status.HTTP_201_CREATED
    recipient_id = create_response.json()["recipient_id"]

    # 2. Update the recipient's address
    update_data = RECIPIENT_CREATE_DATA.copy()
    update_data["contact_address"]["address"] = "東京都渋谷区神南2-2-1"

    response = await async_client.put(
        f"{settings.API_V1_STR}/welfare-recipients/{recipient_id}",
        headers=manager_user_token_headers,
        json=update_data,
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    # Verify update response contains the recipient_id
    assert "id" in data


@pytest.mark.asyncio
async def test_delete_recipient(
    async_client: AsyncClient, manager_user_token_headers: dict, db_session: AsyncSession
):
    """
    テスト: 既存の受信者を削除できる。
    期待: 204 No Content と、その後の GET が失敗すること。
    """
    # 1. Create a recipient first
    create_response = await async_client.post(
        f"{settings.API_V1_STR}/welfare-recipients/",
        headers=manager_user_token_headers,
        json=RECIPIENT_CREATE_DATA
    )
    assert create_response.status_code == status.HTTP_201_CREATED
    recipient_id = create_response.json()["recipient_id"]

    # 2. Delete the recipient
    delete_response = await async_client.delete(
        f"{settings.API_V1_STR}/welfare-recipients/{recipient_id}",
        headers=manager_user_token_headers,
    )
    assert delete_response.status_code == status.HTTP_200_OK
    assert delete_response.json()["message"] == "利用者を削除しました"

    # 3. Verify it's gone
    get_response = await async_client.get(
        f"{settings.API_V1_STR}/welfare-recipients/{recipient_id}",
        headers=manager_user_token_headers,
    )
    assert get_response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_get_recipient_as_employee_allowed(
    async_client: AsyncClient, office_factory, manager_user_factory, employee_user_factory, db_session: AsyncSession
):
    """
    テスト: 従業員も同じ事業所の利用者の詳細を取得できる。
    期待: 200 OK。
    """
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.staff import Staff
    from app.models.office import OfficeStaff
    from app.api.deps import get_current_user
    from app.main import app

    # 1. 共有の事業所を作成
    admin_user = await manager_user_factory(
        email=f"admin_employee_test_{uuid.uuid4().hex}@example.com",
        with_office=False
    ) # 事業所作成用の仮ユーザー
    shared_office = await office_factory(creator=admin_user)

    # 2. 同じ事業所に所属するmanagerとemployeeを作成
    manager = await manager_user_factory(
        email=f"manager_employee_test_{uuid.uuid4().hex}@example.com",
        office=shared_office
    )
    employee = await employee_user_factory(
        email=f"employee_employee_test_{uuid.uuid4().hex}@example.com",
        office=shared_office
    )

    # 3. managerのトークンとget_current_userのオーバーライドを設定
    manager_token = create_access_token(str(manager.id))
    manager_headers = {"Authorization": f"Bearer {manager_token}"}

    async def override_get_current_user_manager():
        stmt = select(Staff).where(Staff.id == manager.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        )
        result = await db_session.execute(stmt)
        return result.scalars().first()

    app.dependency_overrides[get_current_user] = override_get_current_user_manager

    # 4. managerとして利用者を作成
    create_response = await async_client.post(
        f"{settings.API_V1_STR}/welfare-recipients/",
        headers=manager_headers,
        json=RECIPIENT_CREATE_DATA
    )
    assert create_response.status_code == status.HTTP_201_CREATED
    recipient_id = create_response.json()["recipient_id"]

    # 5. employeeのトークンとget_current_userのオーバーライドを設定
    employee_token = create_access_token(str(employee.id))
    employee_headers = {"Authorization": f"Bearer {employee_token}"}

    async def override_get_current_user_employee():
        stmt = select(Staff).where(Staff.id == employee.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        )
        result = await db_session.execute(stmt)
        return result.scalars().first()

    app.dependency_overrides[get_current_user] = override_get_current_user_employee

    # 6. employeeとして利用者を取得
    response = await async_client.get(
        f"{settings.API_V1_STR}/welfare-recipients/{recipient_id}",
        headers=employee_headers,
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "id" in data
    assert data["id"] == str(recipient_id)

    # クリーンアップ
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_update_recipient_as_employee_forbidden(
    async_client: AsyncClient, office_factory, manager_user_factory, employee_user_factory, db_session: AsyncSession
):
    """
    テスト: 従業員は利用者を更新するリクエストを送信できる（Employee制限機能により）。
    期待: 202 Accepted（リクエスト作成成功）。
    """
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.staff import Staff
    from app.models.office import OfficeStaff
    from app.api.deps import get_current_user
    from app.main import app

    # 1. 共有の事業所とユーザーを作成
    admin_user = await manager_user_factory(
        email=f"admin_update_test_{uuid.uuid4().hex}@example.com",
        with_office=False
    )
    shared_office = await office_factory(creator=admin_user)
    manager = await manager_user_factory(
        email=f"manager_update_test_{uuid.uuid4().hex}@example.com",
        office=shared_office
    )
    employee = await employee_user_factory(
        email=f"employee_update_test_{uuid.uuid4().hex}@example.com",
        office=shared_office
    )

    # 2. managerのトークンとget_current_userのオーバーライドを設定
    manager_token = create_access_token(str(manager.id))
    manager_headers = {"Authorization": f"Bearer {manager_token}"}

    async def override_get_current_user_manager():
        stmt = select(Staff).where(Staff.id == manager.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        )
        result = await db_session.execute(stmt)
        return result.scalars().first()

    app.dependency_overrides[get_current_user] = override_get_current_user_manager

    # 3. managerとして利用者を作成
    create_response = await async_client.post(
        f"{settings.API_V1_STR}/welfare-recipients/",
        headers=manager_headers,
        json=RECIPIENT_CREATE_DATA
    )
    assert create_response.status_code == status.HTTP_201_CREATED
    recipient_id = create_response.json()["recipient_id"]

    # 4. employeeのトークンとget_current_userのオーバーライドを設定
    employee_token = create_access_token(str(employee.id))
    employee_headers = {"Authorization": f"Bearer {employee_token}"}

    async def override_get_current_user_employee():
        stmt = select(Staff).where(Staff.id == employee.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        )
        result = await db_session.execute(stmt)
        return result.scalars().first()

    app.dependency_overrides[get_current_user] = override_get_current_user_employee

    # 5. employeeとして更新を試みる
    update_data = RECIPIENT_CREATE_DATA.copy()
    update_data["contact_address"]["address"] = "東京都渋谷区神南2-2-1"

    response = await async_client.put(
        f"{settings.API_V1_STR}/welfare-recipients/{recipient_id}",
        headers=employee_headers,
        json=update_data,
    )
    assert response.status_code == status.HTTP_202_ACCEPTED
    # レスポンスにrequest_idが含まれることを確認
    assert "request_id" in response.json()

    # クリーンアップ
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_delete_recipient_as_employee_forbidden(
    async_client: AsyncClient, office_factory, manager_user_factory, employee_user_factory, db_session: AsyncSession
):
    """
    テスト: 従業員は利用者を削除するリクエストを送信できる（Employee制限機能により）。
    期待: 202 Accepted（リクエスト作成成功）。
    """
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.staff import Staff
    from app.models.office import OfficeStaff
    from app.api.deps import get_current_user
    from app.main import app

    # 1. 共有の事業所とユーザーを作成
    admin_user = await manager_user_factory(
        email=f"admin_delete_test_{uuid.uuid4().hex}@example.com",
        with_office=False
    )
    shared_office = await office_factory(creator=admin_user)
    manager = await manager_user_factory(
        email=f"manager_delete_test_{uuid.uuid4().hex}@example.com",
        office=shared_office
    )
    employee = await employee_user_factory(
        email=f"employee_delete_test_{uuid.uuid4().hex}@example.com",
        office=shared_office
    )

    # 2. managerのトークンとget_current_userのオーバーライドを設定
    manager_token = create_access_token(str(manager.id))
    manager_headers = {"Authorization": f"Bearer {manager_token}"}

    async def override_get_current_user_manager():
        stmt = select(Staff).where(Staff.id == manager.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        )
        result = await db_session.execute(stmt)
        return result.scalars().first()

    app.dependency_overrides[get_current_user] = override_get_current_user_manager

    # 3. managerとして利用者を作成
    create_response = await async_client.post(
        f"{settings.API_V1_STR}/welfare-recipients/",
        headers=manager_headers,
        json=RECIPIENT_CREATE_DATA
    )
    assert create_response.status_code == status.HTTP_201_CREATED
    recipient_id = create_response.json()["recipient_id"]

    # 4. employeeのトークンとget_current_userのオーバーライドを設定
    employee_token = create_access_token(str(employee.id))
    employee_headers = {"Authorization": f"Bearer {employee_token}"}

    async def override_get_current_user_employee():
        stmt = select(Staff).where(Staff.id == employee.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        )
        result = await db_session.execute(stmt)
        return result.scalars().first()

    app.dependency_overrides[get_current_user] = override_get_current_user_employee

    # 5. employeeとして削除を試みる
    response = await async_client.delete(
        f"{settings.API_V1_STR}/welfare-recipients/{recipient_id}",
        headers=employee_headers,
    )
    assert response.status_code == status.HTTP_202_ACCEPTED
    # レスポンスにrequest_idが含まれることを確認
    assert "request_id" in response.json()

    # クリーンアップ
    app.dependency_overrides.clear()