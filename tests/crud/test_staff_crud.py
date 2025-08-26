import pytest
import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.schemas.staff import StaffCreate

# Pytestに非同期テストであることを認識させる
pytestmark = pytest.mark.asyncio


async def test_create_admin_user(db_session: AsyncSession) -> None:
    """
    Test creating a service_administrator staff user directly via CRUD.
    """
    # Arrange
    # Eメールが一意になるようにランダムな接尾辞を追加
    random_suffix = uuid.uuid4().hex[:6]
    user_in = StaffCreate(
        email=f"test_crud_{random_suffix}@example.com",
        name="CRUD Test User",
        password="a-secure-password",
    )

    # Act
    # CRUD関数を直接呼び出す
    created_user = await crud.staff.create_admin(db=db_session, obj_in=user_in)

    # Assert
    assert created_user is not None
    assert created_user.email == user_in.email
    assert created_user.name == user_in.name
    assert created_user.role.value == "service_administrator"
