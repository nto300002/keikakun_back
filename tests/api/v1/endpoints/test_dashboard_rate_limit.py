"""
ダッシュボードAPIのレート制限テスト

レート制限:
- 60リクエスト/分
- 超過時: 429 Too Many Requests
"""

import pytest
import asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.models import OfficeStaff
from app.models.enums import StaffRole, BillingStatus, OfficeType
from tests.utils.dashboard_helpers import create_test_office
from tests.utils.helpers import create_random_staff


@pytest.mark.asyncio
class TestDashboardRateLimit:
    """ダッシュボードAPIのレート制限テスト"""

    async def test_rate_limit_allows_normal_requests(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession
    ):
        """通常のリクエスト数ではレート制限に引っかからない"""
        # Arrange: テストスタッフと事業所を作成
        office = await create_test_office(db_session)
        staff = await create_random_staff(
            db_session,
            role=StaffRole.manager,
            is_mfa_enabled=True
        )
        db_session.add(OfficeStaff(
            staff_id=staff.id,
            office_id=office.id,
            is_primary=True
        ))
        await db_session.commit()

        # 認証トークン取得（ログイン）
        login_response = await async_client.post(
            "/api/v1/auth/login",
            json={
                "email": staff.email,
                "password": "TestPassword123!"
            }
        )
        assert login_response.status_code == 200
        access_token = login_response.json()["access_token"]

        # Act: 10回連続でリクエスト（60リクエスト/分以下）
        for i in range(10):
            response = await async_client.get(
                "/api/v1/dashboard/",
                headers={"Authorization": f"Bearer {access_token}"}
            )

            # Assert: すべて成功
            assert response.status_code == 200, f"Request {i+1} failed with status {response.status_code}"

    async def test_rate_limit_blocks_excessive_requests(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession
    ):
        """過剰なリクエストはレート制限でブロックされる"""
        # Arrange: テストスタッフと事業所を作成
        office = await create_test_office(db_session)
        staff = await create_random_staff(
            db_session,
                        role=StaffRole.manager,
            is_mfa_enabled=True
        )
        await db_session.flush()
        # スタッフと事業所を紐付け
        db_session.add(OfficeStaff(
            staff_id=staff.id,
            office_id=office.id,
            is_primary=True
        ))
        await db_session.commit()

        # 認証トークン取得
        login_response = await async_client.post(
            "/api/v1/auth/login",
            json={
                "email": staff.email,
                "password": "TestPassword123!"
            }
        )
        assert login_response.status_code == 200
        access_token = login_response.json()["access_token"]

        # Act: 65回連続でリクエスト（60リクエスト/分を超える）
        success_count = 0
        rate_limited_count = 0

        for i in range(65):
            response = await async_client.get(
                "/api/v1/dashboard/",
                headers={"Authorization": f"Bearer {access_token}"}
            )

            if response.status_code == 200:
                success_count += 1
            elif response.status_code == 429:
                rate_limited_count += 1

            # 短時間で大量リクエストを送る
            await asyncio.sleep(0.01)

        # Assert: 60リクエストまで成功、それ以降は429エラー
        assert success_count <= 60, f"Expected max 60 successful requests, got {success_count}"
        assert rate_limited_count > 0, "Expected some requests to be rate limited"

    async def test_rate_limit_response_format(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession
    ):
        """レート制限エラーのレスポンス形式が正しい"""
        # Arrange: テストスタッフと事業所を作成
        office = await create_test_office(db_session)
        staff = await create_random_staff(
            db_session,
                        role=StaffRole.manager,
            is_mfa_enabled=True
        )
        await db_session.flush()
        # スタッフと事業所を紐付け
        db_session.add(OfficeStaff(
            staff_id=staff.id,
            office_id=office.id,
            is_primary=True
        ))
        await db_session.commit()

        # 認証トークン取得
        login_response = await async_client.post(
            "/api/v1/auth/login",
            json={
                "email": staff.email,
                "password": "TestPassword123!"
            }
        )
        assert login_response.status_code == 200
        access_token = login_response.json()["access_token"]

        # Act: レート制限に到達するまでリクエスト
        response_429 = None
        for i in range(65):
            response = await async_client.get(
                "/api/v1/dashboard/",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            if response.status_code == 429:
                response_429 = response
                break
            await asyncio.sleep(0.01)

        # Assert: 429エラーのレスポンス形式
        assert response_429 is not None, "Expected to hit rate limit"
        assert response_429.status_code == 429

        # レスポンスヘッダーにレート制限情報が含まれる
        assert "X-RateLimit-Limit" in response_429.headers or "Retry-After" in response_429.headers

    async def test_rate_limit_per_user(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession
    ):
        """レート制限はユーザーごとに独立している"""
        # Arrange: 2人のスタッフを作成
        office = await create_test_office(db_session)
        staff1 = await create_random_staff(
            db_session,
            role=StaffRole.manager,
            is_mfa_enabled=True
        )
        staff2 = await create_random_staff(
            db_session,
            role=StaffRole.manager,
            is_mfa_enabled=True
        )
        await db_session.flush()
        # 両スタッフと事業所を紐付け
        db_session.add(OfficeStaff(
            staff_id=staff1.id,
            office_id=office.id,
            is_primary=True
        ))
        db_session.add(OfficeStaff(
            staff_id=staff2.id,
            office_id=office.id,
            is_primary=True
        ))
        await db_session.commit()

        # スタッフ1のトークン取得
        login1 = await async_client.post(
            "/api/v1/auth/login",
            json={
                "email": staff1.email,
                "password": "TestPassword123!"
            }
        )
        token1 = login1.json()["access_token"]

        # スタッフ2のトークン取得
        login2 = await async_client.post(
            "/api/v1/auth/login",
            json={
                "email": staff2.email,
                "password": "TestPassword123!"
            }
        )
        token2 = login2.json()["access_token"]

        # Act: スタッフ1で30回、スタッフ2で30回リクエスト
        for i in range(30):
            response1 = await async_client.get(
                "/api/v1/dashboard/",
                headers={"Authorization": f"Bearer {token1}"}
            )
            response2 = await async_client.get(
                "/api/v1/dashboard/",
                headers={"Authorization": f"Bearer {token2}"}
            )

            # Assert: どちらも成功（レート制限に引っかからない）
            assert response1.status_code == 200, f"Staff1 request {i+1} failed"
            assert response2.status_code == 200, f"Staff2 request {i+1} failed"

            await asyncio.sleep(0.01)

    @pytest.mark.performance
    async def test_rate_limit_performance(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession
    ):
        """レート制限のパフォーマンステスト（オーバーヘッド確認）"""
        # Arrange
        office = await create_test_office(db_session)
        staff = await create_random_staff(
            db_session,
                        role=StaffRole.manager,
            is_mfa_enabled=True
        )
        await db_session.flush()
        # スタッフと事業所を紐付け
        db_session.add(OfficeStaff(
            staff_id=staff.id,
            office_id=office.id,
            is_primary=True
        ))
        await db_session.commit()

        # 認証トークン取得
        login_response = await async_client.post(
            "/api/v1/auth/login",
            json={
                "email": staff.email,
                "password": "TestPassword123!"
            }
        )
        token = login_response.json()["access_token"]

        # Act: レート制限のオーバーヘッド測定
        import time
        start_time = time.time()

        for i in range(10):
            response = await async_client.get(
                "/api/v1/dashboard/",
                headers={"Authorization": f"Bearer {token}"}
            )
            assert response.status_code == 200

        elapsed_time = time.time() - start_time

        # Assert: レート制限によるオーバーヘッドが小さい（10リクエストで5秒以内）
        assert elapsed_time < 5.0, f"Rate limiting overhead too high: {elapsed_time}s"
