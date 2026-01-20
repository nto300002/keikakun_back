"""
Push Subscription API のテスト
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import status

from app import crud
from app.core.security import create_access_token
from app.schemas.push_subscription import PushSubscriptionInDB


pytestmark = pytest.mark.asyncio


class TestSubscribePush:
    """POST /api/v1/push-subscriptions/subscribe のテスト"""

    async def test_subscribe_success(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        office_factory,
        staff_factory
    ):
        """Push購読登録が成功するテスト"""
        office = await office_factory()
        staff = await staff_factory(office_id=office.id)
        await db_session.commit()

        token = create_access_token(subject=str(staff.id))
        headers = {"Authorization": f"Bearer {token}"}

        subscription_data = {
            "endpoint": "https://fcm.googleapis.com/fcm/send/test_endpoint_1",
            "keys": {
                "p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUK",
                "auth": "tBHItJI5svbpez7KI4CCXg"
            }
        }

        response = await async_client.post(
            "/api/v1/push-subscriptions/subscribe",
            headers=headers,
            json=subscription_data
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert "id" in data
        assert data["staff_id"] == str(staff.id)
        assert data["endpoint"] == subscription_data["endpoint"]
        assert "created_at" in data

        # DBに保存されていることを確認
        saved = await crud.push_subscription.get_by_endpoint(
            db=db_session,
            endpoint=subscription_data["endpoint"]
        )
        assert saved is not None
        assert saved.staff_id == staff.id

    async def test_subscribe_duplicate_endpoint_updates(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        office_factory,
        staff_factory
    ):
        """同一エンドポイントを再登録すると更新されるテスト"""
        office = await office_factory()
        staff1 = await staff_factory(office_id=office.id)
        staff2 = await staff_factory(office_id=office.id)
        await db_session.commit()

        endpoint = "https://fcm.googleapis.com/fcm/send/shared_endpoint"

        # staff1で最初に登録
        token1 = create_access_token(subject=str(staff1.id))
        headers1 = {"Authorization": f"Bearer {token1}"}

        subscription_data = {
            "endpoint": endpoint,
            "keys": {
                "p256dh": "original_key",
                "auth": "original_auth"
            }
        }

        response1 = await async_client.post(
            "/api/v1/push-subscriptions/subscribe",
            headers=headers1,
            json=subscription_data
        )
        assert response1.status_code == status.HTTP_200_OK
        original_id = response1.json()["id"]

        # staff2で同一エンドポイントを登録（更新）
        token2 = create_access_token(subject=str(staff2.id))
        headers2 = {"Authorization": f"Bearer {token2}"}

        subscription_data["keys"] = {
            "p256dh": "updated_key",
            "auth": "updated_auth"
        }

        response2 = await async_client.post(
            "/api/v1/push-subscriptions/subscribe",
            headers=headers2,
            json=subscription_data
        )
        assert response2.status_code == status.HTTP_200_OK
        updated_id = response2.json()["id"]

        # 同じIDで更新されること
        assert updated_id == original_id

        # DBで確認
        saved = await crud.push_subscription.get_by_endpoint(
            db=db_session,
            endpoint=endpoint
        )
        assert saved.staff_id == staff2.id
        assert saved.p256dh_key == "updated_key"

    async def test_subscribe_unauthorized(
        self,
        async_client: AsyncClient
    ):
        """認証なしでPush購読しようとするとエラーになるテスト"""
        subscription_data = {
            "endpoint": "https://fcm.googleapis.com/fcm/send/test",
            "keys": {
                "p256dh": "key",
                "auth": "auth"
            }
        }

        response = await async_client.post(
            "/api/v1/push-subscriptions/subscribe",
            json=subscription_data
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_subscribe_invalid_data(
        self,
        async_client: AsyncClient,
        office_factory,
        staff_factory,
        db_session: AsyncSession
    ):
        """不正なデータでPush購読しようとするとエラーになるテスト"""
        office = await office_factory()
        staff = await staff_factory(office_id=office.id)
        await db_session.commit()

        token = create_access_token(subject=str(staff.id))
        headers = {"Authorization": f"Bearer {token}"}

        # keysが欠けている
        invalid_data = {
            "endpoint": "https://fcm.googleapis.com/fcm/send/test"
        }

        response = await async_client.post(
            "/api/v1/push-subscriptions/subscribe",
            headers=headers,
            json=invalid_data
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestUnsubscribePush:
    """DELETE /api/v1/push-subscriptions/unsubscribe のテスト"""

    async def test_unsubscribe_success(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        office_factory,
        staff_factory
    ):
        """Push購読解除が成功するテスト"""
        office = await office_factory()
        staff = await staff_factory(office_id=office.id)
        await db_session.commit()

        endpoint = "https://fcm.googleapis.com/fcm/send/to_unsubscribe"

        # 購読登録
        subscription_data = PushSubscriptionInDB(
            staff_id=staff.id,
            endpoint=endpoint,
            p256dh_key="key",
            auth_key="auth"
        )
        await crud.push_subscription.create(db=db_session, obj_in=subscription_data)
        await db_session.commit()

        # 購読解除
        token = create_access_token(subject=str(staff.id))
        headers = {"Authorization": f"Bearer {token}"}

        response = await async_client.delete(
            f"/api/v1/push-subscriptions/unsubscribe?endpoint={endpoint}",
            headers=headers
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["message"] == "Unsubscribed successfully"

        # DBから削除されていることを確認
        deleted = await crud.push_subscription.get_by_endpoint(
            db=db_session,
            endpoint=endpoint
        )
        assert deleted is None

    async def test_unsubscribe_not_found(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        office_factory,
        staff_factory
    ):
        """存在しないエンドポイントを削除しようとするとエラーになるテスト"""
        office = await office_factory()
        staff = await staff_factory(office_id=office.id)
        await db_session.commit()

        token = create_access_token(subject=str(staff.id))
        headers = {"Authorization": f"Bearer {token}"}

        response = await async_client.delete(
            "/api/v1/push-subscriptions/unsubscribe?endpoint=https://nonexistent.endpoint",
            headers=headers
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_unsubscribe_other_user_subscription(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        office_factory,
        staff_factory
    ):
        """他のユーザーの購読情報を削除しようとするとエラーになるテスト"""
        office = await office_factory()
        staff1 = await staff_factory(office_id=office.id)
        staff2 = await staff_factory(office_id=office.id)
        await db_session.commit()

        endpoint = "https://fcm.googleapis.com/fcm/send/staff1_device"

        # staff1の購読登録
        subscription_data = PushSubscriptionInDB(
            staff_id=staff1.id,
            endpoint=endpoint,
            p256dh_key="key",
            auth_key="auth"
        )
        await crud.push_subscription.create(db=db_session, obj_in=subscription_data)
        await db_session.commit()

        # staff2が削除しようとする
        token2 = create_access_token(subject=str(staff2.id))
        headers2 = {"Authorization": f"Bearer {token2}"}

        response = await async_client.delete(
            f"/api/v1/push-subscriptions/unsubscribe?endpoint={endpoint}",
            headers=headers2
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_unsubscribe_unauthorized(
        self,
        async_client: AsyncClient
    ):
        """認証なしでPush購読解除しようとするとエラーになるテスト"""
        response = await async_client.delete(
            "/api/v1/push-subscriptions/unsubscribe?endpoint=https://test.endpoint"
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestGetMySubscriptions:
    """GET /api/v1/push-subscriptions/my-subscriptions のテスト"""

    async def test_get_my_subscriptions_success(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        office_factory,
        staff_factory
    ):
        """自分の購読情報一覧を取得できるテスト"""
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

        # 取得
        token = create_access_token(subject=str(staff.id))
        headers = {"Authorization": f"Bearer {token}"}

        response = await async_client.get(
            "/api/v1/push-subscriptions/my-subscriptions",
            headers=headers
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert len(data) == 3
        endpoints = [sub["endpoint"] for sub in data]
        assert "https://fcm.googleapis.com/fcm/send/device0" in endpoints
        assert "https://fcm.googleapis.com/fcm/send/device1" in endpoints
        assert "https://fcm.googleapis.com/fcm/send/device2" in endpoints

    async def test_get_my_subscriptions_empty(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        office_factory,
        staff_factory
    ):
        """購読情報がない場合は空のリストが返るテスト"""
        office = await office_factory()
        staff = await staff_factory(office_id=office.id)
        await db_session.commit()

        token = create_access_token(subject=str(staff.id))
        headers = {"Authorization": f"Bearer {token}"}

        response = await async_client.get(
            "/api/v1/push-subscriptions/my-subscriptions",
            headers=headers
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 0

    async def test_get_my_subscriptions_only_own(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        office_factory,
        staff_factory
    ):
        """自分の購読情報のみが取得できるテスト（他人のは含まれない）"""
        office = await office_factory()
        staff1 = await staff_factory(office_id=office.id)
        staff2 = await staff_factory(office_id=office.id)
        await db_session.commit()

        # staff1の購読登録
        subscription1 = PushSubscriptionInDB(
            staff_id=staff1.id,
            endpoint="https://fcm.googleapis.com/fcm/send/staff1",
            p256dh_key="key1",
            auth_key="auth1"
        )
        await crud.push_subscription.create(db=db_session, obj_in=subscription1)

        # staff2の購読登録
        subscription2 = PushSubscriptionInDB(
            staff_id=staff2.id,
            endpoint="https://fcm.googleapis.com/fcm/send/staff2",
            p256dh_key="key2",
            auth_key="auth2"
        )
        await crud.push_subscription.create(db=db_session, obj_in=subscription2)
        await db_session.commit()

        # staff1で取得
        token1 = create_access_token(subject=str(staff1.id))
        headers1 = {"Authorization": f"Bearer {token1}"}

        response = await async_client.get(
            "/api/v1/push-subscriptions/my-subscriptions",
            headers=headers1
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert len(data) == 1
        assert data[0]["endpoint"] == "https://fcm.googleapis.com/fcm/send/staff1"

    async def test_get_my_subscriptions_unauthorized(
        self,
        async_client: AsyncClient
    ):
        """認証なしで購読情報を取得しようとするとエラーになるテスト"""
        response = await async_client.get(
            "/api/v1/push-subscriptions/my-subscriptions"
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestSubscriptionCleanup:
    """購読情報のクリーンアップに関するテスト"""

    async def test_multiple_subscriptions_from_same_user_are_allowed(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        office_factory,
        staff_factory
    ):
        """
        同じユーザーが複数デバイスで購読した場合、すべての購読が保持されるテスト

        設計方針:
        - 1ユーザーが複数デバイス（PC、スマホ、複数ブラウザ）で通知を受信できるよう、
          各デバイスの購読情報を保持する
        - 各デバイスは異なるendpointを持つため、すべて保存される
        - 古い購読の自動削除は行わない（期限切れ410/404エラー時のみ削除）

        シナリオ:
        1. ユーザーがPC Chromeで購読を作成
        2. ユーザーがスマホで購読を作成
        3. ユーザーがPC Firefoxで購読を作成
        4. DBには3つすべての購読が保持される
        """
        office = await office_factory()
        staff = await staff_factory(office_id=office.id)
        await db_session.commit()

        token = create_access_token(subject=str(staff.id))
        headers = {"Authorization": f"Bearer {token}"}

        # 1回目の購読（PC Chrome）
        subscription_data_1 = {
            "endpoint": "https://fcm.googleapis.com/fcm/send/first_subscription",
            "keys": {
                "p256dh": "first_p256dh_key",
                "auth": "first_auth_key"
            }
        }
        response_1 = await async_client.post(
            "/api/v1/push-subscriptions/subscribe",
            headers=headers,
            json=subscription_data_1
        )
        assert response_1.status_code == status.HTTP_200_OK

        # 2回目の購読（スマホ）
        subscription_data_2 = {
            "endpoint": "https://fcm.googleapis.com/fcm/send/second_subscription",
            "keys": {
                "p256dh": "second_p256dh_key",
                "auth": "second_auth_key"
            }
        }
        response_2 = await async_client.post(
            "/api/v1/push-subscriptions/subscribe",
            headers=headers,
            json=subscription_data_2
        )
        assert response_2.status_code == status.HTTP_200_OK

        # 3回目の購読（PC Firefox）
        subscription_data_3 = {
            "endpoint": "https://fcm.googleapis.com/fcm/send/third_subscription",
            "keys": {
                "p256dh": "third_p256dh_key",
                "auth": "third_auth_key"
            }
        }
        response_3 = await async_client.post(
            "/api/v1/push-subscriptions/subscribe",
            headers=headers,
            json=subscription_data_3
        )
        assert response_3.status_code == status.HTTP_200_OK

        # DBに保存されている購読数を確認
        subscriptions = await crud.push_subscription.get_by_staff_id(
            db=db_session,
            staff_id=staff.id
        )

        # 重要: 複数デバイス対応のため、3つすべての購読が保持されるべき
        assert len(subscriptions) == 3, (
            f"Expected 3 subscriptions (multi-device support), but found {len(subscriptions)}. "
            f"All device subscriptions should be kept."
        )

        # すべてのendpointが保存されていることを確認
        endpoints = {sub.endpoint for sub in subscriptions}
        expected_endpoints = {
            subscription_data_1["endpoint"],
            subscription_data_2["endpoint"],
            subscription_data_3["endpoint"]
        }
        assert endpoints == expected_endpoints, "All unique endpoints should be stored"

