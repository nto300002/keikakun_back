"""
事務所情報変更 CRUD のテスト
TDD方式でテストを先に作成
"""
from sqlalchemy.ext.asyncio import AsyncSession
import pytest
from uuid import UUID

from app import crud
from app.models.office import Office

pytestmark = pytest.mark.asyncio


async def test_update_office_info_basic(
    db_session: AsyncSession,
    owner_user_factory
) -> None:
    """
    事務所情報更新の基本テスト
    name, address, phone_number, emailを更新できることを確認
    """
    owner = await owner_user_factory()
    office = owner.office_associations[0].office if owner.office_associations else None

    assert office is not None

    # 更新データ
    update_data = {
        "name": "更新後の事務所名",
        "address": "東京都渋谷区1-2-3",
        "phone_number": "03-1234-5678",
        "email": "updated@example.com"
    }

    # 事務所情報を更新
    updated_office = await crud.office.update_office_info(
        db=db_session,
        office_id=office.id,
        update_data=update_data
    )

    assert updated_office.id == office.id
    assert updated_office.name == "更新後の事務所名"
    assert updated_office.address == "東京都渋谷区1-2-3"
    assert updated_office.phone_number == "03-1234-5678"
    assert updated_office.email == "updated@example.com"


async def test_update_office_info_partial(
    db_session: AsyncSession,
    owner_user_factory
) -> None:
    """
    事務所情報の部分更新テスト
    一部のフィールドのみ更新できることを確認
    """
    owner = await owner_user_factory()
    office = owner.office_associations[0].office if owner.office_associations else None

    assert office is not None
    original_name = office.name

    # 住所のみ更新
    update_data = {
        "address": "大阪府大阪市北区4-5-6"
    }

    updated_office = await crud.office.update_office_info(
        db=db_session,
        office_id=office.id,
        update_data=update_data
    )

    assert updated_office.name == original_name  # 名前は変更されていない
    assert updated_office.address == "大阪府大阪市北区4-5-6"


async def test_update_office_info_returns_old_values(
    db_session: AsyncSession,
    owner_user_factory
) -> None:
    """
    事務所情報更新時に変更前の値を取得できることを確認
    監査ログ用に必要
    """
    owner = await owner_user_factory()
    office = owner.office_associations[0].office if owner.office_associations else None

    assert office is not None

    # 初期値を設定
    office.name = "元の事務所名"
    office.address = "元の住所"
    await db_session.flush()
    await db_session.refresh(office)

    # 更新前の値を保存
    old_name = office.name
    old_address = office.address

    # 更新データ
    update_data = {
        "name": "新しい事務所名",
        "address": "新しい住所"
    }

    # 更新実行
    updated_office = await crud.office.update_office_info(
        db=db_session,
        office_id=office.id,
        update_data=update_data
    )

    # 更新後の値を確認
    assert updated_office.name == "新しい事務所名"
    assert updated_office.address == "新しい住所"

    # 変更前の値は別途取得できる仕組みが必要
    # （実装時にold_valuesを返すか、呼び出し側で事前取得する）


async def test_update_office_info_nonexistent(
    db_session: AsyncSession
) -> None:
    """
    存在しない事務所IDでの更新テスト
    適切なエラーハンドリングを確認
    """
    from uuid import uuid4

    fake_office_id = uuid4()
    update_data = {"name": "存在しない事務所"}

    with pytest.raises(Exception):  # 適切な例外を定義する
        await crud.office.update_office_info(
            db=db_session,
            office_id=fake_office_id,
            update_data=update_data
        )


async def test_create_office_audit_log(
    db_session: AsyncSession,
    owner_user_factory
) -> None:
    """
    事務所情報変更の監査ログ作成テスト
    """
    owner = await owner_user_factory()
    office = owner.office_associations[0].office if owner.office_associations else None

    assert office is not None

    old_values = {
        "name": "元の事務所名",
        "address": "元の住所"
    }
    new_values = {
        "name": "新しい事務所名",
        "address": "新しい住所"
    }

    # 監査ログを作成
    audit_log = await crud.office_audit_log.create_office_update_log(
        db=db_session,
        office_id=office.id,
        staff_id=owner.id,
        action_type="office_info_updated",
        old_values=old_values,
        new_values=new_values
    )

    assert audit_log.id is not None
    assert audit_log.office_id == office.id
    assert audit_log.staff_id == owner.id
    assert audit_log.action_type == "office_info_updated"
    # details に JSON 形式で保存されることを確認
    assert "name" in str(audit_log.details)


async def test_get_office_audit_logs(
    db_session: AsyncSession,
    owner_user_factory
) -> None:
    """
    事務所の監査ログ取得テスト
    """
    owner = await owner_user_factory()
    office = owner.office_associations[0].office if owner.office_associations else None

    assert office is not None

    # 複数の監査ログを作成
    for i in range(3):
        await crud.office_audit_log.create_office_update_log(
            db=db_session,
            office_id=office.id,
            staff_id=owner.id,
            action_type="office_info_updated",
            old_values={"name": f"旧名称{i}"},
            new_values={"name": f"新名称{i}"}
        )

    await db_session.flush()

    # 監査ログを取得
    audit_logs = await crud.office_audit_log.get_by_office_id(
        db=db_session,
        office_id=office.id,
        skip=0,
        limit=10
    )

    assert len(audit_logs) >= 3
    # 最新のログが先頭に来るように並んでいることを確認
    assert audit_logs[0].created_at >= audit_logs[-1].created_at
