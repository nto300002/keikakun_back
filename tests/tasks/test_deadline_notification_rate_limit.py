"""
期限アラートメール通知のDoS対策テスト (レート制限 + タイムアウト)

テスト対象:
- 並列送信数の制限 (Semaphore)
- 送信タイムアウト (30秒)
- 送信間隔の遅延 (100ms)
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession

from app.tasks.deadline_notification import send_deadline_alert_emails
from app.models.office import Office
from app.models.staff import Staff
from app.schemas.deadline_alert import DeadlineAlertResponse, DeadlineAlertItem


@pytest.mark.asyncio
async def test_rate_limit_enforced(db_session: AsyncSession):
    """
    レート制限が正しく適用されることを確認

    検証内容:
    - 最大5件の並列送信が制限される
    - Semaphoreによる並列数制御
    """
    with patch('app.tasks.deadline_notification.select') as mock_select, \
         patch('app.tasks.deadline_notification.WelfareRecipientService.get_deadline_alerts') as mock_get_alerts, \
         patch('app.tasks.deadline_notification.send_deadline_alert_email') as mock_send_email, \
         patch('app.tasks.deadline_notification.crud.audit_log.create_log') as mock_audit_log:

        offices = [
            Office(id=f"office-{i}", name=f"Office {i}", deleted_at=None)
            for i in range(10)
        ]

        staffs = [
            Staff(
                id=f"staff-{i}",
                email=f"staff{i}@example.com",
                last_name="山田",
                first_name=f"太郎{i}",
                deleted_at=None
            )
            for i in range(10)
        ]

        mock_office_result = MagicMock()
        mock_office_result.scalars().all.return_value = offices

        mock_staff_result = MagicMock()
        mock_staff_result.scalars().all.return_value = [staffs[0]]

        async def execute_side_effect(stmt):
            if "Office" in str(stmt):
                return mock_office_result
            else:
                return mock_staff_result

        db_session.execute = AsyncMock(side_effect=execute_side_effect)

        mock_get_alerts.return_value = DeadlineAlertResponse(
            alerts=[
                DeadlineAlertItem(
                    id="recipient-1",
                    full_name="利用者1",
                    alert_type="renewal_deadline",
                    message="更新期限が近づいています",
                    days_remaining=15,
                    current_cycle_number=1
                )
            ],
            total=1
        )

        concurrent_sends = []
        max_concurrent = 0
        current_concurrent = 0
        lock = asyncio.Lock()

        async def track_concurrent_send(*args, **kwargs):
            nonlocal current_concurrent, max_concurrent
            async with lock:
                current_concurrent += 1
                max_concurrent = max(max_concurrent, current_concurrent)

            await asyncio.sleep(0.01)

            async with lock:
                current_concurrent -= 1

        mock_send_email.side_effect = track_concurrent_send

        await send_deadline_alert_emails(db=db_session, dry_run=False)

        assert max_concurrent <= 5, f"Expected max 5 concurrent sends, got {max_concurrent}"


@pytest.mark.asyncio
async def test_timeout_on_slow_email(db_session: AsyncSession):
    """
    タイムアウトが正しく適用されることを確認

    検証内容:
    - 30秒以上かかるメール送信はタイムアウト
    - タイムアウトしてもエラーログを出して続行
    """
    with patch('app.tasks.deadline_notification.select') as mock_select, \
         patch('app.tasks.deadline_notification.WelfareRecipientService.get_deadline_alerts') as mock_get_alerts, \
         patch('app.tasks.deadline_notification.send_deadline_alert_email') as mock_send_email, \
         patch('app.tasks.deadline_notification.crud.audit_log.create_log') as mock_audit_log:

        office = Office(id="office-1", name="Office 1", deleted_at=None)
        staff = Staff(
            id="staff-1",
            email="staff1@example.com",
            last_name="山田",
            first_name="太郎",
            deleted_at=None
        )

        mock_office_result = MagicMock()
        mock_office_result.scalars().all.return_value = [office]

        mock_staff_result = MagicMock()
        mock_staff_result.scalars().all.return_value = [staff]

        async def execute_side_effect(stmt):
            if "Office" in str(stmt):
                return mock_office_result
            else:
                return mock_staff_result

        db_session.execute = AsyncMock(side_effect=execute_side_effect)

        mock_get_alerts.return_value = DeadlineAlertResponse(
            alerts=[
                DeadlineAlertItem(
                    id="recipient-1",
                    full_name="利用者1",
                    alert_type="renewal_deadline",
                    message="更新期限が近づいています",
                    days_remaining=15,
                    current_cycle_number=1
                )
            ],
            total=1
        )

        async def slow_send(*args, **kwargs):
            await asyncio.sleep(35)

        mock_send_email.side_effect = slow_send

        import time
        start = time.time()
        count = await send_deadline_alert_emails(db=db_session, dry_run=False)
        elapsed = time.time() - start

        assert elapsed < 32, f"Expected timeout around 30s, took {elapsed}s"
        assert count == 0, "Expected 0 emails sent due to timeout"


@pytest.mark.asyncio
async def test_delay_between_emails(db_session: AsyncSession):
    """
    メール送信間隔の遅延が正しく適用されることを確認

    検証内容:
    - 各メール送信の間に100ms以上の遅延がある
    """
    with patch('app.tasks.deadline_notification.select') as mock_select, \
         patch('app.tasks.deadline_notification.WelfareRecipientService.get_deadline_alerts') as mock_get_alerts, \
         patch('app.tasks.deadline_notification.send_deadline_alert_email') as mock_send_email, \
         patch('app.tasks.deadline_notification.crud.audit_log.create_log') as mock_audit_log:

        office = Office(id="office-1", name="Office 1", deleted_at=None)

        staffs = [
            Staff(
                id=f"staff-{i}",
                email=f"staff{i}@example.com",
                last_name="山田",
                first_name=f"太郎{i}",
                deleted_at=None
            )
            for i in range(3)
        ]

        mock_office_result = MagicMock()
        mock_office_result.scalars().all.return_value = [office]

        mock_staff_result = MagicMock()
        mock_staff_result.scalars().all.return_value = staffs

        async def execute_side_effect(stmt):
            if "Office" in str(stmt):
                return mock_office_result
            else:
                return mock_staff_result

        db_session.execute = AsyncMock(side_effect=execute_side_effect)

        mock_get_alerts.return_value = DeadlineAlertResponse(
            alerts=[
                DeadlineAlertItem(
                    id="recipient-1",
                    full_name="利用者1",
                    alert_type="renewal_deadline",
                    message="更新期限が近づいています",
                    days_remaining=15,
                    current_cycle_number=1
                )
            ],
            total=1
        )

        send_times = []

        async def track_send_time(*args, **kwargs):
            import time
            send_times.append(time.time())

        mock_send_email.side_effect = track_send_time

        await send_deadline_alert_emails(db=db_session, dry_run=False)

        for i in range(1, len(send_times)):
            delay = (send_times[i] - send_times[i-1]) * 1000
            assert delay >= 95, f"Expected at least 100ms delay, got {delay}ms between email {i-1} and {i}"
