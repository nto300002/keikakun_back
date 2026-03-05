"""
mfa.py (services) の TDD テスト

2-B: API層のcommit違反修正
- 7メソッドがDBにcommitを行うことを確認
"""
import pytest
from uuid import uuid4
from unittest.mock import patch
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.staff import Staff
from app.models.enums import StaffRole
from app.core.security import get_password_hash, generate_totp_secret, generate_recovery_codes
from app.services.mfa import MfaService

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


async def _create_staff(db: AsyncSession, *, is_mfa_enabled: bool = False, set_secret: bool = False) -> Staff:
    """テスト用スタッフを作成してcommitする"""
    staff = Staff(
        first_name="テスト",
        last_name="スタッフ",
        full_name="スタッフ テスト",
        email=f"mfa_{uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash("Password123!"),
        role=StaffRole.employee,
        is_mfa_enabled=is_mfa_enabled,
    )
    if set_secret:
        staff.set_mfa_secret(generate_totp_secret())
    db.add(staff)
    await db.commit()
    return staff


# ===========================
# 2-B-1/2: enroll_mfa
# ===========================

@pytest.mark.asyncio
async def test_enroll_mfa_commits(db: AsyncSession):
    """【2-B-1/2】enroll_mfa: MFAシークレットをDBにコミットすること"""
    staff = await _create_staff(db)
    assert staff.mfa_secret is None

    result = await MfaService(db).enroll_mfa(user=staff)

    assert "secret_key" in result
    assert "qr_code_uri" in result

    # DBにcommitされていること
    refreshed = (await db.execute(select(Staff).where(Staff.id == staff.id))).scalar_one()
    assert refreshed.mfa_secret is not None
    assert refreshed.is_mfa_enabled is False  # enroll時点ではまだ無効


# ===========================
# 2-B-3/4: verify_mfa
# ===========================

@pytest.mark.asyncio
async def test_verify_mfa_commits(db: AsyncSession):
    """【2-B-3/4】verify_mfa: MFA有効化フラグをDBにコミットすること"""
    staff = await _create_staff(db, set_secret=True)
    assert staff.is_mfa_enabled is False
    assert staff.is_mfa_verified_by_user is False

    with patch("app.services.mfa.verify_totp", return_value=True):
        result = await MfaService(db).verify_mfa(user=staff, totp_code="000000")

    assert result is True

    # DBにcommitされていること
    refreshed = (await db.execute(select(Staff).where(Staff.id == staff.id))).scalar_one()
    assert refreshed.is_mfa_enabled is True
    assert refreshed.is_mfa_verified_by_user is True


# ===========================
# 2-B-5/6: disable_mfa
# ===========================

@pytest.mark.asyncio
async def test_disable_mfa_commits(db: AsyncSession):
    """【2-B-5/6】disable_mfa: MFA無効化をDBにコミットすること"""
    staff = await _create_staff(db, is_mfa_enabled=True, set_secret=True)
    assert staff.is_mfa_enabled is True
    assert staff.mfa_secret is not None

    await MfaService(db).disable_mfa(user=staff)

    # DBにcommitされていること
    refreshed = (await db.execute(select(Staff).where(Staff.id == staff.id))).scalar_one()
    assert refreshed.is_mfa_enabled is False
    assert refreshed.mfa_secret is None


# ===========================
# 2-B-7/8: admin_enable_staff_mfa
# ===========================

@pytest.mark.asyncio
async def test_admin_enable_staff_mfa_commits(db: AsyncSession):
    """【2-B-7/8】admin_enable_staff_mfa: 管理者によるMFA有効化をDBにコミットすること"""
    staff = await _create_staff(db, is_mfa_enabled=False)
    secret = generate_totp_secret()
    recovery_codes = generate_recovery_codes(count=5)

    await MfaService(db).admin_enable_staff_mfa(
        target_staff=staff,
        secret=secret,
        recovery_codes=recovery_codes,
    )

    # DBにcommitされていること
    refreshed = (await db.execute(select(Staff).where(Staff.id == staff.id))).scalar_one()
    assert refreshed.is_mfa_enabled is True
    assert refreshed.is_mfa_verified_by_user is False  # 管理者有効化 → ユーザー検証は未完了
    assert refreshed.mfa_secret is not None


# ===========================
# 2-B-9/10: admin_disable_staff_mfa
# ===========================

@pytest.mark.asyncio
async def test_admin_disable_staff_mfa_commits(db: AsyncSession):
    """【2-B-9/10】admin_disable_staff_mfa: 管理者によるMFA無効化をDBにコミットすること"""
    staff = await _create_staff(db, is_mfa_enabled=True, set_secret=True)
    assert staff.is_mfa_enabled is True

    await MfaService(db).admin_disable_staff_mfa(target_staff=staff)

    # DBにcommitされていること
    refreshed = (await db.execute(select(Staff).where(Staff.id == staff.id))).scalar_one()
    assert refreshed.is_mfa_enabled is False
    assert refreshed.mfa_secret is None


# ===========================
# 2-B-11/12: disable_all_office_mfa
# ===========================

@pytest.mark.asyncio
async def test_disable_all_office_mfa_commits(db: AsyncSession):
    """【2-B-11/12】disable_all_office_mfa: 全スタッフのMFA一括無効化をDBにコミットすること"""
    staff1 = await _create_staff(db, is_mfa_enabled=True, set_secret=True)
    staff2 = await _create_staff(db, is_mfa_enabled=True, set_secret=True)

    disabled_count = await MfaService(db).disable_all_office_mfa(all_staffs=[staff1, staff2])

    assert disabled_count == 2

    # DBにcommitされていること（両スタッフとも無効化）
    r1 = (await db.execute(select(Staff).where(Staff.id == staff1.id))).scalar_one()
    r2 = (await db.execute(select(Staff).where(Staff.id == staff2.id))).scalar_one()
    assert r1.is_mfa_enabled is False
    assert r2.is_mfa_enabled is False


# ===========================
# 2-B-13/14: enable_all_office_mfa
# ===========================

@pytest.mark.asyncio
async def test_enable_all_office_mfa_commits(db: AsyncSession):
    """【2-B-13/14】enable_all_office_mfa: 全スタッフのMFA一括有効化をDBにコミットすること"""
    staff1 = await _create_staff(db, is_mfa_enabled=False)
    staff2 = await _create_staff(db, is_mfa_enabled=False)

    enabled_count, staff_mfa_data = await MfaService(db).enable_all_office_mfa(
        all_staffs=[staff1, staff2]
    )

    assert enabled_count == 2
    assert len(staff_mfa_data) == 2

    # DBにcommitされていること（両スタッフとも有効化）
    r1 = (await db.execute(select(Staff).where(Staff.id == staff1.id))).scalar_one()
    r2 = (await db.execute(select(Staff).where(Staff.id == staff2.id))).scalar_one()
    assert r1.is_mfa_enabled is True
    assert r2.is_mfa_enabled is True
    assert r1.is_mfa_verified_by_user is False
    assert r2.is_mfa_verified_by_user is False
