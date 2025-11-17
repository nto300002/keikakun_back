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
from app.messages import ja

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
        detail=ja.PERM_CREDENTIALS_INVALID,
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


# --- 権限チェック依存関数 ---

async def require_manager_or_owner(
    current_staff: Staff = Depends(get_current_user)
) -> Staff:
    """
    Manager または Owner のみアクセス可能
    Employee権限のスタッフがアクセスした場合は403エラーを返す
    """
    from app.models.enums import StaffRole

    if current_staff.role not in [StaffRole.manager, StaffRole.owner]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ja.PERM_MANAGER_OR_OWNER_REQUIRED
        )
    return current_staff


async def require_owner(
    current_staff: Staff = Depends(get_current_user)
) -> Staff:
    """
    Owner のみアクセス可能
    Manager、Employee権限のスタッフがアクセスした場合は403エラーを返す
    """
    from app.models.enums import StaffRole

    if current_staff.role != StaffRole.owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ja.PERM_OWNER_REQUIRED
        )
    return current_staff


async def check_employee_restriction(
    db: AsyncSession,
    current_staff: Staff,
    resource_type: "ResourceType",
    action_type: "ActionType",
    resource_id: Optional[uuid.UUID] = None,
    request_data: Optional[dict] = None
) -> Optional["EmployeeActionRequest"]:
    """
    Employee制限チェック
    - Manager/Owner: None を返す（制限なし、直接実行可能）
    - Employee: EmployeeActionRequest を作成して返す（承認が必要）

    Args:
        db: データベースセッション
        current_staff: 現在のスタッフ
        resource_type: リソースタイプ（welfare_recipient, support_plan_cycle, etc.）
        action_type: アクションタイプ（create, update, delete）
        resource_id: リソースID（updateまたはdeleteの場合）
        request_data: リクエストデータ（createまたはupdateの場合）

    Returns:
        EmployeeActionRequest: Employeeの場合は作成されたリクエスト
        None: Manager/Ownerの場合は制限なし
    """
    from app.models.enums import StaffRole
    from app.schemas.employee_action_request import EmployeeActionRequestCreate
    from app.services import employee_action_service

    # Manager/Ownerは制限なし
    if current_staff.role in [StaffRole.manager, StaffRole.owner]:
        return None

    # Employeeの場合、リクエストを作成
    # office_idを取得（office_associations経由）
    office_id = None
    if current_staff.office:
        office_id = current_staff.office.id
    elif current_staff.office_associations:
        # プライマリ事業所を優先
        primary_office = next(
            (assoc.office for assoc in current_staff.office_associations if assoc.is_primary),
            None
        )
        if primary_office:
            office_id = primary_office.id
        elif current_staff.office_associations:
            # プライマリがなければ最初の事業所
            office_id = current_staff.office_associations[0].office_id

    if not office_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ja.PERM_OFFICE_REQUIRED
        )

    # スキーマオブジェクトを作成
    obj_in = EmployeeActionRequestCreate(
        resource_type=resource_type,
        action_type=action_type,
        resource_id=resource_id,
        request_data=request_data
    )

    # リクエストを作成
    request = await employee_action_service.create_request(
        db=db,
        requester_staff_id=current_staff.id,
        office_id=office_id,
        obj_in=obj_in
    )

    return request


# 型ヒント用のインポート
get_current_staff = get_current_user  # エイリアス（get_current_staffという名前でも使えるようにする）