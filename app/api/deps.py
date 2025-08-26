from typing import AsyncGenerator

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.core.config import settings
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
    try:
        # トークンをデコードしてペイロードを取得します。
        # SECRET_KEYとアルゴリズムは設定ファイルから読み込みます。
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        # ペイロードの'sub'（subject）にユーザーのemailが含まれていることを期待します。
        token_data = TokenData(sub=payload.get("sub"))
    except (JWTError, ValidationError):
        # トークンの形式が不正、またはデコードに失敗した場合
        raise credentials_exception

    if token_data.sub is None:
        raise credentials_exception

    # emailを元に、crud層を経由してユーザーをデータベースから検索します。
    user = await crud.staff.get_by_email(db, email=token_data.sub)
    if not user:
        raise credentials_exception
    return user