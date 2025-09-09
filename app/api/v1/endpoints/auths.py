import os
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from jose import jwt, JWTError
from pydantic import ValidationError

from app import crud, schemas, models
from app.api import deps
from app.api.deps import get_current_user
from app.core.limiter import limiter
from app.core.security import (
    verify_password, create_access_token, create_refresh_token, ALGORITHM
)

from app.core.security import (
    verify_password, create_access_token, create_refresh_token, ALGORITHM, 
    create_email_verification_token, verify_email_verification_token,
    create_temporary_token, verify_temporary_token, verify_totp
)
from app.core.mail import send_verification_email
from pydantic import BaseModel

class MFAVerifyRequest(BaseModel):
    temporary_token: str
    totp_code: str = None
    recovery_code: str = None

# DIするためのヘルパー関数
async def get_staff_crud():
    return crud.staff

router = APIRouter()


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
            detail="The user with this email already exists in the system.",
        )

    user = await staff_crud.create_admin(db=db, obj_in=staff_in)

    # コミットするとuserオブジェクトが期限切れになり、user.emailにアクセスできなくなるため
    # 先にメールアドレスを変数に格納しておく
    user_email = user.email
    await db.commit()
    await db.refresh(user) # DBから最新の状態を読み込み、オブジェクトを「新鮮」な状態にする
    
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
            detail="The user with this email already exists in the system.",
        )

    # staff_in.role は StaffCreate スキーマのバリデーターによって
    # `owner` でないことが保証されている
    user = await staff_crud.create_staff(db=db, obj_in=staff_in)

    user_email = user.email
    await db.commit()
    await db.refresh(user)
    
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
            detail="Invalid or expired token",
        )
    
    user = await staff_crud.get_by_email(db, email=email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    if user.is_email_verified:
        return {"message": "Email already verified", "role": user.role}

    # commit前にroleを保存
    user_role = user.role
    user.is_email_verified = True
    db.add(user)
    await db.commit()

    return {"message": "Email verified successfully", "role": user_role}



@router.post("/token") # response_modelを削除
@limiter.limit("5/minute")
async def login_for_access_token(
    *,
    request: Request,  # limiterがIPアドレスを取得するために必要
    db: AsyncSession = Depends(deps.get_db),
    form_data: OAuth2PasswordRequestForm = Depends(),
    staff_crud=Depends(get_staff_crud),
):
    """
    OAuth2 compatible token login, get an access token for future requests
    """
    user = await staff_crud.get_by_email(db, email=form_data.username)
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_email_verified:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email not verified",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.is_mfa_enabled:
        temporary_token = create_temporary_token(user_id=str(user.id), token_type="mfa_verify")
        return {
            "requires_mfa_verification": True,
            "temporary_token": temporary_token,
            "token_type": "bearer", # token_typeはMFA検証フローでも必要に応じて含める
        }
    
    access_token = create_access_token(subject=str(user.id))
    refresh_token = create_refresh_token(subject=str(user.id))
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


@router.post("/refresh-token", response_model=schemas.AccessToken)
async def refresh_access_token(refresh_token_data: schemas.RefreshToken):
    """
    Refresh access token
    """
    try:
        secret_key = os.getenv("SECRET_KEY", "test_secret_key_for_pytest")
        payload = jwt.decode(
            refresh_token_data.refresh_token, secret_key, algorithms=[ALGORITHM]
        )
        # ここでtoken_typeの検証などを追加することも可能
        token_data = schemas.TokenData(**payload)
    except (JWTError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # ここでユーザーの存在をDBで再確認することも可能だが、
    # トークンが有効であればユーザーは存在するとみなし、新しいアクセストークンを発行する
    new_access_token = create_access_token(subject=token_data.sub)
    return {"access_token": new_access_token, "token_type": "bearer"}


@router.post("/token/verify-mfa", response_model=schemas.Token)
async def verify_mfa_for_login(
    *,
    db: AsyncSession = Depends(deps.get_db),
    mfa_data: MFAVerifyRequest,
    staff_crud=Depends(get_staff_crud),
):
    user_id = verify_temporary_token(mfa_data.temporary_token, expected_type="mfa_verify")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired temporary token",
        )

    user = await staff_crud.get(db, id=user_id)
    if not user or not user.is_mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="MFA not properly configured"
        )

    # Verify either TOTP code or recovery code
    verification_successful = False
    
    if mfa_data.totp_code:
        if user.mfa_secret and verify_totp(secret=user.mfa_secret, token=mfa_data.totp_code):
            verification_successful = True
    
    if mfa_data.recovery_code and not verification_successful:
        from app.core.security import verify_recovery_code
        if verify_recovery_code(user, mfa_data.recovery_code):
            verification_successful = True
    
    if not verification_successful:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Invalid TOTP code or recovery code"
        )

    access_token = create_access_token(subject=str(user.id))
    refresh_token = create_refresh_token(subject=str(user.id))
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }

@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.Staff = Depends(get_current_user),
):
    """
    ユーザーをログアウトします。
    クライアント側でトークンを無効化するためのエンドポイントです。
    サーバー側での追加のアクションは現在ありません。
    """
    # 今後のためにcurrent_userとdbは引数として残しておく
    return {"message": "Logout successful"}