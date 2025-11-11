"""
通知APIエンドポイント

スタッフ宛の通知を管理するためのAPI
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from uuid import UUID

from app.api import deps
from app.models.staff import Staff
from app.schemas.notice import NoticeResponse, NoticeListResponse
from app.crud.crud_notice import crud_notice

router = APIRouter()


@router.get("", response_model=NoticeListResponse)
async def get_notices(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: Staff = Depends(deps.get_current_user),
    is_read: Optional[bool] = Query(None),
    type: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100)
) -> NoticeListResponse:
    """
    自分宛の通知一覧を取得

    - is_read: 既読フィルタリング（true=既読のみ、false=未読のみ）
    - type: 通知タイプでフィルタリング
    - skip: スキップ数
    - limit: 取得数上限
    """
    # 自分宛の通知を取得
    if is_read is False:
        # 未読のみ
        notices = await crud_notice.get_unread_by_staff_id(
            db=db,
            staff_id=current_user.id
        )
    elif type:
        # タイプでフィルタリング
        notices = await crud_notice.get_by_type(
            db=db,
            staff_id=current_user.id,
            notice_type=type
        )
    else:
        # 全て取得
        notices = await crud_notice.get_by_staff_id(
            db=db,
            staff_id=current_user.id
        )

    # is_read=trueの場合、既読のみフィルタリング
    if is_read is True:
        notices = [n for n in notices if n.is_read]

    # 未読件数を計算
    unread_notices = await crud_notice.get_unread_by_staff_id(
        db=db,
        staff_id=current_user.id
    )
    unread_count = len(unread_notices)

    # ページネーション
    total = len(notices)
    notices = notices[skip : skip + limit]

    return NoticeListResponse(
        notices=notices,
        total=total,
        unread_count=unread_count
    )


@router.get("/unread-count")
async def get_unread_count(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: Staff = Depends(deps.get_current_user)
) -> dict:
    """
    未読通知の件数を取得
    """
    unread_notices = await crud_notice.get_unread_by_staff_id(
        db=db,
        staff_id=current_user.id
    )
    return {"unread_count": len(unread_notices)}


@router.patch("/{notice_id}/read", response_model=NoticeResponse)
async def mark_notice_as_read(
    *,
    db: AsyncSession = Depends(deps.get_db),
    notice_id: UUID,
    current_user: Staff = Depends(deps.get_current_user)
) -> NoticeResponse:
    """
    通知を既読にする

    - 自分宛の通知のみ既読化可能
    """
    # 通知を取得
    notice = await crud_notice.get(db=db, id=notice_id)
    if not notice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notice not found"
        )

    # 自分宛の通知かチェック
    if notice.recipient_staff_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only mark your own notices as read"
        )

    # 既読にする
    updated_notice = await crud_notice.mark_as_read(db=db, notice_id=notice_id)
    return updated_notice


@router.patch("/read-all")
async def mark_all_notices_as_read(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: Staff = Depends(deps.get_current_user)
) -> dict:
    """
    全通知を既読にする

    - 自分宛の全未読通知を既読化
    """
    marked_count = await crud_notice.mark_all_as_read(
        db=db,
        staff_id=current_user.id
    )
    return {"marked_count": marked_count}


@router.delete("/{notice_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notice(
    *,
    db: AsyncSession = Depends(deps.get_db),
    notice_id: UUID,
    current_user: Staff = Depends(deps.get_current_user)
):
    """
    通知を削除

    - 自分宛の通知のみ削除可能
    """
    # 通知を取得
    notice = await crud_notice.get(db=db, id=notice_id)
    if not notice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notice not found"
        )

    # 自分宛の通知かチェック
    if notice.recipient_staff_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your own notices"
        )

    # 削除
    await crud_notice.remove(db=db, id=notice_id)
    await db.commit()
