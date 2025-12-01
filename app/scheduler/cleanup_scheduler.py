"""物理削除クリーンアップスケジューラー

論理削除から30日経過したレコードを定期的に物理削除する
バックグラウンドジョブを管理する。
"""

import asyncio
import logging
from typing import Optional
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.services.cleanup_service import cleanup_service
from app.db.session import AsyncSessionLocal


logger = logging.getLogger(__name__)


class CleanupScheduler:
    """物理削除クリーンアップスケジューラー

    APSchedulerを使用して、論理削除から30日経過したレコードを
    定期的に物理削除する。
    """

    def __init__(self, cleanup_interval_hours: int = 24, days_threshold: int = 30):
        """初期化

        Args:
            cleanup_interval_hours: クリーンアップ間隔（時間）。デフォルトは24時間（1日）。
            days_threshold: 論理削除からの経過日数閾値。デフォルトは30日。
        """
        self.scheduler = BackgroundScheduler()
        self.job_id = "physical_deletion_cleanup_job"
        self.cleanup_interval_hours = cleanup_interval_hours
        self.days_threshold = days_threshold

    async def cleanup_deleted_records(self) -> None:
        """論理削除されたレコードを物理削除する

        このメソッドはスケジューラーから定期的に呼び出される。
        """
        logger.info("=" * 80)
        logger.info("物理削除クリーンアップジョブ開始")
        logger.info(f"閾値: {self.days_threshold}日前までに論理削除されたレコード")
        logger.info("=" * 80)

        try:
            # 非同期セッションを作成
            async with AsyncSessionLocal() as db:
                # 論理削除されたレコードを物理削除
                result = await cleanup_service.cleanup_soft_deleted_records(
                    db=db,
                    days_threshold=self.days_threshold
                )

                deleted_staff = result.get("deleted_staff_count", 0)
                deleted_offices = result.get("deleted_office_count", 0)
                errors = result.get("errors", [])

                logger.info(
                    f"物理削除完了: スタッフ={deleted_staff}件, "
                    f"事務所={deleted_offices}件"
                )

                if errors:
                    logger.error(f"{len(errors)}件のエラーが発生しました:")
                    for error in errors:
                        logger.error(f"  - {error}")
                elif deleted_staff == 0 and deleted_offices == 0:
                    logger.info("物理削除対象のレコードはありませんでした")

        except Exception as e:
            logger.error(
                f"物理削除クリーンアップジョブでエラーが発生しました: "
                f"{type(e).__name__}: {e}"
            )
            import traceback
            logger.error(f"トレースバック:\n{traceback.format_exc()}")

        logger.info("=" * 80)
        logger.info("物理削除クリーンアップジョブ終了")
        logger.info("=" * 80)

    def _cleanup_wrapper(self) -> None:
        """クリーンアップジョブのラッパー

        APSchedulerは同期関数を期待するため、
        非同期関数をラップして実行する。
        """
        asyncio.run(self.cleanup_deleted_records())

    def start(self) -> None:
        """スケジューラーを開始する

        既にジョブが登録されている場合は、重複登録を避ける。
        """
        # 既存のジョブを確認
        existing_job = self.scheduler.get_job(self.job_id)

        if existing_job is None:
            # ジョブを登録
            self.scheduler.add_job(
                func=self._cleanup_wrapper,
                trigger=IntervalTrigger(hours=self.cleanup_interval_hours),
                id=self.job_id,
                name="物理削除クリーンアップジョブ",
                replace_existing=True
            )
            logger.info(
                f"物理削除クリーンアップジョブを登録しました "
                f"（間隔: {self.cleanup_interval_hours}時間, 閾値: {self.days_threshold}日）"
            )
        else:
            logger.info("物理削除クリーンアップジョブは既に登録されています")

        # スケジューラーを開始
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("物理削除クリーンアップスケジューラーを開始しました")
        else:
            logger.info("物理削除クリーンアップスケジューラーは既に実行中です")

    def shutdown(self, wait: bool = True) -> None:
        """スケジューラーをシャットダウンする

        Args:
            wait: 実行中のジョブの完了を待つかどうか
        """
        if self.scheduler.running:
            self.scheduler.shutdown(wait=wait)
            logger.info("物理削除クリーンアップスケジューラーをシャットダウンしました")


# シングルトンインスタンス
# デフォルト: 1日ごとに実行、30日前に論理削除されたレコードを物理削除
cleanup_scheduler = CleanupScheduler(cleanup_interval_hours=24, days_threshold=30)
