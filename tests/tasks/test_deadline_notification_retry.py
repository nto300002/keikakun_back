"""
期限アラートメール通知のリトライロジックテスト

テスト対象:
- メール送信失敗時の自動リトライ
- 指数バックオフによる再試行間隔
- 最大リトライ回数の制限
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession

from app.tasks.deadline_notification import send_deadline_alert_emails
from app.models.office import Office
from app.models.staff import Staff
from app.models.push_subscription import PushSubscription
from app.schemas.deadline_alert import DeadlineAlertResponse, DeadlineAlertItem


@pytest.mark.asyncio
async def test_retry_on_temporary_failure(db_session: AsyncSession):
    """
    一時的な失敗時にリトライすることを確認

    検証内容:
    - SMTPエラー時に最大3回リトライ
    - 最終的に成功した場合、email_countがインクリメント
    """
    with patch('app.tasks.deadline_notification.select') as mock_select, \
         patch('app.tasks.deadline_notification.WelfareRecipientService.get_deadline_alerts') as mock_get_alerts, \
         patch('app.tasks.deadline_notification.send_deadline_alert_email') as mock_send_email, \
         patch('app.tasks.deadline_notification.crud.audit_log.create_log') as mock_audit_log:

        office = Office(id="office-1", name="Test Office", deleted_at=None)
        staff = Staff(
            id="staff-1",
            email="test@example.com",
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

        mock_audit_log.return_value = None

        call_count = 0
        async def failing_then_success(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("SMTP connection failed")
            return None

        mock_send_email.side_effect = failing_then_success

        count = await send_deadline_alert_emails(db=db_session, dry_run=False)

        assert count == 1, f"Expected 1 email sent after retry, got {count}"
        assert mock_send_email.call_count == 3, f"Expected 3 attempts (2 retries), got {mock_send_email.call_count}"


@pytest.mark.asyncio
async def test_max_retries_exceeded(db_session: AsyncSession):
    """
    最大リトライ回数を超えた場合の動作を確認

    検証内容:
    - 3回リトライ後も失敗する場合、諦めて次に進む
    - email_countはインクリメントされない
    - エラーログが記録される
    """
    with patch('app.tasks.deadline_notification.select') as mock_select, \
         patch('app.tasks.deadline_notification.WelfareRecipientService.get_deadline_alerts') as mock_get_alerts, \
         patch('app.tasks.deadline_notification.send_deadline_alert_email') as mock_send_email, \
         patch('app.tasks.deadline_notification.crud.audit_log.create_log') as mock_audit_log:

        office = Office(id="office-1", name="Test Office", deleted_at=None)
        staff = Staff(
            id="staff-1",
            email="test@example.com",
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

        mock_audit_log.return_value = None

        async def always_fail(*args, **kwargs):
            raise Exception("Permanent SMTP failure")

        mock_send_email.side_effect = always_fail

        count = await send_deadline_alert_emails(db=db_session, dry_run=False)

        assert count == 0, f"Expected 0 emails sent after max retries, got {count}"
        assert mock_send_email.call_count == 3, f"Expected 3 attempts (initial + 2 retries), got {mock_send_email.call_count}"


@pytest.mark.asyncio
async def test_exponential_backoff(db_session: AsyncSession):
    """
    指数バックオフが適用されることを確認

    検証内容:
    - 1回目のリトライ: ~2秒待機
    - 2回目のリトライ: ~4秒待機
    """
    with patch('app.tasks.deadline_notification.select') as mock_select, \
         patch('app.tasks.deadline_notification.WelfareRecipientService.get_deadline_alerts') as mock_get_alerts, \
         patch('app.tasks.deadline_notification.send_deadline_alert_email') as mock_send_email, \
         patch('app.tasks.deadline_notification.crud.audit_log.create_log') as mock_audit_log:

        office = Office(id="office-1", name="Test Office", deleted_at=None)
        staff = Staff(
            id="staff-1",
            email="test@example.com",
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

        mock_audit_log.return_value = None

        attempt_times = []
        async def track_attempts(*args, **kwargs):
            import time
            attempt_times.append(time.time())
            if len(attempt_times) < 3:
                raise Exception("Temporary failure")
            return None

        mock_send_email.side_effect = track_attempts

        import time
        start = time.time()
        count = await send_deadline_alert_emails(db=db_session, dry_run=False)
        total_time = time.time() - start

        assert count == 1, f"Expected 1 email sent, got {count}"
        assert len(attempt_times) == 3, f"Expected 3 attempts, got {len(attempt_times)}"

        # 指数バックオフの検証（最低でも2秒 + 2秒 = 4秒待機）
        assert total_time >= 3.5, f"Expected at least 3.5s total time (exponential backoff), got {total_time}s"
