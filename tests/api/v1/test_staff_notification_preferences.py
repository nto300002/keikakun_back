"""
Staff Notification Preferences API のテスト
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import status

from app.core.security import create_access_token


pytestmark = pytest.mark.asyncio


class TestGetNotificationPreferences:
    """GET /api/v1/staffs/me/notification-preferences のテスト"""

    async def test_get_notification_preferences_success(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        office_factory,
        staff_factory
    ):
        """通知設定取得が成功するテスト"""
        office = await office_factory()
        staff = await staff_factory(office_id=office.id)
        await db_session.commit()

        token = create_access_token(subject=str(staff.id))
        headers = {"Authorization": f"Bearer {token}"}

        response = await async_client.get(
            "/api/v1/staffs/me/notification-preferences",
            headers=headers
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert "in_app_notification" in data
        assert "email_notification" in data
        assert "system_notification" in data

        assert data["in_app_notification"] is True
        assert data["email_notification"] is True
        assert data["system_notification"] is False

    async def test_get_notification_preferences_unauthorized(
        self,
        async_client: AsyncClient
    ):
        """認証なしで通知設定を取得しようとするとエラーになるテスト"""
        response = await async_client.get(
            "/api/v1/staffs/me/notification-preferences"
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestUpdateNotificationPreferences:
    """PUT /api/v1/staffs/me/notification-preferences のテスト"""

    async def test_update_notification_preferences_success(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        office_factory,
        staff_factory
    ):
        """通知設定更新が成功するテスト"""
        office = await office_factory()
        staff = await staff_factory(office_id=office.id)
        await db_session.commit()

        token = create_access_token(subject=str(staff.id))
        headers = {"Authorization": f"Bearer {token}"}

        new_preferences = {
            "in_app_notification": True,
            "email_notification": False,
            "system_notification": True
        }

        response = await async_client.put(
            "/api/v1/staffs/me/notification-preferences",
            headers=headers,
            json=new_preferences
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["in_app_notification"] is True
        assert data["email_notification"] is False
        assert data["system_notification"] is True

    async def test_update_all_false_should_fail(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        office_factory,
        staff_factory
    ):
        """全ての通知をfalseにしようとするとエラーになるテスト"""
        office = await office_factory()
        staff = await staff_factory(office_id=office.id)
        await db_session.commit()

        token = create_access_token(subject=str(staff.id))
        headers = {"Authorization": f"Bearer {token}"}

        all_false_preferences = {
            "in_app_notification": False,
            "email_notification": False,
            "system_notification": False
        }

        response = await async_client.put(
            "/api/v1/staffs/me/notification-preferences",
            headers=headers,
            json=all_false_preferences
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    async def test_update_notification_preferences_persistence(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        office_factory,
        staff_factory
    ):
        """通知設定の永続化テスト（更新後に取得して確認）"""
        office = await office_factory()
        staff = await staff_factory(office_id=office.id)
        await db_session.commit()

        token = create_access_token(subject=str(staff.id))
        headers = {"Authorization": f"Bearer {token}"}

        new_preferences = {
            "in_app_notification": False,
            "email_notification": True,
            "system_notification": True
        }

        update_response = await async_client.put(
            "/api/v1/staffs/me/notification-preferences",
            headers=headers,
            json=new_preferences
        )
        assert update_response.status_code == status.HTTP_200_OK

        get_response = await async_client.get(
            "/api/v1/staffs/me/notification-preferences",
            headers=headers
        )
        assert get_response.status_code == status.HTTP_200_OK

        data = get_response.json()
        assert data["in_app_notification"] is False
        assert data["email_notification"] is True
        assert data["system_notification"] is True

    async def test_update_notification_preferences_unauthorized(
        self,
        async_client: AsyncClient
    ):
        """認証なしで通知設定を更新しようとするとエラーになるテスト"""
        new_preferences = {
            "in_app_notification": True,
            "email_notification": True,
            "system_notification": False
        }

        response = await async_client.put(
            "/api/v1/staffs/me/notification-preferences",
            json=new_preferences
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_update_notification_preferences_invalid_data(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        office_factory,
        staff_factory
    ):
        """不正なデータで通知設定を更新しようとするとエラーになるテスト"""
        office = await office_factory()
        staff = await staff_factory(office_id=office.id)
        await db_session.commit()

        token = create_access_token(subject=str(staff.id))
        headers = {"Authorization": f"Bearer {token}"}

        invalid_preferences = {
            "in_app_notification": "invalid_string",
            "email_notification": True,
            "system_notification": False
        }

        response = await async_client.put(
            "/api/v1/staffs/me/notification-preferences",
            headers=headers,
            json=invalid_preferences
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    async def test_update_notification_preferences_missing_keys(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        office_factory,
        staff_factory
    ):
        """必須キーが欠けている場合エラーになるテスト"""
        office = await office_factory()
        staff = await staff_factory(office_id=office.id)
        await db_session.commit()

        token = create_access_token(subject=str(staff.id))
        headers = {"Authorization": f"Bearer {token}"}

        incomplete_preferences = {
            "in_app_notification": True
        }

        response = await async_client.put(
            "/api/v1/staffs/me/notification-preferences",
            headers=headers,
            json=incomplete_preferences
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    async def test_update_notification_preferences_with_thresholds_success(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        office_factory,
        staff_factory
    ):
        """閾値フィールドを含む通知設定更新が成功するテスト"""
        office = await office_factory()
        staff = await staff_factory(office_id=office.id)
        await db_session.commit()

        token = create_access_token(subject=str(staff.id))
        headers = {"Authorization": f"Bearer {token}"}

        preferences_with_thresholds = {
            "in_app_notification": True,
            "email_notification": True,
            "system_notification": True,
            "email_threshold_days": 20,
            "push_threshold_days": 30
        }

        response = await async_client.put(
            "/api/v1/staffs/me/notification-preferences",
            headers=headers,
            json=preferences_with_thresholds
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["email_notification"] is True
        assert data["system_notification"] is True
        assert data["email_threshold_days"] == 20
        assert data["push_threshold_days"] == 30

    async def test_update_notification_preferences_invalid_threshold_value(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        office_factory,
        staff_factory
    ):
        """無効な閾値（5, 10, 20, 30以外）でエラーになるテスト"""
        office = await office_factory()
        staff = await staff_factory(office_id=office.id)
        await db_session.commit()

        token = create_access_token(subject=str(staff.id))
        headers = {"Authorization": f"Bearer {token}"}

        invalid_threshold_preferences = {
            "in_app_notification": True,
            "email_notification": True,
            "system_notification": False,
            "email_threshold_days": 15,  # 無効値
            "push_threshold_days": 10
        }

        response = await async_client.put(
            "/api/v1/staffs/me/notification-preferences",
            headers=headers,
            json=invalid_threshold_preferences
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    async def test_update_notification_preferences_valid_threshold_values(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        office_factory,
        staff_factory
    ):
        """有効な閾値（5, 10, 20, 30）全てが正常に更新されるテスト"""
        office = await office_factory()
        staff = await staff_factory(office_id=office.id)
        await db_session.commit()

        token = create_access_token(subject=str(staff.id))
        headers = {"Authorization": f"Bearer {token}"}

        valid_thresholds = [5, 10, 20, 30]

        for threshold in valid_thresholds:
            preferences = {
                "in_app_notification": True,
                "email_notification": True,
                "system_notification": True,
                "email_threshold_days": threshold,
                "push_threshold_days": threshold
            }

            response = await async_client.put(
                "/api/v1/staffs/me/notification-preferences",
                headers=headers,
                json=preferences
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["email_threshold_days"] == threshold
            assert data["push_threshold_days"] == threshold

    async def test_get_notification_preferences_includes_thresholds(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        office_factory,
        staff_factory
    ):
        """GET APIが閾値フィールドを含むことを確認するテスト"""
        office = await office_factory()
        staff = await staff_factory(office_id=office.id)
        await db_session.commit()

        token = create_access_token(subject=str(staff.id))
        headers = {"Authorization": f"Bearer {token}"}

        response = await async_client.get(
            "/api/v1/staffs/me/notification-preferences",
            headers=headers
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert "email_threshold_days" in data
        assert "push_threshold_days" in data
        assert data["email_threshold_days"] == 30  # デフォルト値
        assert data["push_threshold_days"] == 10  # デフォルト値
