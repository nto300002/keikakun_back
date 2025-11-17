from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import List, Optional
from datetime import date
from app.models.enums import (
    GenderType,
    FormOfResidence,
    MeansOfTransportation,
    LivelihoodProtection,
    ApplicationStatus,
    PhysicalDisabilityType,
    DisabilityCategory,
)
import uuid
from app.messages import ja


# Emergency Contact Schemas
class EmergencyContactCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    first_name: str = Field(..., min_length=1, max_length=255, alias="firstName")
    last_name: str = Field(..., min_length=1, max_length=255, alias="lastName")
    first_name_furigana: str = Field(..., min_length=1, max_length=255, alias="firstNameFurigana")
    last_name_furigana: str = Field(..., min_length=1, max_length=255, alias="lastNameFurigana")
    relationship: str = Field(..., min_length=1, max_length=255)
    tel: str = Field(..., min_length=1)
    address: Optional[str] = Field(None)
    notes: Optional[str] = Field(None)
    priority: int = Field(1, ge=1, le=10)


class EmergencyContactResponse(EmergencyContactCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    service_recipient_detail_id: int


# Service Recipient Detail Schemas
class ServiceRecipientDetailCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    address: str = Field(..., min_length=1)
    form_of_residence: FormOfResidence = Field(..., alias="formOfResidence")
    form_of_residence_other_text: Optional[str] = Field(None, alias="formOfResidenceOtherText")
    means_of_transportation: MeansOfTransportation = Field(..., alias="meansOfTransportation")
    means_of_transportation_other_text: Optional[str] = Field(None, alias="meansOfTransportationOtherText")
    tel: str = Field(..., min_length=1)
    emergency_contacts: List[EmergencyContactCreate] = Field(default_factory=list, alias="emergencyContacts")


class ServiceRecipientDetailResponse(ServiceRecipientDetailCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    welfare_recipient_id: uuid.UUID
    emergency_contacts: List[EmergencyContactResponse]


# Disability Detail Schemas
class DisabilityDetailCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    category: DisabilityCategory
    grade_or_level: Optional[str] = Field(None, alias="gradeOrLevel")
    physical_disability_type: Optional[PhysicalDisabilityType] = Field(None, alias="physicalDisabilityType")
    physical_disability_type_other_text: Optional[str] = Field(None, alias="physicalDisabilityTypeOtherText")
    application_status: ApplicationStatus = Field(..., alias="applicationStatus")


class DisabilityDetailResponse(DisabilityDetailCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    disability_status_id: int


# Disability Status Schemas
class DisabilityStatusCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    disability_or_disease_name: str = Field(..., min_length=1, alias="disabilityOrDiseaseName")
    livelihood_protection: LivelihoodProtection = Field(..., alias="livelihoodProtection")
    special_remarks: Optional[str] = Field(None, max_length=2000, alias="specialRemarks")
    details: List[DisabilityDetailCreate] = Field(default_factory=list)


class DisabilityStatusResponse(DisabilityStatusCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    welfare_recipient_id: uuid.UUID
    details: List[DisabilityDetailResponse]


# Welfare Recipient Schemas
class WelfareRecipientCreate(BaseModel):
    # Basic Information
    first_name: str = Field(..., min_length=1, max_length=255)
    last_name: str = Field(..., min_length=1, max_length=255)
    first_name_furigana: str = Field(..., min_length=1, max_length=255)
    last_name_furigana: str = Field(..., min_length=1, max_length=255)
    birth_day: date
    gender: GenderType

    # Related data
    detail: Optional[ServiceRecipientDetailCreate] = Field(None)
    disability_status: Optional[DisabilityStatusCreate] = Field(None)

    @field_validator('birth_day')
    @classmethod
    def validate_birth_day(cls, v: date) -> date:
        from datetime import date as dt_date
        if v > dt_date.today():
            raise ValueError(ja.VALIDATION_BIRTH_DATE_FUTURE)
        return v


class WelfareRecipientUpdate(BaseModel):
    first_name: Optional[str] = Field(None, min_length=1, max_length=255)
    last_name: Optional[str] = Field(None, min_length=1, max_length=255)
    first_name_furigana: Optional[str] = Field(None, min_length=1, max_length=255)
    last_name_furigana: Optional[str] = Field(None, min_length=1, max_length=255)
    birth_day: Optional[date] = None
    gender: Optional[GenderType] = None

    detail: Optional[ServiceRecipientDetailCreate] = Field(None)
    disability_status: Optional[DisabilityStatusCreate] = Field(None)

    @field_validator('birth_day')
    @classmethod
    def validate_birth_day(cls, v: Optional[date]) -> Optional[date]:
        if v is None:
            return v
        from datetime import date as dt_date
        if v > dt_date.today():
            raise ValueError(ja.VALIDATION_BIRTH_DATE_FUTURE)
        return v


class WelfareRecipientResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    first_name: str
    last_name: str
    first_name_furigana: str
    last_name_furigana: str
    birth_day: date
    gender: GenderType

    detail: Optional[ServiceRecipientDetailResponse] = None
    disability_status: Optional[DisabilityStatusResponse] = None


# List response for paginated results
class WelfareRecipientListResponse(BaseModel):
    recipients: List[WelfareRecipientResponse]
    total: int
    page: int
    per_page: int
    pages: int


# Form data aggregated schema (matches frontend form structure)
class BasicInfo(BaseModel):
    firstName: str = Field(..., min_length=1, max_length=255)
    lastName: str = Field(..., min_length=1, max_length=255)
    firstNameFurigana: str = Field(..., min_length=1, max_length=255)
    lastNameFurigana: str = Field(..., min_length=1, max_length=255)
    birthDay: date
    gender: GenderType

class ContactAddress(BaseModel):
    address: str = Field(..., min_length=1)
    formOfResidence: FormOfResidence
    formOfResidenceOtherText: Optional[str] = None
    meansOfTransportation: MeansOfTransportation
    meansOfTransportationOtherText: Optional[str] = None
    tel: str = Field(..., min_length=1)

class DisabilityInfo(BaseModel):
    disabilityOrDiseaseName: str = Field(..., min_length=1)
    livelihoodProtection: LivelihoodProtection
    specialRemarks: Optional[str] = Field(None, max_length=2000)

class UserRegistrationRequest(BaseModel):
    """
    Aggregated schema that matches the frontend multi-section form structure
    """
    model_config = ConfigDict(populate_by_name=True)

    basic_info: BasicInfo
    contact_address: ContactAddress
    emergency_contacts: List[EmergencyContactCreate] = Field(default_factory=list)
    disability_info: DisabilityInfo
    disability_details: List[DisabilityDetailCreate] = Field(default_factory=list)


class UserRegistrationResponse(BaseModel):
    """Response after successful user registration"""
    success: bool = True
    message: str = "利用者の登録が完了しました"
    recipient_id: Optional[uuid.UUID] = None
    support_plan_created: bool = True
    request_id: Optional[uuid.UUID] = None  # For employee requests pending approval