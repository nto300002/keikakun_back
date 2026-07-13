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
from app.models.enums import StaffRole
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


async def _get_current_user(
    request: Request,
    db: AsyncSession,
    token: Optional[str],
    *,
    load_office: bool,
) -> Staff:
    cookie_token = request.cookies.get("access_token")
    final_token = cookie_token if cookie_token else token

    logger.debug(
        "auth_context load_office=%s cookie_credential_present=%s header_credential_present=%s source=%s",
        load_office,
        bool(cookie_token),
        bool(token),
        "cookie" if cookie_token else "header" if token else "none",
    )

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=ja.PERM_CREDENTIALS_INVALID,
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not final_token:
        logger.warning("Missing credential - raising 401")
        raise credentials_exception

    payload = decode_access_token(final_token)
    logger.debug("Credential claims decoded")

    if payload is None:
        logger.warning("Credential claims missing - raising 401")
        raise credentials_exception

    try:
        token_data = TokenData(sub=payload.get("sub"))
        logger.debug("Credential subject parsed")
    except ValidationError:
        logger.warning("Credential subject validation failed")
        raise credentials_exception

    if token_data.sub is None:
        logger.warning("Credential subject missing - raising 401")
        raise credentials_exception

    # IDを元に、crud層を経由してユーザーをデータベースから検索します。
    try:
        user_id = uuid.UUID(token_data.sub)
        logger.debug("Credential subject UUID parsed")
    except ValueError as e:
        logger.warning("ValueError parsing UUID: %s", e)
        raise credentials_exception

    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.office import OfficeStaff

    stmt = select(Staff).where(Staff.id == user_id)
    if load_office:
        stmt = stmt.options(selectinload(Staff.office_associations).selectinload(OfficeStaff.office))

    result = await db.execute(stmt)
    user = result.scalars().first()

    if not user:
        logger.warning("Credential subject not found")
        raise credentials_exception

    # office付き依存の場合だけ、所属事務所の削除済みチェックも実施する。
    if load_office and user.role != StaffRole.app_admin:
        if user.office_associations:
            # いずれかの事務所が削除済みの場合、アクセス拒否
            for office_assoc in user.office_associations:
                if office_assoc.office and office_assoc.office.is_deleted:
                    logger.warning("Access rejected because associated office is deleted")
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="所属事務所が退会済みのため、アクセスできません",
                        headers={"WWW-Authenticate": "Bearer"},
                    )

    # 削除済みスタッフチェック（事務所チェックの後に実行）
    if user.is_deleted:
        logger.warning("Deleted account attempted access")
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
                logger.warning("Credential rejected after account credential rotation")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=ja.AUTH_TOKEN_INVALIDATED_BY_PASSWORD_CHANGE,
                    headers={"WWW-Authenticate": "Bearer"},
                )

    logger.debug("User found: id=%s", user.id)
    return user


async def get_current_user_minimal(
    request: Request,
    db: AsyncSession = Depends(get_db),
    token: Optional[str] = Depends(reusable_oauth2)
) -> Staff:
    """
    認証済みStaffを取得する軽量依存。

    Staff本体、role、MFAなどStaff上のフィールドだけが必要なendpointで使用する。
    office_associations / office はeager loadしない。
    """
    return await _get_current_user(request, db, token, load_office=False)


async def get_current_user_with_office(
    request: Request,
    db: AsyncSession = Depends(get_db),
    token: Optional[str] = Depends(reusable_oauth2)
) -> Staff:
    """
    認証済みStaffと所属事務所情報を取得する依存。

    office_associations / office や所属事務所の削除済みチェックが必要なendpointで使用する。
    """
    return await _get_current_user(request, db, token, load_office=True)


# 既存endpoint/テスト互換: 従来の get_current_user は office付き依存として残す。
get_current_user = get_current_user_with_office


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
    current_staff: Staff = Depends(get_current_user_minimal)
) -> Staff:
    """
    Manager または Owner のみアクセス可能
    Employee権限のスタッフがアクセスした場合は403エラーを返す
    """
    if current_staff.role not in [StaffRole.manager, StaffRole.owner]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ja.PERM_MANAGER_OR_OWNER_REQUIRED
        )
    return current_staff


async def require_owner(
    current_staff: Staff = Depends(get_current_user_minimal)
) -> Staff:
    """
    Owner のみアクセス可能
    Manager、Employee権限のスタッフがアクセスした場合は403エラーを返す
    """
    if current_staff.role != StaffRole.owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ja.PERM_OWNER_REQUIRED
        )
    return current_staff


async def require_owner_with_office(
    current_staff: Staff = Depends(get_current_user_with_office)
) -> Staff:
    """
    Owner のみアクセス可能で、office_associations も必要なendpoint向け。
    """
    if current_staff.role != StaffRole.owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ja.PERM_OWNER_REQUIRED
        )
    return current_staff


async def require_app_admin(
    current_staff: Staff = Depends(get_current_user_minimal)
) -> Staff:
    """
    app_admin のみアクセス可能
    app_admin以外のスタッフがアクセスした場合は403エラーを返す
    """
    if current_staff.role != StaffRole.app_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="権限がありません。この操作はアプリ管理者のみが実行できます"
        )
    return current_staff


async def check_employee_restriction(
    db: AsyncSession,
    current_staff: Staff,
    office_id: Optional[uuid.UUID],
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
        office_id: 操作対象の事業所ID
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
    current_staff: Staff = Depends(get_current_user_with_office)
) -> Staff:
    """
    課金ステータスチェック（Phase 1: 機能制限）

    billing_status が past_due / trial_expired / payment_failed / canceled の場合、
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
        HTTPException: 課金ステータスが past_due/trial_expired/payment_failed/canceled の場合
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
        logger.warning("Billing not found, creating new billing")
        billing = await crud.billing.create_for_office(db=db, office_id=office_id)
        await db.commit()

    # 課金ステータスチェック
    if billing.billing_status in [
        BillingStatus.past_due,
        BillingStatus.trial_expired,
        BillingStatus.payment_failed,
        BillingStatus.canceled,
    ]:
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
            logger.warning("CSRF validation failed: %s", type(e).__name__)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ja.SECURITY_REQUEST_EXPIRED
            )
