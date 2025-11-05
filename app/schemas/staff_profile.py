"""スタッフプロフィール関連のスキーマ"""
import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, field_validator, ConfigDict
import re


class StaffNameUpdate(BaseModel):
    """名前更新用スキーマ"""
    last_name: str
    first_name: str
    last_name_furigana: str
    first_name_furigana: str

    @field_validator("last_name", "first_name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """名前のバリデーション"""
        if not v or not v.strip():
            raise ValueError("名前は必須です")

        v = v.strip()

        # 文字数チェック
        if len(v) < 1 or len(v) > 50:
            raise ValueError("名前は1文字以上50文字以内で入力してください")

        # 数字のみの名前を禁止（文字種チェックより先に実施）
        if v.replace(' ', '').replace('　', '').isdigit():
            raise ValueError("名前に数字のみは使用できません")

        # 文字種チェック（ひらがな、カタカナ、漢字、全角スペース、一部記号）
        if not re.match(r'^[ぁ-んァ-ヶー一-龠々・\s]+$', v):
            raise ValueError("名前に使用できない文字が含まれています")

        # 連続する空白を1つに正規化
        return re.sub(r'\s+', ' ', v)

    @field_validator("last_name_furigana", "first_name_furigana")
    @classmethod
    def validate_furigana(cls, v: str) -> str:
        """ふりがなのバリデーション"""
        if not v or not v.strip():
            raise ValueError("ふりがなは必須です")

        v = v.strip()

        # 文字数チェック
        if len(v) < 1 or len(v) > 100:
            raise ValueError("ふりがなは1文字以上100文字以内で入力してください")

        # ひらがなのみチェック
        if not re.match(r'^[ぁ-ん\s]+$', v):
            raise ValueError("ふりがなはひらがなで入力してください")

        # 連続する空白を1つに正規化
        return re.sub(r'\s+', ' ', v)


class StaffNameUpdateResponse(BaseModel):
    """名前更新レスポンス"""
    id: uuid.UUID
    last_name: str
    first_name: str
    full_name: str
    last_name_furigana: str
    first_name_furigana: str
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EmailChangeRequest(BaseModel):
    """メールアドレス変更リクエスト"""
    new_email: str
    password: str

    @field_validator("new_email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        """メールアドレスのバリデーション"""
        v = v.strip().lower()

        # 長さチェック
        if len(v) > 254:
            raise ValueError("メールアドレスは254文字以内で入力してください")

        # 基本的なメール形式チェック
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, v):
            raise ValueError("メールアドレスの形式が正しくありません")

        return v


class EmailChangeRequestResponse(BaseModel):
    """メールアドレス変更リクエストレスポンス"""
    message: str
    verification_token_expires_at: datetime
    status: str


class EmailChangeConfirm(BaseModel):
    """メールアドレス変更確認"""
    verification_token: str


class EmailChangeConfirmResponse(BaseModel):
    """メールアドレス変更確認レスポンス"""
    message: str
    new_email: str
    updated_at: datetime


class PasswordChange(BaseModel):
    """パスワード変更"""
    current_password: str
    new_password: str
    new_password_confirm: str

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """パスワード強度の検証"""
        errors = []

        # 長さチェック
        if len(v) < 8:
            errors.append("パスワードは8文字以上にしてください")
        if len(v) > 128:
            errors.append("パスワードは128文字以内にしてください")

        # 文字種チェック
        if not re.search(r'[a-z]', v):
            errors.append("少なくとも1つの小文字を含めてください")
        if not re.search(r'[A-Z]', v):
            errors.append("少なくとも1つの大文字を含めてください")
        if not re.search(r'\d', v):
            errors.append("少なくとも1つの数字を含めてください")
        if not re.search(r'[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]', v):
            errors.append("少なくとも1つの特殊文字を含めてください")

        # 連続文字チェック
        if re.search(r'(.)\1{2,}', v):
            errors.append("同じ文字を3回以上連続して使用できません")

        # 一般的なパスワードチェック（完全一致のみ）
        common_passwords = [
            "password", "123456", "12345678", "qwerty", "abc123",
            "monkey", "1234567", "letmein", "trustno1", "dragon",
            "baseball", "iloveyou", "master", "sunshine", "ashley",
            "password123", "password123!", "password1", "password1!"
        ]
        v_lower = v.lower()
        # 完全一致でチェック
        if v_lower in common_passwords:
            errors.append("このパスワードは一般的すぎるため使用できません")

        if errors:
            raise ValueError("\n".join(errors))

        return v


class PasswordChangeResponse(BaseModel):
    """パスワード変更レスポンス"""
    message: str
    updated_at: datetime
    logged_out_devices: int
