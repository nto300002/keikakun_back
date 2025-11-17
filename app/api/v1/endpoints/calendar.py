"""カレンダー設定APIエンドポイント"""
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.api import deps
from app.services.calendar_service import calendar_service
from app.schemas.calendar_account import (
    CalendarSetupRequest,
    CalendarSetupResponse,
    OfficeCalendarAccountResponse
)
from app.messages import ja

router = APIRouter()


@router.post("/setup", response_model=CalendarSetupResponse, status_code=status.HTTP_201_CREATED)
async def setup_calendar(
    *,
    db: AsyncSession = Depends(deps.get_db),
    request: CalendarSetupRequest,
    current_user: models.Staff = Depends(deps.get_current_user),
) -> Any:
    """
    事業所のGoogleカレンダー連携を設定する

    Args:
        db: データベースセッション
        request: カレンダー設定リクエスト
        current_user: 現在のユーザー

    Returns:
        CalendarSetupResponse: 設定結果

    Raises:
        HTTPException:
            - 403: owner以外のロールでアクセスした場合
            - 400: 既にカレンダー設定が存在する場合
            - 500: その他のエラー
    """
    # 権限チェック: ownerのみが設定可能
    if current_user.role != models.StaffRole.owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ja.CALENDAR_OWNER_ONLY,
        )

    try:
        # サービス層でカレンダー設定を作成
        account = await calendar_service.setup_office_calendar(db=db, request=request)

        # カレンダー接続をテスト
        connection_success = await calendar_service.test_calendar_connection(
            db=db,
            account_id=account.id
        )

        # 最新の状態を再取得
        account = await calendar_service.get_office_calendar_by_id(db=db, account_id=account.id)

        # セッションから明示的に属性を取得してレスポンスを作成
        account_response = OfficeCalendarAccountResponse(
            id=account.id,
            office_id=account.office_id,
            google_calendar_id=account.google_calendar_id,
            calendar_name=account.calendar_name,
            calendar_url=account.calendar_url,
            service_account_email=account.service_account_email,
            connection_status=account.connection_status,
            auto_invite_staff=account.auto_invite_staff,
            default_reminder_minutes=account.default_reminder_minutes,
            last_sync_at=account.last_sync_at,
            last_error_message=account.last_error_message,
            created_at=account.created_at,
            updated_at=account.updated_at
        )

        if connection_success:
            message = ja.CALENDAR_SETUP_SUCCESS_WITH_CONNECTION
        else:
            message = ja.CALENDAR_SETUP_FAILED_CONNECTION

        response = CalendarSetupResponse(
            success=True,
            message=message,
            account=account_response
        )

        # トランザクションをコミット
        await db.commit()

        return response

    except HTTPException:
        # エラー時はロールバック
        await db.rollback()
        # HTTPException はそのまま再raise
        raise

    except Exception as e:
        # エラー時はロールバック
        await db.rollback()

        # その他の予期しないエラー
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ja.CALENDAR_SETUP_ERROR.format(error=str(e))
        )


@router.get("/office/{office_id}", response_model=OfficeCalendarAccountResponse)
async def get_calendar_by_office(
    *,
    db: AsyncSession = Depends(deps.get_db),
    office_id: UUID,
    current_user: models.Staff = Depends(deps.get_current_user),
) -> Any:
    """
    事業所IDでカレンダー設定を取得する

    Args:
        db: データベースセッション
        office_id: 事業所ID
        current_user: 現在のユーザー

    Returns:
        OfficeCalendarAccountResponse: カレンダー設定

    Raises:
        HTTPException:
            - 404: カレンダー設定が存在しない場合
    """
    # カレンダー設定を取得
    account = await calendar_service.get_office_calendar_by_office_id(db=db, office_id=office_id)

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ja.CALENDAR_NOT_FOUND_FOR_OFFICE.format(office_id=office_id),
        )

    # デバッグログ: calendar_name の値を確認
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"[GET /office/{office_id}] calendar_name={account.calendar_name}")
    logger.info(f"[GET /office/{office_id}] google_calendar_id={account.google_calendar_id}")
    logger.info(f"[GET /office/{office_id}] connection_status={account.connection_status}")

    return OfficeCalendarAccountResponse.model_validate(account)


@router.get("/{account_id}", response_model=OfficeCalendarAccountResponse)
async def get_calendar_by_id(
    *,
    db: AsyncSession = Depends(deps.get_db),
    account_id: UUID,
    current_user: models.Staff = Depends(deps.get_current_user),
) -> Any:
    """
    カレンダーアカウントIDで設定を取得する

    Args:
        db: データベースセッション
        account_id: カレンダーアカウントID
        current_user: 現在のユーザー

    Returns:
        OfficeCalendarAccountResponse: カレンダー設定

    Raises:
        HTTPException:
            - 404: カレンダー設定が存在しない場合
    """
    # カレンダー設定を取得
    account = await calendar_service.get_office_calendar_by_id(db=db, account_id=account_id)

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ja.CALENDAR_ACCOUNT_NOT_FOUND.format(account_id=account_id),
        )

    return OfficeCalendarAccountResponse.model_validate(account)


@router.put("/{account_id}", response_model=CalendarSetupResponse)
async def update_calendar(
    *,
    db: AsyncSession = Depends(deps.get_db),
    account_id: UUID,
    request: CalendarSetupRequest,
    current_user: models.Staff = Depends(deps.get_current_user),
) -> Any:
    """
    カレンダー設定を更新する（JSONファイル再アップロード）

    Args:
        db: データベースセッション
        account_id: カレンダーアカウントID
        request: カレンダー設定リクエスト
        current_user: 現在のユーザー

    Returns:
        CalendarSetupResponse: 更新結果

    Raises:
        HTTPException:
            - 403: owner以外のロールでアクセスした場合
            - 404: カレンダーアカウントが存在しない場合
            - 500: その他のエラー
    """
    # 権限チェック: ownerのみが更新可能
    if current_user.role != models.StaffRole.owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ja.CALENDAR_UPDATE_OWNER_ONLY,
        )

    try:
        # サービス層でカレンダー設定を更新
        account = await calendar_service.update_office_calendar(
            db=db,
            account_id=account_id,
            request=request
        )

        # カレンダー接続を再テスト
        connection_success = await calendar_service.test_calendar_connection(
            db=db,
            account_id=account.id
        )

        # 最新の状態を再取得
        account = await calendar_service.get_office_calendar_by_id(db=db, account_id=account.id)

        # レスポンスを作成
        account_response = OfficeCalendarAccountResponse(
            id=account.id,
            office_id=account.office_id,
            google_calendar_id=account.google_calendar_id,
            calendar_name=account.calendar_name,
            calendar_url=account.calendar_url,
            service_account_email=account.service_account_email,
            connection_status=account.connection_status,
            auto_invite_staff=account.auto_invite_staff,
            default_reminder_minutes=account.default_reminder_minutes,
            last_sync_at=account.last_sync_at,
            last_error_message=account.last_error_message,
            created_at=account.created_at,
            updated_at=account.updated_at
        )

        if connection_success:
            message = ja.CALENDAR_UPDATE_SUCCESS_WITH_CONNECTION
        else:
            message = ja.CALENDAR_UPDATE_FAILED_CONNECTION

        response = CalendarSetupResponse(
            success=True,
            message=message,
            account=account_response
        )

        # トランザクションをコミット
        await db.commit()

        return response

    except HTTPException:
        # エラー時はロールバック
        await db.rollback()
        # HTTPException はそのまま再raise
        raise

    except Exception as e:
        # エラー時はロールバック
        await db.rollback()

        # その他の予期しないエラー
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ja.CALENDAR_UPDATE_ERROR.format(error=str(e))
        )


@router.delete("/{account_id}")
async def delete_calendar(
    *,
    db: AsyncSession = Depends(deps.get_db),
    account_id: UUID,
    current_user: models.Staff = Depends(deps.get_current_user),
) -> Any:
    """
    カレンダー連携を解除する

    Args:
        db: データベースセッション
        account_id: カレンダーアカウントID
        current_user: 現在のユーザー

    Returns:
        dict: 削除結果

    Raises:
        HTTPException:
            - 403: owner以外のロールでアクセスした場合
            - 404: カレンダーアカウントが存在しない場合
            - 500: その他のエラー
    """
    # 権限チェック: ownerのみが削除可能
    if current_user.role != models.StaffRole.owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ja.CALENDAR_DELETE_OWNER_ONLY,
        )

    try:
        # サービス層でカレンダー設定を削除
        await calendar_service.delete_office_calendar(db=db, account_id=account_id)

        # トランザクションをコミット
        await db.commit()

        return {
            "success": True,
            "message": ja.CALENDAR_DELETE_SUCCESS
        }

    except HTTPException:
        # エラー時はロールバック
        await db.rollback()
        # HTTPException はそのまま再raise
        raise

    except Exception as e:
        # エラー時はロールバック
        await db.rollback()

        # その他の予期しないエラー
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ja.CALENDAR_DELETE_ERROR.format(error=str(e))
        )


@router.post("/sync-pending")
async def sync_pending_events(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.Staff = Depends(deps.get_current_user),
) -> Any:
    """
    未同期イベントをGoogle Calendarに同期する

    Args:
        db: データベースセッション
        current_user: 現在のユーザー

    Returns:
        dict: 同期結果 {"synced": 成功数, "failed": 失敗数}

    Raises:
        HTTPException:
            - 500: 同期処理中にエラーが発生した場合
    """
    try:
        # 全ての未同期イベントを同期
        result = await calendar_service.sync_pending_events(db=db)

        # トランザクションをコミット
        await db.commit()

        return {
            "success": True,
            "message": ja.CALENDAR_SYNC_SUCCESS.format(synced=result['synced'], failed=result['failed']),
            "synced": result["synced"],
            "failed": result["failed"]
        }

    except Exception as e:
        # エラー時はロールバック
        await db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ja.CALENDAR_SYNC_ERROR.format(error=str(e))
        )
