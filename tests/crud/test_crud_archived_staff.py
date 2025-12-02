"""
archived_staff CRUD のユニットテスト（TDD - RED phase）

モデル・CRUD実装前にテストを先に作成する。
要件定義書に基づき、以下の機能をテストする：
- Staffレコードからアーカイブ作成
- 個人情報の匿名化
- 法定保存期限の計算
- 期限切れアーカイブの取得・削除
"""
import pytest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

# テスト対象（まだ存在しない）
from app.crud.crud_archived_staff import archived_staff
from app.models.archived_staff import ArchivedStaff
from app.models.staff import Staff
from app.models.office import Office, OfficeStaff
from app.models.enums import StaffRole

# pytestを非同期で実行するためのマーク
pytestmark = pytest.mark.asyncio


class TestCRUDArchivedStaff:
    """アーカイブCRUDのテスト"""

    async def test_create_from_staff_basic(self, db_session):
        """
        基本的なStaffからアーカイブ作成のテスト

        要件:
        - Staffレコードから法定保存データを抽出
        - 個人識別情報を匿名化
        - アーカイブレコードを作成
        """
        # 1. Setup: テスト用のStaffを作成
        test_staff = Staff(
            id=uuid4(),
            email="test@example.com",
            hashed_password="hashed_password",
            full_name="山田 太郎",
            role=StaffRole.employee,
            is_email_verified=True,
            is_mfa_enabled=False,
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            is_test_data=True
        )
        db_session.add(test_staff)
        await db_session.flush()

        # 2. Execute: アーカイブ作成
        archive = await archived_staff.create_from_staff(
            db=db_session,
            staff=test_staff,
            reason="staff_deletion",
            deleted_by=uuid4()
        )

        # 3. Assert: アーカイブが正しく作成されている
        assert archive is not None
        assert archive.id is not None
        assert archive.original_staff_id == test_staff.id
        assert archive.role == StaffRole.employee.value
        assert archive.hired_at == test_staff.created_at
        assert archive.archive_reason == "staff_deletion"
        assert archive.is_test_data is True

        # 法定保存期限が正しく計算されている（退職日 + 5年）
        assert archive.legal_retention_until is not None
        # relativedelta を使っているので、うるう年を正しく計算
        from dateutil.relativedelta import relativedelta
        expected_retention = archive.terminated_at + relativedelta(years=5)
        # 誤差を許容（1秒以内）
        assert abs((archive.legal_retention_until - expected_retention).total_seconds()) < 1

    async def test_anonymization(self, db_session):
        """
        個人情報の匿名化テスト

        要件:
        - 氏名が匿名化される（例: "スタッフ-ABC123DEF"）
        - メールアドレスが匿名化される（例: "archived-ABC123DEF@deleted.local"）
        - 元のメール・氏名は保存されない
        """
        # 1. Setup
        test_staff = Staff(
            id=uuid4(),
            email="john.doe@example.com",
            hashed_password="hashed",
            full_name="田中 花子",
            role=StaffRole.manager,
            created_at=datetime(2023, 6, 15, tzinfo=timezone.utc),
            is_test_data=True
        )
        db_session.add(test_staff)
        await db_session.flush()

        # 2. Execute
        archive = await archived_staff.create_from_staff(
            db=db_session,
            staff=test_staff,
            reason="staff_withdrawal",
            deleted_by=uuid4()
        )

        # 3. Assert: 匿名化されている
        # 氏名が "スタッフ-" で始まる
        assert archive.anonymized_full_name.startswith("スタッフ-")
        assert "田中" not in archive.anonymized_full_name
        assert "花子" not in archive.anonymized_full_name

        # メールアドレスが匿名化されている
        assert archive.anonymized_email.startswith("archived-")
        assert archive.anonymized_email.endswith("@deleted.local")
        assert "john.doe" not in archive.anonymized_email
        assert "example.com" not in archive.anonymized_email

        # 匿名化IDが9文字の英数字（SHA-256の先頭9文字）
        anon_id = archive.anonymized_full_name.replace("スタッフ-", "")
        assert len(anon_id) == 9
        assert anon_id.isalnum()
        assert anon_id.isupper()

    async def test_create_from_staff_with_office(self, db_session):
        """
        事務所情報を含むアーカイブ作成テスト

        要件:
        - 所属事務所IDとスナップショットが保存される
        - プライマリ事務所が優先される
        """
        # 1. Setup: スタッフを先に作成（Officeの created_by として必要）
        test_staff = Staff(
            id=uuid4(),
            email="staff@example.com",
            hashed_password="hashed",
            full_name="佐藤 次郎",
            role=StaffRole.owner,
            created_at=datetime(2022, 3, 1, tzinfo=timezone.utc),
            is_test_data=True
        )
        db_session.add(test_staff)
        await db_session.flush()  # Staffを先にflush

        # 事務所を作成（test_staffをcreated_byとして使用）
        test_office = Office(
            id=uuid4(),
            name="テスト事務所",
            type="type_A_office",
            created_by=test_staff.id,
            last_modified_by=test_staff.id,
            is_test_data=True
        )
        db_session.add(test_office)

        # 事務所-スタッフの関連付け
        office_staff = OfficeStaff(
            staff_id=test_staff.id,
            office_id=test_office.id,
            is_primary=True,
            is_test_data=True
        )
        db_session.add(office_staff)
        await db_session.flush()

        # リレーションシップを明示的にロード
        await db_session.refresh(test_staff, ["office_associations"])
        for assoc in test_staff.office_associations:
            await db_session.refresh(assoc, ["office"])

        # 2. Execute
        archive = await archived_staff.create_from_staff(
            db=db_session,
            staff=test_staff,
            reason="office_withdrawal",
            deleted_by=uuid4()
        )

        # 3. Assert: 事務所情報が保存されている
        assert archive.office_id == test_office.id
        assert archive.office_name == "テスト事務所"

    async def test_retention_calculation(self):
        """
        法定保存期限の計算テスト

        要件:
        - 退職日 + 5年が正しく計算される
        - デフォルトは5年
        """
        # 1. Setup
        terminated_at = datetime(2024, 12, 31, tzinfo=timezone.utc)

        # 2. Execute
        retention_until = ArchivedStaff.calculate_retention_until(terminated_at, years=5)

        # 3. Assert
        expected = datetime(2029, 12, 31, tzinfo=timezone.utc)
        assert retention_until == expected

    async def test_is_retention_expired(self, db_session):
        """
        保存期限切れチェックのテスト

        要件:
        - 現在日時が legal_retention_until を過ぎている場合 True
        """
        # 1. Setup: 期限切れのアーカイブ
        past_date = datetime.now(timezone.utc) - timedelta(days=1)

        expired_archive = ArchivedStaff(
            original_staff_id=uuid4(),
            anonymized_full_name="スタッフ-TEST00001",
            anonymized_email="archived-TEST00001@deleted.local",
            role=StaffRole.employee.value,
            hired_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
            terminated_at=datetime(2020, 12, 31, tzinfo=timezone.utc),
            archive_reason="staff_deletion",
            legal_retention_until=past_date,
            is_test_data=True
        )
        db_session.add(expired_archive)
        await db_session.flush()

        # 2. Execute & Assert
        assert expired_archive.is_retention_expired() is True

        # 3. Setup: 有効期限内のアーカイブ
        future_date = datetime.now(timezone.utc) + timedelta(days=365 * 3)

        valid_archive = ArchivedStaff(
            original_staff_id=uuid4(),
            anonymized_full_name="スタッフ-TEST00002",
            anonymized_email="archived-TEST00002@deleted.local",
            role=StaffRole.manager.value,
            hired_at=datetime(2023, 1, 1, tzinfo=timezone.utc),
            terminated_at=datetime(2023, 12, 31, tzinfo=timezone.utc),
            archive_reason="staff_withdrawal",
            legal_retention_until=future_date,
            is_test_data=True
        )
        db_session.add(valid_archive)
        await db_session.flush()

        # 4. Execute & Assert
        assert valid_archive.is_retention_expired() is False

    async def test_get_by_original_staff_id(self, db_session):
        """
        元のスタッフIDでアーカイブを取得するテスト

        要件:
        - original_staff_id で検索できる
        """
        # 1. Setup
        staff_id = uuid4()
        test_archive = ArchivedStaff(
            original_staff_id=staff_id,
            anonymized_full_name="スタッフ-FINDME123",
            anonymized_email="archived-FINDME123@deleted.local",
            role=StaffRole.employee.value,
            hired_at=datetime(2021, 4, 1, tzinfo=timezone.utc),
            terminated_at=datetime(2024, 3, 31, tzinfo=timezone.utc),
            archive_reason="staff_deletion",
            legal_retention_until=datetime(2029, 3, 31, tzinfo=timezone.utc),
            is_test_data=True
        )
        db_session.add(test_archive)
        await db_session.commit()

        # 2. Execute
        found = await archived_staff.get_by_original_staff_id(
            db=db_session,
            staff_id=staff_id
        )

        # 3. Assert
        assert found is not None
        assert found.original_staff_id == staff_id
        assert found.anonymized_full_name == "スタッフ-FINDME123"

    async def test_get_expired_archives(self, db_session):
        """
        期限切れアーカイブの取得テスト

        要件:
        - legal_retention_until が現在日時を過ぎているレコードを取得
        - テストデータは除外可能
        """
        # 1. Setup: 期限切れアーカイブ（本番データ）
        past_date = datetime.now(timezone.utc) - timedelta(days=10)
        expired1 = ArchivedStaff(
            original_staff_id=uuid4(),
            anonymized_full_name="スタッフ-EXP00001",
            anonymized_email="archived-EXP00001@deleted.local",
            role=StaffRole.employee.value,
            hired_at=datetime(2015, 1, 1, tzinfo=timezone.utc),
            terminated_at=datetime(2019, 12, 31, tzinfo=timezone.utc),
            archive_reason="staff_deletion",
            legal_retention_until=past_date,
            is_test_data=False  # 本番データ
        )
        db_session.add(expired1)

        # 期限切れアーカイブ（テストデータ）
        expired2 = ArchivedStaff(
            original_staff_id=uuid4(),
            anonymized_full_name="スタッフ-EXP00002",
            anonymized_email="archived-EXP00002@deleted.local",
            role=StaffRole.manager.value,
            hired_at=datetime(2016, 1, 1, tzinfo=timezone.utc),
            terminated_at=datetime(2020, 12, 31, tzinfo=timezone.utc),
            archive_reason="office_withdrawal",
            legal_retention_until=past_date,
            is_test_data=True  # テストデータ
        )
        db_session.add(expired2)

        # 有効期限内のアーカイブ
        future_date = datetime.now(timezone.utc) + timedelta(days=365 * 2)
        valid = ArchivedStaff(
            original_staff_id=uuid4(),
            anonymized_full_name="スタッフ-VALID001",
            anonymized_email="archived-VALID001@deleted.local",
            role=StaffRole.owner.value,
            hired_at=datetime(2023, 1, 1, tzinfo=timezone.utc),
            terminated_at=datetime(2024, 12, 31, tzinfo=timezone.utc),
            archive_reason="staff_withdrawal",
            legal_retention_until=future_date,
            is_test_data=False
        )
        db_session.add(valid)
        await db_session.commit()

        # 2. Execute: テストデータを除外
        expired_list = await archived_staff.get_expired_archives(
            db=db_session,
            exclude_test_data=True
        )

        # 3. Assert: 本番データの期限切れのみ
        assert len(expired_list) == 1
        assert expired_list[0].anonymized_full_name == "スタッフ-EXP00001"

        # 4. Execute: テストデータも含む
        all_expired = await archived_staff.get_expired_archives(
            db=db_session,
            exclude_test_data=False
        )

        # 5. Assert: 期限切れが2件
        assert len(all_expired) == 2

    async def test_delete_expired_archives(self, db_session):
        """
        期限切れアーカイブの削除テスト

        要件:
        - 期限切れのアーカイブを削除
        - 削除件数を返す
        - テストデータは除外可能
        """
        # 1. Setup: 期限切れアーカイブを3件作成
        past_date = datetime.now(timezone.utc) - timedelta(days=5)

        for i in range(3):
            archive = ArchivedStaff(
                original_staff_id=uuid4(),
                anonymized_full_name=f"スタッフ-DEL{i:05d}",
                anonymized_email=f"archived-DEL{i:05d}@deleted.local",
                role=StaffRole.employee.value,
                hired_at=datetime(2015, 1, 1, tzinfo=timezone.utc),
                terminated_at=datetime(2019, 12, 31, tzinfo=timezone.utc),
                archive_reason="staff_deletion",
                legal_retention_until=past_date,
                is_test_data=False
            )
            db_session.add(archive)
        await db_session.commit()

        # 2. Execute
        deleted_count = await archived_staff.delete_expired_archives(
            db=db_session,
            exclude_test_data=True
        )

        # 3. Assert
        assert deleted_count == 3

        # 4. Verify: 削除されたことを確認
        remaining = await archived_staff.get_expired_archives(
            db=db_session,
            exclude_test_data=True
        )
        assert len(remaining) == 0

    async def test_metadata_stored(self, db_session):
        """
        メタデータの保存テスト

        要件:
        - deleted_by, email_domain, mfa_enabled などのメタデータが保存される
        - JSONB形式で保存される
        """
        # 1. Setup
        deleter_id = uuid4()
        test_staff = Staff(
            id=uuid4(),
            email="user@company.co.jp",
            hashed_password="hashed",
            full_name="鈴木 三郎",
            role=StaffRole.employee,
            is_email_verified=True,
            is_mfa_enabled=True,
            created_at=datetime(2023, 1, 1, tzinfo=timezone.utc),
            is_test_data=True
        )
        db_session.add(test_staff)
        await db_session.flush()

        # 2. Execute
        archive = await archived_staff.create_from_staff(
            db=db_session,
            staff=test_staff,
            reason="staff_deletion",
            deleted_by=deleter_id
        )

        # 3. Assert: メタデータが保存されている
        assert archive.metadata_ is not None
        assert "deleted_by_staff_id" in archive.metadata_
        assert archive.metadata_["deleted_by_staff_id"] == str(deleter_id)
        assert archive.metadata_["original_email_domain"] == "company.co.jp"
        assert archive.metadata_["mfa_was_enabled"] is True
        assert archive.metadata_["is_email_verified"] is True
