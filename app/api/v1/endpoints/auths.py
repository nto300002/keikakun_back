import os
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Request, Form, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from jose import jwt, JWTError
from pydantic import ValidationError
from typing import Optional

from app import crud, schemas, models
from app.api import deps
from app.api.deps import get_current_user
from app.core.limiter import limiter
from app.core.security import (
    verify_password, create_access_token, create_refresh_token, ALGORITHM
)
from app.messages import ja

from app.core.security import (
    verify_password, create_access_token, create_refresh_token, ALGORITHM,
    create_email_verification_token, verify_email_verification_token,
    create_temporary_token, verify_temporary_token, verify_temporary_token_with_session, verify_totp,
    generate_totp_uri
)
from app.core.mail import send_verification_email
from pydantic import BaseModel
from app.models.office import OfficeStaff

class MFAVerifyRequest(BaseModel):
    temporary_token: str
    totp_code: str = None
    recovery_code: str = None

# DIするためのヘルパー関数
async def get_staff_crud():
    return crud.staff

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post(
    "/register-admin",
    response_model=schemas.staff.Staff,
    status_code=status.HTTP_201_CREATED,
)
async def register_admin(
    *,
    db: AsyncSession = Depends(deps.get_db),
    staff_in: schemas.staff.AdminCreate,
    staff_crud=Depends(get_staff_crud),
):
    """
    サービス責任者ロールを持つ新しいスタッフを作成し、確認メールを送信します。
    """
    user = await staff_crud.get_by_email(db, email=staff_in.email)
    if user:
        raise HTTPException(
            status_code=409,  # Conflict
            detail=ja.AUTH_EMAIL_ALREADY_EXISTS,
        )

    user = await staff_crud.create_admin(db=db, obj_in=staff_in)

    # コミットするとuserオブジェクトが期限切れになり、user.emailにアクセスできなくなるため
    # 先にメールアドレスとIDを変数に格納しておく
    user_email = user.email
    user_id = user.id
    await db.commit()

    # DBから最新の状態を読み込み、office_associationsもeager loadする
    stmt = select(models.Staff).options(
        selectinload(models.Staff.office_associations).selectinload(OfficeStaff.office)
    ).where(models.Staff.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one()

    # メール確認トークンを生成して送信
    token = create_email_verification_token(email=user_email)
    await send_verification_email(recipient_email=user_email, token=token)

    return user


@router.post(
    "/register",
    response_model=schemas.staff.Staff,
    status_code=status.HTTP_201_CREATED,
)
async def register_staff(
    *,
    db: AsyncSession = Depends(deps.get_db),
    staff_in: schemas.staff.StaffCreate,
    staff_crud=Depends(get_staff_crud),
):
    """
    一般スタッフ（employee/manager）として新しいスタッフを作成し、確認メールを送信します。
    """
    user = await staff_crud.get_by_email(db, email=staff_in.email)
    if user:
        raise HTTPException(
            status_code=409,  # Conflict
            detail=ja.AUTH_EMAIL_ALREADY_EXISTS,
        )

    # staff_in.role は StaffCreate スキーマのバリデーターによって
    # `owner` でないことが保証されている
    user = await staff_crud.create_staff(db=db, obj_in=staff_in)

    user_email = user.email
    user_id = user.id
    await db.commit()

    # DBから最新の状態を読み込み、office_associationsもeager loadする
    stmt = select(models.Staff).options(
        selectinload(models.Staff.office_associations).selectinload(OfficeStaff.office)
    ).where(models.Staff.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one()

    token = create_email_verification_token(email=user_email)
    await send_verification_email(recipient_email=user_email, token=token)

    return user


@router.get("/verify-email")
async def verify_email(
    token: str,
    db: AsyncSession = Depends(deps.get_db),
    staff_crud=Depends(get_staff_crud),
):
    """
    メール確認トークンを検証し、ユーザーを有効化します。
    """
    email = verify_email_verification_token(token)
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ja.AUTH_INVALID_TOKEN,
        )

    user = await staff_crud.get_by_email(db, email=email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ja.AUTH_USER_NOT_FOUND,
        )

    if user.is_email_verified:
        return {"message": ja.AUTH_EMAIL_ALREADY_VERIFIED, "role": user.role}

    # commit前にroleを保存
    user_role = user.role
    user.is_email_verified = True
    db.add(user)
    await db.commit()

    return {"message": ja.AUTH_EMAIL_VERIFIED, "role": user_role}



@router.post("/token") # response_modelを削除
@limiter.limit("5/minute")
async def login_for_access_token(
    *,
    response: Response,  # Cookie設定のため追加
    request: Request,  # limiterがIPアドレスを取得するために必要
    db: AsyncSession = Depends(deps.get_db),
    username: str = Form(...),
    password: str = Form(...),
    staff_crud=Depends(get_staff_crud),
):
    """
    OAuth2 compatible token login, get an access token for future requests
    """
    user = await staff_crud.get_by_email(db, email=username)
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ja.AUTH_INCORRECT_CREDENTIALS,
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_email_verified:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ja.AUTH_EMAIL_NOT_VERIFIED,
            headers={"WWW-Authenticate": "Bearer"},
        )

    # セッション期間を常に1時間に固定
    session_duration = 3600  # 1時間（秒）
    session_type = "standard"

    if user.is_mfa_enabled:
        temporary_token = create_temporary_token(
            user_id=str(user.id),
            token_type="mfa_verify",
            session_duration=session_duration,
            session_type=session_type
        )

        # 管理者が設定したが、ユーザーが未検証の場合 → 初回検証フロー
        if not user.is_mfa_verified_by_user:
            try:
                decrypted_secret = user.get_mfa_secret()
                qr_code_uri = generate_totp_uri(user.email, decrypted_secret)

                return {
                    "requires_mfa_first_setup": True,
                    "temporary_token": temporary_token,
                    "qr_code_uri": qr_code_uri,
                    "secret_key": decrypted_secret,
                    "message": "管理者がMFAを設定しました。以下の情報でTOTPアプリに登録してください。",
                    "token_type": "bearer",
                    "session_duration": session_duration,
                    "session_type": session_type,
                }
            except ValueError as e:
                # シークレット復号化失敗 → MFAをリセット
                logger.error(f"[LOGIN MFA] Secret decryption failed for {user.email}: {str(e)}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="MFA設定にエラーがあります。管理者に連絡してください。",
                )

        # 通常のMFA検証フロー
        return {
            "requires_mfa_verification": True,
            "temporary_token": temporary_token,
            "token_type": "bearer",
            "session_duration": session_duration,
            "session_type": session_type,
        }

    access_token = create_access_token(
        subject=str(user.id),
        expires_delta_seconds=session_duration,
        session_type=session_type
    )
    refresh_token = create_refresh_token(
        subject=str(user.id),
        session_duration=session_duration,
        session_type=session_type
    )

    # Cookie設定
    environment_value = os.getenv("ENVIRONMENT")
    is_production = environment_value == "production"
    cookie_domain = os.getenv("COOKIE_DOMAIN", None)
    cookie_samesite = os.getenv("COOKIE_SAMESITE", None)  # 未設定の場合はNone

    # 環境変数の値を検証（コメントや日本語が含まれていないかチェック）
    if cookie_domain:
        cookie_domain = cookie_domain.strip()
        # コメント記号で始まる、または空の場合はNoneに設定
        if cookie_domain.startswith('#') or not cookie_domain:
            cookie_domain = None
        else:
            # latin-1でエンコード可能かチェック（日本語等を除外）
            try:
                cookie_domain.encode('latin-1')
            except UnicodeEncodeError:
                logger.warning(f"[LOGIN COOKIE] Invalid COOKIE_DOMAIN (contains non-latin-1 characters): {cookie_domain}")
                cookie_domain = None

    if cookie_samesite:
        cookie_samesite = cookie_samesite.strip().lower()
        # 有効な値のみを許可
        if cookie_samesite not in ['none', 'lax', 'strict']:
            logger.warning(f"[LOGIN COOKIE] Invalid COOKIE_SAMESITE value: {cookie_samesite}")
            cookie_samesite = None

    # デバッグログ
    logger.info(f"[LOGIN COOKIE DEBUG] ENVIRONMENT={environment_value}, is_production={is_production}")
    logger.info(f"[LOGIN COOKIE DEBUG] COOKIE_DOMAIN={cookie_domain}, COOKIE_SAMESITE={cookie_samesite}")

    cookie_options = {
        "key": "access_token",
        "value": access_token,
        "httponly": True,
        "secure": is_production,
        "max_age": session_duration,
        # 開発環境(HTTP): SameSite=Lax (localhost間は同一サイトとみなされる)
        # 本番環境(HTTPS): SameSite=None (クロスオリジンでCookie送信が必要、secure=Trueと組み合わせ)
        "samesite": cookie_samesite if cookie_samesite else ("none" if is_production else "lax"),
    }
    if cookie_domain:
        cookie_options["domain"] = cookie_domain

    logger.info(f"[LOGIN COOKIE DEBUG] Cookie options: secure={cookie_options['secure']}, samesite={cookie_options['samesite']}, domain={cookie_options.get('domain', 'not set')}")

    response.set_cookie(**cookie_options)

    # セキュリティ向上: レスポンスボディからaccess_tokenを削除
    # トークンはCookieでのみ送信される（refresh_tokenは保持）
    return {
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "session_duration": session_duration,
        "session_type": session_type,
        "message": ja.AUTH_LOGIN_SUCCESS
    }


@router.post("/refresh-token", response_model=schemas.TokenRefreshResponse)
async def refresh_access_token(
    response: Response,  # Cookie設定のため追加
    refresh_token_data: schemas.RefreshToken
):
    """
    Refresh access token
    """
    try:
        secret_key = os.getenv("SECRET_KEY", "test_secret_key_for_pytest")
        payload = jwt.decode(
            refresh_token_data.refresh_token, secret_key, algorithms=[ALGORITHM]
        )

        # セッション情報を取得
        user_id = payload.get("sub")
        session_duration = payload.get("session_duration", 3600)  # デフォルト1時間
        session_type = payload.get("session_type", "standard")

        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ja.AUTH_INVALID_REFRESH_TOKEN,
                headers={"WWW-Authenticate": "Bearer"},
            )

    except (JWTError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ja.AUTH_INVALID_REFRESH_TOKEN,
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 元のセッション種別を維持して新しいアクセストークンを発行
    new_access_token = create_access_token(
        subject=user_id,
        expires_delta_seconds=session_duration,
        session_type=session_type
    )

    # Cookie設定
    is_production = os.getenv("ENVIRONMENT") == "production"
    cookie_domain = os.getenv("COOKIE_DOMAIN", None)
    cookie_samesite = os.getenv("COOKIE_SAMESITE", None)  # 未設定の場合はNone

    cookie_options = {
        "key": "access_token",
        "value": new_access_token,
        "httponly": True,
        "secure": is_production,
        "max_age": session_duration,
        # samesiteのデフォルトは'lax'なので、開発環境ではNoneを明示的に設定
        "samesite": cookie_samesite if cookie_samesite else "none" if not is_production else "lax",
    }
    if cookie_domain:
        cookie_options["domain"] = cookie_domain

    response.set_cookie(**cookie_options)

    # セキュリティ向上: レスポンスボディからaccess_tokenを削除
    return {
        "token_type": "bearer",
        "session_duration": session_duration,
        "session_type": session_type,
        "message": ja.AUTH_TOKEN_REFRESHED
    }


@router.post("/token/verify-mfa", response_model=schemas.TokenWithCookie)
async def verify_mfa_for_login(
    *,
    response: Response,  # Cookie設定のため追加
    db: AsyncSession = Depends(deps.get_db),
    mfa_data: MFAVerifyRequest,
    staff_crud=Depends(get_staff_crud),
):
    logger.info(f"[MFA VERIFY] Starting MFA verification")
    logger.info(f"[MFA VERIFY] temporary_token length: {len(mfa_data.temporary_token) if mfa_data.temporary_token else 0}")
    logger.info(f"[MFA VERIFY] totp_code: {mfa_data.totp_code}")

    token_data = verify_temporary_token_with_session(mfa_data.temporary_token, expected_type="mfa_verify")
    if not token_data:
        logger.error(f"[MFA VERIFY] Invalid temporary token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ja.AUTH_INVALID_TEMPORARY_TOKEN,
        )

    user_id = token_data["user_id"]
    session_duration = token_data["session_duration"]
    session_type = token_data["session_type"]
    logger.info(f"[MFA VERIFY] Token validated, user_id: {user_id}")

    user = await staff_crud.get(db, id=user_id)
    if not user:
        logger.error(f"[MFA VERIFY] User not found: {user_id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=ja.AUTH_MFA_NOT_CONFIGURED
        )
    if not user.is_mfa_enabled:
        logger.error(f"[MFA VERIFY] MFA not enabled for user: {user_id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=ja.AUTH_MFA_NOT_CONFIGURED
        )

    logger.info(f"[MFA VERIFY] User found, MFA enabled: {user.is_mfa_enabled}")
    logger.info(f"[MFA VERIFY] MFA secret exists: {bool(user.mfa_secret)}")

    # Verify either TOTP code or recovery code
    verification_successful = False

    if mfa_data.totp_code:
        logger.info(f"[MFA VERIFY] Attempting TOTP verification")
        if user.mfa_secret:
            try:
                # MFA secretは暗号化されているため、復号化が必要
                decrypted_secret = user.get_mfa_secret()
                logger.info(f"[MFA VERIFY] Secret decrypted successfully: {bool(decrypted_secret)}")
                totp_result = verify_totp(secret=decrypted_secret, token=mfa_data.totp_code)
                logger.info(f"[MFA VERIFY] TOTP verification result: {totp_result}")
                if totp_result:
                    verification_successful = True
            except ValueError as e:
                # シークレット復号化失敗 → MFAに問題がある
                logger.error(f"[MFA VERIFY] Secret decryption failed for user {user.email}: {str(e)}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="MFA設定にエラーがあります。管理者に連絡してください。",
                )
        else:
            logger.error(f"[MFA VERIFY] MFA secret is missing")

    if mfa_data.recovery_code and not verification_successful:
        logger.info(f"[MFA VERIFY] Attempting recovery code verification")
        from app.core.security import verify_recovery_code
        from app.models.mfa import MFABackupCode
        from sqlalchemy import select

        # データベースから未使用のリカバリーコードを取得
        stmt = select(MFABackupCode).where(
            MFABackupCode.staff_id == user.id,
            MFABackupCode.is_used == False
        )
        result = await db.execute(stmt)
        backup_codes = result.scalars().all()

        # 各リカバリーコードと照合
        for backup_code in backup_codes:
            if verify_recovery_code(mfa_data.recovery_code, backup_code.code_hash):
                # マッチした場合、使用済みとしてマーク
                backup_code.mark_as_used()
                await db.commit()
                verification_successful = True
                logger.info(f"[MFA VERIFY] Recovery code verified successfully")
                break

    if not verification_successful:
        logger.error(f"[MFA VERIFY] Verification failed")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ja.AUTH_INVALID_MFA_CODE
        )

    access_token = create_access_token(
        subject=str(user.id),
        expires_delta_seconds=session_duration,
        session_type=session_type
    )
    refresh_token = create_refresh_token(
        subject=str(user.id),
        session_duration=session_duration,
        session_type=session_type
    )

    # Cookie設定
    environment_value = os.getenv("ENVIRONMENT")
    is_production = environment_value == "production"
    cookie_domain = os.getenv("COOKIE_DOMAIN", None)
    cookie_samesite = os.getenv("COOKIE_SAMESITE", None)  # 未設定の場合はNone

    # デバッグログ
    logger.info(f"[MFA COOKIE DEBUG] ENVIRONMENT={environment_value}, is_production={is_production}")
    logger.info(f"[MFA COOKIE DEBUG] COOKIE_DOMAIN={cookie_domain}, COOKIE_SAMESITE={cookie_samesite}")

    cookie_options = {
        "key": "access_token",
        "value": access_token,
        "httponly": True,
        "secure": is_production,
        "max_age": session_duration,
        # 開発環境(HTTP): SameSite=Lax (localhost間は同一サイトとみなされる)
        # 本番環境(HTTPS): SameSite=None (クロスオリジンでCookie送信が必要、secure=Trueと組み合わせ)
        "samesite": cookie_samesite if cookie_samesite else ("none" if is_production else "lax"),
    }
    if cookie_domain:
        cookie_options["domain"] = cookie_domain

    logger.info(f"[MFA COOKIE DEBUG] Cookie options: secure={cookie_options['secure']}, samesite={cookie_options['samesite']}, domain={cookie_options.get('domain', 'not set')}")

    response.set_cookie(**cookie_options)

    # セキュリティ向上: レスポンスボディからaccess_tokenを削除
    return {
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "session_duration": session_duration,
        "session_type": session_type,
        "message": ja.AUTH_MFA_VERIFICATION_SUCCESS
    }


@router.post(
    "/mfa/first-time-verify",
    response_model=schemas.TokenWithCookie,
    status_code=status.HTTP_200_OK,
    summary="MFA初回検証（管理者設定後）",
    description="管理者が設定したMFAの初回検証を行います。検証成功後、ユーザーのis_mfa_verified_by_userフラグをTrueに設定します。",
)
async def verify_mfa_first_time(
    *,
    response: Response,
    db: AsyncSession = Depends(deps.get_db),
    mfa_data: MFAVerifyRequest,
    staff_crud=Depends(get_staff_crud),
):
    """
    管理者が設定したMFAの初回検証を行います。

    - **temporary_token**: ログイン時に発行された一時トークン
    - **totp_code**: TOTPアプリから取得した6桁のコード

    検証成功後、is_mfa_verified_by_userフラグをTrueに設定し、
    以降は通常のMFAフローを使用できるようになります。
    """
    logger.info(f"[MFA FIRST TIME VERIFY] Starting first-time MFA verification")

    # 一時トークンを検証
    token_data = verify_temporary_token_with_session(mfa_data.temporary_token, expected_type="mfa_verify")
    if not token_data:
        logger.error(f"[MFA FIRST TIME VERIFY] Invalid temporary token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ja.AUTH_INVALID_TEMPORARY_TOKEN,
        )

    user_id = token_data["user_id"]
    session_duration = token_data["session_duration"]
    session_type = token_data["session_type"]
    logger.info(f"[MFA FIRST TIME VERIFY] Token validated, user_id: {user_id}")

    # ユーザーを取得
    user = await staff_crud.get(db, id=user_id)
    if not user:
        logger.error(f"[MFA FIRST TIME VERIFY] User not found: {user_id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ja.AUTH_USER_NOT_FOUND,
        )

    # MFAが有効で、かつユーザー未検証の状態であることを確認
    if not user.is_mfa_enabled:
        logger.error(f"[MFA FIRST TIME VERIFY] MFA not enabled for user: {user_id}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ja.AUTH_MFA_NOT_CONFIGURED,
        )

    if user.is_mfa_verified_by_user:
        logger.error(f"[MFA FIRST TIME VERIFY] User already verified: {user_id}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFAは既に検証済みです。通常のログインフローを使用してください。",
        )

    logger.info(f"[MFA FIRST TIME VERIFY] User found, MFA enabled but not verified by user")

    # TOTPコードを検証
    if not mfa_data.totp_code:
        logger.error(f"[MFA FIRST TIME VERIFY] TOTP code is required")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="TOTPコードが必要です。",
        )

    if not user.mfa_secret:
        logger.error(f"[MFA FIRST TIME VERIFY] MFA secret is missing")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="MFA設定にエラーがあります。管理者に連絡してください。",
        )

    # シークレットを復号化してTOTPコードを検証
    try:
        decrypted_secret = user.get_mfa_secret()
        logger.info(f"[MFA FIRST TIME VERIFY] Secret decrypted successfully")

        totp_result = verify_totp(secret=decrypted_secret, token=mfa_data.totp_code)
        logger.info(f"[MFA FIRST TIME VERIFY] TOTP verification result: {totp_result}")

        if not totp_result:
            logger.error(f"[MFA FIRST TIME VERIFY] Invalid TOTP code")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ja.AUTH_INVALID_MFA_CODE,
            )
    except ValueError as e:
        logger.error(f"[MFA FIRST TIME VERIFY] Secret decryption failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="MFA設定にエラーがあります。管理者に連絡してください。",
        )

    # 検証成功: is_mfa_verified_by_user フラグを True に設定
    user.is_mfa_verified_by_user = True
    await db.commit()
    await db.refresh(user)
    logger.info(f"[MFA FIRST TIME VERIFY] User verification flag set to True")

    # アクセストークンとリフレッシュトークンを生成
    access_token = create_access_token(
        subject=str(user.id),
        expires_delta_seconds=session_duration,
        session_type=session_type
    )
    refresh_token = create_refresh_token(
        subject=str(user.id),
        session_duration=session_duration,
        session_type=session_type
    )

    # Cookie設定
    environment_value = os.getenv("ENVIRONMENT")
    is_production = environment_value == "production"
    cookie_domain = os.getenv("COOKIE_DOMAIN", None)
    cookie_samesite = os.getenv("COOKIE_SAMESITE", None)

    logger.info(f"[MFA FIRST TIME VERIFY COOKIE] ENVIRONMENT={environment_value}, is_production={is_production}")
    logger.info(f"[MFA FIRST TIME VERIFY COOKIE] COOKIE_DOMAIN={cookie_domain}, COOKIE_SAMESITE={cookie_samesite}")

    cookie_options = {
        "key": "access_token",
        "value": access_token,
        "httponly": True,
        "secure": is_production,
        "max_age": session_duration,
        "samesite": cookie_samesite if cookie_samesite else ("none" if is_production else "lax"),
    }
    if cookie_domain:
        cookie_options["domain"] = cookie_domain

    logger.info(f"[MFA FIRST TIME VERIFY COOKIE] Cookie options: secure={cookie_options['secure']}, samesite={cookie_options['samesite']}, domain={cookie_options.get('domain', 'not set')}")

    response.set_cookie(**cookie_options)

    # レスポンス返却
    return {
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "session_duration": session_duration,
        "session_type": session_type,
        "message": "MFAの初回検証が完了しました。ログインに成功しました。"
    }


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(
    *,
    response: Response,  # Cookie削除のため追加
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.Staff = Depends(get_current_user),
):
    """
    ユーザーをログアウトします。
    クライアント側でトークンを無効化するためのエンドポイントです。
    サーバー側での追加のアクションは現在ありません。
    """
    # Cookieをクリア（ログイン時と同じパラメータで削除）
    is_production = os.getenv("ENVIRONMENT") == "production"
    cookie_domain = os.getenv("COOKIE_DOMAIN", None)
    cookie_samesite = os.getenv("COOKIE_SAMESITE", None)

    delete_cookie_options = {
        "key": "access_token",
        "path": "/",  # Cookie設定時と同じpathを明示的に指定
        # 開発環境(HTTP): SameSite=Lax (localhost間は同一サイトとみなされる)
        # 本番環境(HTTPS): SameSite=None (クロスオリジンでCookie送信が必要、secure=Trueと組み合わせ)
        "samesite": cookie_samesite if cookie_samesite else ("none" if is_production else "lax"),
    }
    if cookie_domain:
        delete_cookie_options["domain"] = cookie_domain

    response.delete_cookie(**delete_cookie_options)

    # 今後のためにcurrent_userとdbは引数として残しておく
    return {"message": ja.AUTH_LOGOUT_SUCCESS}


# ==========================================
# パスワードリセット関連のエンドポイント
# ==========================================

@router.post(
    "/forgot-password",
    response_model=schemas.token.PasswordResetResponse,
    status_code=status.HTTP_200_OK,
)
async def forgot_password(
    *,
    request: Request,
    db: AsyncSession = Depends(deps.get_db),
    data: schemas.token.ForgotPasswordRequest,
):
    """
    パスワードリセットをリクエストします。

    Phase 1: エンドポイントとレスポンス構造のみ実装
    Phase 2以降でデータベース統合を実装予定
    """
    # Phase 1: モックレスポンスを返す
    # セキュリティのため、メールアドレスの存在に関わらず成功メッセージを返す
    return schemas.token.PasswordResetResponse(
        message=ja.AUTH_PASSWORD_RESET_EMAIL_SENT
    )


@router.get(
    "/verify-reset-token",
    response_model=schemas.token.TokenValidityResponse,
    status_code=status.HTTP_200_OK,
)
async def verify_reset_token(
    token: str,
    db: AsyncSession = Depends(deps.get_db),
):
    """
    パスワードリセットトークンの有効性を確認します。

    Phase 1: エンドポイントとレスポンス構造のみ実装
    Phase 2以降でデータベース統合を実装予定
    """
    # Phase 1: モックレスポンスを返す
    # 実際にはDBからトークンを検索して有効性を確認する
    return schemas.token.TokenValidityResponse(
        valid=False,
        message=ja.AUTH_RESET_TOKEN_INVALID_OR_EXPIRED
    )


@router.post(
    "/reset-password",
    response_model=schemas.token.PasswordResetResponse,
    status_code=status.HTTP_200_OK,
)
async def reset_password(
    *,
    db: AsyncSession = Depends(deps.get_db),
    data: schemas.token.ResetPasswordRequest,
):
    """
    トークンを使用してパスワードをリセットします。

    Phase 1: エンドポイントとレスポンス構造のみ実装
    Phase 2以降でデータベース統合を実装予定
    """
    # Phase 1: トークンが無効というエラーレスポンスを返す
    # 実際にはトークンを検証してパスワードをリセットする
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=ja.AUTH_RESET_TOKEN_INVALID_OR_EXPIRED,
    )