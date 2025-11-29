"""
app_admin用お知らせAPIエンドポイント

全スタッフへのお知らせ（MessageType.announcement）を管理
"""
from fastapi import APIRouter, Depends, Query, Request, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.api.deps import get_db, require_app_admin, validate_csrf
from app.models.staff import Staff
from app.models.message import Message
from app.models.enums import MessageType
from app.schemas.message import MessageResponse, MessageAnnouncementCreate, MessageDetailResponse
from app.crud.crud_message import crud_message
from app import crud

router = APIRouter()


@router.get("", response_model=dict)
async def get_announcements(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: Staff = Depends(require_app_admin),
    skip: int = Query(0, ge=0, description="スキップ数"),
    limit: int = Query(30, ge=1, le=100, description="取得数上限（最大100）")
) -> dict:
    """
    お知らせ一覧を取得（app_admin専用）

    全スタッフへのお知らせ（MessageType.announcement）を取得

    - **skip**: ページネーション用オフセット
    - **limit**: 取得件数（デフォルト30件、最大100件）
    """
    # お知らせメッセージを取得
    query = (
        select(Message)
        .where(Message.message_type == MessageType.announcement)
        .options(
            selectinload(Message.sender),
            selectinload(Message.office),
            selectinload(Message.recipients)
        )
        .order_by(Message.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    result = await db.execute(query)
    messages = list(result.scalars().all())

    # 総件数を取得
    count_query = (
        select(func.count())
        .select_from(Message)
        .where(Message.message_type == MessageType.announcement)
    )
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    # レスポンスを作成（フロントエンドの期待する形式に合わせる）
    items = []
    for message in messages:
        item = MessageResponse.model_validate(message).model_dump()
        item["recipient_count"] = len(message.recipients) if message.recipients else 0
        items.append(item)

    return {
        "announcements": items,  # フロントエンドは "announcements" キーを期待
        "total": total,
        "skip": skip,
        "limit": limit
    }


@router.post("", response_model=MessageDetailResponse, status_code=status.HTTP_201_CREATED)
async def send_announcement_to_all(
    *,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Staff = Depends(require_app_admin),
    message_in: MessageAnnouncementCreate,
    _: None = Depends(validate_csrf)
):
    """
    全事務所の全スタッフへお知らせを送信（app_admin専用）

    - app_admin権限が必要
    - 全事務所の全スタッフに一斉送信
    - CSRF保護: Cookie認証の場合はCSRFトークンが必要
    """
    # 全スタッフを取得（app_admin自身を除く）
    all_staff_query = (
        select(Staff)
        .where(
            Staff.is_deleted == False,  # noqa: E712
            Staff.id != current_user.id
        )
    )
    all_staff_result = await db.execute(all_staff_query)
    all_staff = list(all_staff_result.scalars().all())

    if not all_staff:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="送信先のスタッフが存在しません"
        )

    # 事務所IDを取得（最初のスタッフの事務所、またはNone）
    office_id = None
    if all_staff and all_staff[0].office_associations:
        office_id = all_staff[0].office_associations[0].office_id

    recipient_ids = [staff.id for staff in all_staff]

    # お知らせを作成
    message_data = {
        "sender_staff_id": current_user.id,
        "office_id": office_id,  # app_adminの場合はNULLでも良い
        "recipient_ids": recipient_ids,
        "message_type": MessageType.announcement,
        "priority": message_in.priority,
        "title": message_in.title,
        "content": message_in.content
    }

    message = await crud_message.create_announcement(db=db, obj_in=message_data)
    await db.commit()
    await db.refresh(message, ["sender", "recipients"])

    # レスポンスを作成
    response_data = MessageDetailResponse.model_validate(message)
    response_dict = response_data.model_dump()
    response_dict["recipient_count"] = len(message.recipients)

    return response_dict
