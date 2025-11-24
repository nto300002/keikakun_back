"""
メッセージAPIエンドポイント

個別メッセージ、一斉通知、受信箱、統計などのAPI
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from uuid import UUID

from app.api import deps
from app.models.staff import Staff
from app.models.enums import MessageType, MessagePriority, StaffRole
from app.schemas.message import (
    MessagePersonalCreate,
    MessageAnnouncementCreate,
    MessageResponse,
    MessageDetailResponse,
    MessageInboxResponse,
    MessageInboxItem,
    MessageStatsResponse,
    UnreadCountResponse,
    MessageMarkAsReadRequest,
    MessageArchiveRequest,
    MessageRecipientResponse,
    MessageBulkMarkAsReadRequest,
    MessageBulkOperationResponse
)
from app.crud.crud_message import crud_message
from app import crud

router = APIRouter()


@router.post("/personal", response_model=MessageDetailResponse, status_code=status.HTTP_201_CREATED)
async def send_personal_message(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: Staff = Depends(deps.get_current_user),
    message_in: MessagePersonalCreate
):
    """
    個別メッセージを送信

    - 受信者と送信者は同じ事務所に所属している必要がある
    - 受信者は1〜100人まで指定可能
    """
    # 送信者の事務所を取得
    if not current_user.office_associations:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="事務所に所属していません"
        )

    sender_office_id = current_user.office_associations[0].office_id

    # 受信者が存在し、同じ事務所に所属しているか確認
    for recipient_id in message_in.recipient_staff_ids:
        recipient = await crud.staff.get(db=db, id=recipient_id)
        if not recipient:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="指定された受信者の一部が無効です"  # セキュリティ: UUIDを含めない
            )

        # アカウント有効性チェック
        if recipient.is_locked:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="無効なアカウントには送信できません"
            )

        # 受信者が同じ事務所に所属しているか確認
        recipient_office_ids = [
            assoc.office_id for assoc in recipient.office_associations
        ]
        if sender_office_id not in recipient_office_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="異なる事務所のスタッフには送信できません"
            )

    # メッセージを作成
    message_data = {
        "sender_staff_id": current_user.id,
        "office_id": sender_office_id,
        "recipient_ids": message_in.recipient_staff_ids,
        "message_type": MessageType.personal,
        "priority": message_in.priority,
        "title": message_in.title,
        "content": message_in.content
    }

    message = await crud_message.create_personal_message(db=db, obj_in=message_data)
    await db.commit()
    await db.refresh(message, ["sender", "recipients"])

    # レスポンスを作成
    response_data = MessageDetailResponse.model_validate(message)
    # recipient_countを追加
    response_dict = response_data.model_dump()
    response_dict["recipient_count"] = len(message.recipients)

    return response_dict


@router.post("/announcement", response_model=MessageDetailResponse, status_code=status.HTTP_201_CREATED)
async def send_announcement(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: Staff = Depends(deps.get_current_user),
    message_in: MessageAnnouncementCreate
):
    """
    一斉通知を送信（事務所内の全スタッフへ）

    - オーナーまたは管理者権限が必要
    - バルクインサート処理で効率的に配信
    """
    # 権限チェック: オーナーまたは管理者のみ
    if current_user.role not in [StaffRole.owner, StaffRole.manager]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="一斉通知を送信する権限がありません"
        )

    # 送信者の事務所を取得
    if not current_user.office_associations:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="事務所に所属していません"
        )

    sender_office_id = current_user.office_associations[0].office_id

    # 同じ事務所の全スタッフを取得
    all_staff = await crud.staff.get_by_office_id(db=db, office_id=sender_office_id)
    recipient_ids = [staff.id for staff in all_staff if staff.id != current_user.id]

    if not recipient_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="送信先のスタッフが存在しません"
        )

    # 一斉通知を作成
    message_data = {
        "sender_staff_id": current_user.id,
        "office_id": sender_office_id,
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


@router.get("/inbox", response_model=MessageInboxResponse)
async def get_inbox_messages(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: Staff = Depends(deps.get_current_user),
    is_read: Optional[bool] = Query(None, description="既読フィルタ"),
    message_type: Optional[MessageType] = Query(None, description="メッセージタイプフィルタ"),
    skip: int = Query(0, ge=0, description="スキップ数"),
    limit: int = Query(20, ge=1, le=100, description="取得数上限")
):
    """
    受信箱のメッセージ一覧を取得

    - is_read: 既読フィルタ（true=既読のみ、false=未読のみ）
    - message_type: メッセージタイプでフィルタ
    - skip: スキップ数
    - limit: 取得数上限（最大100）
    """
    # 受信箱のメッセージを取得
    messages = await crud_message.get_inbox_messages(
        db=db,
        recipient_staff_id=current_user.id,
        message_type=message_type,
        is_read=is_read,
        skip=skip,
        limit=limit
    )

    # 未読件数を取得
    unread_count = await crud_message.get_unread_count(
        db=db,
        recipient_staff_id=current_user.id
    )

    # MessageInboxItemに変換
    inbox_items = []
    for message in messages:
        # このメッセージの受信者情報を取得
        recipient_info = next(
            (r for r in message.recipients if r.recipient_staff_id == current_user.id),
            None
        )

        if recipient_info:
            sender_name = None
            if message.sender:
                sender_name = f"{message.sender.last_name} {message.sender.first_name}"

            inbox_item = MessageInboxItem(
                message_id=message.id,
                title=message.title,
                content=message.content,
                message_type=message.message_type,
                priority=message.priority,
                created_at=message.created_at,
                sender_staff_id=message.sender_staff_id,
                sender_name=sender_name,
                recipient_id=recipient_info.id,
                is_read=recipient_info.is_read,
                read_at=recipient_info.read_at,
                is_archived=recipient_info.is_archived
            )
            inbox_items.append(inbox_item)

    return MessageInboxResponse(
        messages=inbox_items,
        total=len(inbox_items),  # 簡易的にアイテム数を返す
        unread_count=unread_count
    )


@router.post("/{message_id}/read", response_model=MessageRecipientResponse)
async def mark_message_as_read(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: Staff = Depends(deps.get_current_user),
    message_id: UUID
):
    """
    メッセージを既読にする

    - 自分宛のメッセージのみ既読化できる
    """
    try:
        recipient = await crud_message.mark_as_read(
            db=db,
            message_id=message_id,
            recipient_staff_id=current_user.id
        )
        await db.commit()
        await db.refresh(recipient)

        return MessageRecipientResponse.model_validate(recipient)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.get("/{message_id}/stats", response_model=MessageStatsResponse)
async def get_message_stats(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: Staff = Depends(deps.get_current_user),
    message_id: UUID
):
    """
    メッセージの統計情報を取得

    - 送信者のみアクセス可能
    """
    # メッセージを取得
    message = await crud_message.get_message_by_id(db=db, message_id=message_id)
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="メッセージが見つかりません"
        )

    # 送信者かチェック
    if message.sender_staff_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="統計情報にアクセスする権限がありません"
        )

    # 統計情報を取得
    stats = await crud_message.get_message_stats(db=db, message_id=message_id)

    return MessageStatsResponse(
        message_id=message_id,
        total_recipients=stats["total_recipients"],
        read_count=stats["read_count"],
        unread_count=stats["unread_count"],
        read_rate=stats["read_rate"] / 100.0  # パーセントから0.0-1.0に変換
    )


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: Staff = Depends(deps.get_current_user)
):
    """
    未読メッセージ件数を取得（通知バッジ用）
    """
    unread_count = await crud_message.get_unread_count(
        db=db,
        recipient_staff_id=current_user.id
    )

    return UnreadCountResponse(unread_count=unread_count)


@router.post("/mark-all-read")
async def mark_all_as_read(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: Staff = Depends(deps.get_current_user)
):
    """
    全未読メッセージを既読にする
    """
    updated_count = await crud_message.mark_all_as_read(
        db=db,
        recipient_staff_id=current_user.id
    )
    await db.commit()

    return {"updated_count": updated_count}


@router.post("/{message_id}/archive", response_model=MessageRecipientResponse)
async def archive_message(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: Staff = Depends(deps.get_current_user),
    message_id: UUID,
    archive_request: MessageArchiveRequest
):
    """
    メッセージをアーカイブ/解除する

    - 自分宛のメッセージのみアーカイブできる
    """
    try:
        recipient = await crud_message.archive_message(
            db=db,
            message_id=message_id,
            recipient_staff_id=current_user.id,
            is_archived=archive_request.is_archived
        )
        await db.commit()
        await db.refresh(recipient)

        return MessageRecipientResponse.model_validate(recipient)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
