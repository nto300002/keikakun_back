import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from uuid import uuid4

from app.scheduler.calendar_sync_scheduler import CalendarSyncScheduler


pytestmark = pytest.mark.asyncio


class TestCalendarSyncScheduler:
    """カレンダー同期スケジューラーのテスト"""

    def test_scheduler_initialization(self):
        """正常系: スケジューラーが正しく初期化されること"""
        scheduler = CalendarSyncScheduler()

        assert scheduler.scheduler is not None
        assert scheduler.job_id == "calendar_sync_job"
        assert scheduler.sync_interval_minutes == 5  # デフォルト5分

    def test_scheduler_initialization_with_custom_interval(self):
        """正常系: カスタムインターバルで初期化できること"""
        scheduler = CalendarSyncScheduler(sync_interval_minutes=10)

        assert scheduler.sync_interval_minutes == 10

    async def test_sync_all_pending_events_success(self):
        """正常系: 全事業所の未同期イベントを同期できること"""
        scheduler = CalendarSyncScheduler()

        # calendar_service.sync_pending_events をモック
        with patch('app.scheduler.calendar_sync_scheduler.calendar_service') as mock_service:
            mock_service.sync_pending_events = AsyncMock(return_value={"synced": 3, "failed": 0})

            # 実行
            await scheduler.sync_all_pending_events()

            # アサーション
            mock_service.sync_pending_events.assert_called_once()
            call_args = mock_service.sync_pending_events.call_args
            assert call_args.kwargs['office_id'] is None  # 全事業所を対象

    async def test_sync_all_pending_events_with_errors(self):
        """正常系: 同期中にエラーが発生してもログが記録されること"""
        scheduler = CalendarSyncScheduler()

        # calendar_service.sync_pending_events をモック（失敗を返す）
        with patch('app.scheduler.calendar_sync_scheduler.calendar_service') as mock_service:
            mock_service.sync_pending_events = AsyncMock(return_value={"synced": 1, "failed": 2})

            # 実行（エラーは発生せず、ログに記録される）
            await scheduler.sync_all_pending_events()

            # アサーション
            mock_service.sync_pending_events.assert_called_once()

    async def test_sync_all_pending_events_exception_handling(self):
        """異常系: sync_pending_events で例外が発生してもクラッシュしないこと"""
        scheduler = CalendarSyncScheduler()

        # calendar_service.sync_pending_events をモック（例外を発生させる）
        with patch('app.scheduler.calendar_sync_scheduler.calendar_service') as mock_service:
            mock_service.sync_pending_events = AsyncMock(side_effect=Exception("Database error"))

            # 実行（例外が発生してもクラッシュしない）
            await scheduler.sync_all_pending_events()

            # アサーション: 例外は内部で処理される
            mock_service.sync_pending_events.assert_called_once()

    def test_start_scheduler(self):
        """正常系: スケジューラーが開始されること"""
        scheduler = CalendarSyncScheduler()

        # スケジューラーを開始
        scheduler.start()

        # アサーション
        assert scheduler.scheduler.running is True

        # ジョブが登録されていることを確認
        jobs = scheduler.scheduler.get_jobs()
        assert len(jobs) == 1
        assert jobs[0].id == "calendar_sync_job"

        # クリーンアップ
        scheduler.shutdown()

    def test_shutdown_scheduler(self):
        """正常系: スケジューラーがシャットダウンできること"""
        scheduler = CalendarSyncScheduler()

        # 開始してからシャットダウン
        scheduler.start()
        assert scheduler.scheduler.running is True

        scheduler.shutdown()
        assert scheduler.scheduler.running is False

    def test_scheduler_job_configuration(self):
        """正常系: ジョブが正しい設定で登録されていること"""
        scheduler = CalendarSyncScheduler(sync_interval_minutes=3)

        scheduler.start()

        # ジョブの設定を確認
        jobs = scheduler.scheduler.get_jobs()
        job = jobs[0]

        assert job.id == "calendar_sync_job"
        assert job.trigger.interval.total_seconds() == 3 * 60  # 3分

        # クリーンアップ
        scheduler.shutdown()

    def test_multiple_start_calls_safe(self):
        """正常系: 複数回startを呼んでも安全であること"""
        scheduler = CalendarSyncScheduler()

        # 複数回開始を呼び出す
        scheduler.start()
        scheduler.start()

        # ジョブは1つだけ登録されている
        jobs = scheduler.scheduler.get_jobs()
        assert len(jobs) == 1

        # クリーンアップ
        scheduler.shutdown()

    @patch('app.scheduler.calendar_sync_scheduler.logger')
    async def test_sync_logging(self, mock_logger):
        """正常系: 同期処理のログが正しく出力されること"""
        scheduler = CalendarSyncScheduler()

        with patch('app.scheduler.calendar_sync_scheduler.calendar_service') as mock_service:
            mock_service.sync_pending_events = AsyncMock(return_value={"synced": 5, "failed": 1})

            await scheduler.sync_all_pending_events()

            # ログが呼ばれたことを確認
            assert mock_logger.info.call_count >= 2  # 開始と終了のログ
