"""
スタッフスキーマのバリデーションテスト
Phase 2: RED phase - first_name/last_nameへの移行
"""

import pytest
from pydantic import ValidationError

from app.schemas.staff import StaffBase, AdminCreate, StaffCreate
from app.models.enums import StaffRole


class TestStaffNameValidation:
    """名前フィールドのバリデーションテスト"""

    def test_valid_japanese_name(self):
        """正常系: 有効な日本語名"""
        staff = StaffBase(
            email="test@example.com",
            first_name="太郎",
            last_name="山田"
        )
        assert staff.first_name == "太郎"
        assert staff.last_name == "山田"

    def test_valid_name_with_space(self):
        """正常系: 全角スペースを含む名前"""
        staff = StaffBase(
            email="test@example.com",
            first_name="太 郎",
            last_name="山 田"
        )
        assert staff.first_name == "太 郎"
        assert staff.last_name == "山 田"

    def test_valid_name_with_nakaten(self):
        """正常系: 中点（・）を含む名前"""
        staff = StaffBase(
            email="test@example.com",
            first_name="太・郎",
            last_name="山田"
        )
        assert staff.first_name == "太・郎"

    def test_valid_name_with_noma(self):
        """正常系: 々（同じく）を含む名前"""
        staff = StaffBase(
            email="test@example.com",
            first_name="太郎",
            last_name="佐々木"
        )
        assert staff.last_name == "佐々木"

    def test_empty_first_name_error(self):
        """異常系: 名が空文字"""
        with pytest.raises(ValidationError) as exc_info:
            StaffBase(
                email="test@example.com",
                first_name="",
                last_name="山田"
            )
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("first_name",) for error in errors)

    def test_empty_last_name_error(self):
        """異常系: 姓が空文字"""
        with pytest.raises(ValidationError) as exc_info:
            StaffBase(
                email="test@example.com",
                first_name="太郎",
                last_name=""
            )
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("last_name",) for error in errors)

    def test_too_long_first_name_error(self):
        """異常系: 名が50文字超過"""
        long_name = "あ" * 51
        with pytest.raises(ValidationError) as exc_info:
            StaffBase(
                email="test@example.com",
                first_name=long_name,
                last_name="山田"
            )
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("first_name",) for error in errors)
        assert any("50文字" in str(error["msg"]) for error in errors)

    def test_too_long_last_name_error(self):
        """異常系: 姓が50文字超過"""
        long_name = "あ" * 51
        with pytest.raises(ValidationError) as exc_info:
            StaffBase(
                email="test@example.com",
                first_name="太郎",
                last_name=long_name
            )
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("last_name",) for error in errors)
        assert any("50文字" in str(error["msg"]) for error in errors)

    def test_invalid_chars_in_first_name_error(self):
        """異常系: 名に半角英数字が含まれる"""
        with pytest.raises(ValidationError) as exc_info:
            StaffBase(
                email="test@example.com",
                first_name="Taro123",
                last_name="山田"
            )
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("first_name",) for error in errors)
        assert any("使用できない文字" in str(error["msg"]) for error in errors)

    def test_invalid_chars_in_last_name_error(self):
        """異常系: 姓に半角英数字が含まれる"""
        with pytest.raises(ValidationError) as exc_info:
            StaffBase(
                email="test@example.com",
                first_name="太郎",
                last_name="Yamada123"
            )
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("last_name",) for error in errors)
        assert any("使用できない文字" in str(error["msg"]) for error in errors)

    def test_numbers_only_first_name_error(self):
        """異常系: 名が数字のみ"""
        with pytest.raises(ValidationError) as exc_info:
            StaffBase(
                email="test@example.com",
                first_name="123",
                last_name="山田"
            )
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("first_name",) for error in errors)
        assert any("数字のみ" in str(error["msg"]) for error in errors)

    def test_numbers_only_last_name_error(self):
        """異常系: 姓が数字のみ"""
        with pytest.raises(ValidationError) as exc_info:
            StaffBase(
                email="test@example.com",
                first_name="太郎",
                last_name="123"
            )
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("last_name",) for error in errors)
        assert any("数字のみ" in str(error["msg"]) for error in errors)


class TestAdminCreate:
    """AdminCreateスキーマのテスト"""

    def test_valid_admin_create(self):
        """正常系: 有効な管理者作成データ"""
        admin = AdminCreate(
            email="admin@example.com",
            first_name="太郎",
            last_name="山田",
            password="SecurePass123!"
        )
        assert admin.first_name == "太郎"
        assert admin.last_name == "山田"
        assert admin.email == "admin@example.com"


class TestStaffCreate:
    """StaffCreateスキーマのテスト"""

    def test_valid_staff_create(self):
        """正常系: 有効なスタッフ作成データ"""
        staff = StaffCreate(
            email="staff@example.com",
            first_name="花子",
            last_name="佐藤",
            password="SecurePass123!",
            role=StaffRole.employee
        )
        assert staff.first_name == "花子"
        assert staff.last_name == "佐藤"
        assert staff.role == StaffRole.employee

    def test_staff_create_owner_role_error(self):
        """異常系: ownerロールは作成不可"""
        with pytest.raises(ValidationError) as exc_info:
            StaffCreate(
                email="staff@example.com",
                first_name="花子",
                last_name="佐藤",
                password="SecurePass123!",
                role=StaffRole.owner
            )
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("role",) for error in errors)
