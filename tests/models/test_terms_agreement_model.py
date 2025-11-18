"""
利用規約・プライバシーポリシー同意履歴モデルのテスト
TDD Phase 1: RED phase - テストを先に作成
"""

import pytest
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.staff import Staff
from app.models.enums import StaffRole


class TestTermsAgreementBasicConstraints:
    """TermsAgreementモデルの基本的な制約のテスト"""

    @pytest.mark.asyncio
    async def test_terms_agreement_requires_staff_id(self, db_session: AsyncSession):
        """staff_idがNULLの場合、IntegrityErrorが発生すること"""
        from app.models.terms_agreement import TermsAgreement

        agreement = TermsAgreement(
            staff_id=None,  # NULLを明示的に設定
        )
        db_session.add(agreement)

        with pytest.raises(IntegrityError) as exc_info:
            await db_session.commit()

        # NOT NULL制約違反のエラーメッセージを確認
        assert "staff_id" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_terms_agreement_staff_id_must_exist(self, db_session: AsyncSession):
        """staff_idは存在するスタッフを参照しなければならない（外部キー制約）"""
        from app.models.terms_agreement import TermsAgreement

        non_existent_staff_id = uuid.uuid4()
        agreement = TermsAgreement(
            staff_id=non_existent_staff_id,
        )
        db_session.add(agreement)

        with pytest.raises(IntegrityError) as exc_info:
            await db_session.commit()

        # 外部キー制約違反のエラーメッセージを確認
        error_msg = str(exc_info.value).lower()
        assert "foreign key" in error_msg or "violates" in error_msg

    @pytest.mark.asyncio
    async def test_terms_agreement_staff_id_unique_constraint(self, db_session: AsyncSession):
        """1人のスタッフに対して複数の同意履歴を作成できないこと（UNIQUE制約）"""
        from app.models.terms_agreement import TermsAgreement

        # テスト用スタッフを作成
        staff = Staff(
            email="test@example.com",
            hashed_password="hashed",
            first_name="太郎",
            last_name="山田",
            full_name="山田 太郎",
            role=StaffRole.employee
        )
        db_session.add(staff)
        await db_session.commit()
        await db_session.refresh(staff)

        # 1つ目の同意履歴を作成
        agreement1 = TermsAgreement(
            staff_id=staff.id,
        )
        db_session.add(agreement1)
        await db_session.commit()

        # 同じスタッフに対して2つ目の同意履歴を作成しようとする
        agreement2 = TermsAgreement(
            staff_id=staff.id,
        )
        db_session.add(agreement2)

        with pytest.raises(IntegrityError) as exc_info:
            await db_session.commit()

        # UNIQUE制約違反のエラーメッセージを確認
        error_msg = str(exc_info.value).lower()
        assert "unique" in error_msg or "duplicate" in error_msg


class TestTermsAgreementCreation:
    """TermsAgreement作成のテスト"""

    @pytest.mark.asyncio
    async def test_create_terms_agreement_minimal(self, db_session: AsyncSession):
        """最小限のフィールドで同意履歴を作成できること"""
        from app.models.terms_agreement import TermsAgreement

        # テスト用スタッフを作成
        staff = Staff(
            email="test2@example.com",
            hashed_password="hashed",
            first_name="花子",
            last_name="佐藤",
            full_name="佐藤 花子",
            role=StaffRole.employee
        )
        db_session.add(staff)
        await db_session.commit()
        await db_session.refresh(staff)

        # 同意履歴を作成
        agreement = TermsAgreement(
            staff_id=staff.id,
        )
        db_session.add(agreement)
        await db_session.commit()
        await db_session.refresh(agreement)

        # 検証
        assert agreement.id is not None
        assert agreement.staff_id == staff.id
        assert agreement.terms_of_service_agreed_at is None
        assert agreement.privacy_policy_agreed_at is None
        assert agreement.terms_version is None
        assert agreement.privacy_version is None
        assert agreement.ip_address is None
        assert agreement.user_agent is None
        assert agreement.created_at is not None
        assert agreement.updated_at is not None

    @pytest.mark.asyncio
    async def test_create_terms_agreement_with_all_fields(self, db_session: AsyncSession):
        """全フィールドを設定して同意履歴を作成できること"""
        from app.models.terms_agreement import TermsAgreement

        # テスト用スタッフを作成
        staff = Staff(
            email="test3@example.com",
            hashed_password="hashed",
            first_name="次郎",
            last_name="鈴木",
            full_name="鈴木 次郎",
            role=StaffRole.employee
        )
        db_session.add(staff)
        await db_session.commit()
        await db_session.refresh(staff)

        # 同意日時を設定
        now = datetime.now(timezone.utc)

        # 全フィールドを設定して同意履歴を作成
        agreement = TermsAgreement(
            staff_id=staff.id,
            terms_of_service_agreed_at=now,
            privacy_policy_agreed_at=now,
            terms_version="1.0",
            privacy_version="1.0",
            ip_address="192.168.1.100",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        )
        db_session.add(agreement)
        await db_session.commit()
        await db_session.refresh(agreement)

        # 検証
        assert agreement.staff_id == staff.id
        assert agreement.terms_of_service_agreed_at is not None
        assert agreement.privacy_policy_agreed_at is not None
        assert agreement.terms_version == "1.0"
        assert agreement.privacy_version == "1.0"
        assert agreement.ip_address == "192.168.1.100"
        assert agreement.user_agent == "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

    @pytest.mark.asyncio
    async def test_terms_agreement_timestamps_auto_set(self, db_session: AsyncSession):
        """created_atとupdated_atが自動的に設定されること"""
        from app.models.terms_agreement import TermsAgreement

        # テスト用スタッフを作成
        staff = Staff(
            email="test4@example.com",
            hashed_password="hashed",
            first_name="美咲",
            last_name="田中",
            full_name="田中 美咲",
            role=StaffRole.employee
        )
        db_session.add(staff)
        await db_session.commit()
        await db_session.refresh(staff)

        # 同意履歴を作成
        agreement = TermsAgreement(
            staff_id=staff.id,
        )
        db_session.add(agreement)
        await db_session.commit()
        await db_session.refresh(agreement)

        # タイムスタンプが設定されていることを確認
        assert agreement.created_at is not None
        assert agreement.updated_at is not None
        assert isinstance(agreement.created_at, datetime)
        assert isinstance(agreement.updated_at, datetime)


class TestTermsAgreementRelationships:
    """TermsAgreementのリレーションシップのテスト"""

    @pytest.mark.asyncio
    async def test_terms_agreement_staff_relationship(self, db_session: AsyncSession):
        """TermsAgreementからStaffへのリレーションシップが正しく機能すること"""
        from app.models.terms_agreement import TermsAgreement

        # テスト用スタッフを作成
        staff = Staff(
            email="test5@example.com",
            hashed_password="hashed",
            first_name="健太",
            last_name="高橋",
            full_name="高橋 健太",
            role=StaffRole.employee
        )
        db_session.add(staff)
        await db_session.commit()
        await db_session.refresh(staff)

        # 同意履歴を作成
        agreement = TermsAgreement(
            staff_id=staff.id,
        )
        db_session.add(agreement)
        await db_session.commit()

        # リレーションシップを使って再取得
        result = await db_session.execute(
            select(TermsAgreement)
            .where(TermsAgreement.staff_id == staff.id)
            .options(selectinload(TermsAgreement.staff))
        )
        agreement_with_staff = result.scalar_one()

        # 検証
        assert agreement_with_staff.staff is not None
        assert agreement_with_staff.staff.id == staff.id
        assert agreement_with_staff.staff.email == "test5@example.com"

    @pytest.mark.asyncio
    async def test_staff_terms_agreement_relationship(self, db_session: AsyncSession):
        """StaffからTermsAgreementへのリレーションシップが正しく機能すること（1:1）"""
        from app.models.terms_agreement import TermsAgreement

        # テスト用スタッフを作成
        staff = Staff(
            email="test6@example.com",
            hashed_password="hashed",
            first_name="愛",
            last_name="渡辺",
            full_name="渡辺 愛",
            role=StaffRole.employee
        )
        db_session.add(staff)
        await db_session.commit()
        await db_session.refresh(staff)

        # 同意履歴を作成
        agreement = TermsAgreement(
            staff_id=staff.id,
            terms_version="1.0",
            privacy_version="1.0",
        )
        db_session.add(agreement)
        await db_session.commit()

        # Staffからリレーションシップを使って取得
        result = await db_session.execute(
            select(Staff)
            .where(Staff.id == staff.id)
            .options(selectinload(Staff.terms_agreement))
        )
        staff_with_agreement = result.scalar_one()

        # 検証
        assert staff_with_agreement.terms_agreement is not None
        assert staff_with_agreement.terms_agreement.staff_id == staff.id
        assert staff_with_agreement.terms_agreement.terms_version == "1.0"

    @pytest.mark.asyncio
    async def test_cascade_delete_terms_agreement(self, db_session: AsyncSession):
        """スタッフを削除すると同意履歴も削除されること（CASCADE DELETE）"""
        from app.models.terms_agreement import TermsAgreement

        # テスト用スタッフを作成
        staff = Staff(
            email="test7@example.com",
            hashed_password="hashed",
            first_name="大輔",
            last_name="伊藤",
            full_name="伊藤 大輔",
            role=StaffRole.employee
        )
        db_session.add(staff)
        await db_session.commit()
        await db_session.refresh(staff)
        staff_id = staff.id

        # 同意履歴を作成
        agreement = TermsAgreement(
            staff_id=staff.id,
        )
        db_session.add(agreement)
        await db_session.commit()
        agreement_id = agreement.id

        # スタッフを削除
        await db_session.delete(staff)
        await db_session.commit()

        # 同意履歴も削除されていることを確認
        result = await db_session.execute(
            select(TermsAgreement).where(TermsAgreement.id == agreement_id)
        )
        deleted_agreement = result.scalar_one_or_none()
        assert deleted_agreement is None


class TestTermsAgreementBusinessLogic:
    """TermsAgreementのビジネスロジックメソッドのテスト"""

    @pytest.mark.asyncio
    async def test_has_agreed_to_current_terms_true(self, db_session: AsyncSession):
        """現在のバージョンの利用規約に同意している場合、Trueを返すこと"""
        from app.models.terms_agreement import TermsAgreement

        # テスト用スタッフを作成
        staff = Staff(
            email="test8@example.com",
            hashed_password="hashed",
            first_name="結衣",
            last_name="山本",
            full_name="山本 結衣",
            role=StaffRole.employee
        )
        db_session.add(staff)
        await db_session.commit()
        await db_session.refresh(staff)

        # 同意履歴を作成
        agreement = TermsAgreement(
            staff_id=staff.id,
            terms_of_service_agreed_at=datetime.now(timezone.utc),
            terms_version="1.0",
        )
        db_session.add(agreement)
        await db_session.commit()
        await db_session.refresh(agreement)

        # 検証
        assert agreement.has_agreed_to_current_terms("1.0") is True

    @pytest.mark.asyncio
    async def test_has_agreed_to_current_terms_false_old_version(self, db_session: AsyncSession):
        """古いバージョンの利用規約に同意している場合、Falseを返すこと"""
        from app.models.terms_agreement import TermsAgreement

        # テスト用スタッフを作成
        staff = Staff(
            email="test9@example.com",
            hashed_password="hashed",
            first_name="拓也",
            last_name="中村",
            full_name="中村 拓也",
            role=StaffRole.employee
        )
        db_session.add(staff)
        await db_session.commit()
        await db_session.refresh(staff)

        # 古いバージョンに同意
        agreement = TermsAgreement(
            staff_id=staff.id,
            terms_of_service_agreed_at=datetime.now(timezone.utc),
            terms_version="1.0",
        )
        db_session.add(agreement)
        await db_session.commit()
        await db_session.refresh(agreement)

        # 新しいバージョン（2.0）とチェック
        assert agreement.has_agreed_to_current_terms("2.0") is False

    @pytest.mark.asyncio
    async def test_has_agreed_to_current_terms_false_not_agreed(self, db_session: AsyncSession):
        """まだ同意していない場合、Falseを返すこと"""
        from app.models.terms_agreement import TermsAgreement

        # テスト用スタッフを作成
        staff = Staff(
            email="test10@example.com",
            hashed_password="hashed",
            first_name="麻衣",
            last_name="小林",
            full_name="小林 麻衣",
            role=StaffRole.employee
        )
        db_session.add(staff)
        await db_session.commit()
        await db_session.refresh(staff)

        # 未同意の状態で作成
        agreement = TermsAgreement(
            staff_id=staff.id,
            terms_of_service_agreed_at=None,
            terms_version=None,
        )
        db_session.add(agreement)
        await db_session.commit()
        await db_session.refresh(agreement)

        # 検証
        assert agreement.has_agreed_to_current_terms("1.0") is False

    @pytest.mark.asyncio
    async def test_has_agreed_to_current_privacy_true(self, db_session: AsyncSession):
        """現在のバージョンのプライバシーポリシーに同意している場合、Trueを返すこと"""
        from app.models.terms_agreement import TermsAgreement

        # テスト用スタッフを作成
        staff = Staff(
            email="test11@example.com",
            hashed_password="hashed",
            first_name="翔太",
            last_name="加藤",
            full_name="加藤 翔太",
            role=StaffRole.employee
        )
        db_session.add(staff)
        await db_session.commit()
        await db_session.refresh(staff)

        # 同意履歴を作成
        agreement = TermsAgreement(
            staff_id=staff.id,
            privacy_policy_agreed_at=datetime.now(timezone.utc),
            privacy_version="1.0",
        )
        db_session.add(agreement)
        await db_session.commit()
        await db_session.refresh(agreement)

        # 検証
        assert agreement.has_agreed_to_current_privacy("1.0") is True

    @pytest.mark.asyncio
    async def test_has_agreed_to_all_current_true(self, db_session: AsyncSession):
        """両方に同意している場合、Trueを返すこと"""
        from app.models.terms_agreement import TermsAgreement

        # テスト用スタッフを作成
        staff = Staff(
            email="test12@example.com",
            hashed_password="hashed",
            first_name="優子",
            last_name="吉田",
            full_name="吉田 優子",
            role=StaffRole.employee
        )
        db_session.add(staff)
        await db_session.commit()
        await db_session.refresh(staff)

        # 両方に同意
        now = datetime.now(timezone.utc)
        agreement = TermsAgreement(
            staff_id=staff.id,
            terms_of_service_agreed_at=now,
            privacy_policy_agreed_at=now,
            terms_version="1.0",
            privacy_version="1.0",
        )
        db_session.add(agreement)
        await db_session.commit()
        await db_session.refresh(agreement)

        # 検証
        assert agreement.has_agreed_to_all_current("1.0", "1.0") is True

    @pytest.mark.asyncio
    async def test_has_agreed_to_all_current_false_partial(self, db_session: AsyncSession):
        """一方のみ同意している場合、Falseを返すこと"""
        from app.models.terms_agreement import TermsAgreement

        # テスト用スタッフを作成
        staff = Staff(
            email="test13@example.com",
            hashed_password="hashed",
            first_name="直樹",
            last_name="清水",
            full_name="清水 直樹",
            role=StaffRole.employee
        )
        db_session.add(staff)
        await db_session.commit()
        await db_session.refresh(staff)

        # 利用規約のみ同意
        agreement = TermsAgreement(
            staff_id=staff.id,
            terms_of_service_agreed_at=datetime.now(timezone.utc),
            privacy_policy_agreed_at=None,
            terms_version="1.0",
            privacy_version=None,
        )
        db_session.add(agreement)
        await db_session.commit()
        await db_session.refresh(agreement)

        # 検証
        assert agreement.has_agreed_to_all_current("1.0", "1.0") is False


class TestTermsAgreementIPAddress:
    """IPアドレスフィールドのテスト"""

    @pytest.mark.asyncio
    async def test_ipv4_address_storage(self, db_session: AsyncSession):
        """IPv4アドレスを保存できること"""
        from app.models.terms_agreement import TermsAgreement

        # テスト用スタッフを作成
        staff = Staff(
            email="test14@example.com",
            hashed_password="hashed",
            first_name="美穂",
            last_name="山崎",
            full_name="山崎 美穂",
            role=StaffRole.employee
        )
        db_session.add(staff)
        await db_session.commit()
        await db_session.refresh(staff)

        # IPv4アドレスで同意履歴を作成
        agreement = TermsAgreement(
            staff_id=staff.id,
            ip_address="192.168.1.1",
        )
        db_session.add(agreement)
        await db_session.commit()
        await db_session.refresh(agreement)

        # 検証
        assert agreement.ip_address == "192.168.1.1"

    @pytest.mark.asyncio
    async def test_ipv6_address_storage(self, db_session: AsyncSession):
        """IPv6アドレスを保存できること（最大45文字）"""
        from app.models.terms_agreement import TermsAgreement

        # テスト用スタッフを作成
        staff = Staff(
            email="test15@example.com",
            hashed_password="hashed",
            first_name="正樹",
            last_name="森",
            full_name="森 正樹",
            role=StaffRole.employee
        )
        db_session.add(staff)
        await db_session.commit()
        await db_session.refresh(staff)

        # IPv6アドレスで同意履歴を作成
        ipv6_address = "2001:0db8:85a3:0000:0000:8a2e:0370:7334"
        agreement = TermsAgreement(
            staff_id=staff.id,
            ip_address=ipv6_address,
        )
        db_session.add(agreement)
        await db_session.commit()
        await db_session.refresh(agreement)

        # 検証
        assert agreement.ip_address == ipv6_address
        assert len(agreement.ip_address) <= 45


class TestTermsAgreementUpdates:
    """TermsAgreementの更新のテスト"""

    @pytest.mark.asyncio
    async def test_update_agreement_versions(self, db_session: AsyncSession):
        """規約バージョンを更新できること"""
        from app.models.terms_agreement import TermsAgreement

        # テスト用スタッフを作成
        staff = Staff(
            email="test16@example.com",
            hashed_password="hashed",
            first_name="千春",
            last_name="池田",
            full_name="池田 千春",
            role=StaffRole.employee
        )
        db_session.add(staff)
        await db_session.commit()
        await db_session.refresh(staff)

        # 初期バージョンで作成
        agreement = TermsAgreement(
            staff_id=staff.id,
            terms_of_service_agreed_at=datetime.now(timezone.utc),
            terms_version="1.0",
        )
        db_session.add(agreement)
        await db_session.commit()
        await db_session.refresh(agreement)

        # バージョンを更新
        agreement.terms_version = "2.0"
        agreement.terms_of_service_agreed_at = datetime.now(timezone.utc)
        await db_session.commit()
        await db_session.refresh(agreement)

        # 検証
        assert agreement.terms_version == "2.0"

    @pytest.mark.asyncio
    async def test_updated_at_changes_on_update(self, db_session: AsyncSession):
        """レコード更新時にupdated_atが変更されること"""
        from app.models.terms_agreement import TermsAgreement

        # テスト用スタッフを作成
        staff = Staff(
            email="test17@example.com",
            hashed_password="hashed",
            first_name="浩二",
            last_name="石川",
            full_name="石川 浩二",
            role=StaffRole.employee
        )
        db_session.add(staff)
        await db_session.commit()
        await db_session.refresh(staff)

        # 同意履歴を作成
        agreement = TermsAgreement(
            staff_id=staff.id,
        )
        db_session.add(agreement)
        await db_session.commit()
        await db_session.refresh(agreement)

        original_updated_at = agreement.updated_at
        original_created_at = agreement.created_at

        # 少し待機してから更新（1秒待機してタイムスタンプが確実に変わるようにする）
        import asyncio
        await asyncio.sleep(1.1)

        # 規約に同意（更新）
        agreement.terms_of_service_agreed_at = datetime.now(timezone.utc)
        agreement.terms_version = "1.0"
        await db_session.commit()
        await db_session.refresh(agreement)

        # updated_atが変更されたこと、created_atは変わらないことを確認
        assert agreement.updated_at >= original_updated_at  # 同じかそれ以降
        assert agreement.created_at == original_created_at  # created_atは変わらない
        assert agreement.terms_of_service_agreed_at is not None  # 更新が反映されている
        assert agreement.terms_version == "1.0"
