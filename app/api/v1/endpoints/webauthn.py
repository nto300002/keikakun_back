"""app_admin本人向けWebAuthn credential管理API。"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.limiter import limiter
from app.messages import ja
from app.models.staff import Staff
from app.schemas.webauthn import (
    WebAuthnCredentialDisplayNameUpdateRequest,
    WebAuthnCredentialResponse,
    WebAuthnRegistrationOptionsResponse,
    WebAuthnRegistrationVerifyRequest,
)
from app.services.webauthn_registration import webauthn_registration_service


router = APIRouter()

REGISTRATION_OPTIONS_RATE_LIMIT = "5/minute"
REGISTRATION_VERIFY_RATE_LIMIT = "5/minute"
CREDENTIAL_MANAGEMENT_RATE_LIMIT = "30/minute"


def _get_session_id(request: Request) -> bytes:
    """認証済みリクエストのトークンをchallenge束縛用にだけ使用する。"""
    authorization = request.headers.get("Authorization")
    if authorization and authorization.startswith("Bearer "):
        return authorization.removeprefix("Bearer ").encode("ascii")
    access_token = request.cookies.get("access_token")
    if access_token:
        return access_token.encode("ascii")
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="認証情報を確認できません",
    )


@router.post(
    "/webauthn/registration/options",
    response_model=WebAuthnRegistrationOptionsResponse,
)
@limiter.limit(REGISTRATION_OPTIONS_RATE_LIMIT)
async def begin_registration(
    request: Request,
    db: AsyncSession = Depends(deps.get_db),
    current_user: Staff = Depends(deps.require_app_admin),
    _: None = Depends(deps.validate_csrf),
) -> WebAuthnRegistrationOptionsResponse:
    options = await webauthn_registration_service.begin_registration(
        db,
        staff=current_user,
        session_id=_get_session_id(request),
    )
    return WebAuthnRegistrationOptionsResponse(publicKey=options)


@router.post(
    "/webauthn/registration/verify",
    response_model=WebAuthnCredentialResponse,
)
@limiter.limit(REGISTRATION_VERIFY_RATE_LIMIT)
async def verify_registration(
    request: Request,
    payload: WebAuthnRegistrationVerifyRequest,
    db: AsyncSession = Depends(deps.get_db),
    current_user: Staff = Depends(deps.require_app_admin),
    _: None = Depends(deps.validate_csrf),
) -> WebAuthnCredentialResponse:
    return await webauthn_registration_service.verify_registration(
        db,
        staff=current_user,
        session_id=_get_session_id(request),
        credential=payload.credential,
        display_name=payload.display_name,
    )


@router.get("/webauthn/credentials", response_model=list[WebAuthnCredentialResponse])
@limiter.limit(CREDENTIAL_MANAGEMENT_RATE_LIMIT)
async def list_credentials(
    request: Request,
    db: AsyncSession = Depends(deps.get_db),
    current_user: Staff = Depends(deps.require_app_admin),
) -> list[WebAuthnCredentialResponse]:
    return await webauthn_registration_service.list_credentials(db, staff=current_user)


@router.patch(
    "/webauthn/credentials/{credential_id}",
    response_model=WebAuthnCredentialResponse,
)
@limiter.limit(CREDENTIAL_MANAGEMENT_RATE_LIMIT)
async def update_credential_display_name(
    request: Request,
    credential_id: uuid.UUID,
    payload: WebAuthnCredentialDisplayNameUpdateRequest,
    db: AsyncSession = Depends(deps.get_db),
    current_user: Staff = Depends(deps.require_app_admin),
    _: None = Depends(deps.validate_csrf),
) -> WebAuthnCredentialResponse:
    credential = await webauthn_registration_service.update_display_name(
        db,
        staff=current_user,
        credential_id=credential_id,
        display_name=payload.display_name,
    )
    if credential is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ja.WEBAUTHN_CREDENTIAL_NOT_FOUND,
        )
    return credential


@router.delete("/webauthn/credentials/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(CREDENTIAL_MANAGEMENT_RATE_LIMIT)
async def revoke_credential(
    request: Request,
    credential_id: uuid.UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: Staff = Depends(deps.require_app_admin),
    _: None = Depends(deps.validate_csrf),
) -> Response:
    revoked = await webauthn_registration_service.revoke_credential(
        db, staff=current_user, credential_id=credential_id
    )
    if not revoked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ja.WEBAUTHN_CREDENTIAL_NOT_FOUND,
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
