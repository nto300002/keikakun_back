"""
アセスメントシート機能のスキーマ定義

アセスメントシートの各セクション（家族構成、福祉サービス利用歴、
医療基本情報、通院歴、就労関係、課題分析）のスキーマを定義します。
"""

from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
from typing import List, Optional
from datetime import date, datetime
import uuid

from app.models.enums import (
    Household,
    MedicalCareInsurance,
    AidingType,
    WorkConditions,
    WorkOutsideFacility,
)


# =============================================================================
# 1. 家族構成スキーマ（Family Member Schemas）
# =============================================================================

class FamilyMemberBase(BaseModel):
    """家族構成の基本スキーマ"""
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., min_length=1, max_length=255, description="氏名")
    relationship: str = Field(..., min_length=1, max_length=100, description="続柄")
    household: Household = Field(..., description="世帯区分")
    ones_health: str = Field(..., min_length=1, max_length=500, description="健康状態")
    remarks: Optional[str] = Field(None, max_length=500, description="備考")
    family_structure_chart: Optional[str] = Field(None, description="家族構成図のURL")

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        """氏名の文字数をバリデーション"""
        if not v or len(v) == 0:
            raise ValueError('氏名は必須です')
        if len(v) > 255:
            raise ValueError('氏名は255文字以内で入力してください')
        return v

    @field_validator('relationship')
    @classmethod
    def validate_relationship(cls, v: str) -> str:
        """続柄の文字数をバリデーション"""
        if not v or len(v) == 0:
            raise ValueError('続柄は必須です')
        if len(v) > 100:
            raise ValueError('続柄は100文字以内で入力してください')
        return v

    @field_validator('ones_health')
    @classmethod
    def validate_ones_health(cls, v: str) -> str:
        """健康状態の文字数をバリデーション"""
        if not v or len(v) == 0:
            raise ValueError('健康状態は必須です')
        if len(v) > 500:
            raise ValueError('健康状態は500文字以内で入力してください')
        return v

    @field_validator('remarks')
    @classmethod
    def validate_remarks(cls, v: Optional[str]) -> Optional[str]:
        """備考の文字数をバリデーション"""
        if v and len(v) > 500:
            raise ValueError('備考は500文字以内で入力してください')
        return v


class FamilyMemberCreate(FamilyMemberBase):
    """家族構成作成時のスキーマ"""
    pass


class FamilyMemberUpdate(BaseModel):
    """家族構成更新時のスキーマ（全フィールドがOptional）"""
    model_config = ConfigDict(populate_by_name=True)

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    relationship: Optional[str] = Field(None, min_length=1, max_length=100)
    household: Optional[Household] = None
    ones_health: Optional[str] = Field(None, min_length=1, max_length=500)
    remarks: Optional[str] = Field(None, max_length=1000)
    family_structure_chart: Optional[str] = None


class FamilyMemberResponse(FamilyMemberBase):
    """家族構成レスポンススキーマ"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    welfare_recipient_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# =============================================================================
# 2. 福祉サービス利用歴スキーマ（Service History Schemas）
# =============================================================================

class ServiceHistoryBase(BaseModel):
    """福祉サービス利用歴の基本スキーマ"""
    model_config = ConfigDict(populate_by_name=True)

    office_name: str = Field(..., min_length=1, max_length=255, description="事業所名")
    starting_day: date = Field(..., description="利用開始日")
    amount_used: str = Field(..., min_length=1, max_length=100, description="利用時間/月")
    service_name: str = Field(..., min_length=1, max_length=255, description="サービス名")

    @field_validator('office_name')
    @classmethod
    def validate_office_name(cls, v: str) -> str:
        """事業所名の文字数をバリデーション"""
        if not v or len(v) == 0:
            raise ValueError('事業所名は必須です')
        if len(v) > 255:
            raise ValueError('事業所名は255文字以内で入力してください')
        return v

    @field_validator('amount_used')
    @classmethod
    def validate_amount_used(cls, v: str) -> str:
        """利用時間/月の文字数をバリデーション"""
        if not v or len(v) == 0:
            raise ValueError('利用時間/月は必須です')
        if len(v) > 100:
            raise ValueError('利用時間/月は100文字以内で入力してください')
        return v

    @field_validator('service_name')
    @classmethod
    def validate_service_name(cls, v: str) -> str:
        """サービス名の文字数をバリデーション"""
        if not v or len(v) == 0:
            raise ValueError('サービス名は必須です')
        if len(v) > 255:
            raise ValueError('サービス名は255文字以内で入力してください')
        return v


class ServiceHistoryCreate(ServiceHistoryBase):
    """福祉サービス利用歴作成時のスキーマ"""
    pass


class ServiceHistoryUpdate(BaseModel):
    """福祉サービス利用歴更新時のスキーマ（全フィールドがOptional）"""
    model_config = ConfigDict(populate_by_name=True)

    office_name: Optional[str] = Field(None, min_length=1, max_length=255)
    starting_day: Optional[date] = None
    amount_used: Optional[str] = Field(None, min_length=1, max_length=100)
    service_name: Optional[str] = Field(None, min_length=1, max_length=255)


class ServiceHistoryResponse(ServiceHistoryBase):
    """福祉サービス利用歴レスポンススキーマ"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    welfare_recipient_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# =============================================================================
# 3. 医療基本情報スキーマ（Medical Info Schemas）
# =============================================================================

class MedicalInfoBase(BaseModel):
    """医療基本情報の基本スキーマ"""
    model_config = ConfigDict(populate_by_name=True)

    medical_care_insurance: MedicalCareInsurance = Field(..., description="医療保険の種類")
    medical_care_insurance_other_text: Optional[str] = Field(None, max_length=255, description="医療保険その他の内容")
    aiding: AidingType = Field(..., description="公費負担")
    history_of_hospitalization_in_the_past_2_years: bool = Field(..., description="過去2年の入院歴")

    @model_validator(mode='after')
    def validate_other_text(self):
        """medical_care_insuranceが"other"の場合、other_textが必須"""
        if self.medical_care_insurance == MedicalCareInsurance.other:
            if not self.medical_care_insurance_other_text:
                raise ValueError('医療保険が"その他"の場合、詳細を入力してください')
        return self


class MedicalInfoCreate(MedicalInfoBase):
    """医療基本情報作成時のスキーマ"""
    pass


class MedicalInfoUpdate(BaseModel):
    """医療基本情報更新時のスキーマ（全フィールドがOptional）"""
    model_config = ConfigDict(populate_by_name=True)

    medical_care_insurance: Optional[MedicalCareInsurance] = None
    medical_care_insurance_other_text: Optional[str] = Field(None, max_length=255)
    aiding: Optional[AidingType] = None
    history_of_hospitalization_in_the_past_2_years: Optional[bool] = None

    @model_validator(mode='after')
    def validate_other_text(self):
        """medical_care_insuranceが"other"の場合、other_textが必須"""
        if self.medical_care_insurance == MedicalCareInsurance.other:
            if not self.medical_care_insurance_other_text:
                raise ValueError('医療保険が"その他"の場合、詳細を入力してください')
        return self


class MedicalInfoResponse(MedicalInfoBase):
    """医療基本情報レスポンススキーマ"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    welfare_recipient_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# =============================================================================
# 4. 通院歴スキーマ（Hospital Visit Schemas）
# =============================================================================

class HospitalVisitBase(BaseModel):
    """通院歴の基本スキーマ"""
    model_config = ConfigDict(populate_by_name=True)

    disease: str = Field(..., min_length=1, max_length=255, description="病名")
    frequency_of_hospital_visits: str = Field(..., min_length=1, max_length=100, description="通院頻度")
    symptoms: str = Field(..., min_length=1, max_length=500, description="症状")
    medical_institution: str = Field(..., min_length=1, max_length=255, description="医療機関名")
    doctor: str = Field(..., min_length=1, max_length=100, description="主治医")
    tel: str = Field(..., min_length=1, description="電話番号")
    taking_medicine: bool = Field(..., description="服薬状況")
    date_started: Optional[date] = Field(None, description="開始日")
    date_ended: Optional[date] = Field(None, description="終了日")
    special_remarks: Optional[str] = Field(None, max_length=1000, description="特記事項")

    @field_validator('disease')
    @classmethod
    def validate_disease(cls, v: str) -> str:
        """病名の文字数をバリデーション"""
        if len(v) > 255:
            raise ValueError('病名は255文字以内で入力してください')
        return v

    @field_validator('frequency_of_hospital_visits')
    @classmethod
    def validate_frequency(cls, v: str) -> str:
        """通院頻度の文字数をバリデーション"""
        if len(v) > 100:
            raise ValueError('通院頻度は100文字以内で入力してください')
        return v

    @field_validator('symptoms')
    @classmethod
    def validate_symptoms(cls, v: str) -> str:
        """症状の文字数をバリデーション"""
        if len(v) > 500:
            raise ValueError('症状は500文字以内で入力してください')
        return v

    @field_validator('medical_institution')
    @classmethod
    def validate_medical_institution(cls, v: str) -> str:
        """医療機関名の文字数をバリデーション"""
        if len(v) > 255:
            raise ValueError('医療機関名は255文字以内で入力してください')
        return v

    @field_validator('doctor')
    @classmethod
    def validate_doctor(cls, v: str) -> str:
        """主治医の文字数をバリデーション"""
        if len(v) > 100:
            raise ValueError('主治医は100文字以内で入力してください')
        return v

    @field_validator('special_remarks')
    @classmethod
    def validate_special_remarks(cls, v: Optional[str]) -> Optional[str]:
        """特記事項の文字数をバリデーション"""
        if v and len(v) > 1000:
            raise ValueError('特記事項は1000文字以内で入力してください')
        return v

    @field_validator('tel')
    @classmethod
    def validate_tel(cls, v: str) -> str:
        """電話番号のフォーマットをバリデーション"""
        # 基本的な電話番号フォーマット（ハイフンあり/なし両対応）
        import re
        # 数字とハイフンのみを許可
        if not re.match(r'^[0-9\-]+$', v):
            raise ValueError('電話番号は数字とハイフンのみ使用できます')
        # 数字のみを抽出して10桁または11桁をチェック
        digits_only = re.sub(r'\D', '', v)
        if len(digits_only) < 10 or len(digits_only) > 11:
            raise ValueError('電話番号は10桁または11桁である必要があります')
        return v

    @model_validator(mode='after')
    def validate_dates(self):
        """日付の論理的整合性をバリデーション"""
        if self.date_started and self.date_ended:
            if self.date_started > self.date_ended:
                raise ValueError('開始日は終了日より前である必要があります')
        return self


class HospitalVisitCreate(HospitalVisitBase):
    """通院歴作成時のスキーマ"""
    pass


class HospitalVisitUpdate(BaseModel):
    """通院歴更新時のスキーマ（全フィールドがOptional）"""
    model_config = ConfigDict(populate_by_name=True)

    disease: Optional[str] = Field(None, min_length=1, max_length=255)
    frequency_of_hospital_visits: Optional[str] = Field(None, min_length=1, max_length=100)
    symptoms: Optional[str] = Field(None, min_length=1, max_length=500)
    medical_institution: Optional[str] = Field(None, min_length=1, max_length=255)
    doctor: Optional[str] = Field(None, min_length=1, max_length=100)
    tel: Optional[str] = Field(None, min_length=1)
    taking_medicine: Optional[bool] = None
    date_started: Optional[date] = None
    date_ended: Optional[date] = None
    special_remarks: Optional[str] = Field(None, max_length=1000)

    @field_validator('disease')
    @classmethod
    def validate_disease(cls, v: Optional[str]) -> Optional[str]:
        """病名の文字数をバリデーション"""
        if v and len(v) > 255:
            raise ValueError('病名は255文字以内で入力してください')
        return v

    @field_validator('frequency_of_hospital_visits')
    @classmethod
    def validate_frequency(cls, v: Optional[str]) -> Optional[str]:
        """通院頻度の文字数をバリデーション"""
        if v and len(v) > 100:
            raise ValueError('通院頻度は100文字以内で入力してください')
        return v

    @field_validator('symptoms')
    @classmethod
    def validate_symptoms(cls, v: Optional[str]) -> Optional[str]:
        """症状の文字数をバリデーション"""
        if v and len(v) > 500:
            raise ValueError('症状は500文字以内で入力してください')
        return v

    @field_validator('medical_institution')
    @classmethod
    def validate_medical_institution(cls, v: Optional[str]) -> Optional[str]:
        """医療機関名の文字数をバリデーション"""
        if v and len(v) > 255:
            raise ValueError('医療機関名は255文字以内で入力してください')
        return v

    @field_validator('doctor')
    @classmethod
    def validate_doctor(cls, v: Optional[str]) -> Optional[str]:
        """主治医の文字数をバリデーション"""
        if v and len(v) > 100:
            raise ValueError('主治医は100文字以内で入力してください')
        return v

    @field_validator('special_remarks')
    @classmethod
    def validate_special_remarks(cls, v: Optional[str]) -> Optional[str]:
        """特記事項の文字数をバリデーション"""
        if v and len(v) > 1000:
            raise ValueError('特記事項は1000文字以内で入力してください')
        return v

    @field_validator('tel')
    @classmethod
    def validate_tel(cls, v: Optional[str]) -> Optional[str]:
        """電話番号のフォーマットをバリデーション"""
        if v is None:
            return v
        import re
        if not re.match(r'^[0-9\-]+$', v):
            raise ValueError('電話番号は数字とハイフンのみ使用できます')
        digits_only = re.sub(r'\D', '', v)
        if len(digits_only) < 10 or len(digits_only) > 11:
            raise ValueError('電話番号は10桁または11桁である必要があります')
        return v

    @model_validator(mode='after')
    def validate_dates(self):
        """日付の論理的整合性をバリデーション"""
        if self.date_started and self.date_ended:
            if self.date_started > self.date_ended:
                raise ValueError('開始日は終了日より前である必要があります')
        return self


class HospitalVisitResponse(HospitalVisitBase):
    """通院歴レスポンススキーマ"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    medical_matters_id: int
    created_at: datetime
    updated_at: datetime


# =============================================================================
# 5. 就労関係スキーマ（Employment Schemas）
# =============================================================================

class EmploymentBase(BaseModel):
    """就労関係の基本スキーマ"""
    model_config = ConfigDict(populate_by_name=True)

    work_conditions: WorkConditions = Field(..., description="就労状況")
    regular_or_part_time_job: bool = Field(..., description="正社員またはパート")
    employment_support: bool = Field(..., description="就労支援利用")
    work_experience_in_the_past_year: bool = Field(..., description="過去1年の就労経験")
    suspension_of_work: bool = Field(..., description="休職中")
    qualifications: Optional[str] = Field(None, max_length=500, description="資格")
    main_places_of_employment: Optional[str] = Field(None, max_length=500, description="主な就労先")
    general_employment_request: bool = Field(..., description="一般就労希望")
    desired_job: Optional[str] = Field(None, max_length=255, description="希望職種")
    special_remarks: Optional[str] = Field(None, max_length=1000, description="特記事項")
    work_outside_the_facility: WorkOutsideFacility = Field(..., description="施設外就労の希望")
    special_note_about_working_outside_the_facility: Optional[str] = Field(None, max_length=1000, description="施設外就労の特記事項")

    @field_validator('qualifications')
    @classmethod
    def validate_qualifications(cls, v: Optional[str]) -> Optional[str]:
        """資格の文字数をバリデーション"""
        if v and len(v) > 500:
            raise ValueError('資格は500文字以内で入力してください')
        return v

    @field_validator('main_places_of_employment')
    @classmethod
    def validate_main_places(cls, v: Optional[str]) -> Optional[str]:
        """主な就労先の文字数をバリデーション"""
        if v and len(v) > 500:
            raise ValueError('主な就労先は500文字以内で入力してください')
        return v

    @field_validator('desired_job')
    @classmethod
    def validate_desired_job(cls, v: Optional[str]) -> Optional[str]:
        """希望職種の文字数をバリデーション"""
        if v and len(v) > 255:
            raise ValueError('希望職種は255文字以内で入力してください')
        return v

    @field_validator('special_remarks')
    @classmethod
    def validate_special_remarks(cls, v: Optional[str]) -> Optional[str]:
        """特記事項の文字数をバリデーション"""
        if v and len(v) > 1000:
            raise ValueError('特記事項は1000文字以内で入力してください')
        return v

    @field_validator('special_note_about_working_outside_the_facility')
    @classmethod
    def validate_facility_note(cls, v: Optional[str]) -> Optional[str]:
        """施設外就労の特記事項の文字数をバリデーション"""
        if v and len(v) > 1000:
            raise ValueError('施設外就労の特記事項は1000文字以内で入力してください')
        return v


class EmploymentCreate(EmploymentBase):
    """就労関係作成時のスキーマ"""
    pass


class EmploymentUpdate(BaseModel):
    """就労関係更新時のスキーマ（全フィールドがOptional）"""
    model_config = ConfigDict(populate_by_name=True)

    work_conditions: Optional[WorkConditions] = None
    regular_or_part_time_job: Optional[bool] = None
    employment_support: Optional[bool] = None
    work_experience_in_the_past_year: Optional[bool] = None
    suspension_of_work: Optional[bool] = None
    qualifications: Optional[str] = Field(None, max_length=500)
    main_places_of_employment: Optional[str] = Field(None, max_length=500)
    general_employment_request: Optional[bool] = None
    desired_job: Optional[str] = Field(None, max_length=255)
    special_remarks: Optional[str] = Field(None, max_length=1000)
    work_outside_the_facility: Optional[WorkOutsideFacility] = None
    special_note_about_working_outside_the_facility: Optional[str] = Field(None, max_length=1000)


class EmploymentResponse(EmploymentBase):
    """就労関係レスポンススキーマ"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    welfare_recipient_id: uuid.UUID
    created_by_staff_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# =============================================================================
# 6. 課題分析スキーマ（Issue Analysis Schemas）
# =============================================================================

class IssueAnalysisBase(BaseModel):
    """課題分析の基本スキーマ（全フィールドがOptional）"""
    model_config = ConfigDict(populate_by_name=True)

    what_i_like_to_do: Optional[str] = Field(None, max_length=1000, description="好き、得意なこと")
    im_not_good_at: Optional[str] = Field(None, max_length=1000, description="嫌い、苦手なこと")
    the_life_i_want: Optional[str] = Field(None, max_length=1000, description="私の望む生活")
    the_support_i_want: Optional[str] = Field(None, max_length=1000, description="特に支援してほしいこと")
    points_to_keep_in_mind_when_providing_support: Optional[str] = Field(None, max_length=1000, description="支援時の注意点")
    future_dreams: Optional[str] = Field(None, max_length=1000, description="将来の夢や希望")
    other: Optional[str] = Field(None, max_length=1000, description="その他")


class IssueAnalysisCreate(IssueAnalysisBase):
    """課題分析作成時のスキーマ"""
    pass


class IssueAnalysisUpdate(IssueAnalysisBase):
    """課題分析更新時のスキーマ（全フィールドがOptional）"""
    pass


class IssueAnalysisResponse(IssueAnalysisBase):
    """課題分析レスポンススキーマ"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    welfare_recipient_id: uuid.UUID
    created_by_staff_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# =============================================================================
# 7. 全アセスメント情報スキーマ（Assessment Response）
# =============================================================================

class AssessmentResponse(BaseModel):
    """全アセスメント情報の一括レスポンススキーマ"""
    model_config = ConfigDict(from_attributes=True)

    family_members: List[FamilyMemberResponse] = Field(default_factory=list, description="家族構成")
    service_history: List[ServiceHistoryResponse] = Field(default_factory=list, description="福祉サービス利用歴")
    medical_info: Optional[MedicalInfoResponse] = Field(None, description="医療基本情報")
    hospital_visits: List[HospitalVisitResponse] = Field(default_factory=list, description="通院歴")
    employment: Optional[EmploymentResponse] = Field(None, description="就労関係")
    issue_analysis: Optional[IssueAnalysisResponse] = Field(None, description="課題分析")
