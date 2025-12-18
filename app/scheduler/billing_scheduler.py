"""
課金関連スケジューラー - トライアル期間終了チェック

定期実行スケジュール:
- トライアル期間終了チェック: 毎日 0:00 UTC
"""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.tasks.billing_check import check_trial_expiration
from app.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

# スケジューラーインスタンス作成
billing_scheduler = AsyncIOScheduler()


async def scheduled_trial_check():
    """
    トライアル期間終了チェックのスケジュール実行

    実行頻度: 毎日 0:00 UTC
    処理内容: trial_end_date が過去で billing_status = 'free' のレコードを past_due に更新
    """
    async with AsyncSessionLocal() as db:
        try:
            count = await check_trial_expiration(db=db)
            logger.info(
                f"[BILLING_SCHEDULER] Trial expiration check completed: "
                f"{count} billing(s) updated to past_due"
            )
        except Exception as e:
            logger.error(
                f"[BILLING_SCHEDULER] Trial expiration check failed: {e}",
                exc_info=True
            )


def start():
    """スケジューラーを開始"""
    # トライアル期間終了チェック - 毎日 0:00 UTC に実行
    billing_scheduler.add_job(
        scheduled_trial_check,
        trigger=CronTrigger(hour=0, minute=0, timezone='UTC'),
        id='check_trial_expiration',
        replace_existing=True,
        name='トライアル期間終了チェック'
    )

    billing_scheduler.start()
    logger.info(
        "[BILLING_SCHEDULER] Started successfully\n"
        "  - check_trial_expiration: Daily at 0:00 UTC"
    )


def shutdown():
    """スケジューラーをシャットダウン"""
    billing_scheduler.shutdown(wait=True)
    logger.info("[BILLING_SCHEDULER] Shutdown completed")
