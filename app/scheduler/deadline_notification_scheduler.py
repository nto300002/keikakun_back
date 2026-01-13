"""
期限アラートメール通知スケジューラー

定期実行スケジュール:
- 期限アラートメール送信: 毎日 0:00 UTC (9:00 JST)
- 実行条件: 平日かつ祝日でない場合のみ
"""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.tasks.deadline_notification import send_deadline_alert_emails
from app.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

deadline_notification_scheduler = AsyncIOScheduler()


async def scheduled_send_alerts():
    """
    期限アラートメール送信のスケジュール実行

    実行頻度: 毎日 0:00 UTC (9:00 JST)
    実行条件: 平日かつ祝日でない場合のみ（バッチ処理内で判定）
    処理内容:
    - 全事業所の期限アラートを取得
    - 該当事業所の全スタッフにメール送信
    """
    async with AsyncSessionLocal() as db:
        try:
            count = await send_deadline_alert_emails(db=db)
            logger.info(
                f"[DEADLINE_NOTIFICATION_SCHEDULER] Email notification completed: "
                f"{count} email(s) sent"
            )
        except Exception as e:
            logger.error(
                f"[DEADLINE_NOTIFICATION_SCHEDULER] Email notification failed: {e}",
                exc_info=True
            )


def start():
    """スケジューラーを開始"""
    deadline_notification_scheduler.add_job(
        scheduled_send_alerts,
        trigger=CronTrigger(hour=0, minute=0, timezone='UTC'),
        id='send_deadline_alert_emails',
        replace_existing=True,
        name='期限アラートメール送信'
    )

    deadline_notification_scheduler.start()
    logger.info(
        "[DEADLINE_NOTIFICATION_SCHEDULER] Started successfully\n"
        "  - send_deadline_alert_emails: Daily at 0:00 UTC (9:00 JST)"
    )


def shutdown():
    """スケジューラーをシャットダウン"""
    deadline_notification_scheduler.shutdown(wait=True)
    logger.info("[DEADLINE_NOTIFICATION_SCHEDULER] Shutdown completed")
