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

    # app_admin以外の場合、所属事務所の削除済みチェック（スタッフチェックより先に実行）
    from app.models.enums import StaffRole
    if user.role != StaffRole.app_admin:
        if user.office_associations:
            # いずれかの事務所が削除済みの場合、アクセス拒否
            for office_assoc in user.office_associations:
                if office_assoc.office and office_assoc.office.is_deleted:
                    print(f"User's office is deleted: office_id={office_assoc.office.id}")
                    logger.warning(f"User {user.email} attempted access with deleted office: office_id={office_assoc.office.id}")
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="所属事務所が退会済みのため、アクセスできません",
                        headers={"WWW-Authenticate": "Bearer"},
                    )

    # 削除済みスタッフチェック（事務所チェックの後に実行）
    if user.is_deleted:
        print(f"User is deleted: {user.email}")
        logger.warning(f"Deleted user attempted access: {user.email}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ja.PERM_ACCOUNT_DELETED,
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Option 1: password_changed_at 検証
    # パスワード変更後に発行されたトークンかをチェック
    # セキュリティ: OWASP A07:2021 Identification and Authentication Failures 対策
    if user.password_changed_at:
        token_iat = payload.get("iat")
        if token_iat:
            # iatはUNIXタイムスタンプ（秒）
            from datetime import datetime, timezone
            token_issued_at = datetime.fromtimestamp(token_iat, tz=timezone.utc)

            # パスワード変更時刻とトークン発行時刻を比較
            if user.password_changed_at > token_issued_at:
                print(f"Token issued before password change - rejecting")
                print(f"  Token issued at: {token_issued_at}")
                print(f"  Password changed at: {user.password_changed_at}")
                logger.warning(
                    f"Token rejected: issued at {token_issued_at}, "
                    f"password changed at {user.password_changed_at}"
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=ja.AUTH_TOKEN_INVALIDATED_BY_PASSWORD_CHANGE,
                    headers={"WWW-Authenticate": "Bearer"},
                )

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


async def require_app_admin(
    current_staff: Staff = Depends(get_current_user)
) -> Staff:
    """
    app_admin のみアクセス可能
    app_admin以外のスタッフがアクセスした場合は403エラーを返す
    """
    from app.models.enums import StaffRole

    if current_staff.role != StaffRole.app_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="権限がありません。この操作はアプリ管理者のみが実行できます"
        )
    return current_staff


async def check_employee_restriction(
    db: AsyncSession,
    current_staff: Staff,
    resource_type: "ResourceType",
    action_type: "ActionType",
    resource_id: Optional[uuid.UUID] = None,
    request_data: Optional[dict] = None
) -> Optional["ApprovalRequest"]:
    """
    Employee制限チェック
    - Manager/Owner: None を返す（制限なし、直接実行可能）
    - Employee: ApprovalRequest を作成して返す（承認が必要）

    Args:
        db: データベースセッション
        current_staff: 現在のスタッフ
        resource_type: リソースタイプ（welfare_recipient, support_plan_cycle, etc.）
        action_type: アクションタイプ（create, update, delete）
        resource_id: リソースID（updateまたはdeleteの場合）
        request_data: リクエストデータ（createまたはupdateの場合）

    Returns:
        ApprovalRequest: Employeeの場合は作成されたリクエスト
        None: Manager/Ownerの場合は制限なし
    """
    from app.models.enums import StaffRole
    from app.crud.crud_approval_request import approval_request

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

    # ApprovalRequestを作成（employee_action種別）
    approval_req = await approval_request.create_employee_action_request(
        db=db,
        requester_staff_id=current_staff.id,
        office_id=office_id,
        resource_type=resource_type.value,
        action_type=action_type.value,
        resource_id=resource_id,
        original_request_data=request_data
    )

    return approval_req


# 型ヒント用のインポート
get_current_staff = get_current_user  # エイリアス（get_current_staffという名前でも使えるようにする）


async def require_active_billing(
    db: AsyncSession = Depends(get_db),
    current_staff: Staff = Depends(get_current_user)
) -> Staff:
    """
    課金ステータスチェック（Phase 1: 機能制限）

    billing_status が past_due または canceled の場合、
    書き込み操作を制限し 402 Payment Required を返す。

    free または active の場合は制限なし。

    使用方法:
    - 書き込み操作（CRUD create/update/delete, PDFアップロード等）のエンドポイントで使用
    - 読み取り専用操作（GET）では使用しない

    Args:
        db: データベースセッション
        current_staff: 現在のスタッフ

    Returns:
        Staff: 課金ステータスが有効な場合

    Raises:
        HTTPException: 課金ステータスが past_due/canceled の場合
    """
    from app import crud
    from app.models.enums import BillingStatus

    # app_adminは課金チェックをスキップ
    from app.models.enums import StaffRole
    if current_staff.role == StaffRole.app_admin:
        return current_staff

    # 所属事務所を取得
    if not current_staff.office_associations:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ja.BILLING_OFFICE_NOT_FOUND
        )

    primary_association = next(
        (assoc for assoc in current_staff.office_associations if assoc.is_primary),
        current_staff.office_associations[0]
    )
    office_id = primary_association.office_id

    # Billing情報を取得
    billing = await crud.billing.get_by_office_id(db=db, office_id=office_id)

    if not billing:
        # Billing情報がない場合は自動作成（マイグレーション後の過渡期対応）
        logger.warning(f"Billing not found for office_id={office_id}, creating new billing")
        billing = await crud.billing.create_for_office(db=db, office_id=office_id)
        await db.commit()

    # 課金ステータスチェック
    if billing.billing_status in [BillingStatus.past_due, BillingStatus.canceled]:
        logger.warning(
            f"Billing restriction: office_id={office_id}, "
            f"status={billing.billing_status}, staff_id={current_staff.id}"
        )
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=ja.BILLING_PAYMENT_REQUIRED
        )

    return current_staff


# --- CSRF保護依存関数 ---

async def validate_csrf(
    request: Request,
) -> None:
    """
    CSRFトークンを検証する依存関数

    Cookie認証を使用している場合のみCSRF検証を行う。
    Bearer認証（Authorizationヘッダー）の場合は検証をスキップ。

    Args:
        request: FastAPIリクエストオブジェクト

    Raises:
        HTTPException: CSRFトークンが無効な場合
    """
    from fastapi_csrf_protect import CsrfProtect
    from fastapi_csrf_protect.exceptions import CsrfProtectError

    # Authorizationヘッダーがある場合（Bearer認証）はCSRF検証をスキップ
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return

    # Cookie認証を使用している場合、CSRF検証を行う
    access_token_cookie = request.cookies.get("access_token")
    if access_token_cookie:
        csrf_protect = CsrfProtect()
        try:
            await csrf_protect.validate_csrf(request)
        except CsrfProtectError as e:
            logger.warning(f"CSRF validation failed: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"CSRF token validation failed"
            )