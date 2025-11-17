from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from app import schemas
from app.api import deps
from app.models.staff import Staff
from app.schemas.staff_profile import (
    StaffNameUpdate,
    StaffNameUpdateResponse,
    PasswordChange,
    PasswordChangeResponse,
    EmailChangeRequest,
    EmailChangeRequestResponse,
    EmailChangeConfirm,
    EmailChangeConfirmResponse
)
from app.services.staff_profile_service import staff_profile_service, RateLimitExceededError
from app.messages import ja

router = APIRouter()


@router.get("/me", response_model=schemas.staff.StaffRead)
async def read_users_me(
    current_user: Staff = Depends(deps.get_current_user),
) -> Staff:
    """
    認証済みユーザーの情報を取得
    """
    return current_user


@router.patch("/me/name", response_model=StaffNameUpdateResponse)
async def update_staff_name(
    *,
    db: AsyncSession = Depends(deps.get_db),
    name_update: StaffNameUpdate,
    current_user: Staff = Depends(deps.get_current_user)
) -> Staff:
    """
    ログイン中のスタッフの名前を更新する

    - 姓名とふりがなを一度に更新
    - 変更履歴を記録
    - 関連する表示データを自動更新（full_name）
    """
    try:
        updated_staff = await staff_profile_service.update_name(
            db=db,
            staff_id=str(current_user.id),
            name_data=name_update
        )
        # レスポンス前に全ての属性を明示的にロード（MissingGreenletエラー対策）
        await db.refresh(updated_staff)
        return updated_staff
    except HTTPException:
        # HTTPException はそのまま再raise
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ja.STAFF_NAME_UPDATE_FAILED
        )


@router.patch("/me/password", response_model=PasswordChangeResponse)
async def change_password(
    *,
    db: AsyncSession = Depends(deps.get_db),
    password_change: PasswordChange,
    current_user: Staff = Depends(deps.get_current_user)
) -> dict:
    """
    ログイン中のスタッフのパスワードを変更する

    - 現在のパスワードによる本人確認必須
    - パスワード強度の検証
    - パスワード履歴の保存（過去3回分は再使用不可）
    - 変更完了メール通知（今後実装）
    """
    try:
        result = await staff_profile_service.change_password(
            db=db,
            staff_id=str(current_user.id),
            password_change=password_change
        )
        return result
    except HTTPException:
        # HTTPException はそのまま再raise
        raise
    except RateLimitExceededError as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ja.STAFF_PASSWORD_CHANGE_FAILED
        )


@router.patch("/{staff_id}/name", response_model=StaffNameUpdateResponse)
async def update_other_staff_name(
    *,
    staff_id: uuid.UUID,
    db: AsyncSession = Depends(deps.get_db),
    name_update: StaffNameUpdate,
    current_user: Staff = Depends(deps.get_current_user)
) -> Staff:
    """
    他のスタッフの名前を更新する（認可テスト用）

    セキュリティ: 自分以外のIDの場合は403 Forbiddenを返す
    """
    # 自分以外のIDを指定した場合は権限エラー
    if str(current_user.id) != str(staff_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ja.PERM_OPERATION_FORBIDDEN_GENERIC
        )

    try:
        updated_staff = await staff_profile_service.update_name(
            db=db,
            staff_id=str(staff_id),
            name_data=name_update
        )
        # レスポンス前に全ての属性を明示的にロード（MissingGreenletエラー対策）
        await db.refresh(updated_staff)
        return updated_staff
    except HTTPException:
        # HTTPException はそのまま再raise
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ja.STAFF_NAME_UPDATE_FAILED
        )


@router.post("/me/email", response_model=EmailChangeRequestResponse)
async def request_email_change(
    *,
    db: AsyncSession = Depends(deps.get_db),
    email_request: EmailChangeRequest,
    current_user: Staff = Depends(deps.get_current_user)
) -> dict:
    """
    ログイン中のスタッフのメールアドレス変更をリクエストする

    - 現在のパスワードによる本人確認必須
    - 新しいメールアドレスに確認メールを送信
    - 旧メールアドレスにも通知メールを送信
    - 24時間以内に3回までリクエスト可能
    """
    try:
        result = await staff_profile_service.request_email_change(
            db=db,
            staff_id=str(current_user.id),
            email_request=email_request
        )
        return result
    except HTTPException:
        # HTTPException はそのまま再raise
        raise
    except RateLimitExceededError as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ja.STAFF_EMAIL_CHANGE_REQUEST_FAILED
        )


@router.post("/me/email/verify", response_model=EmailChangeConfirmResponse)
async def verify_email_change(
    *,
    db: AsyncSession = Depends(deps.get_db),
    email_confirm: EmailChangeConfirm
) -> dict:
    """
    メールアドレス変更を確認・完了する

    - 確認メールに記載されたトークンで検証
    - トークンの有効期限は30分
    - 変更完了後、旧メールアドレスに通知を送信
    """
    print(f"[DEBUG] verify_email_change called with token: {email_confirm.verification_token[:10]}...")
    try:
        result = await staff_profile_service.verify_email_change(
            db=db,
            verification_token=email_confirm.verification_token
        )
        print(f"[DEBUG] verify_email_change succeeded: {result}")
        return result
    except HTTPException:
        # HTTPException はそのまま再raise
        raise
    except Exception as e:
        print(f"[DEBUG] Exception in verify_email_change: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ja.STAFF_EMAIL_CHANGE_VERIFY_FAILED.format(error=str(e))
        )
