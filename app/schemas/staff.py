import uuid
import re
from typing import Optional
from pydantic import BaseModel, EmailStr, field_validator, ConfigDict
from app.models.enums import StaffRole


class StaffBase(BaseModel):
    email: EmailStr
    name: str


class AdminCreate(StaffBase):
    password: str

    @field_validator("password")
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("パスワードは8文字以上である必要があります")
        
        checks = {
            "lowercase": lambda s: re.search(r'[a-z]', s),
            "uppercase": lambda s: re.search(r'[A-Z]', s),
            "digit": lambda s: re.search(r'\d', s),
            "symbol": lambda s: re.search(r'[!@#$%^&*(),.?":{}|<>]', s),
        }
        
        score = sum(1 for check in checks.values() if check(v))
        
        if score < 4:
            raise ValueError("パスワードは次のうち少なくとも3つを含む必要があります: 英字小文字、大文字、数字、記号")

        return v


class StaffCreate(StaffBase):
    password: str
    role: StaffRole

    @field_validator("role")
    def validate_role(cls, v: StaffRole):
        if v == StaffRole.owner:
            raise ValueError("Cannot register as an owner through this endpoint.")
        return v

    @field_validator("password")
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("パスワードは8文字以上である必要があります")
        
        checks = {
            "lowercase": lambda s: re.search(r'[a-z]', s),
            "uppercase": lambda s: re.search(r'[A-Z]', s),
            "digit": lambda s: re.search(r'\d', s),
            "symbol": lambda s: re.search(r'[!@#$%^&*(),.?":{}|<>]', s),
        }
        
        score = sum(1 for check in checks.values() if check(v))
        
        if score < 4:
            raise ValueError("パスワードは次のうち少なくとも3つを含む必要があります: 英字小文字、大文字、数字、記号")

        return v


from typing import Optional

# StaffReadスキーマに所属事業所情報を追加するためのスキーマ
class OfficeInStaffRead(BaseModel):
    id: uuid.UUID
    name: str

    model_config = ConfigDict(from_attributes=True)

class Staff(StaffBase):
    id: uuid.UUID
    role: StaffRole
    office: Optional[OfficeInStaffRead] = None # office情報を追加

    model_config = ConfigDict(from_attributes=True)


# レスポンス用のエイリアス
StaffRead = Staff

class EmailVerificationResponse(BaseModel):
    message: str
    role: StaffRole
