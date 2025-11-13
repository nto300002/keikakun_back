import uuid
import random
import string
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.core.security import get_password_hash
from app.models.staff import Staff
from app.models.enums import StaffRole, GenderType
from app.models.welfare_recipient import WelfareRecipient, OfficeWelfareRecipient
from datetime import date


async def create_welfare_recipient(db: AsyncSession, office_id: uuid.UUID, first_name: str = "テスト", last_name: str = "利用者") -> WelfareRecipient:
    """テスト用の利用者を作成し、指定された事業所に関連付けて返す"""
    recipient = WelfareRecipient(
        first_name=first_name,
        last_name=last_name,
        first_name_furigana="てすと",
        last_name_furigana="りようしゃ",
        birth_day=date(1980, 1, 1),
        gender=GenderType.male
    )
    db.add(recipient)
    await db.flush()

    association = OfficeWelfareRecipient(office_id=office_id, welfare_recipient_id=recipient.id)
    db.add(association)

    await db.commit()
    await db.refresh(recipient)
    return recipient


def random_email() -> str:
    """ランダムなメールアドレスを生成"""
    return f"test_{random_string(8)}@example.com"


def random_string(length: int = 10) -> str:
    """ランダムな文字列を生成"""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))


def random_password() -> str:
    """ランダムなパスワードを生成"""
    return random_string(12)


async def create_random_staff(
    db: AsyncSession,
    *,
    email: Optional[str] = None,
    name: Optional[str] = None,  # DEPRECATED: 後方互換性のため残す
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    role: Optional[StaffRole] = None,
    is_email_verified: bool = True,
    is_mfa_enabled: bool = False,
    password: Optional[str] = None,
) -> Staff:
    """テスト用のランダムなStaffを作成"""
    if email is None:
        email = random_email()

    # 後方互換性: nameが指定されている場合は分割
    if name is not None and first_name is None and last_name is None:
        parts = name.split(maxsplit=1)
        if len(parts) == 2:
            last_name, first_name = parts
        else:
            first_name = parts[0]
            last_name = "テスト"

    if first_name is None:
        first_name = "太郎"
    if last_name is None:
        # 日本語のみのバリデーションがあるため、ランダムな数字の代わりにランダムなひらがなを使用
        random_suffix = ''.join(random.choices('あいうえおかきくけこさしすせそたちつてと', k=3))
        last_name = f"テスト{random_suffix}"

    full_name = f"{last_name} {first_name}"

    if role is None:
        role = StaffRole.employee
    if password is None:
        password = random_password()

    staff = Staff(
        email=email,
        hashed_password=get_password_hash(password),
        first_name=first_name,
        last_name=last_name,
        full_name=full_name,
        role=role,
        is_email_verified=is_email_verified,
        is_mfa_enabled=is_mfa_enabled,
    )

    db.add(staff)
    # Note: commitは呼び出し元で行う
    return staff


async def create_admin_staff(
    db: AsyncSession,
    *,
    email: Optional[str] = None,
    name: Optional[str] = None,  # DEPRECATED
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    is_mfa_enabled: bool = False,
    password: Optional[str] = None,
) -> Staff:
    """テスト用のadmin Staffを作成"""
    return await create_random_staff(
        db,
        email=email,
        name=name,
        first_name=first_name,
        last_name=last_name,
        role=StaffRole.owner,
        is_mfa_enabled=is_mfa_enabled,
        password=password,
    )


async def create_manager_staff(
    db: AsyncSession,
    *,
    email: Optional[str] = None,
    name: Optional[str] = None,  # DEPRECATED
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    is_mfa_enabled: bool = False,
    password: Optional[str] = None,
) -> Staff:
    """テスト用のmanager Staffを作成"""
    return await create_random_staff(
        db,
        email=email,
        name=name,
        first_name=first_name,
        last_name=last_name,
        role=StaffRole.manager,
        is_mfa_enabled=is_mfa_enabled,
        password=password,
    )


def get_staff_password(staff: Staff) -> str:
    """テスト用スタッフの元のパスワードを取得（テストでは固定値を使用）"""
    # 実際のテストでは、作成時のパスワードを別途保存するか、
    # 固定のテストパスワードを使用する
    return "testpassword123"


class TestDataFactory:
    """テストデータ作成用のファクトリークラス"""
    
    @staticmethod
    def create_test_email() -> str:
        return random_email()
    
    @staticmethod
    def create_test_name() -> str:
        return f"Test User {random_string(5)}"
    
    @staticmethod
    def create_test_password() -> str:
        return random_password()
    
    @staticmethod
    def create_mfa_secret() -> str:
        """テスト用のMFAシークレット"""
        return "TESTSECRET123456789012345678AB"
    
    @staticmethod
    def create_recovery_code() -> str:
        """テスト用のリカバリーコード"""
        def random_group():
            return ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        
        return f"{random_group()}-{random_group()}-{random_group()}-{random_group()}"
    
    @staticmethod
    def create_recovery_codes(count: int = 10) -> list[str]:
        """テスト用のリカバリーコードリスト"""
        return [TestDataFactory.create_recovery_code() for _ in range(count)]
    
    @staticmethod
    def create_totp_code() -> str:
        """テスト用のTOTPコード（6桁）"""
        return f"{random.randint(0, 999999):06d}"
    
    @staticmethod
    def create_invalid_totp_code() -> str:
        """テスト用の無効なTOTPコード"""
        return random.choice([
            "12345",      # 5桁
            "1234567",    # 7桁
            "12345a",     # 非数字含む
            "",           # 空文字
        ])


async def load_staff_with_office(db: AsyncSession, staff: Staff) -> Staff:
    """
    Staffオブジェクトのoffice_associationsリレーションシップを明示的にロードする

    MissingGreenletエラーを防ぐため、リレーションシップをeager loadingで取得
    office_associations内のofficeリレーションシップもネストしてロード
    """
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.office import OfficeStaff

    stmt = (
        select(Staff)
        .where(Staff.id == staff.id)
        .options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        )
        .execution_options(populate_existing=True)
    )
    result = await db.execute(stmt)
    return result.scalars().first()


# テスト用の定数
TEST_STAFF_PASSWORD = "testpassword123"
TEST_ADMIN_EMAIL = "admin@example.com"
TEST_EMPLOYEE_EMAIL = "employee@example.com"
TEST_MANAGER_EMAIL = "manager@example.com"