"""
Push Subscription CRUD のテスト
"""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app import crud
from app.schemas.push_subscription import PushSubscriptionInDB

pytestmark = pytest.mark.asyncio


async def test_create_push_subscription(
    db_session: AsyncSession,
    office_factory,
    staff_factory
) -> None:
    """Push購読情報の作成テスト"""
    office = await office_factory()
    staff = await staff_factory(office_id=office.id)
    await db_session.commit()

    subscription_data = PushSubscriptionInDB(
        staff_id=staff.id,
        endpoint="https://fcm.googleapis.com/fcm/send/test_endpoint_123",
        p256dh_key="BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUK",
        auth_key="tBHItJI5svbpez7KI4CCXg",
        user_agent="Mozilla/5.0 (Macintosh)"
    )

    subscription = await crud.push_subscription.create(
        db=db_session,
        obj_in=subscription_data,
        auto_commit=True
    )

    assert subscription.id is not None
    assert subscription.staff_id == staff.id
    assert subscription.endpoint == "https://fcm.googleapis.com/fcm/send/test_endpoint_123"
    assert subscription.p256dh_key == "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUK"
    assert subscription.auth_key == "tBHItJI5svbpez7KI4CCXg"
    assert subscription.user_agent == "Mozilla/5.0 (Macintosh)"
    assert subscription.created_at is not None
    assert subscription.updated_at is not None


async def test_get_by_staff_id(
    db_session: AsyncSession,
    office_factory,
    staff_factory
) -> None:
    """スタッフIDでPush購読情報を取得するテスト"""
    office = await office_factory()
    staff = await staff_factory(office_id=office.id)
    await db_session.commit()

    # 同一スタッフに2つのデバイスを登録
    subscription1_data = PushSubscriptionInDB(
        staff_id=staff.id,
        endpoint="https://fcm.googleapis.com/fcm/send/device1",
        p256dh_key="key1",
        auth_key="auth1"
    )
    subscription2_data = PushSubscriptionInDB(
        staff_id=staff.id,
        endpoint="https://fcm.googleapis.com/fcm/send/device2",
        p256dh_key="key2",
        auth_key="auth2"
    )

    await crud.push_subscription.create(db=db_session, obj_in=subscription1_data)
    await crud.push_subscription.create(db=db_session, obj_in=subscription2_data)
    await db_session.commit()

    # スタッフIDで全デバイス取得
    subscriptions = await crud.push_subscription.get_by_staff_id(
        db=db_session,
        staff_id=staff.id
    )

    assert len(subscriptions) == 2
    endpoints = [sub.endpoint for sub in subscriptions]
    assert "https://fcm.googleapis.com/fcm/send/device1" in endpoints
    assert "https://fcm.googleapis.com/fcm/send/device2" in endpoints


async def test_get_by_endpoint(
    db_session: AsyncSession,
    office_factory,
    staff_factory
) -> None:
    """エンドポイントでPush購読情報を取得するテスト"""
    office = await office_factory()
    staff = await staff_factory(office_id=office.id)
    await db_session.commit()

    endpoint = "https://fcm.googleapis.com/fcm/send/test_unique_endpoint"
    subscription_data = PushSubscriptionInDB(
        staff_id=staff.id,
        endpoint=endpoint,
        p256dh_key="test_key",
        auth_key="test_auth"
    )

    created = await crud.push_subscription.create(
        db=db_session,
        obj_in=subscription_data
    )
    await db_session.commit()

    # エンドポイントで取得
    subscription = await crud.push_subscription.get_by_endpoint(
        db=db_session,
        endpoint=endpoint
    )

    assert subscription is not None
    assert subscription.id == created.id
    assert subscription.endpoint == endpoint


async def test_get_by_endpoint_not_found(
    db_session: AsyncSession
) -> None:
    """存在しないエンドポイントで取得するとNoneが返るテスト"""
    subscription = await crud.push_subscription.get_by_endpoint(
        db=db_session,
        endpoint="https://nonexistent.endpoint"
    )

    assert subscription is None


async def test_create_or_update_new_subscription(
    db_session: AsyncSession,
    office_factory,
    staff_factory
) -> None:
    """create_or_updateで新規作成するテスト"""
    office = await office_factory()
    staff = await staff_factory(office_id=office.id)
    await db_session.commit()

    subscription = await crud.push_subscription.create_or_update(
        db=db_session,
        staff_id=staff.id,
        endpoint="https://fcm.googleapis.com/fcm/send/new_device",
        p256dh_key="new_key",
        auth_key="new_auth",
        user_agent="Chrome/120.0"
    )

    assert subscription.id is not None
    assert subscription.staff_id == staff.id
    assert subscription.endpoint == "https://fcm.googleapis.com/fcm/send/new_device"
    assert subscription.p256dh_key == "new_key"
    assert subscription.auth_key == "new_auth"
    assert subscription.user_agent == "Chrome/120.0"


async def test_create_or_update_existing_subscription(
    db_session: AsyncSession,
    office_factory,
    staff_factory
) -> None:
    """create_or_updateで既存の購読情報を更新するテスト"""
    office = await office_factory()
    staff1 = await staff_factory(office_id=office.id)
    staff2 = await staff_factory(office_id=office.id)
    await db_session.commit()

    endpoint = "https://fcm.googleapis.com/fcm/send/shared_endpoint"

    # staff1のデバイスとして登録
    original = await crud.push_subscription.create_or_update(
        db=db_session,
        staff_id=staff1.id,
        endpoint=endpoint,
        p256dh_key="original_key",
        auth_key="original_auth"
    )

    original_id = original.id

    # 同一エンドポイントをstaff2で再登録（更新）
    updated = await crud.push_subscription.create_or_update(
        db=db_session,
        staff_id=staff2.id,
        endpoint=endpoint,
        p256dh_key="updated_key",
        auth_key="updated_auth",
        user_agent="Updated UA"
    )

    # 同じIDで更新されること
    assert updated.id == original_id
    # 情報が更新されること
    assert updated.staff_id == staff2.id
    assert updated.p256dh_key == "updated_key"
    assert updated.auth_key == "updated_auth"
    assert updated.user_agent == "Updated UA"

    # DBに1件のみ存在すること
    all_subs = await crud.push_subscription.get_by_endpoint(
        db=db_session,
        endpoint=endpoint
    )
    assert all_subs is not None


async def test_delete_by_endpoint(
    db_session: AsyncSession,
    office_factory,
    staff_factory
) -> None:
    """エンドポイントで購読情報を削除するテスト"""
    office = await office_factory()
    staff = await staff_factory(office_id=office.id)
    await db_session.commit()

    endpoint = "https://fcm.googleapis.com/fcm/send/to_be_deleted"
    subscription_data = PushSubscriptionInDB(
        staff_id=staff.id,
        endpoint=endpoint,
        p256dh_key="key",
        auth_key="auth"
    )

    await crud.push_subscription.create(db=db_session, obj_in=subscription_data)
    await db_session.commit()

    # 削除実行
    result = await crud.push_subscription.delete_by_endpoint(
        db=db_session,
        endpoint=endpoint
    )

    assert result is True

    # 削除確認
    deleted = await crud.push_subscription.get_by_endpoint(
        db=db_session,
        endpoint=endpoint
    )
    assert deleted is None


async def test_delete_by_endpoint_not_found(
    db_session: AsyncSession
) -> None:
    """存在しないエンドポイントを削除しようとするとFalseが返るテスト"""
    result = await crud.push_subscription.delete_by_endpoint(
        db=db_session,
        endpoint="https://nonexistent.endpoint"
    )

    assert result is False


async def test_delete_by_staff_id(
    db_session: AsyncSession,
    office_factory,
    staff_factory
) -> None:
    """スタッフIDで全購読情報を削除するテスト"""
    office = await office_factory()
    staff = await staff_factory(office_id=office.id)
    await db_session.commit()

    # 3つのデバイスを登録
    for i in range(3):
        subscription_data = PushSubscriptionInDB(
            staff_id=staff.id,
            endpoint=f"https://fcm.googleapis.com/fcm/send/device{i}",
            p256dh_key=f"key{i}",
            auth_key=f"auth{i}"
        )
        await crud.push_subscription.create(db=db_session, obj_in=subscription_data)

    await db_session.commit()

    # 削除実行
    deleted_count = await crud.push_subscription.delete_by_staff_id(
        db=db_session,
        staff_id=staff.id
    )

    assert deleted_count == 3

    # 削除確認
    remaining = await crud.push_subscription.get_by_staff_id(
        db=db_session,
        staff_id=staff.id
    )
    assert len(remaining) == 0


async def test_cascade_delete_on_staff_deletion(
    db_session: AsyncSession,
    office_factory,
    staff_factory
) -> None:
    """スタッフ削除時にPush購読情報もCASCADE削除されるテスト"""
    office = await office_factory()
    staff = await staff_factory(office_id=office.id)
    await db_session.commit()

    # Push購読登録
    subscription_data = PushSubscriptionInDB(
        staff_id=staff.id,
        endpoint="https://fcm.googleapis.com/fcm/send/cascade_test",
        p256dh_key="key",
        auth_key="auth"
    )
    await crud.push_subscription.create(db=db_session, obj_in=subscription_data)
    await db_session.commit()

    # OfficeStaffアソシエーションを先に削除（外部キー制約のため）
    from sqlalchemy import select, delete
    from app.models.office import OfficeStaff
    delete_stmt = delete(OfficeStaff).where(OfficeStaff.staff_id == staff.id)
    await db_session.execute(delete_stmt)
    await db_session.commit()

    # スタッフを削除
    await db_session.delete(staff)
    await db_session.commit()

    # Push購読情報も削除されていることを確認
    subscriptions = await crud.push_subscription.get_by_endpoint(
        db=db_session,
        endpoint="https://fcm.googleapis.com/fcm/send/cascade_test"
    )
    assert subscriptions is None
