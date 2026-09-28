"""Integration coverage for the public 422 validation-error contract."""
from typing import Annotated
from uuid import UUID

import pytest
from fastapi import FastAPI, File, Header, Query
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, Field

from app.main import validation_exception_handler


class _NestedProfile(BaseModel):
    password: Annotated[str, Field(min_length=12)]


class _NestedPayload(BaseModel):
    profile: _NestedProfile


def _create_validation_app() -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_exception_handler)

    @app.post("/json")
    async def validate_json(payload: _NestedPayload):
        return payload

    @app.get("/query")
    async def validate_query(token: Annotated[str, Query(pattern="^safe$")]):
        return {"token": token}

    @app.get("/header")
    async def validate_header(authorization: Annotated[str, Header(pattern="^safe$")]):
        return {"authorization": authorization}

    @app.get("/path/{recipient_id}")
    async def validate_path(recipient_id: UUID):
        return {"recipient_id": str(recipient_id)}

    @app.post("/multipart")
    async def validate_multipart(attachment: Annotated[bytes, File(max_length=3)]):
        return {"size": len(attachment)}

    return app


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "request_kwargs", "raw_value", "location_source"),
    [
        (
            "post",
            "/json",
            {"json": {"profile": {"password": "pw-secret"}}},
            "pw-secret",
            "body",
        ),
        (
            "get",
            "/query",
            {"params": {"token": "query-token-value-must-not-appear"}},
            "query-token-value-must-not-appear",
            "query",
        ),
        (
            "get",
            "/header",
            {"headers": {"authorization": "header-credential-must-not-appear"}},
            "header-credential-must-not-appear",
            "header",
        ),
        (
            "get",
            "/path/not-a-uuid-value",
            {},
            "not-a-uuid-value",
            "path",
        ),
        (
            "post",
            "/multipart",
            {"files": {"attachment": ("private.txt", b"multipart-private-content-must-not-appear")}},
            "multipart-private-content-must-not-appear",
            "body",
        ),
    ],
)
async def test_validation_error_requests_return_only_safe_schema(
    method,
    path,
    request_kwargs,
    raw_value,
    location_source,
):
    """FastAPI request parsing cannot reintroduce raw values into a 422 response."""
    app = _create_validation_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
        response = await getattr(client, method)(path, **request_kwargs)

    assert response.status_code == 422
    assert raw_value not in response.text
    assert response.json()["detail"][0]["loc"] == [location_source]
    assert set(response.json()["detail"][0]) == {"loc", "code", "message"}
