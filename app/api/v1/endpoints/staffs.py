from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select
import uuid
from datetime import datetime, timezone

from app import schemas, crud
from app.api import deps
from app.models.staff import Staff
from app.models.office import OfficeStaff
from app.models.enums import StaffRole
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


@router.delete("/{staff_id}")
async def delete_staff(
    *,
    db: AsyncSession = Depends(deps.get_db),
    request: Request,
    staff_id: uuid.UUID,
    current_user: Staff = Depends(deps.require_owner),
) -> dict:
    """
    スタッフを削除（Owner のみ）

    削除処理:
    1. バリデーション（自己削除チェック、最後のOwnerチェック、同一事務所チェック）
    2. スタッフの論理削除
    3. 監査ログの記録
    4. システム通知の送信（事務所内の全スタッフへ）

    権限: Owner のみアクセス可能
    すべての操作を同一トランザクション内で実行
    """
    try:
        # ユーザーの所属情報を eager load する
        stmt = (
            select(Staff)
            .options(selectinload(Staff.office_associations).selectinload(OfficeStaff.office))
            .where(Staff.id == current_user.id)
        )
        result = await db.execute(stmt)
        current_user_full = result.scalar_one_or_none()

        if not current_user_full or not current_user_full.office_associations:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ja.OFFICE_NOT_FOUND_FOR_USER,
            )

        # ユーザーの所属事務所を取得
        current_user_office = current_user_full.office_associations[0].office
        if not current_user_office:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ja.OFFICE_INFO_NOT_FOUND,
            )

        # 削除対象スタッフを取得（eager load）
        stmt = (
            select(Staff)
            .options(selectinload(Staff.office_associations).selectinload(OfficeStaff.office))
            .where(Staff.id == staff_id)
        )
        result = await db.execute(stmt)
        target_staff = result.scalar_one_or_none()

        # 存在確認
        if not target_staff:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ja.STAFF_NOT_FOUND
            )

        # 削除済みチェック
        if target_staff.is_deleted:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ja.STAFF_ALREADY_DELETED
            )

        # 自己削除チェック
        if target_staff.id == current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ja.STAFF_CANNOT_DELETE_SELF
            )

        # 同一事務所チェック
        target_staff_office_ids = {assoc.office_id for assoc in target_staff.office_associations}
        if current_user_office.id not in target_staff_office_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ja.STAFF_DIFFERENT_OFFICE
            )

        # 最後のOwnerチェック
        if target_staff.role == StaffRole.owner:
            owner_count = await crud.staff.count_owners_in_office(
                db=db,
                office_id=current_user_office.id
            )
            if owner_count <= 1:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=ja.STAFF_CANNOT_DELETE_LAST_OWNER
                )

        # トランザクション開始: すべての操作をflushのみで実行

        # 1. スタッフの論理削除
        deleted_staff = await crud.staff.soft_delete(
            db=db,
            staff_id=staff_id,
            deleted_by=current_user.id
        )

        # 2. 監査ログの記録
        # IPアドレスとUser-Agentを取得
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")

        await crud.staff_audit_log.create_audit_log(
            db=db,
            staff_id=staff_id,
            action="deleted",
            performed_by=current_user.id,
            ip_address=ip_address,
            user_agent=user_agent,
            details={
                "deleted_staff_email": target_staff.email,
                "deleted_staff_name": f"{target_staff.last_name} {target_staff.first_name}",
                "deleted_staff_role": target_staff.role.value,
                "office_id": str(current_user_office.id)
            }
        )

        # 3. システム通知の送信（事務所内の全スタッフへ）
        # 削除されたスタッフを除く、事務所内の有効なスタッフIDリストを取得
        active_staffs = await crud.staff.get_by_office_id(
            db=db,
            office_id=current_user_office.id,
            exclude_deleted=True
        )

        # 削除されたスタッフを受信者から除外
        recipient_ids = [
            staff.id for staff in active_staffs
            if staff.id != staff_id
        ]

        if recipient_ids:
            # システム通知を作成
            notification_title = "スタッフ退会のお知らせ"
            notification_content = f"{target_staff.last_name} {target_staff.first_name}さんが退会しました。"

            await crud.message.create_announcement(
                db=db,
                obj_in={
                    "sender_staff_id": None,  # システム通知はsender_idがNone
                    "office_id": current_user_office.id,
                    "recipient_ids": recipient_ids,
                    "title": notification_title,
                    "content": notification_content
                }
            )

        # すべての操作が成功したら commit
        await db.commit()
        await db.refresh(deleted_staff)

        return {
            "message": ja.STAFF_DELETED_SUCCESS,
            "staff_id": str(staff_id),
            "deleted_at": deleted_staff.deleted_at.isoformat()
        }

    except HTTPException:
        # HTTPExceptionはそのまま再raise
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ja.STAFF_DELETE_FAILED.format(error=str(e))
        )
