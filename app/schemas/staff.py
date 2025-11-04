import uuid
import re
from typing import Optional
from pydantic import BaseModel, EmailStr, field_validator, ConfigDict, Field
from app.models.enums import StaffRole


class StaffBase(BaseModel):
    email: EmailStr
    first_name: str = Field(...)
    last_name: str = Field(...)

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_name_fields(cls, v: str, info) -> str:
        """姓名のバリデーション"""
        # 空白のトリミング
        v = v.strip()

        if not v:
            raise ValueError(f"{info.field_name}は空にできません")

        # 50文字制限
        if len(v) > 50:
            raise ValueError(f"{info.field_name}は50文字以内にしてください")

        # 数字のみの名前を禁止
        if v.replace(' ', '').replace('　', '').isdigit():
            raise ValueError("名前に数字のみは使用できません")

        # 使用可能文字のチェック
        # 日本語（ひらがな・カタカナ・漢字）、全角スペース、・（中点）、々（同じく）のみ許可
        allowed_pattern = r'^[ぁ-ん ァ-ヶー一-龥々・　]+$'
        if not re.match(allowed_pattern, v):
            raise ValueError("名前に使用できない文字が含まれています（日本語のみ使用可能）")

        return v


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

class Staff(BaseModel):
    # 基本フィールド
    id: uuid.UUID
    email: EmailStr
    role: StaffRole
    is_mfa_enabled: bool
    office: Optional[OfficeInStaffRead] = None # office情報を追加

    # 名前フィールド（必須）
    first_name: str
    last_name: str
    full_name: str  # {last_name} {first_name}の形式

    # ふりがなフィールド（オプション）
    last_name_furigana: Optional[str] = None
    first_name_furigana: Optional[str] = None

    # 後方互換性のためのフィールド（deprecated）
    name: Optional[str] = None  # ⚠️ Deprecated: full_nameを使用してください

    model_config = ConfigDict(from_attributes=True)


# レスポンス用のエイリアス
StaffRead = Staff

class EmailVerificationResponse(BaseModel):
    message: str
    role: StaffRole
