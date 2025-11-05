import pytest
import uuid
import logging
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.models.enums import StaffRole
from app.schemas.staff import AdminCreate 

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
        first_name="太郎",
        last_name="山田",
        password="Test-password123!",
    )

    # Act
    # CRUD関数を直接呼び出す
    created_user = await crud.staff.create_admin(db=db_session, obj_in=user_in)

    # Assert
    assert created_user is not None
    assert created_user.email == user_in.email
    assert created_user.first_name == user_in.first_name
    assert created_user.last_name == user_in.last_name
    assert created_user.full_name == f"{user_in.last_name} {user_in.first_name}"
    assert created_user.role == StaffRole.owner # create_admin内で設定されることを確認


async def test_get_staff_with_office(db_session: AsyncSession, employee_user_factory, office_factory):
    """正常系: 事業所に所属するスタッフを取得した際、事業所情報も読み込まれることをテスト"""
    # SQLログを有効化
    import logging
    logging.basicConfig()
    logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

    # Arrange
    # 1. テスト用のスタッフと、そのスタッフが作成者となる事業所を作成
    test_staff = await employee_user_factory(email="relation_test@example.com", with_office=False)
    print(f"\n[DEBUG] Created test_staff: id={test_staff.id}, full_name={test_staff.full_name}")

    test_office = await office_factory(name="リレーションテスト事業所", creator=test_staff)
    print(f"[DEBUG] Created test_office: id={test_office.id}, name={test_office.name}")

    # 2. スタッフと事業所を紐付ける
    from app.models.office import OfficeStaff

    # IDを事前に取得（expire_all前に）
    staff_id = test_staff.id
    office_id = test_office.id

    association = OfficeStaff(staff_id=staff_id, office_id=office_id, is_primary=True)
    db_session.add(association)
    await db_session.flush()
    print(f"[DEBUG] Created association: staff_id={association.staff_id}, office_id={association.office_id}, is_primary={association.is_primary}")

    # デバッグ: DBに実際にデータが保存されているか確認
    from sqlalchemy import select, text
    check_query = text("SELECT * FROM office_staffs WHERE staff_id = :staff_id")
    result = await db_session.execute(check_query, {"staff_id": str(staff_id)})
    rows = result.fetchall()
    print(f"[DEBUG] Direct SQL check - office_staffs records: {len(rows)}")
    for row in rows:
        print(f"[DEBUG]   {row}")

    # セッションの状態をクリアして、次のクエリで確実にDBから取得させる
    db_session.expire_all()
    print("[DEBUG] Called db_session.expire_all()")

    # Act
    # CRUDのgetメソッドでスタッフを再取得
    print("\n[DEBUG] === Calling crud.staff.get() ===")
    retrieved_staff = await crud.staff.get(db=db_session, id=staff_id)

    # Debug: 取得したスタッフの情報を出力
    print(f"\n[DEBUG] Retrieved staff: id={retrieved_staff.id if retrieved_staff else None}")
    if retrieved_staff:
        print(f"[DEBUG] retrieved_staff.office_associations: {retrieved_staff.office_associations}")
        print(f"[DEBUG] len(office_associations): {len(retrieved_staff.office_associations)}")

        if retrieved_staff.office_associations:
            for idx, assoc in enumerate(retrieved_staff.office_associations):
                print(f"[DEBUG] association[{idx}]: id={assoc.id}, is_primary={assoc.is_primary}")
                print(f"[DEBUG] association[{idx}].office: {assoc.office}")
                if assoc.office:
                    print(f"[DEBUG] association[{idx}].office.id: {assoc.office.id}, name: {assoc.office.name}")

        print(f"[DEBUG] retrieved_staff.office (property): {retrieved_staff.office}")

    # Assert
    assert retrieved_staff is not None
    assert retrieved_staff.office is not None, f"office is None. office_associations: {retrieved_staff.office_associations}"
    assert retrieved_staff.office.id == office_id
    assert retrieved_staff.office.name == "リレーションテスト事業所"


async def test_get_staff_without_office(db_session: AsyncSession, employee_user_factory):
    """正常系: 事業所に所属しないスタッフを取得した際、事業所情報がNoneであることをテスト"""
    # Arrange
    # 事業所に紐付けないスタッフを作成
    test_staff = await employee_user_factory(email="no_office@example.com", with_office=False)

    # Act
    retrieved_staff = await crud.staff.get(db=db_session, id=test_staff.id)

    # Assert
    assert retrieved_staff is not None
    assert retrieved_staff.office is None
