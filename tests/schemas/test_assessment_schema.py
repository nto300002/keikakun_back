"""
アセスメントシート機能のスキーマテスト

TDD (テスト駆動開発) アプローチに基づき、
スキーマ実装前にテストを作成します。
"""

import pytest
from pydantic import ValidationError
from datetime import date, timedelta
import uuid

# テスト対象のスキーマ
from app.schemas.assessment import (
    FamilyMemberBase,
    FamilyMemberCreate,
    FamilyMemberUpdate,
    FamilyMemberResponse,
    ServiceHistoryBase,
    ServiceHistoryCreate,
    ServiceHistoryUpdate,
    ServiceHistoryResponse,
    MedicalInfoBase,
    MedicalInfoCreate,
    MedicalInfoUpdate,
    MedicalInfoResponse,
    HospitalVisitBase,
    HospitalVisitCreate,
    HospitalVisitUpdate,
    HospitalVisitResponse,
    EmploymentBase,
    EmploymentCreate,
    EmploymentUpdate,
    EmploymentResponse,
    IssueAnalysisBase,
    IssueAnalysisCreate,
    IssueAnalysisUpdate,
    IssueAnalysisResponse,
    AssessmentResponse,
)

from app.models.enums import (
    Household,
    MedicalCareInsurance,
    AidingType,
    WorkConditions,
    WorkOutsideFacility,
)


# =============================================================================
# 1. 家族構成スキーマのテスト
# =============================================================================

class TestFamilyMemberSchemas:
    """家族構成スキーマのテストクラス"""

    def test_family_member_create_valid(self):
        """正常系: 全フィールドが正しく設定されること"""

        valid_data = {
            "name": "山田太郎",
            "relationship": "父",
            "household": Household.same,
            "ones_health": "良好",
            "remarks": "特になし",
            "family_structure_chart": "https://example.com/chart.png"
        }
        member = FamilyMemberCreate(**valid_data)

        assert member.name == "山田太郎"
        assert member.relationship == "父"
        assert member.household == Household.same
        assert member.ones_health == "良好"
        assert member.remarks == "特になし"
        assert member.family_structure_chart == "https://example.com/chart.png"

    
    def test_family_member_create_required_fields_only(self):
        """正常系: 必須フィールドのみで作成可能"""
        from app.schemas.assessment import FamilyMemberCreate

        valid_data = {
            "name": "山田太郎",
            "relationship": "父",
            "household": Household.same,
            "ones_health": "良好",
        }
        member = FamilyMemberCreate(**valid_data)

        assert member.name == "山田太郎"
        assert member.remarks is None
        assert member.family_structure_chart is None

    
    def test_family_member_create_name_empty_raises_error(self):
        """異常系: nameが空文字列の場合、ValidationErrorが発生"""
        from app.schemas.assessment import FamilyMemberCreate

        invalid_data = {
            "name": "",
            "relationship": "父",
            "household": Household.same,
            "ones_health": "良好",
        }

        with pytest.raises(ValidationError) as exc_info:
            FamilyMemberCreate(**invalid_data)

        assert "name" in str(exc_info.value)

    
    def test_family_member_create_name_too_long_raises_error(self):
        """異常系: nameが255文字を超える場合、ValidationErrorが発生"""
        from app.schemas.assessment import FamilyMemberCreate

        invalid_data = {
            "name": "あ" * 256,
            "relationship": "父",
            "household": Household.same,
            "ones_health": "良好",
        }

        with pytest.raises(ValidationError) as exc_info:
            FamilyMemberCreate(**invalid_data)

        assert "name" in str(exc_info.value)

    
    def test_family_member_create_relationship_too_long_raises_error(self):
        """異常系: relationshipが100文字を超える場合、ValidationErrorが発生"""
        from app.schemas.assessment import FamilyMemberCreate

        invalid_data = {
            "name": "山田太郎",
            "relationship": "あ" * 101,
            "household": Household.same,
            "ones_health": "良好",
        }

        with pytest.raises(ValidationError) as exc_info:
            FamilyMemberCreate(**invalid_data)

        assert "relationship" in str(exc_info.value)

    
    def test_family_member_create_ones_health_too_long_raises_error(self):
        """異常系: ones_healthが500文字を超える場合、ValidationErrorが発生"""
        from app.schemas.assessment import FamilyMemberCreate

        invalid_data = {
            "name": "山田太郎",
            "relationship": "父",
            "household": Household.same,
            "ones_health": "あ" * 501,
        }

        with pytest.raises(ValidationError) as exc_info:
            FamilyMemberCreate(**invalid_data)

        assert "ones_health" in str(exc_info.value)

    
    def test_family_member_create_remarks_too_long_raises_error(self):
        """異常系: remarksが1000文字を超える場合、ValidationErrorが発生"""
        from app.schemas.assessment import FamilyMemberCreate

        invalid_data = {
            "name": "山田太郎",
            "relationship": "父",
            "household": Household.same,
            "ones_health": "良好",
            "remarks": "あ" * 1001,
        }

        with pytest.raises(ValidationError) as exc_info:
            FamilyMemberCreate(**invalid_data)

        assert "remarks" in str(exc_info.value)

    
    def test_family_member_create_invalid_household_raises_error(self):
        """異常系: householdが無効な値の場合、ValidationErrorが発生"""
        from app.schemas.assessment import FamilyMemberCreate

        invalid_data = {
            "name": "山田太郎",
            "relationship": "父",
            "household": "invalid_value",  # 無効な値
            "ones_health": "良好",
        }

        with pytest.raises(ValidationError) as exc_info:
            FamilyMemberCreate(**invalid_data)

        assert "household" in str(exc_info.value)

    
    def test_family_member_update_all_fields_optional(self):
        """正常系: Updateスキーマで全フィールドがOptional"""
        from app.schemas.assessment import FamilyMemberUpdate

        # 空のリクエストも受け入れられる
        empty_update = FamilyMemberUpdate()
        assert empty_update.name is None
        assert empty_update.relationship is None

        # 一部のフィールドのみ更新可能
        partial_update = FamilyMemberUpdate(name="新しい名前")
        assert partial_update.name == "新しい名前"
        assert partial_update.relationship is None

    
    def test_family_member_response_includes_metadata(self):
        """正常系: Responseスキーマにメタデータが含まれる"""
        from app.schemas.assessment import FamilyMemberResponse
        from datetime import datetime

        response_data = {
            "id": 1,
            "welfare_recipient_id": uuid.uuid4(),
            "name": "山田太郎",
            "relationship": "父",
            "household": Household.same,
            "ones_health": "良好",
            "remarks": None,
            "family_structure_chart": None,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }

        response = FamilyMemberResponse(**response_data)
        assert response.id == 1
        assert isinstance(response.welfare_recipient_id, uuid.UUID)
        assert isinstance(response.created_at, datetime)
        assert isinstance(response.updated_at, datetime)


# =============================================================================
# 2. 福祉サービス利用歴スキーマのテスト
# =============================================================================

class TestServiceHistorySchemas:
    """福祉サービス利用歴スキーマのテストクラス"""

    
    def test_service_history_create_valid(self):
        """正常系: 全フィールドが正しく設定されること"""
        from app.schemas.assessment import ServiceHistoryCreate

        valid_data = {
            "office_name": "テスト事業所",
            "starting_day": date(2023, 1, 1),
            "amount_used": "週5日",
            "service_name": "就労継続支援B型",
        }
        history = ServiceHistoryCreate(**valid_data)

        assert history.office_name == "テスト事業所"
        assert history.starting_day == date(2023, 1, 1)
        assert history.amount_used == "週5日"
        assert history.service_name == "就労継続支援B型"

    
    def test_service_history_create_office_name_empty_raises_error(self):
        """異常系: office_nameが空文字列の場合、ValidationErrorが発生"""
        from app.schemas.assessment import ServiceHistoryCreate

        invalid_data = {
            "office_name": "",
            "starting_day": date(2023, 1, 1),
            "amount_used": "週5日",
            "service_name": "就労継続支援B型",
        }

        with pytest.raises(ValidationError) as exc_info:
            ServiceHistoryCreate(**invalid_data)

        assert "office_name" in str(exc_info.value)

    
    def test_service_history_create_office_name_too_long_raises_error(self):
        """異常系: office_nameが255文字を超える場合、ValidationErrorが発生"""
        from app.schemas.assessment import ServiceHistoryCreate

        invalid_data = {
            "office_name": "あ" * 256,
            "starting_day": date(2023, 1, 1),
            "amount_used": "週5日",
            "service_name": "就労継続支援B型",
        }

        with pytest.raises(ValidationError) as exc_info:
            ServiceHistoryCreate(**invalid_data)

        assert "office_name" in str(exc_info.value)

    
    def test_service_history_create_future_date_allowed(self):
        """正常系: 未来の開始日も受け入れられる（開始予定日の可能性）"""
        from app.schemas.assessment import ServiceHistoryCreate

        future_date = date.today() + timedelta(days=30)
        valid_data = {
            "office_name": "テスト事業所",
            "starting_day": future_date,
            "amount_used": "週5日",
            "service_name": "就労継続支援B型",
        }
        history = ServiceHistoryCreate(**valid_data)

        assert history.starting_day == future_date


# =============================================================================
# 3. 医療基本情報スキーマのテスト
# =============================================================================

class TestMedicalInfoSchemas:
    """医療基本情報スキーマのテストクラス"""

    
    def test_medical_info_create_valid(self):
        """正常系: 全フィールドが正しく設定されること"""
        from app.schemas.assessment import MedicalInfoCreate

        valid_data = {
            "medical_care_insurance": MedicalCareInsurance.national_health_insurance,
            "medical_care_insurance_other_text": None,
            "aiding": AidingType.none,
            "history_of_hospitalization_in_the_past_2_years": False,
        }
        medical_info = MedicalInfoCreate(**valid_data)

        assert medical_info.medical_care_insurance == MedicalCareInsurance.national_health_insurance
        assert medical_info.aiding == AidingType.none
        assert medical_info.history_of_hospitalization_in_the_past_2_years is False


    def test_medical_info_create_other_requires_text(self):
        """異常系: medical_care_insuranceが"other"の場合、other_textが必須"""
        from app.schemas.assessment import MedicalInfoCreate

        # other_textがない場合、ValidationErrorが発生
        invalid_data = {
            "medical_care_insurance": MedicalCareInsurance.other,
            "medical_care_insurance_other_text": None,
            "aiding": AidingType.none,
            "history_of_hospitalization_in_the_past_2_years": False,
        }

        with pytest.raises(ValidationError) as exc_info:
            MedicalInfoCreate(**invalid_data)

        # カスタムエラーメッセージが含まれることを確認
        assert "その他" in str(exc_info.value) or "詳細" in str(exc_info.value)

    
    def test_medical_info_create_other_with_text_valid(self):
        """正常系: medical_care_insuranceが"other"の場合、other_textがあれば正常"""
        from app.schemas.assessment import MedicalInfoCreate

        valid_data = {
            "medical_care_insurance": MedicalCareInsurance.other,
            "medical_care_insurance_other_text": "特殊な保険",
            "aiding": AidingType.none,
            "history_of_hospitalization_in_the_past_2_years": False,
        }
        medical_info = MedicalInfoCreate(**valid_data)

        assert medical_info.medical_care_insurance_other_text == "特殊な保険"

    
    def test_medical_info_update_all_fields_optional(self):
        """正常系: Updateスキーマで全フィールドがOptional"""
        from app.schemas.assessment import MedicalInfoUpdate

        # 空のリクエストも受け入れられる
        empty_update = MedicalInfoUpdate()
        assert empty_update.medical_care_insurance is None
        assert empty_update.aiding is None


# =============================================================================
# 4. 通院歴スキーマのテスト
# =============================================================================

class TestHospitalVisitSchemas:
    """通院歴スキーマのテストクラス"""

    
    def test_hospital_visit_create_valid(self):
        """正常系: 全フィールドが正しく設定されること"""
        from app.schemas.assessment import HospitalVisitCreate

        valid_data = {
            "disease": "糖尿病",
            "frequency_of_hospital_visits": "月1回",
            "symptoms": "特になし",
            "medical_institution": "〇〇病院",
            "doctor": "田中医師",
            "tel": "03-1234-5678",
            "taking_medicine": True,
            "date_started": date(2020, 1, 1),
            "date_ended": None,
            "special_remarks": "継続治療中",
        }
        visit = HospitalVisitCreate(**valid_data)

        assert visit.disease == "糖尿病"
        assert visit.tel == "03-1234-5678"
        assert visit.taking_medicine is True


    def test_hospital_visit_create_date_validation(self):
        """異常系: date_startedがdate_endedより後の場合、ValidationErrorが発生"""
        from app.schemas.assessment import HospitalVisitCreate

        invalid_data = {
            "disease": "糖尿病",
            "frequency_of_hospital_visits": "月1回",
            "symptoms": "特になし",
            "medical_institution": "〇〇病院",
            "doctor": "田中医師",
            "tel": "03-1234-5678",
            "taking_medicine": True,
            "date_started": date(2023, 12, 31),
            "date_ended": date(2023, 1, 1),  # 開始日より前
            "special_remarks": None,
        }

        with pytest.raises(ValidationError) as exc_info:
            HospitalVisitCreate(**invalid_data)

        # date_endedがdate_startedより前であることを示すエラーメッセージを確認
        error_message = str(exc_info.value)
        assert "開始日" in error_message or "終了日" in error_message

    
    def test_hospital_visit_create_tel_format_validation(self):
        """異常系: telが電話番号形式でない場合、ValidationErrorが発生"""
        from app.schemas.assessment import HospitalVisitCreate

        invalid_data = {
            "disease": "糖尿病",
            "frequency_of_hospital_visits": "月1回",
            "symptoms": "特になし",
            "medical_institution": "〇〇病院",
            "doctor": "田中医師",
            "tel": "invalid-phone",  # 無効な電話番号
            "taking_medicine": True,
            "date_started": date(2020, 1, 1),
            "date_ended": None,
            "special_remarks": None,
        }

        with pytest.raises(ValidationError) as exc_info:
            HospitalVisitCreate(**invalid_data)

        assert "tel" in str(exc_info.value)


# =============================================================================
# 5. 就労関係スキーマのテスト
# =============================================================================

class TestEmploymentSchemas:
    """就労関係スキーマのテストクラス"""

    
    def test_employment_create_valid(self):
        """正常系: 全フィールドが正しく設定されること"""
        from app.schemas.assessment import EmploymentCreate

        valid_data = {
            "work_conditions": WorkConditions.general_employment,
            "regular_or_part_time_job": True,
            "employment_support": False,
            "work_experience_in_the_past_year": True,
            "suspension_of_work": False,
            "qualifications": "簿記2級",
            "main_places_of_employment": "A株式会社",
            "general_employment_request": True,
            "desired_job": "事務職",
            "special_remarks": "特になし",
            "work_outside_the_facility": WorkOutsideFacility.hope,
            "special_note_about_working_outside_the_facility": "積極的に希望",
        }
        employment = EmploymentCreate(**valid_data)

        assert employment.work_conditions == WorkConditions.general_employment
        assert employment.regular_or_part_time_job is True
        assert employment.work_outside_the_facility == WorkOutsideFacility.hope

    
    def test_employment_create_required_only(self):
        """正常系: 必須フィールドのみで作成可能"""
        from app.schemas.assessment import EmploymentCreate

        valid_data = {
            "work_conditions": WorkConditions.part_time,
            "regular_or_part_time_job": False,
            "employment_support": True,
            "work_experience_in_the_past_year": False,
            "suspension_of_work": False,
            "general_employment_request": False,
            "work_outside_the_facility": WorkOutsideFacility.not_hope,
        }
        employment = EmploymentCreate(**valid_data)

        assert employment.qualifications is None
        assert employment.desired_job is None


# =============================================================================
# 6. 課題分析スキーマのテスト
# =============================================================================

class TestIssueAnalysisSchemas:
    """課題分析スキーマのテストクラス"""

    
    def test_issue_analysis_create_all_fields_optional(self):
        """正常系: 全フィールドがOptional"""
        from app.schemas.assessment import IssueAnalysisCreate

        # 空のリクエストも受け入れられる
        empty_data = IssueAnalysisCreate()
        assert empty_data.what_i_like_to_do is None
        assert empty_data.im_not_good_at is None

        # 一部のフィールドのみ設定可能
        partial_data = IssueAnalysisCreate(
            what_i_like_to_do="絵を描くこと",
            future_dreams="アーティストになること"
        )
        assert partial_data.what_i_like_to_do == "絵を描くこと"
        assert partial_data.future_dreams == "アーティストになること"
        assert partial_data.im_not_good_at is None

    
    def test_issue_analysis_create_all_fields_set(self):
        """正常系: 全フィールドが正しく設定されること"""
        from app.schemas.assessment import IssueAnalysisCreate

        valid_data = {
            "what_i_like_to_do": "絵を描くこと",
            "im_not_good_at": "人前で話すこと",
            "the_life_i_want": "自立した生活",
            "the_support_i_want": "コミュニケーション支援",
            "points_to_keep_in_mind_when_providing_support": "ゆっくり話すこと",
            "future_dreams": "アーティストになること",
            "other": "その他の情報",
        }
        analysis = IssueAnalysisCreate(**valid_data)

        assert analysis.what_i_like_to_do == "絵を描くこと"
        assert analysis.im_not_good_at == "人前で話すこと"
        assert analysis.future_dreams == "アーティストになること"


# =============================================================================
# 7. 全アセスメント情報スキーマのテスト
# =============================================================================

class TestAssessmentResponse:
    """全アセスメント情報スキーマのテストクラス"""

    
    def test_assessment_response_structure(self):
        """正常系: 全サブスキーマが正しく含まれること"""
        from app.schemas.assessment import AssessmentResponse

        response_data = {
            "family_members": [],
            "service_history": [],
            "medical_info": None,
            "hospital_visits": [],
            "employment": None,
            "issue_analysis": None,
        }
        response = AssessmentResponse(**response_data)

        assert isinstance(response.family_members, list)
        assert isinstance(response.service_history, list)
        assert response.medical_info is None
        assert isinstance(response.hospital_visits, list)
        assert response.employment is None
        assert response.issue_analysis is None

    
    def test_assessment_response_with_data(self):
        """正常系: データが含まれる場合の動作確認"""
        from app.schemas.assessment import (
            AssessmentResponse,
            FamilyMemberResponse,
            ServiceHistoryResponse,
        )
        from datetime import datetime

        family_member_data = {
            "id": 1,
            "welfare_recipient_id": uuid.uuid4(),
            "name": "山田太郎",
            "relationship": "父",
            "household": Household.same,
            "ones_health": "良好",
            "remarks": None,
            "family_structure_chart": None,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }

        response_data = {
            "family_members": [family_member_data],
            "service_history": [],
            "medical_info": None,
            "hospital_visits": [],
            "employment": None,
            "issue_analysis": None,
        }
        response = AssessmentResponse(**response_data)

        assert len(response.family_members) == 1
        assert response.family_members[0].name == "山田太郎"
