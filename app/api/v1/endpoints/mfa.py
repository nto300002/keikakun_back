from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud, models, schemas
from app.api import deps
from app.core.security import create_access_token, verify_password
from app.services.mfa import MfaService


class MFACode(BaseModel):
    totp_code: str


class MFADisableRequest(BaseModel):
    password: str

router = APIRouter()


@router.post(
    "/mfa/enroll",
    response_model=schemas.MfaEnrollmentResponse,
    status_code=status.HTTP_200_OK,
    summary="MFA登録開始",
    description="ユーザーのMFA登録を開始し、QRコード生成用の情報とMFAシークレットを返します。",
)
async def enroll_mfa(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.Staff = Depends(deps.get_current_user),
) -> schemas.MfaEnrollmentResponse:
    """
    MFA（多要素認証）の登録を開始します。

    - **current_user**: 認証された有効なスタッフユーザー。

    ユーザーがMFAを既に有効にしている場合は、400 Bad Requestエラーを返します。
    成功した場合、TOTP URIとMFAシークレットを含むレスポンスを返します。
    """
    if current_user.is_mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is already enabled for this user.",
        )

    mfa_service = MfaService(db)
    mfa_enrollment_data = await mfa_service.enroll(user=current_user)

    return schemas.MfaEnrollmentResponse(
        secret_key=mfa_enrollment_data["secret_key"],
        qr_code_uri=mfa_enrollment_data["qr_code_uri"],
    )


@router.post(
    "/mfa/verify",
    status_code=status.HTTP_200_OK,
    summary="MFA検証と有効化",
    description="提供されたTOTPコードを検証し、検証が成功した場合にユーザーのMFAを有効化します。",
)
async def verify_mfa(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.Staff = Depends(deps.get_current_user),
    code_data: MFACode,
) -> dict[str, str]:
    """
    TOTPコードを検証し、MFAを有効化します。

    - **current_user**: 認証された有効なスタッフユーザー。
    - **code_data**: 検証に使用するTOTPコードを含むデータ。

    ユーザーがMFAを登録していない、または既に有効化している場合はエラーを返します。
    TOTPコードが無効な場合もエラーを返します。
    成功した場合、MFAが有効化されたことを示すメッセージを返します。
    """
    if not current_user.mfa_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is not enrolled for this user.",
        )

    if current_user.is_mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is already enabled.",
        )

    mfa_service = MfaService(db)
    is_valid = await mfa_service.verify(
        user=current_user, totp_code=code_data.totp_code
    )

    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid TOTP code."
        )

    return {"message": "MFA verification successful"}


@router.post(
    "/mfa/disable",
    status_code=status.HTTP_200_OK,
    summary="MFA無効化",
    description="ユーザーのMFAを無効化します。パスワード確認が必要です。",
)
async def disable_mfa(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.Staff = Depends(deps.get_current_user),
    disable_data: MFADisableRequest,
) -> dict[str, str]:
    """
    ユーザーのMFAを無効化します。

    - **current_user**: 認証された有効なスタッフユーザー。
    - **disable_data**: パスワード確認のためのデータ。

    ユーザーがMFAを有効化していない場合はエラーを返します。
    パスワードが正しくない場合もエラーを返します。
    成功した場合、MFAが無効化されたことを示すメッセージを返します。
    """
    if not current_user.is_mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is not enabled for this user.",
        )

    # パスワード確認
    if not verify_password(disable_data.password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password.",
        )

    # MFAを無効化
    await current_user.disable_mfa(db)
    await db.commit()

    return {"message": "MFA disabled successfully"}



