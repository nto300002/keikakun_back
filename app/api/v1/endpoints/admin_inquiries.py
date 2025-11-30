"""
app_admin用問い合わせAPIエンドポイント

スタッフからの問い合わせ（MessageType.inquiry）を管理
"""
from typing import List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.api.deps import get_db, require_app_admin
from app.models.staff import Staff
from app.models.message import Message
from app.models.enums import MessageType
from app.schemas.message import MessageResponse

router = APIRouter()


@router.get("", response_model=dict)
async def get_inquiries(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: Staff = Depends(require_app_admin),
    skip: int = Query(0, ge=0, description="スキップ数"),
    limit: int = Query(30, ge=1, le=100, description="取得数上限（最大100）")
) -> dict:
    """
    問い合わせ一覧を取得（app_admin専用）

    スタッフからの問い合わせ（MessageType.inquiry）を取得

    - **skip**: ページネーション用オフセット
    - **limit**: 取得件数（デフォルト30件、最大100件）
    """
    # 問い合わせメッセージを取得
    query = (
        select(Message)
        .where(Message.message_type == MessageType.inquiry)
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
        .where(Message.message_type == MessageType.inquiry)
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
        "inquiries": items,  # フロントエンドは "inquiries" キーを期待
        "total": total,
        "skip": skip,
        "limit": limit
    }
