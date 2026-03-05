"""
Web Push通知購読APIエンドポイント
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.api import deps
from app.models.staff import Staff
from app.schemas.push_subscription import (
    PushSubscriptionCreate,
    PushSubscriptionResponse,
    PushSubscriptionInDB
)
from app import crud
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/subscribe", response_model=PushSubscriptionResponse)
async def subscribe_push(
    request: Request,
    subscription: PushSubscriptionCreate,
    current_user: Staff = Depends(deps.get_current_user),
    db: AsyncSession = Depends(deps.get_db)
):
    """
    Web Push通知購読登録

    スタッフのデバイスをWeb Push通知の購読リストに追加します。
    同一エンドポイントが既に存在する場合は、情報を更新します。

    Args:
        request: FastAPI Request
        subscription: 購読情報（endpoint, keys）
        current_user: 認証済みスタッフ
        db: データベースセッション

    Returns:
        PushSubscriptionResponse: 登録された購読情報

    Raises:
        HTTPException: 登録失敗時

    Example:
        POST /api/v1/push-subscriptions/subscribe
        {
            "endpoint": "https://fcm.googleapis.com/fcm/send/...",
            "keys": {
                "p256dh": "BNcRd...",
                "auth": "tBHI..."
            }
        }
    """
    try:
        user_agent = request.headers.get("User-Agent")

        new_subscription = await crud.push_subscription.create_or_update(
            db=db,
            staff_id=current_user.id,
            endpoint=subscription.endpoint,
            p256dh_key=subscription.keys.p256dh,
            auth_key=subscription.keys.auth,
            user_agent=user_agent
        )

        logger.info(
            f"[PUSH_SUBSCRIPTION] Staff {current_user.email} subscribed "
            f"(subscription_id: {new_subscription.id})"
        )

        return new_subscription

    except Exception as e:
        logger.error(f"[PUSH_SUBSCRIPTION] Failed to subscribe: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="プッシュ通知の登録に失敗しました")


@router.delete("/unsubscribe")
async def unsubscribe_push(
    endpoint: str,
    current_user: Staff = Depends(deps.get_current_user),
    db: AsyncSession = Depends(deps.get_db)
):
    """
    Web Push通知購読解除

    指定したエンドポイントの購読情報を削除します。

    Args:
        endpoint: 削除対象のエンドポイントURL
        current_user: 認証済みスタッフ
        db: データベースセッション

    Returns:
        dict: 成功メッセージ

    Raises:
        HTTPException: 削除失敗時

    Example:
        DELETE /api/v1/push-subscriptions/unsubscribe?endpoint=https://fcm.googleapis.com/...
    """
    try:
        existing = await crud.push_subscription.get_by_endpoint(db=db, endpoint=endpoint)

        if not existing:
            raise HTTPException(status_code=404, detail="サブスクリプションが見つかりません")

        if existing.staff_id != current_user.id:
            raise HTTPException(status_code=403, detail="このサブスクリプションを削除する権限がありません")

        deleted = await crud.push_subscription.delete_by_endpoint(db=db, endpoint=endpoint)

        if not deleted:
            raise HTTPException(status_code=404, detail="サブスクリプションが見つかりません")

        logger.info(
            f"[PUSH_SUBSCRIPTION] Staff {current_user.email} unsubscribed "
            f"(endpoint: {endpoint[:50]}...)"
        )

        return {"message": "Unsubscribed successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PUSH_SUBSCRIPTION] Failed to unsubscribe: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="プッシュ通知の解除に失敗しました")


@router.get("/my-subscriptions", response_model=List[PushSubscriptionResponse])
async def get_my_subscriptions(
    current_user: Staff = Depends(deps.get_current_user),
    db: AsyncSession = Depends(deps.get_db)
):
    """
    自分の購読情報一覧を取得

    現在ログイン中のスタッフの全デバイスの購読情報を取得します。

    Args:
        current_user: 認証済みスタッフ
        db: データベースセッション

    Returns:
        List[PushSubscriptionResponse]: 購読情報のリスト

    Example:
        GET /api/v1/push-subscriptions/my-subscriptions
    """
    try:
        subscriptions = await crud.push_subscription.get_by_staff_id(
            db=db,
            staff_id=current_user.id
        )

        return subscriptions

    except Exception as e:
        logger.error(f"[PUSH_SUBSCRIPTION] Failed to get subscriptions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="サブスクリプション一覧の取得に失敗しました")


