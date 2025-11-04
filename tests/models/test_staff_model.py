"""
スタッフモデルのテスト
Phase 1: RED phase - full_name NOT NULL制約とname deprecation
"""

import pytest
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models.staff import Staff
from app.models.enums import StaffRole


class TestStaffNameFields:
    """Staffモデルの名前フィールドのテスト"""

    @pytest.mark.asyncio
    async def test_staff_full_name_not_null_constraint(self, db_session: AsyncSession):
        """full_nameがNULLの場合、IntegrityErrorが発生すること"""
        staff = Staff(
            email="test@example.com",
            hashed_password="hashed_password",
            first_name="太郎",
            last_name="山田",
            full_name=None,  # NULLを明示的に設定
            role=StaffRole.employee
        )
        db_session.add(staff)

        with pytest.raises(IntegrityError) as exc_info:
            await db_session.commit()

        # NOT NULL制約違反のエラーメッセージを確認
        assert "full_name" in str(exc_info.value).lower()
        assert "null" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_staff_with_first_last_name_requires_full_name(self, db_session: AsyncSession):
        """first_nameとlast_nameがある場合、full_nameが必須であること"""
        staff = Staff(
            email="test2@example.com",
            hashed_password="hashed_password",
            first_name="花子",
            last_name="佐藤",
            # full_nameを設定しない（デフォルト値も設定されていない想定）
            role=StaffRole.employee
        )
        db_session.add(staff)

        with pytest.raises(IntegrityError) as exc_info:
            await db_session.commit()

        assert "full_name" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_staff_with_valid_full_name(self, db_session: AsyncSession):
        """full_nameが正しく設定されている場合、正常に保存できること"""
        staff = Staff(
            email="test3@example.com",
            hashed_password="hashed_password",
            first_name="次郎",
            last_name="鈴木",
            full_name="鈴木 次郎",  # 正しく設定
            role=StaffRole.employee
        )
        db_session.add(staff)
        await db_session.commit()
        await db_session.refresh(staff)

        assert staff.first_name == "次郎"
        assert staff.last_name == "鈴木"
        assert staff.full_name == "鈴木 次郎"

    @pytest.mark.asyncio
    async def test_staff_full_name_format(self, db_session: AsyncSession):
        """full_nameが 'last_name first_name' の形式であること"""
        staff = Staff(
            email="test4@example.com",
            hashed_password="hashed_password",
            first_name="美咲",
            last_name="田中",
            full_name="田中 美咲",
            role=StaffRole.employee
        )
        db_session.add(staff)
        await db_session.commit()
        await db_session.refresh(staff)

        # full_nameが期待する形式であることを確認
        expected_full_name = f"{staff.last_name} {staff.first_name}"
        assert staff.full_name == expected_full_name

    @pytest.mark.asyncio
    async def test_staff_name_field_is_optional(self, db_session: AsyncSession):
        """nameフィールドはオプショナル（deprecated）であること"""
        staff = Staff(
            email="test5@example.com",
            hashed_password="hashed_password",
            first_name="健太",
            last_name="高橋",
            full_name="高橋 健太",
            name=None,  # nameはオプショナル（deprecated）
            role=StaffRole.employee
        )
        db_session.add(staff)
        await db_session.commit()
        await db_session.refresh(staff)

        # nameがNULLでも保存できることを確認
        assert staff.name is None
        assert staff.full_name == "高橋 健太"

    @pytest.mark.asyncio
    async def test_staff_name_field_can_be_set_for_backward_compatibility(self, db_session: AsyncSession):
        """後方互換性のため、nameフィールドは設定可能であること"""
        staff = Staff(
            email="test6@example.com",
            hashed_password="hashed_password",
            first_name="愛",
            last_name="渡辺",
            full_name="渡辺 愛",
            name="渡辺愛",  # 後方互換性のため設定可能
            role=StaffRole.employee
        )
        db_session.add(staff)
        await db_session.commit()
        await db_session.refresh(staff)

        assert staff.name == "渡辺愛"
        assert staff.full_name == "渡辺 愛"


class TestStaffNameMigration:
    """名前フィールド移行に関するテスト"""

    @pytest.mark.asyncio
    async def test_existing_staff_should_have_full_name(self, db_session: AsyncSession):
        """既存のスタッフレコードはマイグレーション後、full_nameを持つべき"""
        # マイグレーション実行後を想定したテスト
        staff = Staff(
            email="migrated@example.com",
            hashed_password="hashed_password",
            first_name="太郎",
            last_name="山田",
            full_name="山田 太郎",  # マイグレーションで設定された値
            name="山田 太郎",  # 旧フィールド（deprecated）
            role=StaffRole.owner
        )
        db_session.add(staff)
        await db_session.commit()
        await db_session.refresh(staff)

        # 両方のフィールドが存在することを確認
        assert staff.name == "山田 太郎"  # deprecated
        assert staff.full_name == "山田 太郎"  # 新しいフィールド
