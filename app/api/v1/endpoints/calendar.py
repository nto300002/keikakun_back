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
            detail="この操作を行う権限がありません。カレンダー設定はowner権限が必要です。",
        )

    try:
        # サービス層でカレンダー設定を作成
        account = await calendar_service.setup_office_calendar(db=db, request=request)

        # レスポンスを作成
        response = CalendarSetupResponse(
            success=True,
            message="カレンダー連携設定が正常に完了しました。",
            account=OfficeCalendarAccountResponse.model_validate(account)
        )
        return response

    except ValueError as e:
        # 既に設定が存在する場合や、バリデーションエラー
        error_message = str(e)
        if "already has a calendar account" in error_message:
            message = "この事業所は既にカレンダー連携設定が存在します。"
        else:
            message = "カレンダー連携設定に失敗しました。"

        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "success": False,
                "message": message,
                "error_details": error_message
            }
        )

    except Exception as e:
        # その他の予期しないエラー
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "message": "カレンダー連携設定中に予期しないエラーが発生しました。",
                "error_details": str(e)
            }
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
            detail=f"事業所 {office_id} のカレンダー設定が見つかりません。",
        )

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
            detail=f"カレンダーアカウント {account_id} が見つかりません。",
        )

    return OfficeCalendarAccountResponse.model_validate(account)
