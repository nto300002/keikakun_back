import pytest
import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.models.enums import StaffRole
from app.schemas.staff import AdminCreate # StaffCreateの代わりにAdminCreateをインポート

# Pytestに非同期テストであることを認識させる
pytestmark = pytest.mark.asyncio


async def test_create_admin_user(db_session: AsyncSession) -> None:
    """
    Test creating staff user directly via CRUD.
    """
    # Arrange
    # Eメールが一意になるようにランダムな接尾辞を追加
    random_suffix = uuid.uuid4().hex[:6]
    # AdminCreateを使用し、roleは含めない
    user_in = AdminCreate(
        email=f"test_crud_{random_suffix}@example.com",
        name="CRUD Test User",
        password="Test-password123!",
    )

    # Act
    # CRUD関数を直接呼び出す
    created_user = await crud.staff.create_admin(db=db_session, obj_in=user_in)

    # Assert
    assert created_user is not None
    assert created_user.email == user_in.email
    assert created_user.name == user_in.name
    assert created_user.role == StaffRole.owner # create_admin内で設定されることを確認


async def test_get_staff_with_office(db_session: AsyncSession, employee_user_factory, office_factory):
    """正常系: 事業所に所属するスタッフを取得した際、事業所情報も読み込まれることをテスト"""
    # Arrange
    # 1. テスト用のスタッフと、そのスタッフが作成者となる事業所を作成
    test_staff = await employee_user_factory(email="relation_test@example.com")
    test_office = await office_factory(name="リレーションテスト事業所", creator=test_staff)

    # 2. スタッフと事業所を紐付ける
    from app.models.office import OfficeStaff
    association = OfficeStaff(staff_id=test_staff.id, office_id=test_office.id)
    db_session.add(association)
    await db_session.flush()

    # Act
    # CRUDのgetメソッドでスタッフを再取得
    retrieved_staff = await crud.staff.get(db=db_session, id=test_staff.id)

    # Assert
    assert retrieved_staff is not None
    assert retrieved_staff.office is not None
    assert retrieved_staff.office.id == test_office.id
    assert retrieved_staff.office.name == "リレーションテスト事業所"


async def test_get_staff_without_office(db_session: AsyncSession, employee_user_factory):
    """正常系: 事業所に所属しないスタッフを取得した際、事業所情報がNoneであることをテスト"""
    # Arrange
    # 事業所に紐付けないスタッフを作成
    test_staff = await employee_user_factory(email="no_office@example.com")

    # Act
    retrieved_staff = await crud.staff.get(db=db_session, id=test_staff.id)

    # Assert
    assert retrieved_staff is not None
    assert retrieved_staff.office is None
