"""
Push購読情報のバッチクエリテスト（Phase 4.2）

N+1クエリ問題を解消するためのバッチクエリメソッドをテストする
"""
import pytest
import pytest_asyncio
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.crud.crud_push_subscription import crud_push_subscription
from app.models.staff import Staff
from app.models.push_subscription import PushSubscription


@pytest_asyncio.fixture
async def test_staff_with_subscriptions(db_session: AsyncSession):
    """
    テスト用に3人のスタッフを作成し、それぞれに購読情報を配置

    Returns:
        dict: {
            "staff_list": [Staff, Staff, Staff],
            "staff_ids": [UUID, UUID, UUID]
        }
    """
    staff_list = []

    for i in range(3):
        # スタッフ作成
        staff = Staff(
            first_name=f"スタッフ{i+1}",
            last_name=f"テスト",
            full_name=f"テスト スタッフ{i+1}",
            email=f"staff_push_batch_{i}@example.com",
            hashed_password="dummy",
            role="employee",
            is_test_data=True
        )
        db_session.add(staff)
        await db_session.flush()
        staff_list.append(staff)

        # 各スタッフに2つのデバイス（購読）を追加
        for j in range(2):
            subscription = PushSubscription(
                staff_id=staff.id,
                endpoint=f"https://fcm.googleapis.com/fcm/send/staff{i}_device{j}",
                p256dh_key=f"p256dh_key_staff{i}_device{j}",
                auth_key=f"auth_key_staff{i}_device{j}",
                user_agent=f"Device {j}"
            )
            db_session.add(subscription)

    await db_session.commit()

    return {
        "staff_list": staff_list,
        "staff_ids": [staff.id for staff in staff_list]
    }


@pytest.mark.asyncio
async def test_get_by_staff_ids_batch(
    db_session: AsyncSession,
    test_staff_with_subscriptions: dict
):
    """
    【バッチクエリテスト】複数スタッフの購読情報を一括取得

    検証項目:
    - 3人のスタッフ全ての購読情報が取得できる
    - 各スタッフに2つの購読（2デバイス）が存在する
    - データが正しいスタッフIDでグループ化されている
    """
    staff_ids = test_staff_with_subscriptions["staff_ids"]

    # バッチで購読情報取得
    subscriptions_by_staff = await crud_push_subscription.get_by_staff_ids_batch(
        db=db_session,
        staff_ids=staff_ids
    )

    # 検証: 3人のスタッフ全ての購読情報が取得できる
    assert len(subscriptions_by_staff) == 3, f"Expected 3 staff, got {len(subscriptions_by_staff)}"

    # 検証: 各スタッフに2つの購読が存在する
    for staff_id in staff_ids:
        assert staff_id in subscriptions_by_staff, f"Staff {staff_id} not found in results"
        subscriptions = subscriptions_by_staff[staff_id]

        # 各スタッフに2デバイス → 2購読
        assert len(subscriptions) == 2, (
            f"Staff {staff_id}: expected 2 subscriptions, got {len(subscriptions)}"
        )

        # 購読情報の確認
        for subscription in subscriptions:
            assert subscription.endpoint is not None
            assert subscription.p256dh_key is not None
            assert subscription.auth_key is not None
            assert subscription.staff_id == staff_id


@pytest.mark.asyncio
async def test_get_by_staff_ids_batch_empty_list(
    db_session: AsyncSession
):
    """
    【エッジケーステスト】スタッフIDリストが空の場合

    検証項目:
    - 空の辞書が返される
    - エラーが発生しない
    """
    subscriptions_by_staff = await crud_push_subscription.get_by_staff_ids_batch(
        db=db_session,
        staff_ids=[]
    )

    assert subscriptions_by_staff == {}


@pytest.mark.asyncio
async def test_batch_query_consistency(
    db_session: AsyncSession,
    test_staff_with_subscriptions: dict
):
    """
    【整合性テスト】個別取得とバッチ取得で結果が一致するか

    検証項目:
    - バッチクエリの結果が個別クエリと同じ
    - データの整合性が保たれている
    """
    staff_ids = test_staff_with_subscriptions["staff_ids"]

    # バッチで取得
    subscriptions_batch = await crud_push_subscription.get_by_staff_ids_batch(
        db=db_session,
        staff_ids=staff_ids
    )

    # 個別に取得して比較
    for staff_id in staff_ids:
        subscriptions_individual = await crud_push_subscription.get_by_staff_id(
            db=db_session,
            staff_id=staff_id
        )

        # 検証: 件数が一致
        assert len(subscriptions_batch[staff_id]) == len(subscriptions_individual), (
            f"Staff {staff_id}: batch count {len(subscriptions_batch[staff_id])} != "
            f"individual count {len(subscriptions_individual)}"
        )

        # 検証: IDが一致（順序は問わない）
        batch_ids = {sub.id for sub in subscriptions_batch[staff_id]}
        individual_ids = {sub.id for sub in subscriptions_individual}
        assert batch_ids == individual_ids, (
            f"Staff {staff_id}: batch IDs {batch_ids} != individual IDs {individual_ids}"
        )


@pytest.mark.asyncio
async def test_batch_query_with_no_subscriptions(
    db_session: AsyncSession
):
    """
    【エッジケーステスト】購読情報がないスタッフを含む場合

    検証項目:
    - 購読情報がないスタッフには空リストが返される
    - エラーが発生しない
    """
    # 購読情報なしのスタッフを作成
    staff = Staff(
        first_name="購読なし",
        last_name="スタッフ",
        full_name="スタッフ 購読なし",
        email="no_subscription@example.com",
        hashed_password="dummy",
        role="employee",
        is_test_data=True
    )
    db_session.add(staff)
    await db_session.flush()

    staff_ids = [staff.id]

    # バッチで取得
    subscriptions_by_staff = await crud_push_subscription.get_by_staff_ids_batch(
        db=db_session,
        staff_ids=staff_ids
    )

    # 検証: 空リストが返される
    assert staff.id in subscriptions_by_staff
    assert subscriptions_by_staff[staff.id] == []
