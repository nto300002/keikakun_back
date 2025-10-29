import uuid
import logging
from typing import AsyncGenerator, Optional
from contextlib import asynccontextmanager

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.core.security import decode_access_token
from app.db.session import AsyncSessionLocal
from app.models.staff import Staff
from app.schemas.token import TokenData

logger = logging.getLogger(__name__)

# OAuth2PasswordBearerは、指定されたURL(tokenUrl)からトークンを取得する"callable"クラスです。
# FastAPIはこれを使って、Swagger UI上で認証を試すためのUIを生成します。
reusable_oauth2 = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    各APIリクエストに対して、独立したDBセッションを提供する依存性注入関数。
    セッションはリクエスト処理の完了後に自動的にクローズされます。
    """
    async with AsyncSessionLocal() as session:
        yield session


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    token: Optional[str] = Depends(reusable_oauth2)
) -> Staff:
    """
    リクエストのCookieまたはAuthorizationヘッダーからJWTトークンを検証し、
    対応するユーザーをDBから取得する依存性注入関数。
    認証が必要なエンドポイントで使用します。

    優先順位:
    1. Cookie (access_token)
    2. Authorization ヘッダー (Bearer token)
    """
    print("\n" + "="*80)
    print("=== get_current_user called ===")

    # まずCookieからトークンを取得
    cookie_token = request.cookies.get("access_token")

    # Cookieが優先、なければAuthorizationヘッダーから
    final_token = cookie_token if cookie_token else token

    print(f"Cookie token: {cookie_token[:20]}..." if cookie_token else "No cookie token")
    print(f"Header token: {token[:20]}..." if token else "No header token")
    print(f"Using token: {final_token[:20]}..." if final_token else "No token")
    logger.info("=== get_current_user called ===")
    logger.info(f"Cookie token: {'present' if cookie_token else 'absent'}")
    logger.info(f"Header token: {'present' if token else 'absent'}")
    logger.info(f"Using token from: {'cookie' if cookie_token else 'header' if token else 'none'}")

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not final_token:
        print("No token provided - raising 401")
        logger.warning("No token provided - raising 401")
        raise credentials_exception

    payload = decode_access_token(final_token)
    print(f"Decoded payload: {payload}")
    logger.info(f"Decoded payload: {payload}")

    if payload is None:
        print("Payload is None - raising 401")
        logger.warning("Payload is None - raising 401")
        raise credentials_exception

    try:
        token_data = TokenData(sub=payload.get("sub"))
        print(f"TokenData created with sub: {token_data.sub}")
        logger.info(f"TokenData created with sub: {token_data.sub}")
    except ValidationError as e:
        print(f"ValidationError: {e}")
        logger.warning(f"ValidationError: {e}")
        raise credentials_exception

    if token_data.sub is None:
        print("token_data.sub is None - raising 401")
        logger.warning("token_data.sub is None - raising 401")
        raise credentials_exception

    # IDを元に、crud層を経由してユーザーをデータベースから検索します。
    try:
        user_id = uuid.UUID(token_data.sub)
        print(f"Parsed user_id: {user_id}")
        logger.info(f"Parsed user_id: {user_id}")
    except ValueError as e:
        print(f"ValueError parsing UUID: {e}")
        logger.warning(f"ValueError parsing UUID: {e}")
        raise credentials_exception

    from sqlalchemy.orm import selectinload
    from sqlalchemy import select
    from app.models.office import OfficeStaff

    stmt = select(Staff).where(Staff.id == user_id).options(
        selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
    )
    result = await db.execute(stmt)
    user = result.scalars().first()

    if not user:
        print(f"User not found for id: {user_id}")
        logger.warning(f"User not found for id: {user_id}")
        raise credentials_exception

    print(f"User found: {user.email}, id: {user.id}")
    print("="*80 + "\n")
    logger.info(f"User found: {user.email}, id: {user.id}")
    return user


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """
    非同期コンテキストマネージャとしてDBセッションを提供する。
    バックグラウンドタスクなど、リクエストのライフサイクル外でDBセッションが必要な場合に使用する。
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise