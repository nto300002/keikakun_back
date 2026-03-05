from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from app import crud, models, schemas
from app.api import deps
from app.core.security import (
    verify_password,
    generate_totp_secret,
    generate_totp_uri,
    generate_recovery_codes,
)
from app.services.mfa import MfaService
from app.messages import ja


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
            detail=ja.MFA_ALREADY_ENABLED,
        )

    mfa_service = MfaService(db)
    mfa_enrollment_data = await mfa_service.enroll_mfa(user=current_user)

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
            detail=ja.MFA_NOT_ENROLLED,
        )

    if current_user.is_mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ja.MFA_ALREADY_ENABLED,
        )

    mfa_service = MfaService(db)

    is_valid = await mfa_service.verify_mfa(
        user=current_user, totp_code=code_data.totp_code
    )

    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=ja.MFA_INVALID_CODE
        )

    return {"message": ja.MFA_VERIFICATION_SUCCESS}


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
            detail=ja.MFA_NOT_ENABLED,
        )

    # パスワード確認
    if not verify_password(disable_data.password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ja.MFA_INCORRECT_PASSWORD,
        )

    # MFAを無効化
    await MfaService(db).disable_mfa(user=current_user)

    return {"message": ja.MFA_DISABLED_SUCCESS}


# ==========================================
# 管理者によるMFA管理エンドポイント
# ==========================================

@router.post(
    "/admin/staff/{staff_id}/mfa/enable",
    response_model=schemas.AdminMfaEnableResponse,
    status_code=status.HTTP_200_OK,
    summary="管理者によるMFA有効化",
    description="管理者が指定したスタッフのMFAを有効化します。",
)
async def admin_enable_staff_mfa(
    *,
    staff_id: uuid.UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_admin: models.Staff = Depends(deps.require_owner),
) -> schemas.AdminMfaEnableResponse:
    """
    管理者が指定したスタッフのMFAを有効化します。

    - **staff_id**: 対象スタッフのID
    - **current_admin**: 管理者権限（owner）を持つ認証されたスタッフ

    スタッフが見つからない場合は404エラーを返します。
    既にMFAが有効な場合は400エラーを返します。
    成功した場合、MFAが有効化されたことを示すメッセージを返します。
    """
    # 対象スタッフを取得
    target_staff = await crud.staff.get(db, id=staff_id)
    if not target_staff:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ja.STAFF_NOT_FOUND,
        )

    # 既にMFAが有効かチェック
    if target_staff.is_mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ja.MFA_ALREADY_ENABLED,
        )

    # MFAシークレットとリカバリーコードを生成
    secret = generate_totp_secret()
    recovery_codes = generate_recovery_codes(count=10)

    # コミット前に必要な値を取得（コミット後は遅延ロードでエラーになる）
    staff_email = target_staff.email
    staff_full_name = target_staff.full_name
    staff_id = target_staff.id

    # MFAを有効化（暗号化とリカバリーコード保存を含む）
    await MfaService(db).admin_enable_staff_mfa(
        target_staff=target_staff,
        secret=secret,
        recovery_codes=recovery_codes,
    )

    # QRコードURIを生成（スタッフがTOTPアプリに登録するため）
    qr_code_uri = generate_totp_uri(staff_email, secret)

    return {
        "message": ja.MFA_ENABLED_SUCCESS,
        "staff_id": str(staff_id),
        "staff_name": staff_full_name,
        "qr_code_uri": qr_code_uri,
        "secret_key": secret,
        "recovery_codes": recovery_codes,
    }


@router.post(
    "/admin/staff/{staff_id}/mfa/disable",
    status_code=status.HTTP_200_OK,
    summary="管理者によるMFA無効化",
    description="管理者が指定したスタッフのMFAを無効化します。",
)
async def admin_disable_staff_mfa(
    *,
    staff_id: uuid.UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_admin: models.Staff = Depends(deps.require_owner),
) -> dict[str, str]:
    """
    管理者が指定したスタッフのMFAを無効化します。

    - **staff_id**: 対象スタッフのID
    - **current_admin**: 管理者権限（owner）を持つ認証されたスタッフ

    スタッフが見つからない場合は404エラーを返します。
    既にMFAが無効な場合は400エラーを返します。
    成功した場合、MFAが無効化されたことを示すメッセージを返します。
    """
    # 対象スタッフを取得
    target_staff = await crud.staff.get(db, id=staff_id)
    if not target_staff:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ja.STAFF_NOT_FOUND,
        )

    # 既にMFAが無効かチェック
    if not target_staff.is_mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ja.MFA_NOT_ENABLED,
        )

    # MFAを無効化
    await MfaService(db).admin_disable_staff_mfa(target_staff=target_staff)

    return {"message": ja.MFA_DISABLED_SUCCESS}


@router.post(
    "/admin/office/mfa/disable-all",
    status_code=status.HTTP_200_OK,
    summary="事務所全スタッフのMFA一括無効化",
    description="管理者が所属事務所の全スタッフのMFAを一括無効化します。"
)
async def disable_all_office_mfa(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.Staff = Depends(deps.require_manager_or_owner),
):
    """
    管理者が所属事務所の全スタッフのMFAを一括無効化

    - **current_user**: Manager または Owner ロールの認証済みユーザー
    - **権限**: Manager または Owner のみ実行可能
    - **対象**: 現在のユーザーが所属する事務所の全スタッフ

    Returns:
        - message: 成功メッセージ
        - disabled_count: 無効化されたスタッフ数
    """
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.office import OfficeStaff

    # ユーザーの所属事務所を取得
    stmt = (
        select(models.Staff)
        .options(selectinload(models.Staff.office_associations)
        .selectinload(OfficeStaff.office))
        .where(models.Staff.id == current_user.id)
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not user.office_associations:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ja.OFFICE_NOT_FOUND_FOR_USER,
        )

    # 事務所を取得
    office = user.office_associations[0].office
    if not office:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ja.OFFICE_INFO_NOT_FOUND,
        )

    # 事務所に所属する全スタッフを取得
    stmt_staffs = (
        select(models.Staff)
        .join(OfficeStaff, models.Staff.id == OfficeStaff.staff_id)
        .where(OfficeStaff.office_id == office.id)
    )
    result_staffs = await db.execute(stmt_staffs)
    all_staffs = result_staffs.scalars().all()

    # MFAが有効なスタッフのみ無効化
    try:
        disabled_count = await MfaService(db).disable_all_office_mfa(all_staffs=all_staffs)
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"[DISABLE ALL MFA] Failed to disable MFA for office {office.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="MFA一括無効化中にエラーが発生しました。管理者に連絡してください。"
        )

    return {
        "message": f"{disabled_count}名のスタッフのMFAを無効化しました。",
        "disabled_count": disabled_count
    }


@router.post(
    "/admin/office/mfa/enable-all",
    status_code=status.HTTP_200_OK,
    summary="事務所全スタッフのMFA一括有効化",
    description="管理者が所属事務所の全スタッフのMFAを一括有効化します。"
)
async def enable_all_office_mfa(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.Staff = Depends(deps.require_manager_or_owner),
):
    """
    管理者が所属事務所の全スタッフのMFAを一括有効化

    - **current_user**: Manager または Owner ロールの認証済みユーザー
    - **権限**: Manager または Owner のみ実行可能
    - **対象**: 現在のユーザーが所属する事務所の全スタッフ

    Returns:
        - message: 成功メッセージ
        - enabled_count: 有効化されたスタッフ数
        - staff_mfa_data: 各スタッフのMFA設定情報（QRコード、シークレットキー、リカバリーコード）
    """
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.office import OfficeStaff

    # ユーザーの所属事務所を取得
    stmt = (
        select(models.Staff)
        .options(selectinload(models.Staff.office_associations)
        .selectinload(OfficeStaff.office))
        .where(models.Staff.id == current_user.id)
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not user.office_associations:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ja.OFFICE_NOT_FOUND_FOR_USER,
        )

    # 事務所を取得
    office = user.office_associations[0].office
    if not office:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ja.OFFICE_INFO_NOT_FOUND,
        )

    # 事務所に所属する全スタッフを取得
    stmt_staffs = (
        select(models.Staff)
        .join(OfficeStaff, models.Staff.id == OfficeStaff.staff_id)
        .where(OfficeStaff.office_id == office.id)
    )
    result_staffs = await db.execute(stmt_staffs)
    all_staffs = result_staffs.scalars().all()

    # MFAが無効なスタッフのみ有効化し、設定情報を収集
    try:
        enabled_count, staff_mfa_data = await MfaService(db).enable_all_office_mfa(
            all_staffs=all_staffs
        )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"[ENABLE ALL MFA] Failed to enable MFA for office {office.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="MFA一括有効化中にエラーが発生しました。管理者に連絡してください。"
        )

    return {
        "message": f"{enabled_count}名のスタッフのMFAを有効化しました。",
        "enabled_count": enabled_count,
        "staff_mfa_data": staff_mfa_data
    }



