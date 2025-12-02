"""
アーカイブスタッフのAPIエンドポイント（app_admin専用）

法定保存義務に基づくスタッフアーカイブの閲覧機能。
- 労働基準法第109条：労働者名簿を退職後5年間保存
- 障害者総合支援法：サービス提供記録を5年間保存
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from uuid import UUID

from app import schemas
from app.api import deps
from app.crud.crud_archived_staff import archived_staff
from app.models.staff import Staff
from app.messages import ja

router = APIRouter()


@router.get("/", response_model=schemas.archived_staff.ArchivedStaffListResponse)
async def list_archived_staffs(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: Staff = Depends(deps.require_app_admin),
    skip: int = 0,
    limit: int = 100,
    office_id: Optional[UUID] = None,
    archive_reason: Optional[str] = None
):
    """
    アーカイブスタッフリスト取得（app_adminのみ）

    Args:
        db: データベースセッション
        current_user: 認証済みapp_adminユーザー
        skip: スキップ件数（ページネーション）
        limit: 取得件数（最大100件）
        office_id: 事務所IDでフィルタリング（オプション）
        archive_reason: アーカイブ理由でフィルタリング（オプション）

    Returns:
        アーカイブスタッフリスト（ページネーション対応）

    権限: app_admin のみアクセス可能
    """
    # limit の最大値チェック
    if limit > 100:
        limit = 100

    # アーカイブリスト取得
    archives, total = await archived_staff.get_multi(
        db,
        skip=skip,
        limit=limit,
        office_id=office_id,
        archive_reason=archive_reason,
        exclude_test_data=True
    )

    # レスポンス作成
    return schemas.archived_staff.ArchivedStaffListResponse(
        items=[
            schemas.archived_staff.ArchivedStaffListItem.model_validate(archive)
            for archive in archives
        ],
        total=total,
        skip=skip,
        limit=limit
    )


@router.get("/{archive_id}", response_model=schemas.archived_staff.ArchivedStaffRead)
async def get_archived_staff(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: Staff = Depends(deps.require_app_admin),
    archive_id: UUID
):
    """
    アーカイブスタッフ詳細取得（app_adminのみ）

    Args:
        db: データベースセッション
        current_user: 認証済みapp_adminユーザー
        archive_id: アーカイブID

    Returns:
        アーカイブスタッフ詳細

    Raises:
        HTTPException: 404 - アーカイブが存在しない

    権限: app_admin のみアクセス可能
    """
    # アーカイブ取得
    archive = await archived_staff.get(db, archive_id=archive_id)

    if not archive:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="指定されたアーカイブが見つかりません"
        )

    return schemas.archived_staff.ArchivedStaffRead.model_validate(archive)
