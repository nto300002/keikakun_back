import pytest
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models.staff import Staff
from app.models.mfa import MFABackupCode
from app.models.enums import StaffRole
from app.core.security import generate_totp_secret, hash_recovery_code


class TestStaffMFAFields:
    """StaffモデルのMFA関連フィールドのテスト"""
    
    @pytest.mark.asyncio
    async def test_staff_mfa_fields_default_values(self, db_session: AsyncSession):
        """StaffのMFA関連フィールドのデフォルト値テスト"""
        staff = Staff(
            email="test@example.com",
            hashed_password="hashed_password",
            name="Test User",
            role=StaffRole.employee
        )
        db_session.add(staff)
        await db_session.commit()
        await db_session.refresh(staff)
        
        # デフォルト値の確認
        assert staff.is_mfa_enabled is False
        assert staff.mfa_secret is None
        assert staff.mfa_backup_codes_used is None or staff.mfa_backup_codes_used == 0
        
    @pytest.mark.asyncio
    async def test_staff_mfa_fields_set_values(self, db_session: AsyncSession):
        """StaffのMFA関連フィールドの値設定テスト"""
        staff = Staff(
            email="test@example.com",
            hashed_password="hashed_password",
            name="Test User",
            role=StaffRole.employee,
            is_mfa_enabled=True,
            mfa_secret="TESTSECRET123456789012345",
            mfa_backup_codes_used=3
        )
        db_session.add(staff)
        await db_session.commit()
        await db_session.refresh(staff)
        
        assert staff.is_mfa_enabled is True
        assert staff.mfa_secret == "TESTSECRET123456789012345"
        assert staff.mfa_backup_codes_used == 3
        
    @pytest.mark.asyncio
    async def test_staff_mfa_secret_encryption(self, db_session: AsyncSession):
        """MFAシークレットの暗号化テスト（実装によって調整が必要）"""
        # 実際の実装では、MFAシークレットは暗号化されて保存される想定
        staff = Staff(
            email="test@example.com",
            hashed_password="hashed_password",
            name="Test User",
            role=StaffRole.employee
        )
        
        original_secret = generate_totp_secret()
        staff.set_mfa_secret(original_secret)  # 暗号化して保存
        
        db_session.add(staff)
        await db_session.commit()
        await db_session.refresh(staff)
        
        # 暗号化されているため、元の値と異なる
        assert staff.mfa_secret != original_secret
        
        # 復号して元の値と一致することを確認
        decrypted_secret = staff.get_mfa_secret()
        assert decrypted_secret == original_secret


class TestMFABackupCodeModel:
    """MFABackupCodeモデルのテスト"""
    
    @pytest.mark.asyncio
    async def test_create_backup_code(self, db_session: AsyncSession, employee_user_factory):
        """MFABackupCode作成のテスト"""
        staff = await employee_user_factory()
        
        backup_code = MFABackupCode(
            staff_id=staff.id,
            code_hash=hash_recovery_code("TEST-CODE-1234-ABCD"),
            is_used=False
        )
        db_session.add(backup_code)
        await db_session.commit()
        await db_session.refresh(backup_code)
        
        assert backup_code.id is not None
        assert backup_code.staff_id == staff.id
        assert backup_code.is_used is False
        assert backup_code.used_at is None
        assert backup_code.created_at is not None
        
    @pytest.mark.asyncio
    async def test_backup_code_unique_constraint(self, db_session: AsyncSession, employee_user_factory):
        """MFABackupCodeの一意制約テスト"""
        staff = await employee_user_factory()
        
        code_hash = hash_recovery_code("TEST-CODE-1234-ABCD")
        
        # 同じハッシュのバックアップコードを2つ作成
        backup_code1 = MFABackupCode(
            staff_id=staff.id,
            code_hash=code_hash,
            is_used=False
        )
        backup_code2 = MFABackupCode(
            staff_id=staff.id,
            code_hash=code_hash,
            is_used=False
        )
        
        db_session.add(backup_code1)
        await db_session.commit()
        
        # 同じハッシュの2つ目を追加しようとすると制約違反
        db_session.add(backup_code2)
        with pytest.raises(IntegrityError):
            await db_session.commit()
            
    @pytest.mark.asyncio
    async def test_backup_code_foreign_key_constraint(self, db_session: AsyncSession):
        """MFABackupCodeの外部キー制約テスト"""
        # 存在しないstaff_idを指定
        fake_staff_id = uuid.uuid4()
        
        backup_code = MFABackupCode(
            staff_id=fake_staff_id,
            code_hash=hash_recovery_code("TEST-CODE-1234-ABCD"),
            is_used=False
        )
        
        db_session.add(backup_code)
        with pytest.raises(IntegrityError):
            await db_session.commit()
            
    @pytest.mark.asyncio
    async def test_backup_code_mark_as_used(self, db_session: AsyncSession, employee_user_factory):
        """MFABackupCodeの使用済みマークテスト"""
        staff = await employee_user_factory()
        
        backup_code = MFABackupCode(
            staff_id=staff.id,
            code_hash=hash_recovery_code("TEST-CODE-1234-ABCD"),
            is_used=False
        )
        db_session.add(backup_code)
        await db_session.commit()
        
        # 使用済みにマーク
        backup_code.mark_as_used()
        await db_session.commit()
        await db_session.refresh(backup_code)
        
        assert backup_code.is_used is True
        assert backup_code.used_at is not None
        assert isinstance(backup_code.used_at, datetime)
        
    @pytest.mark.asyncio
    async def test_backup_code_staff_relationship(self, db_session: AsyncSession, employee_user_factory):
        """MFABackupCodeとStaffの関係テスト"""
        staff = await employee_user_factory()
        
        backup_code = MFABackupCode(
            staff_id=staff.id,
            code_hash=hash_recovery_code("TEST-CODE-1234-ABCD"),
            is_used=False
        )
        db_session.add(backup_code)
        await db_session.commit()
        
        # Eagerロードしてrelationshipを確認
        await db_session.refresh(backup_code, ["staff"])
        
        assert backup_code.staff is not None
        assert backup_code.staff.id == staff.id
        assert backup_code.staff.email == staff.email


class TestMFAModelMethods:
    """MFAモデルのメソッドのテスト"""
    
    @pytest.mark.asyncio
    async def test_staff_enable_mfa(self, db_session: AsyncSession, employee_user_factory):
        """Staff.enable_mfaメソッドのテスト"""
        staff = await employee_user_factory(is_mfa_enabled=False)
        
        secret = generate_totp_secret()
        recovery_codes = ["CODE1-2345-6789-ABCD", "CODE2-3456-789A-BCDE"]
        
        await staff.enable_mfa(db_session, secret, recovery_codes)
        await db_session.commit()
        await db_session.refresh(staff)
        
        assert staff.is_mfa_enabled is True
        assert staff.get_mfa_secret() == secret
        
        # バックアップコードが作成されていることを確認
        backup_codes = await staff.get_backup_codes(db_session)
        assert len(backup_codes) == 2
        assert all(not code.is_used for code in backup_codes)
        
    @pytest.mark.asyncio
    async def test_staff_disable_mfa(self, db_session: AsyncSession, employee_user_factory):
        """Staff.disable_mfaメソッドのテスト"""
        staff = await employee_user_factory(is_mfa_enabled=True)
        staff.set_mfa_secret(generate_totp_secret())
        await db_session.commit()
        
        # バックアップコードも作成
        backup_codes = ["CODE1-2345-6789-ABCD", "CODE2-3456-789A-BCDE"]
        for code in backup_codes:
            backup_code = MFABackupCode(
                staff_id=staff.id,
                code_hash=hash_recovery_code(code),
                is_used=False
            )
            db_session.add(backup_code)
        await db_session.commit()
        
        # リレーションをロードするためにリフレッシュ
        await db_session.refresh(staff, ["mfa_backup_codes"])
        
        await staff.disable_mfa(db_session)
        await db_session.commit()
        await db_session.refresh(staff)
        
        assert staff.is_mfa_enabled is False
        assert staff.mfa_secret is None
        
        # バックアップコードも削除されていることを確認
        backup_codes = await staff.get_backup_codes(db_session)
        assert len(backup_codes) == 0
        
    @pytest.mark.asyncio
    async def test_staff_get_unused_backup_codes(self, db_session: AsyncSession, employee_user_factory):
        """Staff.get_unused_backup_codesメソッドのテスト"""
        staff = await employee_user_factory()
        
        # 使用済みと未使用のバックアップコードを作成
        used_code = MFABackupCode(
            staff_id=staff.id,
            code_hash=hash_recovery_code("USED-CODE-1234-ABCD"),
            is_used=True,
            used_at=datetime.now(timezone.utc)
        )
        unused_code1 = MFABackupCode(
            staff_id=staff.id,
            code_hash=hash_recovery_code("UNUSED-CODE1-234-ABCD"),
            is_used=False
        )
        unused_code2 = MFABackupCode(
            staff_id=staff.id,
            code_hash=hash_recovery_code("UNUSED-CODE2-234-ABCD"),
            is_used=False
        )
        
        db_session.add_all([used_code, unused_code1, unused_code2])
        await db_session.commit()
        
        unused_codes = await staff.get_unused_backup_codes(db_session)
        
        assert len(unused_codes) == 2
        assert all(not code.is_used for code in unused_codes)
        
    @pytest.mark.asyncio
    async def test_staff_has_backup_codes_remaining(self, db_session: AsyncSession, employee_user_factory):
        """Staff.has_backup_codes_remainingメソッドのテスト"""
        staff = await employee_user_factory()
        
        # 最初は残りコードなし
        has_remaining = await staff.has_backup_codes_remaining(db_session)
        assert has_remaining is False
        
        # 未使用コードを追加
        unused_code = MFABackupCode(
            staff_id=staff.id,
            code_hash=hash_recovery_code("UNUSED-CODE-1234-ABCD"),
            is_used=False
        )
        db_session.add(unused_code)
        await db_session.commit()
        
        # 残りコードあり
        has_remaining = await staff.has_backup_codes_remaining(db_session)
        assert has_remaining is True