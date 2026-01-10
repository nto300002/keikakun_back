"""
アセスメントシート機能のAPI層テスト

GET /api/v1/recipients/{recipient_id}/assessment - 全アセスメント情報取得
GET /api/v1/recipients/{recipient_id}/family-members - 家族構成一覧
POST /api/v1/recipients/{recipient_id}/family-members - 家族構成作成
PATCH /api/v1/family-members/{family_member_id} - 家族構成更新
DELETE /api/v1/family-members/{family_member_id} - 家族構成削除
"""

import logging
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import status
from datetime import date, timedelta
from uuid import uuid4

from app.core.config import settings

logger = logging.getLogger(__name__)
from app.models.welfare_recipient import WelfareRecipient, OfficeWelfareRecipient
from app.models.staff import Staff
from app.models.office import Office, OfficeStaff
from app.models.assessment import (
    FamilyOfServiceRecipients,
    WelfareServicesUsed,
    MedicalMatters,
    HistoryOfHospitalVisits,
    EmploymentRelated,
    IssueAnalysis,
)
from app.models.enums import (
    GenderType,
    StaffRole,
    OfficeType,
    Household,
    MedicalCareInsurance,
    AidingType,
    WorkConditions,
    WorkOutsideFacility,
)
from app.core.security import get_password_hash, create_access_token


pytestmark = pytest.mark.asyncio


# テストデータ
EMPLOYMENT_BASE_DATA = {
    "work_conditions": "other",
    "regular_or_part_time_job": False,
    "employment_support": False,
    "work_experience_in_the_past_year": False,
    "suspension_of_work": False,
    "general_employment_request": False,
    "work_outside_the_facility": "not_hope",
}
FAMILY_MEMBER_CREATE_DATA = {
    "name": "花子",
    "relationship": "母",
    "household": "same",
    "ones_health": "良好",
    "remarks": "特になし"
}

MEDICAL_INFO_CREATE_DATA = {
    "medical_care_insurance": "national_health_insurance",
    "aiding": "none",
    "history_of_hospitalization_in_the_past_2_years": False
}

MEDICAL_INFO_CREATE_DATA_WITH_OTHER = {
    "medical_care_insurance": "other",
    "medical_care_insurance_other_text": "特殊な保険",
    "aiding": "none",
    "history_of_hospitalization_in_the_past_2_years": False
}

HOSPITAL_VISIT_CREATE_DATA = {
    "disease": "高血圧",
    "frequency_of_hospital_visits": "月1回",
    "symptoms": "頭痛、めまい",
    "medical_institution": "〇〇病院",
    "doctor": "山田医師",
    "tel": "03-1234-5678",
    "taking_medicine": True,
    "date_started": "2024-01-01",
    "special_remarks": "特になし"
}

EMPLOYMENT_CREATE_DATA = {
    "work_conditions": "other",
    "regular_or_part_time_job": False,
    "employment_support": False,
    "work_experience_in_the_past_year": False,
    "suspension_of_work": False,
    "general_employment_request": False,
    "work_outside_the_facility": "not_hope"
}

ISSUE_ANALYSIS_CREATE_DATA = {
    "what_i_like_to_do": "音楽鑑賞、散歩",
    "im_not_good_at": "人前で話すこと",
    "the_life_i_want": "自立した生活",
    "the_support_i_want": "就労支援",
    "points_to_keep_in_mind_when_providing_support": "ゆっくり話しかけること",
    "future_dreams": "一般就労を目指したい",
    "other": "特になし"
}


class TestGetAllAssessmentData:
    """全アセスメント情報取得のAPIテスト"""

    async def test_get_all_assessment_data_success(
        self, async_client: AsyncClient, db_session: AsyncSession, setup_recipient
    ):
        """200: 全アセスメント情報を正常に取得"""
        recipient, staff, office, token_headers = setup_recipient

        # 家族構成を作成
        family_member = FamilyOfServiceRecipients(
            welfare_recipient_id=recipient.id,
            name="花子",
            relationship="母",
            household=Household.same,
            ones_health="良好",
        )
        db_session.add(family_member)
        await db_session.commit()

        # APIリクエスト
        response = await async_client.get(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/assessment",
            headers=token_headers,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # レスポンス構造の検証
        assert "family_members" in data
        assert "service_history" in data
        assert "medical_info" in data
        assert "hospital_visits" in data
        assert "employment" in data
        assert "issue_analysis" in data

        # 家族構成が取得されていることを確認
        assert len(data["family_members"]) == 1
        assert data["family_members"][0]["name"] == "花子"

    async def test_get_all_assessment_data_empty(
        self, async_client: AsyncClient, setup_recipient
    ):
        """200: データが存在しない場合、空リストまたはNullを返す"""
        recipient, _, _, token_headers = setup_recipient

        response = await async_client.get(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/assessment",
            headers=token_headers,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # 空のデータ構造を確認
        assert data["family_members"] == []
        assert data["service_history"] == []
        assert data["medical_info"] is None
        assert data["hospital_visits"] == []
        assert data["employment"] is None
        assert data["issue_analysis"] is None

    async def test_get_all_assessment_data_unauthorized(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        """401: 未認証の場合、エラーを返す"""
        print("\n" + "="*80)
        print("=== TEST: test_get_all_assessment_data_unauthorized START ===")
        print("NOTE: This test does NOT use setup_recipient to avoid dependency override")
        logger.info("=== test_get_all_assessment_data_unauthorized start ===")

        # 利用者だけを作成（オーバーライドなし）
        recipient = WelfareRecipient(
            last_name="テスト",
            first_name="太郎",
            last_name_furigana="テスト",
            first_name_furigana="タロウ",
            birth_day=date(1990, 1, 1),
            gender=GenderType.male
        )
        db_session.add(recipient)
        await db_session.flush()
        await db_session.refresh(recipient)

        print(f"Testing with recipient_id: {recipient.id}")
        print("Sending request WITHOUT authorization headers (no override)")
        logger.info(f"Testing with recipient_id: {recipient.id}")
        logger.info("Sending request WITHOUT authorization headers")

        response = await async_client.get(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/assessment",
        )

        print(f"Response status code: {response.status_code}")
        print(f"Response body: {response.text}")
        print("="*80 + "\n")
        logger.info(f"Response status code: {response.status_code}")
        logger.info(f"Response body: {response.text}")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_get_all_assessment_data_forbidden(
        self, async_client: AsyncClient, db_session: AsyncSession, setup_other_office_staff, manager_user_factory, office_factory
    ):
        """403: 別事業所のスタッフはアクセス拒否"""
        # 別の事業所と利用者を作成（setup_recipientを使わない）
        manager = await manager_user_factory(session=db_session)
        await db_session.commit()
        office = manager.office_associations[0].office

        recipient = WelfareRecipient(
            last_name="テスト",
            first_name="太郎",
            last_name_furigana="テスト",
            first_name_furigana="タロウ",
            birth_day=date(1990, 1, 1),
            gender=GenderType.male
        )
        db_session.add(recipient)
        await db_session.flush()

        # 事業所との関連付け
        office_recipient_association = OfficeWelfareRecipient(
            welfare_recipient_id=recipient.id,
            office_id=office.id
        )
        db_session.add(office_recipient_association)
        await db_session.flush()
        await db_session.refresh(recipient)
        _, other_office_token_headers = setup_other_office_staff

        response = await async_client.get(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/assessment",
            headers=other_office_token_headers,  # 別事業所のトークン
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_get_all_assessment_data_not_found(
        self, async_client: AsyncClient, manager_user_token_headers: dict
    ):
        """404: 存在しない利用者の場合、エラーを返す"""
        nonexistent_recipient_id = uuid4()

        response = await async_client.get(
            f"{settings.API_V1_STR}/recipients/{nonexistent_recipient_id}/assessment",
            headers=manager_user_token_headers,
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestFamilyMemberEndpoints:
    """家族構成のエンドポイントテスト"""

    async def test_get_family_members_success(
        self, async_client: AsyncClient, setup_recipient
    ):
        """200: 家族構成一覧を正常に取得"""
        recipient, _, _, token_headers = setup_recipient

        response = await async_client.get(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/family-members",
            headers=token_headers,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)

    async def test_get_family_members_empty_list(
        self, async_client: AsyncClient, setup_recipient
    ):
        """200: データがない場合、空リストを返す"""
        recipient, _, _, token_headers = setup_recipient

        response = await async_client.get(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/family-members",
            headers=token_headers,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data == []

    async def test_create_family_member_success(
        self, async_client: AsyncClient, setup_recipient
    ):
        """201: 家族構成を正常に作成"""
        recipient, _, _, token_headers = setup_recipient

        response = await async_client.post(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/family-members",
            headers=token_headers,
            json=FAMILY_MEMBER_CREATE_DATA,
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["name"] == "花子"
        assert data["relationship"] == "母"
        assert "id" in data
        assert "created_at" in data

    async def test_create_family_member_validation_error(
        self, async_client: AsyncClient, setup_recipient
    ):
        """422: バリデーションエラー（必須フィールド欠如）"""
        recipient, _, _, token_headers = setup_recipient

        invalid_data = {
            "name": "",  # 空文字列
            "relationship": "母",
            "household": "same",
            "ones_health": "良好"
        }

        response = await async_client.post(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/family-members",
            headers=token_headers,
            json=invalid_data,
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    async def test_create_family_member_unauthorized(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        """401: 未認証の場合、エラーを返す"""
        # 利用者だけを作成（オーバーライドなし）
        recipient = WelfareRecipient(
            last_name="テスト",
            first_name="太郎",
            last_name_furigana="テスト",
            first_name_furigana="タロウ",
            birth_day=date(1990, 1, 1),
            gender=GenderType.male
        )
        db_session.add(recipient)
        await db_session.flush()
        await db_session.refresh(recipient)

        response = await async_client.post(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/family-members",
            json=FAMILY_MEMBER_CREATE_DATA,
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_create_family_member_forbidden(
        self, async_client: AsyncClient, db_session: AsyncSession, setup_other_office_staff, manager_user_factory, office_factory
    ):
        """403: 別事業所のスタッフは作成拒否"""
        # 別の事業所と利用者を作成（setup_recipientを使わない）
        manager = await manager_user_factory(session=db_session)
        await db_session.commit()
        office = manager.office_associations[0].office

        recipient = WelfareRecipient(
            last_name="テスト",
            first_name="太郎",
            last_name_furigana="テスト",
            first_name_furigana="タロウ",
            birth_day=date(1990, 1, 1),
            gender=GenderType.male
        )
        db_session.add(recipient)
        await db_session.flush()

        # 事業所との関連付け
        office_recipient_association = OfficeWelfareRecipient(
            welfare_recipient_id=recipient.id,
            office_id=office.id
        )
        db_session.add(office_recipient_association)
        await db_session.flush()
        await db_session.refresh(recipient)
        _, other_office_token_headers = setup_other_office_staff

        response = await async_client.post(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/family-members",
            headers=other_office_token_headers,  # 別事業所のトークン
            json=FAMILY_MEMBER_CREATE_DATA,
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_create_family_member_recipient_not_found(
        self, async_client: AsyncClient, manager_user_token_headers: dict
    ):
        """404: 存在しない利用者の場合、エラーを返す"""
        nonexistent_recipient_id = uuid4()

        response = await async_client.post(
            f"{settings.API_V1_STR}/recipients/{nonexistent_recipient_id}/family-members",
            headers=manager_user_token_headers,
            json=FAMILY_MEMBER_CREATE_DATA,
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_update_family_member_success(
        self, async_client: AsyncClient, db_session: AsyncSession, setup_recipient
    ):
        """200: 家族構成を正常に更新"""
        recipient, _, _, token_headers = setup_recipient

        # 家族構成を作成
        family_member = FamilyOfServiceRecipients(
            welfare_recipient_id=recipient.id,
            name="花子",
            relationship="母",
            household=Household.same,
            ones_health="良好",
        )
        db_session.add(family_member)
        await db_session.commit()
        await db_session.refresh(family_member)

        update_data = {
            "name": "花子（更新）",
            "ones_health": "やや不良"
        }

        response = await async_client.patch(
            f"{settings.API_V1_STR}/family-members/{family_member.id}",
            headers=token_headers,
            json=update_data,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["name"] == "花子（更新）"
        assert data["ones_health"] == "やや不良"

    async def test_update_family_member_not_found(
        self, async_client: AsyncClient, manager_user_token_headers: dict
    ):
        """404: 存在しない家族構成の場合、エラーを返す"""
        nonexistent_family_member_id = 99999

        update_data = {"name": "更新"}

        response = await async_client.patch(
            f"{settings.API_V1_STR}/family-members/{nonexistent_family_member_id}",
            headers=manager_user_token_headers,
            json=update_data,
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_delete_family_member_success(
        self, async_client: AsyncClient, db_session: AsyncSession, setup_recipient
    ):
        """200: 家族構成を正常に削除"""
        recipient, _, _, token_headers = setup_recipient

        # 家族構成を作成
        family_member = FamilyOfServiceRecipients(
            welfare_recipient_id=recipient.id,
            name="花子",
            relationship="母",
            household=Household.same,
            ones_health="良好",
        )
        db_session.add(family_member)
        await db_session.commit()
        await db_session.refresh(family_member)

        response = await async_client.delete(
            f"{settings.API_V1_STR}/family-members/{family_member.id}",
            headers=token_headers,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "message" in data

    async def test_delete_family_member_not_found(
        self, async_client: AsyncClient, manager_user_token_headers: dict
    ):
        """404: 存在しない家族構成の場合、エラーを返す"""
        nonexistent_family_member_id = 99999

        response = await async_client.delete(
            f"{settings.API_V1_STR}/family-members/{nonexistent_family_member_id}",
            headers=manager_user_token_headers,
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestMedicalInfoEndpoints:
    """医療基本情報のエンドポイントテスト"""

    async def test_get_medical_info_success(
        self, async_client: AsyncClient, db_session: AsyncSession, setup_recipient
    ):
        """200: 医療基本情報を正常に取得"""
        recipient, _, _, token_headers = setup_recipient

        # 医療基本情報を作成
        medical_info = MedicalMatters(
            welfare_recipient_id=recipient.id,
            medical_care_insurance=MedicalCareInsurance.national_health_insurance,
            aiding=AidingType.none,
            history_of_hospitalization_in_the_past_2_years=False,
        )
        db_session.add(medical_info)
        await db_session.commit()
        await db_session.refresh(medical_info)

        response = await async_client.get(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/medical-info",
            headers=token_headers,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["medical_care_insurance"] == "national_health_insurance"
        assert data["aiding"] == "none"
        assert data["history_of_hospitalization_in_the_past_2_years"] is False
        assert "id" in data

    async def test_get_medical_info_null(
        self, async_client: AsyncClient, setup_recipient
    ):
        """200: データがない場合、nullを返す"""
        recipient, _, _, token_headers = setup_recipient

        response = await async_client.get(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/medical-info",
            headers=token_headers,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data is None

    async def test_get_medical_info_unauthorized(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        """401: 未認証の場合、エラーを返す"""
        # 利用者だけを作成（オーバーライドなし）
        recipient = WelfareRecipient(
            last_name="テスト",
            first_name="太郎",
            last_name_furigana="テスト",
            first_name_furigana="タロウ",
            birth_day=date(1990, 1, 1),
            gender=GenderType.male
        )
        db_session.add(recipient)
        await db_session.flush()
        await db_session.refresh(recipient)

        response = await async_client.get(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/medical-info",
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_get_medical_info_forbidden(
        self, async_client: AsyncClient, db_session: AsyncSession, setup_other_office_staff, manager_user_factory, office_factory
    ):
        """403: 別事業所のスタッフはアクセス拒否"""
        # 別の事業所と利用者を作成（setup_recipientを使わない）
        manager = await manager_user_factory(session=db_session)
        await db_session.commit()
        office = manager.office_associations[0].office

        recipient = WelfareRecipient(
            last_name="テスト",
            first_name="太郎",
            last_name_furigana="テスト",
            first_name_furigana="タロウ",
            birth_day=date(1990, 1, 1),
            gender=GenderType.male
        )
        db_session.add(recipient)
        await db_session.flush()

        # 事業所との関連付け
        office_recipient_association = OfficeWelfareRecipient(
            welfare_recipient_id=recipient.id,
            office_id=office.id
        )
        db_session.add(office_recipient_association)
        await db_session.flush()
        await db_session.refresh(recipient)
        _, other_office_token_headers = setup_other_office_staff

        response = await async_client.get(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/medical-info",
            headers=other_office_token_headers,  # 別事業所のトークン
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_get_medical_info_not_found(
        self, async_client: AsyncClient, manager_user_token_headers: dict
    ):
        """404: 存在しない利用者の場合、エラーを返す"""
        nonexistent_recipient_id = uuid4()

        response = await async_client.get(
            f"{settings.API_V1_STR}/recipients/{nonexistent_recipient_id}/medical-info",
            headers=manager_user_token_headers,
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_upsert_medical_info_create_success(
        self, async_client: AsyncClient, setup_recipient
    ):
        """200: 医療基本情報を正常に作成（upsert）"""
        recipient, _, _, token_headers = setup_recipient

        response = await async_client.put(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/medical-info",
            headers=token_headers,
            json=MEDICAL_INFO_CREATE_DATA,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["medical_care_insurance"] == "national_health_insurance"
        assert "id" in data
        assert "created_at" in data

    async def test_upsert_medical_info_update_success(
        self, async_client: AsyncClient, db_session: AsyncSession, setup_recipient
    ):
        """200: 医療基本情報を正常に更新"""
        recipient, _, _, token_headers = setup_recipient

        # 医療基本情報を先に作成
        medical_info = MedicalMatters(
            welfare_recipient_id=recipient.id,
            medical_care_insurance=MedicalCareInsurance.national_health_insurance,
            aiding=AidingType.none,
            history_of_hospitalization_in_the_past_2_years=False,
        )
        db_session.add(medical_info)
        await db_session.commit()

        # 更新
        update_data = {
            "medical_care_insurance": "social_insurance",
            "aiding": "none",
            "history_of_hospitalization_in_the_past_2_years": True,
        }

        response = await async_client.put(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/medical-info",
            headers=token_headers,
            json=update_data,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["medical_care_insurance"] == "social_insurance"
        assert data["history_of_hospitalization_in_the_past_2_years"] is True

    async def test_upsert_medical_info_validation_error_other_text_missing(
        self, async_client: AsyncClient, setup_recipient
    ):
        """422: 条件付きバリデーションエラー（other指定時のテキスト欠如）"""
        recipient, _, _, token_headers = setup_recipient

        invalid_data = {
            "medical_care_insurance": "other",
            # medical_care_insurance_other_text が欠如
            "aiding": "none",
            "history_of_hospitalization_in_the_past_2_years": False,
        }

        response = await async_client.put(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/medical-info",
            headers=token_headers,
            json=invalid_data,
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    async def test_upsert_medical_info_with_other_text_success(
        self, async_client: AsyncClient, setup_recipient
    ):
        """200: medical_care_insurance=otherの場合、other_textを含めて作成（upsert）"""
        recipient, _, _, token_headers = setup_recipient

        response = await async_client.put(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/medical-info",
            headers=token_headers,
            json=MEDICAL_INFO_CREATE_DATA_WITH_OTHER,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["medical_care_insurance"] == "other"
        assert data["medical_care_insurance_other_text"] == "特殊な保険"

    async def test_upsert_medical_info_unauthorized(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        """401: 未認証の場合、エラーを返す"""
        # 利用者だけを作成（オーバーライドなし）
        recipient = WelfareRecipient(
            last_name="テスト",
            first_name="太郎",
            last_name_furigana="テスト",
            first_name_furigana="タロウ",
            birth_day=date(1990, 1, 1),
            gender=GenderType.male
        )
        db_session.add(recipient)
        await db_session.flush()
        await db_session.refresh(recipient)

        response = await async_client.put(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/medical-info",
            json=MEDICAL_INFO_CREATE_DATA,
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_upsert_medical_info_forbidden(
        self, async_client: AsyncClient, db_session: AsyncSession, setup_other_office_staff, manager_user_factory, office_factory
    ):
        """403: 別事業所のスタッフは作成/更新拒否"""
        # 別の事業所と利用者を作成（setup_recipientを使わない）
        manager = await manager_user_factory(session=db_session)
        await db_session.commit()
        office = manager.office_associations[0].office

        recipient = WelfareRecipient(
            last_name="テスト",
            first_name="太郎",
            last_name_furigana="テスト",
            first_name_furigana="タロウ",
            birth_day=date(1990, 1, 1),
            gender=GenderType.male
        )
        db_session.add(recipient)
        await db_session.flush()

        # 事業所との関連付け
        office_recipient_association = OfficeWelfareRecipient(
            welfare_recipient_id=recipient.id,
            office_id=office.id
        )
        db_session.add(office_recipient_association)
        await db_session.flush()
        await db_session.refresh(recipient)
        _, other_office_token_headers = setup_other_office_staff

        response = await async_client.put(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/medical-info",
            headers=other_office_token_headers,  # 別事業所のトークン
            json=MEDICAL_INFO_CREATE_DATA,
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_upsert_medical_info_recipient_not_found(
        self, async_client: AsyncClient, manager_user_token_headers: dict
    ):
        """404: 存在しない利用者の場合、エラーを返す"""
        nonexistent_recipient_id = uuid4()

        response = await async_client.put(
            f"{settings.API_V1_STR}/recipients/{nonexistent_recipient_id}/medical-info",
            headers=manager_user_token_headers,
            json=MEDICAL_INFO_CREATE_DATA,
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestHospitalVisitEndpoints:
    """通院歴のエンドポイントテスト"""

    async def test_get_hospital_visits_success(
        self, async_client: AsyncClient, db_session: AsyncSession, setup_recipient
    ):
        """200: 通院歴一覧を正常に取得"""
        recipient, _, _, token_headers = setup_recipient

        # 医療基本情報を作成
        medical_info = MedicalMatters(
            welfare_recipient_id=recipient.id,
            medical_care_insurance=MedicalCareInsurance.national_health_insurance,
            aiding=AidingType.none,
            history_of_hospitalization_in_the_past_2_years=False,
        )
        db_session.add(medical_info)
        await db_session.commit()
        await db_session.refresh(medical_info)

        # 通院歴を作成
        hospital_visit = HistoryOfHospitalVisits(
            medical_matters_id=medical_info.id,
            disease="高血圧",
            frequency_of_hospital_visits="月1回",
            symptoms="頭痛、めまい",
            medical_institution="〇〇病院",
            doctor="山田医師",
            tel="03-1234-5678",
            taking_medicine=True,
            date_started=date(2024, 1, 1),
        )
        db_session.add(hospital_visit)
        await db_session.commit()

        response = await async_client.get(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/hospital-visits",
            headers=token_headers,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["disease"] == "高血圧"

    async def test_get_hospital_visits_empty_list(
        self, async_client: AsyncClient, setup_recipient
    ):
        """200: データがない場合、空リストを返す"""
        recipient, _, _, token_headers = setup_recipient

        response = await async_client.get(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/hospital-visits",
            headers=token_headers,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data == []

    async def test_create_hospital_visit_success(
        self, async_client: AsyncClient, setup_recipient
    ):
        """201: 通院歴を正常に作成"""
        recipient, _, _, token_headers = setup_recipient

        response = await async_client.post(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/hospital-visits",
            headers=token_headers,
            json=HOSPITAL_VISIT_CREATE_DATA,
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["disease"] == "高血圧"
        assert data["doctor"] == "山田医師"
        assert "id" in data
        assert "created_at" in data

    async def test_create_hospital_visit_validation_error(
        self, async_client: AsyncClient, setup_recipient
    ):
        """422: バリデーションエラー（必須フィールド欠如）"""
        recipient, _, _, token_headers = setup_recipient

        invalid_data = {
            "disease": "",  # 空文字列
            "frequency_of_hospital_visits": "月1回",
            "symptoms": "頭痛",
            "medical_institution": "〇〇病院",
            "doctor": "山田医師",
            "tel": "03-1234-5678",
            "taking_medicine": True,
        }

        response = await async_client.post(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/hospital-visits",
            headers=token_headers,
            json=invalid_data,
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    async def test_create_hospital_visit_date_validation_error(
        self, async_client: AsyncClient, setup_recipient
    ):
        """400: 日付の論理的整合性エラー（date_started > date_ended）"""
        recipient, _, _, token_headers = setup_recipient

        invalid_data = {
            "disease": "高血圧",
            "frequency_of_hospital_visits": "月1回",
            "symptoms": "頭痛",
            "medical_institution": "〇〇病院",
            "doctor": "山田医師",
            "tel": "03-1234-5678",
            "taking_medicine": True,
            "date_started": "2024-12-31",
            "date_ended": "2024-01-01",  # date_startedより前
        }

        response = await async_client.post(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/hospital-visits",
            headers=token_headers,
            json=invalid_data,
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    async def test_create_hospital_visit_unauthorized(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        """401: 未認証の場合、エラーを返す"""
        # 利用者だけを作成（オーバーライドなし）
        recipient = WelfareRecipient(
            last_name="テスト",
            first_name="太郎",
            last_name_furigana="テスト",
            first_name_furigana="タロウ",
            birth_day=date(1990, 1, 1),
            gender=GenderType.male
        )
        db_session.add(recipient)
        await db_session.flush()
        await db_session.refresh(recipient)

        response = await async_client.post(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/hospital-visits",
            json=HOSPITAL_VISIT_CREATE_DATA,
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_update_hospital_visit_success(
        self, async_client: AsyncClient, db_session: AsyncSession, setup_recipient
    ):
        """200: 通院歴を正常に更新"""
        recipient, _, _, token_headers = setup_recipient

        # 医療基本情報を作成
        medical_info = MedicalMatters(
            welfare_recipient_id=recipient.id,
            medical_care_insurance=MedicalCareInsurance.national_health_insurance,
            aiding=AidingType.none,
            history_of_hospitalization_in_the_past_2_years=False,
        )
        db_session.add(medical_info)
        await db_session.commit()
        await db_session.refresh(medical_info)

        # 通院歴を作成
        hospital_visit = HistoryOfHospitalVisits(
            medical_matters_id=medical_info.id,
            disease="高血圧",
            frequency_of_hospital_visits="月1回",
            symptoms="頭痛、めまい",
            medical_institution="〇〇病院",
            doctor="山田医師",
            tel="03-1234-5678",
            taking_medicine=True,
        )
        db_session.add(hospital_visit)
        await db_session.commit()
        await db_session.refresh(hospital_visit)

        update_data = {
            "disease": "高血圧（安定）",
            "frequency_of_hospital_visits": "3ヶ月に1回"
        }

        response = await async_client.patch(
            f"{settings.API_V1_STR}/hospital-visits/{hospital_visit.id}",
            headers=token_headers,
            json=update_data,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["disease"] == "高血圧（安定）"
        assert data["frequency_of_hospital_visits"] == "3ヶ月に1回"

    async def test_update_hospital_visit_not_found(
        self, async_client: AsyncClient, manager_user_token_headers: dict
    ):
        """404: 存在しない通院歴の場合、エラーを返す"""
        nonexistent_visit_id = 99999

        update_data = {"disease": "更新"}

        response = await async_client.patch(
            f"{settings.API_V1_STR}/hospital-visits/{nonexistent_visit_id}",
            headers=manager_user_token_headers,
            json=update_data,
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_delete_hospital_visit_success(
        self, async_client: AsyncClient, db_session: AsyncSession, setup_recipient
    ):
        """200: 通院歴を正常に削除"""
        recipient, _, _, token_headers = setup_recipient

        # 医療基本情報を作成
        medical_info = MedicalMatters(
            welfare_recipient_id=recipient.id,
            medical_care_insurance=MedicalCareInsurance.national_health_insurance,
            aiding=AidingType.none,
            history_of_hospitalization_in_the_past_2_years=False,
        )
        db_session.add(medical_info)
        await db_session.commit()
        await db_session.refresh(medical_info)

        # 通院歴を作成
        hospital_visit = HistoryOfHospitalVisits(
            medical_matters_id=medical_info.id,
            disease="高血圧",
            frequency_of_hospital_visits="月1回",
            symptoms="頭痛、めまい",
            medical_institution="〇〇病院",
            doctor="山田医師",
            tel="03-1234-5678",
            taking_medicine=True,
        )
        db_session.add(hospital_visit)
        await db_session.commit()
        await db_session.refresh(hospital_visit)

        response = await async_client.delete(
            f"{settings.API_V1_STR}/hospital-visits/{hospital_visit.id}",
            headers=token_headers,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "message" in data

    async def test_delete_hospital_visit_not_found(
        self, async_client: AsyncClient, manager_user_token_headers: dict
    ):
        """404: 存在しない通院歴の場合、エラーを返す"""
        nonexistent_visit_id = 99999

        response = await async_client.delete(
            f"{settings.API_V1_STR}/hospital-visits/{nonexistent_visit_id}",
            headers=manager_user_token_headers,
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestEmploymentEndpoints:
    """就労関係のエンドポイントテスト"""

    async def test_get_employment_success(
        self, async_client: AsyncClient, db_session: AsyncSession, setup_recipient
    ):
        """200: 就労関係情報を正常に取得"""
        recipient, staff, _, token_headers = setup_recipient

        # 就労関係情報を作成
        employment = EmploymentRelated(
            welfare_recipient_id=recipient.id,
            created_by_staff_id=staff.id,
            work_conditions=WorkConditions.other,
            regular_or_part_time_job=False,
            employment_support=False,
            work_experience_in_the_past_year=False,
            suspension_of_work=False,
            general_employment_request=False,
            work_outside_the_facility=WorkOutsideFacility.not_hope,
        )
        db_session.add(employment)
        await db_session.commit()
        await db_session.refresh(employment)

        response = await async_client.get(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/employment",
            headers=token_headers,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["work_conditions"] == "other"
        assert data["regular_or_part_time_job"] is False
        assert "id" in data
        assert "created_by_staff_id" in data

    async def test_get_employment_null(
        self, async_client: AsyncClient, setup_recipient
    ):
        """200: データがない場合、nullを返す"""
        recipient, _, _, token_headers = setup_recipient

        response = await async_client.get(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/employment",
            headers=token_headers,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data is None

    async def test_get_employment_unauthorized(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        """401: 未認証の場合、エラーを返す"""
        # 利用者だけを作成（オーバーライドなし）
        recipient = WelfareRecipient(
            last_name="テスト",
            first_name="太郎",
            last_name_furigana="テスト",
            first_name_furigana="タロウ",
            birth_day=date(1990, 1, 1),
            gender=GenderType.male
        )
        db_session.add(recipient)
        await db_session.flush()
        await db_session.refresh(recipient)

        response = await async_client.get(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/employment",
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_get_employment_forbidden(
        self, async_client: AsyncClient, db_session: AsyncSession, setup_other_office_staff, manager_user_factory, office_factory
    ):
        """403: 別事業所のスタッフはアクセス拒否"""
        # 別の事業所と利用者を作成（setup_recipientを使わない）
        manager = await manager_user_factory(session=db_session)
        await db_session.commit()
        office = manager.office_associations[0].office

        recipient = WelfareRecipient(
            last_name="テスト",
            first_name="太郎",
            last_name_furigana="テスト",
            first_name_furigana="タロウ",
            birth_day=date(1990, 1, 1),
            gender=GenderType.male
        )
        db_session.add(recipient)
        await db_session.flush()

        # 事業所との関連付け
        office_recipient_association = OfficeWelfareRecipient(
            welfare_recipient_id=recipient.id,
            office_id=office.id
        )
        db_session.add(office_recipient_association)
        await db_session.flush()
        await db_session.refresh(recipient)
        _, other_office_token_headers = setup_other_office_staff

        response = await async_client.get(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/employment",
            headers=other_office_token_headers,  # 別事業所のトークン
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_get_employment_not_found(
        self, async_client: AsyncClient, manager_user_token_headers: dict
    ):
        """404: 存在しない利用者の場合、エラーを返す"""
        nonexistent_recipient_id = uuid4()

        response = await async_client.get(
            f"{settings.API_V1_STR}/recipients/{nonexistent_recipient_id}/employment",
            headers=manager_user_token_headers,
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_upsert_employment_create_success(
        self, async_client: AsyncClient, setup_recipient
    ):
        """201: 就労関係情報を正常に作成"""
        recipient, _, _, token_headers = setup_recipient

        response = await async_client.put(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/employment",
            headers=token_headers,
            json=EMPLOYMENT_CREATE_DATA,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["work_conditions"] == "other"
        assert "id" in data
        assert "created_at" in data
        assert "created_by_staff_id" in data

    async def test_upsert_employment_update_success(
        self, async_client: AsyncClient, db_session: AsyncSession, setup_recipient
    ):
        """200: 就労関係情報を正常に更新"""
        recipient, staff, _, token_headers = setup_recipient

        # 就労関係情報を先に作成
        employment = EmploymentRelated(
            welfare_recipient_id=recipient.id,
            created_by_staff_id=staff.id,
            work_conditions=WorkConditions.other,
            regular_or_part_time_job=False,
            employment_support=False,
            work_experience_in_the_past_year=False,
            suspension_of_work=False,
            general_employment_request=False,
            work_outside_the_facility=WorkOutsideFacility.not_hope,
        )
        db_session.add(employment)
        await db_session.commit()
        await db_session.refresh(employment)

        original_staff_id = employment.created_by_staff_id

        # 更新
        update_data = {
            "work_conditions": "general_employment",
            "regular_or_part_time_job": True,
            "employment_support": True,
            "work_experience_in_the_past_year": True,
            "suspension_of_work": False,
            "general_employment_request": True,
            "work_outside_the_facility": "hope",
        }

        response = await async_client.put(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/employment",
            headers=token_headers,
            json=update_data,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["work_conditions"] == "general_employment"
        assert data["regular_or_part_time_job"] is True
        # created_by_staff_idは変更されないことを確認
        assert data["created_by_staff_id"] == str(original_staff_id)

    async def test_upsert_employment_validation_error(
        self, async_client: AsyncClient, setup_recipient
    ):
        """422: バリデーションエラー（必須フィールド欠如）"""
        recipient, _, _, token_headers = setup_recipient

        invalid_data = {
            # work_conditions が欠如
            "regular_or_part_time_job": False,
            "employment_support": False,
        }

        response = await async_client.put(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/employment",
            headers=token_headers,
            json=invalid_data,
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    async def test_upsert_employment_unauthorized(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        """401: 未認証の場合、エラーを返す"""
        # 利用者だけを作成（オーバーライドなし）
        recipient = WelfareRecipient(
            last_name="テスト",
            first_name="太郎",
            last_name_furigana="テスト",
            first_name_furigana="タロウ",
            birth_day=date(1990, 1, 1),
            gender=GenderType.male
        )
        db_session.add(recipient)
        await db_session.flush()
        await db_session.refresh(recipient)

        response = await async_client.put(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/employment",
            json=EMPLOYMENT_CREATE_DATA,
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_upsert_employment_forbidden(
        self, async_client: AsyncClient, db_session: AsyncSession, setup_other_office_staff, manager_user_factory, office_factory
    ):
        """403: 別事業所のスタッフは作成/更新拒否"""
        # 別の事業所と利用者を作成（setup_recipientを使わない）
        manager = await manager_user_factory(session=db_session)
        await db_session.commit()
        office = manager.office_associations[0].office

        recipient = WelfareRecipient(
            last_name="テスト",
            first_name="太郎",
            last_name_furigana="テスト",
            first_name_furigana="タロウ",
            birth_day=date(1990, 1, 1),
            gender=GenderType.male
        )
        db_session.add(recipient)
        await db_session.flush()

        # 事業所との関連付け
        office_recipient_association = OfficeWelfareRecipient(
            welfare_recipient_id=recipient.id,
            office_id=office.id
        )
        db_session.add(office_recipient_association)
        await db_session.flush()
        await db_session.refresh(recipient)
        _, other_office_token_headers = setup_other_office_staff

        response = await async_client.put(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/employment",
            headers=other_office_token_headers,  # 別事業所のトークン
            json=EMPLOYMENT_CREATE_DATA,
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_upsert_employment_recipient_not_found(
        self, async_client: AsyncClient, manager_user_token_headers: dict
    ):
        """404: 存在しない利用者の場合、エラーを返す"""
        nonexistent_recipient_id = uuid4()

        response = await async_client.put(
            f"{settings.API_V1_STR}/recipients/{nonexistent_recipient_id}/employment",
            headers=manager_user_token_headers,
            json=EMPLOYMENT_CREATE_DATA,
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestIssueAnalysisEndpoints:
    """課題分析のエンドポイントテスト"""

    async def test_get_issue_analysis_success(
        self, async_client: AsyncClient, db_session: AsyncSession, setup_recipient
    ):
        """200: 課題分析を正常に取得"""
        recipient, staff, _, token_headers = setup_recipient

        # 課題分析を作成
        issue_analysis = IssueAnalysis(
            welfare_recipient_id=recipient.id,
            created_by_staff_id=staff.id,
            what_i_like_to_do="音楽鑑賞、散歩",
            im_not_good_at="人前で話すこと",
            the_life_i_want="自立した生活",
            the_support_i_want="就労支援",
        )
        db_session.add(issue_analysis)
        await db_session.commit()
        await db_session.refresh(issue_analysis)

        response = await async_client.get(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/issue-analysis",
            headers=token_headers,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["what_i_like_to_do"] == "音楽鑑賞、散歩"
        assert data["im_not_good_at"] == "人前で話すこと"
        assert "id" in data
        assert "created_by_staff_id" in data

    async def test_get_issue_analysis_null(
        self, async_client: AsyncClient, setup_recipient
    ):
        """200: データがない場合、nullを返す"""
        recipient, _, _, token_headers = setup_recipient

        response = await async_client.get(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/issue-analysis",
            headers=token_headers,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data is None

    async def test_get_issue_analysis_unauthorized(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        """401: 未認証の場合、エラーを返す"""
        # 利用者だけを作成（オーバーライドなし）
        recipient = WelfareRecipient(
            last_name="テスト",
            first_name="太郎",
            last_name_furigana="テスト",
            first_name_furigana="タロウ",
            birth_day=date(1990, 1, 1),
            gender=GenderType.male
        )
        db_session.add(recipient)
        await db_session.flush()
        await db_session.refresh(recipient)

        response = await async_client.get(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/issue-analysis",
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_get_issue_analysis_forbidden(
        self, async_client: AsyncClient, db_session: AsyncSession, setup_other_office_staff, manager_user_factory, office_factory
    ):
        """403: 別事業所のスタッフはアクセス拒否"""
        # 別の事業所と利用者を作成（setup_recipientを使わない）
        manager = await manager_user_factory(session=db_session)
        await db_session.commit()
        office = manager.office_associations[0].office

        recipient = WelfareRecipient(
            last_name="テスト",
            first_name="太郎",
            last_name_furigana="テスト",
            first_name_furigana="タロウ",
            birth_day=date(1990, 1, 1),
            gender=GenderType.male
        )
        db_session.add(recipient)
        await db_session.flush()

        # 事業所との関連付け
        office_recipient_association = OfficeWelfareRecipient(
            welfare_recipient_id=recipient.id,
            office_id=office.id
        )
        db_session.add(office_recipient_association)
        await db_session.flush()
        await db_session.refresh(recipient)
        _, other_office_token_headers = setup_other_office_staff

        response = await async_client.get(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/issue-analysis",
            headers=other_office_token_headers,  # 別事業所のトークン
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_get_issue_analysis_not_found(
        self, async_client: AsyncClient, manager_user_token_headers: dict
    ):
        """404: 存在しない利用者の場合、エラーを返す"""
        nonexistent_recipient_id = uuid4()

        response = await async_client.get(
            f"{settings.API_V1_STR}/recipients/{nonexistent_recipient_id}/issue-analysis",
            headers=manager_user_token_headers,
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_upsert_issue_analysis_create_success(
        self, async_client: AsyncClient, setup_recipient
    ):
        """201: 課題分析を正常に作成"""
        recipient, _, _, token_headers = setup_recipient

        response = await async_client.put(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/issue-analysis",
            headers=token_headers,
            json=ISSUE_ANALYSIS_CREATE_DATA,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["what_i_like_to_do"] == "音楽鑑賞、散歩"
        assert data["future_dreams"] == "一般就労を目指したい"
        assert "id" in data
        assert "created_by_staff_id" in data

    async def test_upsert_issue_analysis_update_success(
        self, async_client: AsyncClient, db_session: AsyncSession, setup_recipient
    ):
        """200: 課題分析を正常に更新"""
        recipient, staff, _, token_headers = setup_recipient

        # 課題分析を先に作成
        issue_analysis = IssueAnalysis(
            welfare_recipient_id=recipient.id,
            created_by_staff_id=staff.id,
            what_i_like_to_do="音楽鑑賞",
            im_not_good_at="人前で話すこと",
        )
        db_session.add(issue_analysis)
        await db_session.commit()
        await db_session.refresh(issue_analysis)

        original_staff_id = issue_analysis.created_by_staff_id

        # 更新
        update_data = {
            "what_i_like_to_do": "音楽鑑賞、散歩、読書",
            "im_not_good_at": "人前で話すこと、長時間の作業",
            "the_life_i_want": "自立した生活を送りたい",
            "the_support_i_want": "就労支援と生活支援",
        }

        response = await async_client.put(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/issue-analysis",
            headers=token_headers,
            json=update_data,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["what_i_like_to_do"] == "音楽鑑賞、散歩、読書"
        assert data["the_life_i_want"] == "自立した生活を送りたい"
        # created_by_staff_idは変更されないことを確認
        assert data["created_by_staff_id"] == str(original_staff_id)

    async def test_upsert_issue_analysis_with_optional_fields(
        self, async_client: AsyncClient, setup_recipient
    ):
        """200: オプショナルフィールドのみでも作成可能"""
        recipient, _, _, token_headers = setup_recipient

        minimal_data = {
            "what_i_like_to_do": "音楽鑑賞"
        }

        response = await async_client.put(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/issue-analysis",
            headers=token_headers,
            json=minimal_data,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["what_i_like_to_do"] == "音楽鑑賞"
        assert data["im_not_good_at"] is None
        assert data["the_life_i_want"] is None

    async def test_upsert_issue_analysis_unauthorized(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        """401: 未認証の場合、エラーを返す"""
        # 利用者だけを作成（オーバーライドなし）
        recipient = WelfareRecipient(
            last_name="テスト",
            first_name="太郎",
            last_name_furigana="テスト",
            first_name_furigana="タロウ",
            birth_day=date(1990, 1, 1),
            gender=GenderType.male
        )
        db_session.add(recipient)
        await db_session.flush()
        await db_session.refresh(recipient)

        response = await async_client.put(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/issue-analysis",
            json=ISSUE_ANALYSIS_CREATE_DATA,
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_upsert_issue_analysis_forbidden(
        self, async_client: AsyncClient, db_session: AsyncSession, setup_other_office_staff, manager_user_factory, office_factory
    ):
        """403: 別事業所のスタッフは作成/更新拒否"""
        # 別の事業所と利用者を作成（setup_recipientを使わない）
        manager = await manager_user_factory(session=db_session)
        await db_session.commit()
        office = manager.office_associations[0].office

        recipient = WelfareRecipient(
            last_name="テスト",
            first_name="太郎",
            last_name_furigana="テスト",
            first_name_furigana="タロウ",
            birth_day=date(1990, 1, 1),
            gender=GenderType.male
        )
        db_session.add(recipient)
        await db_session.flush()

        # 事業所との関連付け
        office_recipient_association = OfficeWelfareRecipient(
            welfare_recipient_id=recipient.id,
            office_id=office.id
        )
        db_session.add(office_recipient_association)
        await db_session.flush()
        await db_session.refresh(recipient)
        _, other_office_token_headers = setup_other_office_staff

        response = await async_client.put(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/issue-analysis",
            headers=other_office_token_headers,  # 別事業所のトークン
            json=ISSUE_ANALYSIS_CREATE_DATA,
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_upsert_issue_analysis_recipient_not_found(
        self, async_client: AsyncClient, manager_user_token_headers: dict
    ):
        """404: 存在しない利用者の場合、エラーを返す"""
        nonexistent_recipient_id = uuid4()

        response = await async_client.put(
            f"{settings.API_V1_STR}/recipients/{nonexistent_recipient_id}/issue-analysis",
            headers=manager_user_token_headers,
            json=ISSUE_ANALYSIS_CREATE_DATA,
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_upsert_employment_desired_tasks_on_asobe_validation(
        self,
        async_client,
        db_session,
        employee_user_factory,
        welfare_recipient_factory,
    ):
        """Task 2: asoBeで希望する作業のバリデーションテスト（TDD - Red Phase）

        1000文字を超える入力はエラーになることを検証
        """
        # Arrange
        staff = await employee_user_factory()
        office_id = staff.office_associations[0].office_id
        recipient = await welfare_recipient_factory(office_id=office_id)
        token = create_access_token(str(staff.id), timedelta(minutes=30))

        # Act: 1001文字の入力（バリデーションエラーになるべき）
        long_text = "あ" * 1001
        response = await async_client.put(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/employment",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "work_conditions": "continuous_support_b",
                "regular_or_part_time_job": False,
                "employment_support": False,
                "work_experience_in_the_past_year": False,
                "suspension_of_work": False,
                "general_employment_request": False,
                "work_outside_the_facility": "hope",
                "desired_tasks_on_asobe": long_text,
            },
        )

        # Assert: バリデーションエラー
        assert response.status_code == 422
        error_detail = response.json()["detail"]
        assert any("1000 characters" in str(err).lower() for err in error_detail)

    async def test_upsert_employment_desired_tasks_on_asobe_success(
        self,
        async_client,
        db_session,
        employee_user_factory,
        welfare_recipient_factory,
    ):
        """Task 2: asoBeで希望する作業の正常系テスト（TDD - Red Phase）

        1000文字以内の入力は正常に保存されることを検証
        """
        # Arrange
        staff = await employee_user_factory()
        office_id = staff.office_associations[0].office_id
        recipient = await welfare_recipient_factory(office_id=office_id)
        token = create_access_token(str(staff.id), timedelta(minutes=30))

        # Act: 正常な入力
        valid_text = "清掃作業、軽作業、梱包作業、データ入力作業を希望します。体力には自信があります。"
        response = await async_client.put(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/employment",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "work_conditions": "continuous_support_b",
                "regular_or_part_time_job": False,
                "employment_support": False,
                "work_experience_in_the_past_year": False,
                "suspension_of_work": False,
                "general_employment_request": False,
                "work_outside_the_facility": "hope",
                "desired_tasks_on_asobe": valid_text,
            },
        )

        # Assert: 成功
        assert response.status_code == 200
        data = response.json()
        assert data["desired_tasks_on_asobe"] == valid_text

    async def test_upsert_employment_desired_tasks_on_asobe_null(
        self,
        async_client,
        db_session,
        employee_user_factory,
        welfare_recipient_factory,
    ):
        """Task 2: asoBeで希望する作業のNULL許容テスト（TDD - Red Phase）

        フィールドがNULLでも正常に保存されることを検証
        """
        # Arrange
        staff = await employee_user_factory()
        office_id = staff.office_associations[0].office_id
        recipient = await welfare_recipient_factory(office_id=office_id)
        token = create_access_token(str(staff.id), timedelta(minutes=30))

        # Act: desired_tasks_on_asobeをNULLで送信
        response = await async_client.put(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/employment",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "work_conditions": "other",
                "regular_or_part_time_job": False,
                "employment_support": False,
                "work_experience_in_the_past_year": False,
                "suspension_of_work": False,
                "general_employment_request": False,
                "work_outside_the_facility": "not_hope",
                "desired_tasks_on_asobe": None,
            },
        )

        # Assert: 成功
        assert response.status_code == 200
        data = response.json()
        assert data["desired_tasks_on_asobe"] is None

    async def test_upsert_employment_no_experience_parent_child_validation(
        self,
        async_client,
        db_session,
        employee_user_factory,
        welfare_recipient_factory,
    ):
        """Task 1: 親子チェックボックスバリデーションテスト（TDD - Red Phase）

        親（no_employment_experience）がFalseの時、全ての子は自動的にFalseになることを検証
        """
        # Arrange
        staff = await employee_user_factory()
        office_id = staff.office_associations[0].office_id
        recipient = await welfare_recipient_factory(office_id=office_id)
        token = create_access_token(str(staff.id), timedelta(minutes=30))

        # Act: 親をFalse、子をTrue（無効になるべき）
        response = await async_client.put(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/employment",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "work_conditions": "other",
                "regular_or_part_time_job": False,
                "employment_support": False,
                "work_experience_in_the_past_year": False,
                "suspension_of_work": False,
                "general_employment_request": False,
                "work_outside_the_facility": "not_hope",
                # 親子チェックボックス
                "no_employment_experience": False,  # 親をFalse
                "attended_job_selection_office": True,  # 子をTrue（無効化されるべき）
                "received_employment_assessment": True,  # 子をTrue（無効化されるべき）
                "employment_other_experience": True,  # 子をTrue（無効化されるべき）
                "employment_other_text": "これは無視されるべき",
            },
        )

        # Assert: バリデータにより全ての子が自動的にFalseになる
        assert response.status_code == 200
        data = response.json()
        assert data["no_employment_experience"] is False
        # 親がFalseなので、子は全てFalseになるべき
        assert data["attended_job_selection_office"] is False
        assert data["received_employment_assessment"] is False
        assert data["employment_other_experience"] is False
        assert data["employment_other_text"] is None

    async def test_upsert_employment_no_experience_success(
        self,
        async_client,
        db_session,
        employee_user_factory,
        welfare_recipient_factory,
    ):
        """Task 1: 就労経験なしフィールドの正常系テスト（TDD - Red Phase）

        親がTrueの時、子の値がそのまま保存されることを検証
        """
        # Arrange
        staff = await employee_user_factory()
        office_id = staff.office_associations[0].office_id
        recipient = await welfare_recipient_factory(office_id=office_id)
        token = create_access_token(str(staff.id), timedelta(minutes=30))

        # Act: 親をTrue、子も適切に設定
        response = await async_client.put(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/employment",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "work_conditions": "other",
                "regular_or_part_time_job": False,
                "employment_support": False,
                "work_experience_in_the_past_year": False,
                "suspension_of_work": False,
                "general_employment_request": False,
                "work_outside_the_facility": "not_hope",
                # 親子チェックボックス（親がTrue）
                "no_employment_experience": True,
                "attended_job_selection_office": True,
                "received_employment_assessment": False,
                "employment_other_experience": True,
                "employment_other_text": "職業訓練を受けた",
            },
        )

        # Assert: 親がTrueなので、子の値がそのまま保存される
        assert response.status_code == 200
        data = response.json()
        assert data["no_employment_experience"] is True
        assert data["attended_job_selection_office"] is True
        assert data["received_employment_assessment"] is False
        assert data["employment_other_experience"] is True
        assert data["employment_other_text"] == "職業訓練を受けた"

    @pytest.mark.asyncio
    async def test_upsert_employment_no_experience_requires_at_least_one_child(
        self,
        async_client,
        db_session,
        employee_user_factory,
        welfare_recipient_factory,
    ):
        """Task 1: 就労経験なしが選択された場合、最低1つの子チェックボックスが必須

        親がTrueだが、全ての子がFalseの場合、バリデーションエラーを返す
        """
        # Arrange
        staff = await employee_user_factory()
        office_id = staff.office_associations[0].office_id
        recipient = await welfare_recipient_factory(office_id=office_id)
        token = create_access_token(str(staff.id), timedelta(minutes=30))

        # Act: 親をTrue、子を全てFalse
        response = await async_client.put(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/employment",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "work_conditions": "other",
                "regular_or_part_time_job": False,
                "employment_support": False,
                "work_experience_in_the_past_year": False,
                "suspension_of_work": False,
                "general_employment_request": False,
                "work_outside_the_facility": "not_hope",
                # 親子チェックボックス（親がTrue、子が全てFalse）
                "no_employment_experience": True,
                "attended_job_selection_office": False,
                "received_employment_assessment": False,
                "employment_other_experience": False,
            },
        )

        # Assert: バリデーションエラーが返される
        assert response.status_code == 422
        error_detail = response.json()["detail"]


class TestEmploymentAuditLog:
    """就労関係の監査ログテスト（Phase 0 - TDD）"""

    @pytest.mark.asyncio
    async def test_employment_create_logs_audit(
        self,
        async_client,
        db_session,
        employee_user_factory,
        welfare_recipient_factory,
    ):
        """就労関係作成時に監査ログが記録されることを確認"""
        from sqlalchemy import select
        from app.models.staff_profile import AuditLog

        # Arrange
        staff = await employee_user_factory()
        office_id = staff.office_associations[0].office_id
        recipient = await welfare_recipient_factory(office_id=office_id)
        token = create_access_token(str(staff.id), timedelta(minutes=30))

        # Act: 就労関係を作成
        response = await async_client.put(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/employment",
            headers={"Authorization": f"Bearer {token}"},
            json={
                **EMPLOYMENT_CREATE_DATA,
                "no_employment_experience": True,
                "attended_job_selection_office": True,
                "received_employment_assessment": False,
                "employment_other_experience": False,
            },
        )

        # Assert: APIレスポンスが成功
        assert response.status_code == 200

        # Assert: 監査ログが記録されている
        stmt = select(AuditLog).where(
            AuditLog.action == "employment.created",
            AuditLog.target_type == "employment_related",
            AuditLog.staff_id == staff.id
        )
        result = await db_session.execute(stmt)
        audit_log = result.scalar_one_or_none()

        assert audit_log is not None, "監査ログが記録されていません"
        assert audit_log.office_id == office_id
        assert audit_log.actor_role == staff.role.value
        assert audit_log.details is not None
        assert "recipient_id" in audit_log.details

    @pytest.mark.asyncio
    async def test_employment_update_logs_audit(
        self,
        async_client,
        db_session,
        employee_user_factory,
        welfare_recipient_factory,
    ):
        """就労関係更新時に監査ログが記録されることを確認"""
        from sqlalchemy import select
        from app.models.staff_profile import AuditLog

        # Arrange: 既存の就労関係を作成
        staff = await employee_user_factory()
        office_id = staff.office_associations[0].office_id
        recipient = await welfare_recipient_factory(office_id=office_id)
        token = create_access_token(str(staff.id), timedelta(minutes=30))

        # 最初の作成
        await async_client.put(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/employment",
            headers={"Authorization": f"Bearer {token}"},
            json=EMPLOYMENT_CREATE_DATA,
        )

        # Act: 就労関係を更新
        response = await async_client.put(
            f"{settings.API_V1_STR}/recipients/{recipient.id}/employment",
            headers={"Authorization": f"Bearer {token}"},
            json={
                **EMPLOYMENT_CREATE_DATA,
                "desired_tasks_on_asobe": "清掃作業を希望します",
            },
        )

        # Assert: APIレスポンスが成功
        assert response.status_code == 200

        # Assert: 更新の監査ログが記録されている
        stmt = select(AuditLog).where(
            AuditLog.action == "employment.updated",
            AuditLog.target_type == "employment_related",
            AuditLog.staff_id == staff.id
        )
        result = await db_session.execute(stmt)
        audit_log = result.scalar_one_or_none()

        assert audit_log is not None, "更新時の監査ログが記録されていません"
        assert audit_log.office_id == office_id
        assert audit_log.details is not None
        assert "changes" in audit_log.details or "recipient_id" in audit_log.details


class TestEmploymentValidationEnhanced:
    """就労関係の強化されたバリデーションテスト"""

    async def test_employment_other_experience_requires_text(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        employee_user_factory,
        welfare_recipient_factory,
    ):
        """employment_other_experience = Trueの場合、employment_other_textが必須"""
        # Arrange
        staff = await employee_user_factory()
        office_id = staff.office_associations[0].office_id
        recipient = await welfare_recipient_factory(office_id=office_id)
        token = create_access_token(str(staff.id), timedelta(minutes=30))

        # Act: employment_other_experience = True だが employment_other_text が None
        response = await async_client.put(
            f"/api/v1/recipients/{recipient.id}/employment",
            headers={"Authorization": f"Bearer {token}"},
            json={
                **EMPLOYMENT_BASE_DATA,
                "no_employment_experience": True,
                "employment_other_experience": True,
                "employment_other_text": None,  # これがエラーの原因
            },
        )

        # Assert: バリデーションエラーを期待
        assert response.status_code == 422
        assert "employment_other_text" in response.text.lower() or "その他" in response.text

    async def test_empty_string_converted_to_none(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        employee_user_factory,
        welfare_recipient_factory,
    ):
        """空文字列がNoneに変換されることを確認"""
        # Arrange
        staff = await employee_user_factory()
        office_id = staff.office_associations[0].office_id
        recipient = await welfare_recipient_factory(office_id=office_id)
        token = create_access_token(str(staff.id), timedelta(minutes=30))

        # Act: 空文字列を送信
        response = await async_client.put(
            f"/api/v1/recipients/{recipient.id}/employment",
            headers={"Authorization": f"Bearer {token}"},
            json={
                **EMPLOYMENT_BASE_DATA,
                "desired_tasks_on_asobe": "",  # 空文字列
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["desired_tasks_on_asobe"] is None  # Noneに変換される

    async def test_whitespace_trimmed(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        employee_user_factory,
        welfare_recipient_factory,
    ):
        """前後の空白が削除されることを確認"""
        # Arrange
        staff = await employee_user_factory()
        office_id = staff.office_associations[0].office_id
        recipient = await welfare_recipient_factory(office_id=office_id)
        token = create_access_token(str(staff.id), timedelta(minutes=30))

        # Act: 前後に空白がある文字列
        response = await async_client.put(
            f"/api/v1/recipients/{recipient.id}/employment",
            headers={"Authorization": f"Bearer {token}"},
            json={
                **EMPLOYMENT_BASE_DATA,
                "no_employment_experience": True,
                "employment_other_experience": True,
                "employment_other_text": "  テスト  ",  # 前後に空白
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        # 空白が削除され、かつHTMLエスケープされている
        assert "テスト" in data["employment_other_text"]
        assert data["employment_other_text"].strip() == data["employment_other_text"]

    async def test_consecutive_newlines_limited(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        employee_user_factory,
        welfare_recipient_factory,
    ):
        """連続する改行が制限されることを確認"""
        # Arrange
        staff = await employee_user_factory()
        office_id = staff.office_associations[0].office_id
        recipient = await welfare_recipient_factory(office_id=office_id)
        token = create_access_token(str(staff.id), timedelta(minutes=30))

        # Act: 5つの連続改行を含むテキスト
        response = await async_client.put(
            f"/api/v1/recipients/{recipient.id}/employment",
            headers={"Authorization": f"Bearer {token}"},
            json={
                **EMPLOYMENT_BASE_DATA,
                "no_employment_experience": True,
                "employment_other_experience": True,
                "employment_other_text": "テスト1\n\n\n\n\nテスト2",  # 5つの改行
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        # 連続改行が2つまでに制限される
        assert "\n\n\n" not in data["employment_other_text"]  # 3つ以上の連続改行はない
        assert "テスト1" in data["employment_other_text"]
        assert "テスト2" in data["employment_other_text"]
