"""
Web Push通知送信サービス

pywebpushライブラリを使用してWeb Push通知を送信します。
"""
import logging
import json
from typing import Optional, Dict, Any
from pywebpush import webpush, WebPushException

from app.core.config import settings

logger = logging.getLogger(__name__)


async def send_push_notification(
    subscription_info: Dict[str, Any],
    title: str,
    body: str,
    icon: str = "/icon-192.png",
    badge: str = "/icon-192.png",
    data: Optional[Dict[str, Any]] = None,
    actions: Optional[list] = None
) -> tuple[bool, bool]:
    """
    Web Push通知を送信

    Args:
        subscription_info: Push購読情報 {"endpoint": str, "keys": {"p256dh": str, "auth": str}}
        title: 通知タイトル
        body: 通知本文
        icon: アイコンURL（デフォルト: /icon-192.png）
        badge: バッジURL（デフォルト: /icon-192.png）
        data: 追加データ（任意）
        actions: 通知アクション（任意）

    Returns:
        tuple[bool, bool]: (送信成功, DBから削除すべきか)
            - (True, False): 送信成功
            - (False, True): 購読が無効（410/404）→DBから削除すべき
            - (False, False): その他のエラー

    Example:
        >>> subscription_info = {
        ...     "endpoint": "https://fcm.googleapis.com/fcm/send/...",
        ...     "keys": {"p256dh": "BNcRd...", "auth": "tBHI..."}
        ... }
        >>> success, should_delete = await send_push_notification(
        ...     subscription_info=subscription_info,
        ...     title="期限アラート",
        ...     body="更新期限が近づいています",
        ...     data={"type": "deadline_alert", "count": 5}
        ... )
        >>> if should_delete:
        ...     # DBから購読を削除
        ...     pass
    """
    if not settings.VAPID_PRIVATE_KEY or not settings.VAPID_SUBJECT:
        logger.error("[PUSH] VAPID settings not configured. Cannot send push notifications.")
        return (False, False)

    try:
        payload = {
            "title": title,
            "body": body,
            "icon": icon,
            "badge": badge,
            "data": data or {},
            "requireInteraction": True
        }

        if actions:
            payload["actions"] = actions

        webpush(
            subscription_info=subscription_info,
            data=json.dumps(payload),
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": settings.VAPID_SUBJECT}
        )

        endpoint_preview = subscription_info.get("endpoint", "")[:50]
        logger.info(f"[PUSH] Notification sent successfully to {endpoint_preview}...")
        return (True, False)

    except WebPushException as e:
        endpoint_preview = subscription_info.get("endpoint", "")[:50]

        # Response オブジェクトの bool() は False を返すことがあるため、is not None で確認
        if e.response is not None and hasattr(e.response, 'status_code') and e.response.status_code in [404, 410]:
            logger.warning(
                f"[PUSH] Subscription expired (HTTP {e.response.status_code}): "
                f"{endpoint_preview}... - Marking for deletion from database"
            )
            return (False, True)
        else:
            logger.error(
                f"[PUSH] Failed to send notification to {endpoint_preview}...: {e}",
                exc_info=True
            )
            return (False, False)

    except Exception as e:
        logger.error(f"[PUSH] Unexpected error during push notification: {e}", exc_info=True)
        return (False, False)
