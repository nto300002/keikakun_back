"""WebAuthn credential管理APIの入出力。"""

import datetime
import uuid
from typing import Any

from pydantic import BaseModel, Field


class WebAuthnRegistrationOptionsResponse(BaseModel):
    publicKey: dict[str, Any]


class WebAuthnAuthenticationOptionsRequest(BaseModel):
    pending_token: str = Field(min_length=1)


class WebAuthnAuthenticationOptionsResponse(BaseModel):
    publicKey: dict[str, Any]


class WebAuthnAuthenticationVerifyRequest(BaseModel):
    pending_token: str = Field(min_length=1)
    credential: dict[str, Any]


class WebAuthnRegistrationVerifyRequest(BaseModel):
    credential: dict[str, Any]
    display_name: str = Field(min_length=1, max_length=100)


class WebAuthnCredentialDisplayNameUpdateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)


class WebAuthnCredentialResponse(BaseModel):
    id: uuid.UUID
    display_name: str
    transports: list[str]
    created_at: datetime.datetime
    last_used_at: datetime.datetime | None

    model_config = {"from_attributes": True}
