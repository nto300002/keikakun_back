"""安全なクリーンアップschedulerログの回帰テスト。"""

from unittest.mock import AsyncMock

import pytest

from app.scheduler import cleanup_scheduler as cleanup_scheduler_module


class _SessionContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, traceback):
        return False


@pytest.mark.asyncio
async def test_cleanup_scheduler_logs_error_count_without_error_contents(monkeypatch, caplog):
    """外部由来のエラー内容をcontainer logへ転記しない。"""
    raw_error = "untrusted-error\\r\\nprivate-detail"
    monkeypatch.setattr(cleanup_scheduler_module, "AsyncSessionLocal", lambda: _SessionContext())
    monkeypatch.setattr(
        cleanup_scheduler_module.cleanup_service,
        "cleanup_soft_deleted_records",
        AsyncMock(
            return_value={
                "deleted_staff_count": 0,
                "deleted_office_count": 0,
                "errors": [raw_error],
            }
        ),
    )

    scheduler = cleanup_scheduler_module.CleanupScheduler()
    await scheduler.cleanup_deleted_records()

    assert raw_error not in caplog.text
    assert "失敗が発生 count=1" in caplog.text
