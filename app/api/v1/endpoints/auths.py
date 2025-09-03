import os
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from jose import jwt, JWTError
from pydantic import ValidationError

from app import crud, schemas
from app.api import deps
from app.core.limiter import limiter
from app.core.security import (
    verify_password, create_access_token, create_refresh_token, ALGORITHM
)

from app.core.security import (
    verify_password, create_access_token, create_refresh_token, ALGORITHM, 
    create_email_verification_token, verify_email_verification_token
)
from app.core.mail import send_verification_email

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
    staff_in: schemas.staff.StaffCreate,
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
        return {"message": "Email already verified"}

    user.is_email_verified = True
    db.add(user)
    await db.commit()

    return {"message": "Email verified successfully"}



@router.post("/token", response_model=schemas.Token)
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
