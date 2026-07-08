from datetime import timedelta

import pytest
from httpx import AsyncClient

from app.core.security import create_access_token


ADMIN_GET_ENDPOINTS = [
    "/api/v1/admin/audit-logs",
    "/api/v1/admin/inquiries",
    "/api/v1/admin/offices",
    "/api/v1/admin/announcements",
    "/api/v1/admin/archived-staffs/",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ADMIN_GET_ENDPOINTS)
async def test_admin_get_endpoints_reject_non_app_admin(
    async_client: AsyncClient,
    owner_user_factory,
    endpoint: str,
):
    owner = await owner_user_factory()
    access_token = create_access_token(str(owner.id), timedelta(minutes=30))

    response = await async_client.get(
        endpoint,
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ADMIN_GET_ENDPOINTS)
async def test_admin_get_endpoints_reject_unauthenticated(
    async_client: AsyncClient,
    endpoint: str,
):
    response = await async_client.get(endpoint)

    assert response.status_code == 401
