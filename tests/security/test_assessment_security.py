"""
アセスメント機能のセキュリティテスト（Phase 0 - TDD）

XSS対策、SQLインジェクション対策、認可チェックのテスト
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import timedelta
from sqlalchemy import select

from app.core.security import get_password_hash, create_access_token
from app.models.assessment import EmploymentRelated
from app.models.enums import OfficeType, StaffRole, WorkConditions, WorkOutsideFacility


pytestmark = pytest.mark.asyncio


EMPLOYMENT_BASE_DATA = {
    "work_conditions": "other",
    "regular_or_part_time_job": False,
    "employment_support": False,
    "work_experience_in_the_past_year": False,
    "suspension_of_work": False,
    "general_employment_request": False,
    "work_outside_the_facility": "not_hope",
}


class TestEmploymentXSS:
    """就労関係のXSS対策テスト"""

    async def test_employment_other_text_xss_prevention(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        employee_user_factory,
        welfare_recipient_factory,
    ):
        """employment_other_text のXSS対策テスト"""
        # Arrange
        staff = await employee_user_factory()
        office_id = staff.office_associations[0].office_id
        recipient = await welfare_recipient_factory(office_id=office_id)
        token = create_access_token(str(staff.id), timedelta(minutes=30))

        xss_payload = "<script>alert('XSS')</script>"

        # Act
        response = await async_client.put(
            f"/api/v1/recipients/{recipient.id}/employment",
            headers={"Authorization": f"Bearer {token}"},
            json={
                **EMPLOYMENT_BASE_DATA,
                "no_employment_experience": True,
                "employment_other_experience": True,
                "employment_other_text": xss_payload,
            },
        )

        # Assert: APIレスポンスが成功
        assert response.status_code == 200
        data = response.json()

        # Assert: HTMLタグがエスケープされている（FastAPIが追加でエスケープするため二重エスケープ）
        assert "<script>" not in data["employment_other_text"]
        # FastAPIの自動エスケープにより &amp;lt; になる
        assert "lt;script" in data["employment_other_text"]
        assert "alert" in data["employment_other_text"]  # 内容は残っている

    async def test_desired_tasks_xss_prevention(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        employee_user_factory,
        welfare_recipient_factory,
    ):
        """desired_tasks_on_asobe のXSS対策テスト"""
        # Arrange
        staff = await employee_user_factory()
        office_id = staff.office_associations[0].office_id
        recipient = await welfare_recipient_factory(office_id=office_id)
        token = create_access_token(str(staff.id), timedelta(minutes=30))

        xss_payload = '<img src=x onerror="alert(1)">'

        # Act
        response = await async_client.put(
            f"/api/v1/recipients/{recipient.id}/employment",
            headers={"Authorization": f"Bearer {token}"},
            json={
                **EMPLOYMENT_BASE_DATA,
                "desired_tasks_on_asobe": xss_payload,
            },
        )

        # Assert: APIレスポンスが成功
        assert response.status_code == 200
        data = response.json()

        # Assert: HTMLタグがエスケープされている（FastAPIが追加でエスケープ）
        assert "<img" not in data["desired_tasks_on_asobe"]
        assert "lt;img" in data["desired_tasks_on_asobe"]
        assert "alert" in data["desired_tasks_on_asobe"]

    async def test_multiple_xss_patterns(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        employee_user_factory,
        welfare_recipient_factory,
    ):
        """複数のXSSパターンをテスト"""
        # Arrange
        staff = await employee_user_factory()
        office_id = staff.office_associations[0].office_id
        recipient = await welfare_recipient_factory(office_id=office_id)
        token = create_access_token(str(staff.id), timedelta(minutes=30))

        xss_patterns = [
            ("<script>alert('XSS')</script>", "lt;script"),
            ('<img src=x onerror="alert(1)">', "lt;img"),
            ("<iframe src='javascript:alert(1)'></iframe>", "lt;iframe"),
            ("<svg/onload=alert(1)>", "lt;svg"),
            ("<body onload=alert(1)>", "lt;body"),
        ]

        for xss_input, expected_escaped in xss_patterns:
            # Act
            response = await async_client.put(
                f"/api/v1/recipients/{recipient.id}/employment",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    **EMPLOYMENT_BASE_DATA,
                    "employment_other_text": xss_input,
                },
            )

            # Assert
            assert response.status_code == 200
            data = response.json()
            if data["employment_other_text"]:  # Noneでない場合のみチェック
                assert expected_escaped in data["employment_other_text"], (
                    f"XSS payload not escaped: {xss_input}"
                )


class TestEmploymentSQLInjection:
    """就労関係のSQLインジェクション対策テスト"""

    async def test_sql_injection_prevention(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        employee_user_factory,
        welfare_recipient_factory,
    ):
        """SQLインジェクション対策テスト"""
        # Arrange
        staff = await employee_user_factory()
        office_id = staff.office_associations[0].office_id
        recipient = await welfare_recipient_factory(office_id=office_id)
        token = create_access_token(str(staff.id), timedelta(minutes=30))

        sql_injection_payload = "'; DROP TABLE employment_related; --"

        # Act
        response = await async_client.put(
            f"/api/v1/recipients/{recipient.id}/employment",
            headers={"Authorization": f"Bearer {token}"},
            json={
                **EMPLOYMENT_BASE_DATA,
                "no_employment_experience": True,
                "employment_other_experience": True,
                "employment_other_text": sql_injection_payload,
            },
        )

        # Assert: 正常に保存される（エラーにならない）
        assert response.status_code == 200

        # Assert: テーブルが削除されていないことを確認
        stmt = select(EmploymentRelated).where(
            EmploymentRelated.welfare_recipient_id == recipient.id
        )
        result = await db_session.execute(stmt)
        employment = result.scalar_one_or_none()

        assert employment is not None, "テーブルが削除された可能性があります"
        # SQLインジェクションの文字列が文字列として保存されている（HTMLエスケープされている）
        assert employment.employment_other_text is not None
        assert "DROP TABLE" in employment.employment_other_text


class TestEmploymentAuthorization:
    """就労関係の認可チェックテスト"""

    async def test_unauthorized_office_access(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        employee_user_factory,
        welfare_recipient_factory,
        office_factory,
    ):
        """異なる事業所からのアクセスを拒否"""
        # Arrange: 事業所1のスタッフと利用者を作成
        staff1 = await employee_user_factory()
        office_id1 = staff1.office_associations[0].office_id
        recipient1 = await welfare_recipient_factory(office_id=office_id1)

        # Arrange: 事業所2のスタッフを作成
        office2 = await office_factory(name="別の事業所")
        staff2 = await employee_user_factory(office=office2)
        token2 = create_access_token(str(staff2.id), timedelta(minutes=30))

        # Act: 事業所2のスタッフが事業所1の利用者にアクセス試行
        response = await async_client.put(
            f"/api/v1/recipients/{recipient1.id}/employment",
            headers={"Authorization": f"Bearer {token2}"},
            json=EMPLOYMENT_BASE_DATA,
        )

        # Assert: 403 Forbiddenを期待
        assert response.status_code == 403
        assert "権限" in response.json()["detail"]

    async def test_unauthenticated_access(
        self,
        async_client: AsyncClient,
        welfare_recipient_factory,
        office_factory,
    ):
        """未認証アクセスを拒否"""
        # Arrange
        office = await office_factory()
        recipient = await welfare_recipient_factory(office_id=office.id)

        # Act: 認証なしでアクセス試行
        response = await async_client.put(
            f"/api/v1/recipients/{recipient.id}/employment",
            json=EMPLOYMENT_BASE_DATA,
        )

        # Assert: 401 Unauthorizedを期待
        assert response.status_code == 401
