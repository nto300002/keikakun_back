"""
メール送信ユーティリティ

リトライポリシー、delivery_log記録、エラーハンドリングを提供
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def send_email_with_retry(
    email_func: Callable,
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    **email_kwargs
) -> Dict[str, Any]:
    """
    Exponential backoff でメールを送信します。

    Args:
        email_func: メール送信関数
        max_retries: 最大リトライ回数
        initial_delay: 初回リトライまでの待機時間（秒）
        max_delay: 最大待機時間（秒）
        backoff_factor: バックオフ係数
        **email_kwargs: メール送信関数に渡す引数

    Returns:
        送信結果を含む辞書
        {
            "success": bool,
            "error": Optional[str],
            "retry_count": int,
            "sent_at": Optional[str]
        }
    """
    result = {
        "success": False,
        "error": None,
        "retry_count": 0,
        "sent_at": None
    }

    delay = initial_delay
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            await email_func(**email_kwargs)
            result["success"] = True
            result["sent_at"] = datetime.now(timezone.utc).isoformat()
            result["retry_count"] = attempt

            if attempt > 0:
                logger.info(
                    f"メール送信成功（リトライ {attempt}回目）: {email_kwargs.get('recipient_email', 'unknown')}"
                )

            return result

        except Exception as e:
            last_error = str(e)
            result["retry_count"] = attempt

            logger.warning(
                f"メール送信失敗（試行 {attempt + 1}/{max_retries + 1}）: {last_error}"
            )

            # 最後の試行でなければリトライ
            if attempt < max_retries:
                await asyncio.sleep(min(delay, max_delay))
                delay *= backoff_factor
            else:
                # すべてのリトライが失敗
                result["error"] = last_error
                logger.error(
                    f"メール送信失敗（すべてのリトライ失敗）: {email_kwargs.get('recipient_email', 'unknown')} - {last_error}"
                )

    return result


def create_delivery_log_entry(
    recipient: str,
    subject: str,
    result: Dict[str, Any],
    email_type: str = "general"
) -> Dict[str, Any]:
    """
    delivery_log用のエントリを作成します。

    Args:
        recipient: 受信者メールアドレス
        subject: メール件名
        result: send_email_with_retryの結果
        email_type: メールタイプ（inquiry_received, inquiry_reply, withdrawal_rejected等）

    Returns:
        delivery_log JSONに追加するエントリ
    """
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "recipient": recipient,
        "subject": subject,
        "email_type": email_type,
        "success": result["success"],
        "error": result.get("error"),
        "retry_count": result["retry_count"],
        "sent_at": result.get("sent_at")
    }


async def send_and_log_email(
    db: AsyncSession,
    inquiry_detail_id: UUID,
    email_func: Callable,
    recipient: str,
    subject: str,
    email_type: str = "general",
    max_retries: int = 3,
    **email_kwargs
) -> bool:
    """
    メールを送信し、delivery_logに記録します。

    Args:
        db: データベースセッション
        inquiry_detail_id: InquiryDetailのID
        email_func: メール送信関数
        recipient: 受信者メールアドレス
        subject: メール件名
        email_type: メールタイプ
        max_retries: 最大リトライ回数
        **email_kwargs: メール送信関数に渡す引数

    Returns:
        送信成功したかどうか
    """
    from app.crud.crud_inquiry import inquiry_detail as inquiry_detail_crud

    # メール送信（リトライ付き）
    result = await send_email_with_retry(
        email_func=email_func,
        max_retries=max_retries,
        recipient_email=recipient,
        **email_kwargs
    )

    # delivery_logエントリ作成
    log_entry = create_delivery_log_entry(
        recipient=recipient,
        subject=subject,
        result=result,
        email_type=email_type
    )

    # InquiryDetailのdelivery_logに追加
    await inquiry_detail_crud.append_delivery_log(
        db=db,
        inquiry_detail_id=inquiry_detail_id,
        log_entry=log_entry
    )

    # 送信失敗時は監査ログに記録
    if not result["success"]:
        from app.crud.crud_audit_log import audit_log

        # システム送信のため、actor_idはダミーのUUIDを使用
        # TODO: システムアカウントのUUIDを設定する
        import uuid
        system_actor_id = uuid.UUID('00000000-0000-0000-0000-000000000000')

        await audit_log.create_log(
            db=db,
            actor_id=system_actor_id,
            action="email_send_failed",
            target_type="inquiry_detail",
            target_id=inquiry_detail_id,
            details={
                "recipient": recipient,
                "subject": subject,
                "email_type": email_type,
                "error": result["error"],
                "retry_count": result["retry_count"]
            }
        )

        logger.error(
            f"メール送信失敗を監査ログに記録: inquiry_detail_id={inquiry_detail_id}, "
            f"recipient={recipient}, error={result['error']}"
        )

    return result["success"]
