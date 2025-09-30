import uuid
from typing import AsyncGenerator

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.core.security import decode_access_token
from app.db.session import AsyncSessionLocal
from app.models.staff import Staff
from app.schemas.token import TokenData

# OAuth2PasswordBearerは、指定されたURL(tokenUrl)からトークンを取得する"callable"クラスです。
# FastAPIはこれを使って、Swagger UI上で認証を試すためのUIを生成します。
reusable_oauth2 = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    各APIリクエストに対して、独立したDBセッションを提供する依存性注入関数。
    セッションはリクエスト処理の完了後に自動的にクローズされます。
    """
    async with AsyncSessionLocal() as session:
        yield session


async def get_current_user(
    db: AsyncSession = Depends(get_db), token: str = Depends(reusable_oauth2)
) -> Staff:
    """
    リクエストのAuthorizationヘッダーからJWTトークンを検証し、
    対応するユーザーをDBから取得する依存性注入関数。
    認証が必要なエンドポイントで使用します。
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_access_token(token)

    if payload is None:
        raise credentials_exception

    try:
        token_data = TokenData(sub=payload.get("sub"))
    except ValidationError:
        raise credentials_exception

    if token_data.sub is None:
        raise credentials_exception

    # IDを元に、crud層を経由してユーザーをデータベースから検索します。
    try:
        user_id = uuid.UUID(token_data.sub)
    except ValueError:
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
        raise credentials_exception
    return user