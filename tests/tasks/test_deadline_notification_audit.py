"""
期限アラートメール通知の監査ログテスト

テスト対象:
- メール送信時の監査ログ作成
- 監査ログに必要な情報が含まれること
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock, call
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone

from app.tasks.deadline_notification import send_deadline_alert_emails
from app.models.office import Office
from app.models.staff import Staff
from app.models.push_subscription import PushSubscription
from app.schemas.deadline_alert import DeadlineAlertResponse, DeadlineAlertItem


@pytest.mark.asyncio
async def test_audit_log_on_email_sent(db_session: AsyncSession):
    """
    メール送信時に監査ログが作成されることを確認

    検証内容:
    - 各メール送信後にaudit_logが作成される
    - crud.audit_log.create_logが呼び出される
    """
    with patch('app.tasks.deadline_notification.select') as mock_select, \
         patch('app.tasks.deadline_notification.WelfareRecipientService.get_deadline_alerts') as mock_get_alerts, \
         patch('app.tasks.deadline_notification.send_deadline_alert_email') as mock_send_email, \
         patch('app.tasks.deadline_notification.crud.audit_log.create_log') as mock_create_log:

        office = Office(id="office-1", name="テスト事業所", deleted_at=None)

        staffs = [
            Staff(
                id="staff-1",
                email="staff1@example.com",
                last_name="山田",
                first_name="太郎",
                deleted_at=None
            ),
            Staff(
                id="staff-2",
                email="staff2@example.com",
                last_name="佐藤",
                first_name="花子",
                deleted_at=None
            )
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
                ),
                DeadlineAlertItem(
                    id="recipient-2",
                    full_name="利用者2",
                    alert_type="assessment_incomplete",
                    message="アセスメントが未完了です",
                    current_cycle_number=2
                )
            ],
            total=2
        )

        mock_send_email.return_value = None
        mock_create_log.return_value = None

        count = await send_deadline_alert_emails(db=db_session, dry_run=False)

        assert count == 2, f"Expected 2 emails sent, got {count}"
        assert mock_create_log.call_count == 2, f"Expected 2 audit logs, got {mock_create_log.call_count}"


@pytest.mark.asyncio
async def test_audit_log_contains_required_fields(db_session: AsyncSession):
    """
    監査ログに必要な情報が含まれることを確認

    検証内容:
    - action: "deadline_notification_sent"
    - office_id: 事業所ID
    - staff_id: スタッフID
    - details: メール送信詳細（受信者メール、アラート件数など）
    """
    with patch('app.tasks.deadline_notification.select') as mock_select, \
         patch('app.tasks.deadline_notification.WelfareRecipientService.get_deadline_alerts') as mock_get_alerts, \
         patch('app.tasks.deadline_notification.send_deadline_alert_email') as mock_send_email, \
         patch('app.tasks.deadline_notification.crud.audit_log.create_log') as mock_create_log:

        office = Office(id="office-123", name="テスト事業所", deleted_at=None)
        staff = Staff(
            id="staff-456",
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
                ),
                DeadlineAlertItem(
                    id="recipient-2",
                    full_name="利用者2",
                    alert_type="assessment_incomplete",
                    message="アセスメントが未完了です",
                    current_cycle_number=2
                )
            ],
            total=2
        )

        mock_send_email.return_value = None
        mock_create_log.return_value = None

        await send_deadline_alert_emails(db=db_session, dry_run=False)

        assert mock_create_log.call_count > 0, "create_log was not called"

        call_args = mock_create_log.call_args
        assert call_args is not None, "create_log was not called"

        kwargs = call_args.kwargs
        assert kwargs["db"] == db_session
        assert kwargs["action"] == "deadline_notification_sent"
        assert "office_id" in kwargs
        assert kwargs["office_id"] is not None
        assert "staff_id" in kwargs
        assert kwargs["staff_id"] is not None

        details = kwargs["details"]
        assert "recipient_email" in details
        assert isinstance(details["recipient_email"], str)
        assert "@" in details["recipient_email"]
        assert "office_name" in details
        assert isinstance(details["office_name"], str)
        assert "renewal_alert_count" in details
        assert isinstance(details["renewal_alert_count"], int)
        assert details["renewal_alert_count"] >= 0
        assert "assessment_alert_count" in details
        assert isinstance(details["assessment_alert_count"], int)
        assert details["assessment_alert_count"] >= 0
        assert "staff_name" in details
        assert isinstance(details["staff_name"], str)


@pytest.mark.asyncio
async def test_audit_log_on_dry_run_skip(db_session: AsyncSession):
    """
    dry_runモード時は監査ログを作成しないことを確認

    検証内容:
    - dry_run=Trueの場合、audit_logが作成されない
    """
    with patch('app.tasks.deadline_notification.select') as mock_select, \
         patch('app.tasks.deadline_notification.WelfareRecipientService.get_deadline_alerts') as mock_get_alerts, \
         patch('app.tasks.deadline_notification.crud.audit_log.create_log') as mock_create_log:

        office = Office(id="office-1", name="テスト事業所", deleted_at=None)
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

        mock_create_log.return_value = None

        count = await send_deadline_alert_emails(db=db_session, dry_run=True)

        assert count == 1, f"Expected 1 email would be sent, got {count}"
        mock_create_log.assert_not_called()
