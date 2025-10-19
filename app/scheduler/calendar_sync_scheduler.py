"""カレンダー同期スケジューラー

未同期のカレンダーイベントを定期的にGoogle Calendarに同期する
バックグラウンドジョブを管理する。
"""

import asyncio
import logging
from typing import Optional
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.services.calendar_service import calendar_service
from app.db.session import AsyncSessionLocal


logger = logging.getLogger(__name__)


class CalendarSyncScheduler:
    """カレンダー同期スケジューラー

    APSchedulerを使用して、未同期のカレンダーイベントを
    定期的にGoogle Calendar APIに同期する。
    """

    def __init__(self, sync_interval_minutes: int = 5):
        """初期化

        Args:
            sync_interval_minutes: 同期間隔（分）。デフォルトは5分。
        """
        self.scheduler = BackgroundScheduler()
        self.job_id = "calendar_sync_job"
        self.sync_interval_minutes = sync_interval_minutes

    async def sync_all_pending_events(self) -> None:
        """全事業所の未同期イベントを同期する

        このメソッドはスケジューラーから定期的に呼び出される。
        """
        logger.info("=" * 80)
        logger.info("カレンダー同期ジョブ開始")
        logger.info("=" * 80)

        try:
            # 非同期セッションを作成
            async with AsyncSessionLocal() as db:
                # 全事業所の未同期イベントを同期
                result = await calendar_service.sync_pending_events(
                    db=db,
                    office_id=None  # None = 全事業所
                )

                synced_count = result.get("synced", 0)
                failed_count = result.get("failed", 0)

                logger.info(f"同期完了: 成功={synced_count}, 失敗={failed_count}")

                if failed_count > 0:
                    logger.warning(f"{failed_count}件のイベント同期に失敗しました")

        except Exception as e:
            logger.error(f"カレンダー同期ジョブでエラーが発生しました: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"トレースバック:\n{traceback.format_exc()}")

        logger.info("=" * 80)
        logger.info("カレンダー同期ジョブ終了")
        logger.info("=" * 80)

    def _sync_wrapper(self) -> None:
        """同期ジョブのラッパー

        APSchedulerは同期関数を期待するため、
        非同期関数をラップして実行する。
        """
        asyncio.run(self.sync_all_pending_events())

    def start(self) -> None:
        """スケジューラーを開始する

        既にジョブが登録されている場合は、重複登録を避ける。
        """
        # 既存のジョブを確認
        existing_job = self.scheduler.get_job(self.job_id)

        if existing_job is None:
            # ジョブを登録
            self.scheduler.add_job(
                func=self._sync_wrapper,
                trigger=IntervalTrigger(minutes=self.sync_interval_minutes),
                id=self.job_id,
                name="カレンダー同期ジョブ",
                replace_existing=True
            )
            logger.info(
                f"カレンダー同期ジョブを登録しました（間隔: {self.sync_interval_minutes}分）"
            )
        else:
            logger.info("カレンダー同期ジョブは既に登録されています")

        # スケジューラーを開始
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("スケジューラーを開始しました")
        else:
            logger.info("スケジューラーは既に実行中です")

    def shutdown(self, wait: bool = True) -> None:
        """スケジューラーをシャットダウンする

        Args:
            wait: 実行中のジョブの完了を待つかどうか
        """
        if self.scheduler.running:
            self.scheduler.shutdown(wait=wait)
            logger.info("スケジューラーをシャットダウンしました")


# シングルトンインスタンス
calendar_sync_scheduler = CalendarSyncScheduler()
