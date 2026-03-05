"""
auth_service.py の TDD テスト

2-A: API層のcommit違反修正
- 7メソッドがDBにcommitを行うことを確認
"""
import pytest
from uuid import UUID, uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from unittest.mock import patch, AsyncMock

from app.db.session import AsyncSessionLocal
from app.models.staff import Staff
from app.models.enums import StaffRole
from app.core.security import get_password_hash
from app.services.auth_service import auth_service

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="function")
async def db() -> AsyncSession:
    """テスト用の非同期DBセッション"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            try:
                await session.rollback()
            except Exception:
                pass


@pytest.fixture(scope="function")
async def existing_staff(db: AsyncSession):
    """テスト用スタッフ（既存データとして使用）"""
    staff = Staff(
        first_name="テスト",
        last_name="スタッフ",
        full_name="スタッフ テスト",
        email=f"existing_{uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash("Password123!"),
        role=StaffRole.employee,
    )
    db.add(staff)
    await db.commit()
    return staff


# ===========================
# 2-A-1: register_admin
# ===========================

@pytest.mark.asyncio
async def test_register_admin_commits(db: AsyncSession):
    """【2-A-1/2】register_admin: 管理者スタッフをDBにコミットすること"""
    from app.schemas.staff import AdminCreate

    email = f"admin_{uuid4().hex[:8]}@example.com"
    staff_in = AdminCreate(
        email=email,
        password="Password123!",
        first_name="テスト",
        last_name="管理者",
    )

    user = await auth_service.register_admin(db=db, staff_in=staff_in)

    # DBにcommitされていること
    result = await db.execute(select(Staff).where(Staff.email == email))
    saved = result.scalar_one_or_none()
    assert saved is not None
    assert user.email == email


# ===========================
# 2-A-3: register_staff
# ===========================

@pytest.mark.asyncio
async def test_register_staff_commits(db: AsyncSession):
    """【2-A-3/4】register_staff: 一般スタッフをDBにコミットすること"""
    from app.schemas.staff import StaffCreate

    email = f"staff_{uuid4().hex[:8]}@example.com"
    staff_in = StaffCreate(
        email=email,
        password="Password123!",
        first_name="テスト",
        last_name="スタッフ",
        role=StaffRole.employee,
    )

    user = await auth_service.register_staff(db=db, staff_in=staff_in)

    # DBにcommitされていること
    result = await db.execute(select(Staff).where(Staff.email == email))
    saved = result.scalar_one_or_none()
    assert saved is not None
    assert user.email == email


# ===========================
# 2-A-5: verify_email
# ===========================

@pytest.mark.asyncio
async def test_verify_email_commits(db: AsyncSession, existing_staff: Staff):
    """【2-A-5/6】verify_email: is_email_verifiedをTrueにコミットすること"""
    assert existing_staff.is_email_verified is False

    await auth_service.verify_email(db=db, user=existing_staff)

    # DBにcommitされていること
    result = await db.execute(
        select(Staff).where(Staff.id == existing_staff.id)
    )
    refreshed = result.scalar_one()
    assert refreshed.is_email_verified is True


# ===========================
# 2-A-7: use_recovery_code
# ===========================

@pytest.mark.asyncio
async def test_use_recovery_code_marks_as_used(db: AsyncSession, existing_staff: Staff):
    """【2-A-7/8】use_recovery_code: リカバリーコードを使用済みとしてコミットすること"""
    from app.models.mfa import MFABackupCode
    from app.core.security import hash_recovery_code

    # テスト用リカバリーコードを作成（4-4-4-4 形式）
    plaintext_code = "ABCD-1234-EFGH-5678"
    backup_code = MFABackupCode(
        staff_id=existing_staff.id,
        code_hash=hash_recovery_code(plaintext_code),
        is_used=False,
    )
    db.add(backup_code)
    await db.commit()
    backup_code_id = backup_code.id

    result = await auth_service.use_recovery_code(
        db=db,
        user_id=existing_staff.id,
        recovery_code=plaintext_code,
    )

    assert result is True

    # DBにcommitされていること（is_used=True）
    refreshed = await db.execute(
        select(MFABackupCode).where(MFABackupCode.id == backup_code_id)
    )
    refreshed_code = refreshed.scalar_one()
    assert refreshed_code.is_used is True


# ===========================
# 2-A-9: set_mfa_verified_by_user
# ===========================

@pytest.mark.asyncio
async def test_set_mfa_verified_by_user_commits(db: AsyncSession, existing_staff: Staff):
    """【2-A-9/10】set_mfa_verified_by_user: is_mfa_verified_by_userをTrueにコミットすること"""
    assert existing_staff.is_mfa_verified_by_user is False

    await auth_service.set_mfa_verified_by_user(db=db, user=existing_staff)

    # DBにcommitされていること
    result = await db.execute(
        select(Staff).where(Staff.id == existing_staff.id)
    )
    refreshed = result.scalar_one()
    assert refreshed.is_mfa_verified_by_user is True


# ===========================
# 2-A-11: create_password_reset_token
# ===========================

@pytest.mark.asyncio
async def test_create_password_reset_token_commits(db: AsyncSession, existing_staff: Staff):
    """【2-A-11/12】create_password_reset_token: トークンをDBにコミットすること"""
    from app.models.staff import PasswordResetToken

    token = await auth_service.create_password_reset_token(
        db=db,
        staff_id=existing_staff.id,
        email=existing_staff.email,
        ip_address="127.0.0.1",
        user_agent="test-agent",
    )

    assert token is not None
    assert isinstance(token, str)

    # DBにcommitされていること（トークンが存在する）
    result = await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.staff_id == existing_staff.id)
    )
    saved_token = result.scalar_one_or_none()
    assert saved_token is not None


# ===========================
# 2-A-13: reset_password
# ===========================

@pytest.mark.asyncio
async def test_reset_password_commits(db: AsyncSession, existing_staff: Staff):
    """【2-A-13/14】reset_password: パスワードをDBにコミットすること"""
    from app.crud import password_reset as crud_password_reset

    original_hash = existing_staff.hashed_password
    token_str = str(uuid4())

    # パスワードリセットトークンを作成
    db_token = await crud_password_reset.create_token(
        db, staff_id=existing_staff.id, token=token_str
    )
    await db.commit()
    token_id = db_token.id

    await auth_service.reset_password(
        db=db,
        token_id=token_id,
        staff=existing_staff,
        new_password="NewPassword456@",
        email=existing_staff.email,
    )

    # DBにcommitされていること（パスワードが変更されている）
    result = await db.execute(
        select(Staff).where(Staff.id == existing_staff.id)
    )
    refreshed = result.scalar_one()
    assert refreshed.hashed_password != original_hash
