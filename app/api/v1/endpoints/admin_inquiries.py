"""
app_admin用問い合わせAPIエンドポイント

InquiryDetailとMessageを使った問い合わせ管理機能
"""
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_app_admin
from app.models.staff import Staff
from app.models.enums import InquiryStatus, InquiryPriority
from app.crud.crud_inquiry import crud_inquiry
from app.schemas.inquiry import (
    InquiryListResponse,
    InquiryListItem,
    InquiryFullResponse,
    InquiryUpdate,
    InquiryUpdateResponse,
    InquiryDeleteResponse,
    InquiryDetailResponse,
    InquiryReply,
    InquiryReplyResponse,
    MessageInfo,
    StaffInfo
)

router = APIRouter()


@router.get("", response_model=InquiryListResponse)
async def get_inquiries(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: Staff = Depends(require_app_admin),
    status: Optional[InquiryStatus] = Query(None, description="ステータスフィルタ"),
    assigned: Optional[UUID] = Query(None, description="担当者IDフィルタ"),
    priority: Optional[InquiryPriority] = Query(None, description="優先度フィルタ"),
    search: Optional[str] = Query(None, max_length=200, description="キーワード検索（件名・本文）"),
    skip: int = Query(0, ge=0, description="オフセット"),
    limit: int = Query(20, ge=1, le=100, description="取得件数"),
    sort: str = Query("created_at", description="ソートキー（created_at | updated_at | priority）"),
    order: str = Query("desc", description="ソート順（asc | desc）"),
    include_test_data: bool = Query(False, description="テストデータを含めるか")
) -> InquiryListResponse:
    """
    問い合わせ一覧を取得（app_admin専用）

    - **status**: ステータスフィルタ (new, open, in_progress, answered, closed, spam)
    - **assigned**: 担当者IDフィルタ
    - **priority**: 優先度フィルタ (low, normal, high)
    - **search**: 検索キーワード（件名・本文を対象）
    - **skip**: ページネーション用オフセット
    - **limit**: 取得件数（デフォルト20件、最大100件）
    - **sort**: ソートキー（created_at, updated_at, priority）
    - **order**: ソート順（asc, desc）
    - **include_test_data**: テストデータを含めるか（デフォルトfalse）
    """
    # バリデーション
    if sort not in ["created_at", "updated_at", "priority"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ソートキーは created_at, updated_at, priority のいずれかを指定してください"
        )

    if order not in ["asc", "desc"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ソート順は asc または desc を指定してください"
        )

    # CRUD層から取得
    inquiries, total = await crud_inquiry.get_inquiries(
        db=db,
        status=status,
        assigned_staff_id=assigned,
        priority=priority,
        search=search,
        skip=skip,
        limit=limit,
        sort=sort,
        order=order,
        include_test_data=include_test_data
    )

    # レスポンス変換
    items = []
    for inquiry in inquiries:
        # Message情報から件名と内容を取得
        title = inquiry.message.title if inquiry.message else ""
        content = inquiry.message.content if inquiry.message else ""

        # 担当者情報を取得
        assigned_staff_info = None
        if inquiry.assigned_staff:
            assigned_staff_info = StaffInfo.model_validate(inquiry.assigned_staff)

        item = InquiryListItem(
            id=inquiry.id,
            message_id=inquiry.message_id,
            title=title,
            content=content,
            status=inquiry.status,
            priority=inquiry.priority,
            sender_name=inquiry.sender_name,
            sender_email=inquiry.sender_email,
            assigned_staff_id=inquiry.assigned_staff_id,
            assigned_staff=assigned_staff_info,
            created_at=inquiry.created_at,
            updated_at=inquiry.updated_at
        )
        items.append(item)

    return InquiryListResponse(
        inquiries=items,
        total=total
    )


@router.get("/{inquiry_id}", response_model=InquiryFullResponse)
async def get_inquiry(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: Staff = Depends(require_app_admin),
    inquiry_id: UUID
) -> InquiryFullResponse:
    """
    問い合わせ詳細を取得（app_admin専用）

    - **inquiry_id**: 問い合わせID
    """
    inquiry = await crud_inquiry.get_inquiry_by_id(db=db, inquiry_id=inquiry_id)

    if not inquiry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="問い合わせが見つかりません"
        )

    # Message情報を取得
    message_info = MessageInfo.model_validate(inquiry.message)

    # InquiryDetail情報を取得
    inquiry_detail = InquiryDetailResponse.model_validate(inquiry)

    # 担当者情報を取得
    assigned_staff_info = None
    if inquiry.assigned_staff:
        assigned_staff_info = StaffInfo.model_validate(inquiry.assigned_staff)

    return InquiryFullResponse(
        id=inquiry.id,
        message=message_info,
        inquiry_detail=inquiry_detail,
        assigned_staff=assigned_staff_info,
        reply_history=None  # 将来の拡張用
    )


@router.patch("/{inquiry_id}", response_model=InquiryUpdateResponse)
async def update_inquiry(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: Staff = Depends(require_app_admin),
    inquiry_id: UUID,
    inquiry_in: InquiryUpdate
) -> InquiryUpdateResponse:
    """
    問い合わせを更新（app_admin専用）

    - **inquiry_id**: 問い合わせID
    - **status**: ステータス
    - **assigned_staff_id**: 担当者ID
    - **priority**: 優先度
    - **admin_notes**: 管理者メモ
    """
    try:
        await crud_inquiry.update_inquiry(
            db=db,
            inquiry_id=inquiry_id,
            status=inquiry_in.status,
            assigned_staff_id=inquiry_in.assigned_staff_id,
            priority=inquiry_in.priority,
            admin_notes=inquiry_in.admin_notes
        )
        await db.commit()

        return InquiryUpdateResponse(
            id=inquiry_id,
            message="更新しました"
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"問い合わせの更新に失敗しました: {str(e)}"
        )


@router.post("/{inquiry_id}/reply", response_model=InquiryReplyResponse)
async def reply_to_inquiry(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: Staff = Depends(require_app_admin),
    inquiry_id: UUID,
    reply_in: InquiryReply
) -> InquiryReplyResponse:
    """
    問い合わせに返信（app_admin専用）

    - **inquiry_id**: 問い合わせID
    - **body**: 返信内容
    - **send_email**: メール送信するか（デフォルト: false）

    Note:
        - 返信用のMessageを作成
        - 送信者がログイン済みの場合はMessageRecipientを作成（内部通知）
        - 問い合わせステータスを「answered」に更新
        - メール送信フラグがTrueの場合は実際にメールを送信
    """
    try:
        # メール送信用にcommit前に問い合わせ情報を取得
        email_data = None
        if reply_in.send_email:
            inquiry = await crud_inquiry.get_inquiry_by_id(db=db, inquiry_id=inquiry_id)
            if inquiry and inquiry.sender_email:
                # メール送信に必要な情報を事前に取得
                original_message = inquiry.message
                email_data = {
                    "recipient_email": inquiry.sender_email,
                    "recipient_name": inquiry.sender_name,
                    "inquiry_title": original_message.title if original_message else "問い合わせ",
                    "inquiry_created_at": inquiry.created_at.isoformat() if inquiry.created_at else "",
                    "reply_content": reply_in.body,
                }

        reply_message = await crud_inquiry.create_reply(
            db=db,
            inquiry_id=inquiry_id,
            reply_staff_id=current_user.id,
            reply_content=reply_in.body,
            send_email=reply_in.send_email
        )

        # コミット前に必要な値を取得（重要！）
        reply_message_id = reply_message.id

        await db.commit()

        # メール送信処理（commit後、ベストエフォート）
        if email_data:
            try:
                from app.core.mail import send_inquiry_reply_email
                await send_inquiry_reply_email(
                    recipient_email=email_data["recipient_email"],
                    recipient_name=email_data["recipient_name"],
                    inquiry_title=email_data["inquiry_title"],
                    inquiry_created_at=email_data["inquiry_created_at"],
                    reply_content=email_data["reply_content"],
                )
            except Exception as email_error:
                # メール送信失敗してもエラーにしない（ログのみ）
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"問い合わせ返信メール送信に失敗: {str(email_error)}")

        # メッセージ内容を決定
        if reply_in.send_email:
            message_text = "返信を送信しました（メール送信を含む）"
        else:
            message_text = "返信を送信しました（内部通知のみ）"

        return InquiryReplyResponse(
            id=reply_message_id,
            message=message_text
        )
    except ValueError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"返信の送信に失敗しました: {str(e)}"
        )


@router.delete("/{inquiry_id}", response_model=InquiryDeleteResponse)
async def delete_inquiry(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: Staff = Depends(require_app_admin),
    inquiry_id: UUID
) -> InquiryDeleteResponse:
    """
    問い合わせを削除（app_admin専用）

    - **inquiry_id**: 問い合わせID

    Note:
        InquiryDetailを削除すると、CASCADEによりMessageとMessageRecipientも削除されます
    """
    try:
        result = await crud_inquiry.delete_inquiry(db=db, inquiry_id=inquiry_id)

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="問い合わせが見つかりません"
            )

        await db.commit()

        return InquiryDeleteResponse(
            message="削除しました"
        )
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"問い合わせの削除に失敗しました: {str(e)}"
        )
