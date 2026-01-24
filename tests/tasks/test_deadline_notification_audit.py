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


@pytest.fixture(autouse=True)
def mock_weekday_check():
    """
    すべてのテストで週末・祝日チェックをスキップ
    テストは曜日に関係なく実行できるようにする
    """
    with patch('app.tasks.deadline_notification.is_japanese_weekday_and_not_holiday', return_value=True):
        yield


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
                deleted_at=None,
                notification_preferences={
                    "in_app_notification": True,
                    "email_notification": True,
                    "system_notification": False,
                    "email_threshold_days": 30,
                    "push_threshold_days": 10
                }
            ),
            Staff(
                id="staff-2",
                email="staff2@example.com",
                last_name="佐藤",
                first_name="花子",
                deleted_at=None,
                notification_preferences={
                    "in_app_notification": True,
                    "email_notification": True,
                    "system_notification": False,
                    "email_threshold_days": 30,
                    "push_threshold_days": 10
                }
            )
        ]

        mock_office_result = MagicMock()
        mock_office_result.scalars().all.return_value = [office]

        mock_staff_result = MagicMock()
        mock_staff_result.scalars().all.return_value = staffs

        execute_call_count = [0]

        async def execute_side_effect(stmt):
            execute_call_count[0] += 1
            # First call returns offices, all other calls return staffs
            if execute_call_count[0] == 1:
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

        result = await send_deadline_alert_emails(db=db_session, dry_run=False)

        assert result["email_sent"] == 2, f"Expected 2 emails sent, got {result['email_sent']}"
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
            deleted_at=None,
            notification_preferences={
                "in_app_notification": True,
                "email_notification": True,
                "system_notification": False,
                "email_threshold_days": 30,
                "push_threshold_days": 10
            }
        )

        mock_office_result = MagicMock()
        mock_office_result.scalars().all.return_value = [office]

        mock_staff_result = MagicMock()
        mock_staff_result.scalars().all.return_value = [staff]

        execute_call_count = [0]

        async def execute_side_effect(stmt):
            execute_call_count[0] += 1
            # First call returns offices, all other calls return staffs
            if execute_call_count[0] == 1:
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
        assert "target_id" in kwargs
        assert kwargs["target_id"] is not None

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
            deleted_at=None,
            notification_preferences={
                "in_app_notification": True,
                "email_notification": True,
                "system_notification": False,
                "email_threshold_days": 30,
                "push_threshold_days": 10
            }
        )

        mock_office_result = MagicMock()
        mock_office_result.scalars().all.return_value = [office]

        mock_staff_result = MagicMock()
        mock_staff_result.scalars().all.return_value = [staff]

        execute_call_count = [0]

        async def execute_side_effect(stmt):
            execute_call_count[0] += 1
            # First call returns offices, all other calls return staffs
            if execute_call_count[0] == 1:
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

        result = await send_deadline_alert_emails(db=db_session, dry_run=True)

        assert result["email_sent"] == 1, f"Expected 1 email would be sent, got {result['email_sent']}"
        mock_create_log.assert_not_called()


@pytest.mark.asyncio
async def test_audit_log_on_push_sent(db_session: AsyncSession):
    """
    Push送信時に監査ログが作成されることを確認（セキュリティ実装）

    検証内容:
    - 各スタッフのPush送信後にaudit_logが作成される
    - crud.audit_log.create_logが呼び出される
    - メール監査ログとは別にPush監査ログが記録される
    """
    with patch('app.tasks.deadline_notification.select') as mock_select, \
         patch('app.tasks.deadline_notification.WelfareRecipientService.get_deadline_alerts') as mock_get_alerts, \
         patch('app.tasks.deadline_notification.send_deadline_alert_email') as mock_send_email, \
         patch('app.tasks.deadline_notification.send_push_notification') as mock_send_push, \
         patch('app.tasks.deadline_notification.crud.audit_log.create_log') as mock_create_log:

        office = Office(id="office-1", name="テスト事業所", deleted_at=None)

        staff = Staff(
            id="staff-1",
            email="staff1@example.com",
            last_name="山田",
            first_name="太郎",
            deleted_at=None,
            notification_preferences={
                "in_app_notification": True,
                "email_notification": True,
                "system_notification": True,  # Push有効
                "email_threshold_days": 30,
                "push_threshold_days": 10
            }
        )

        # Push購読をモック
        push_sub = PushSubscription(
            staff_id=staff.id,
            endpoint="https://fcm.googleapis.com/fcm/send/test",
            p256dh_key="test_p256dh",
            auth_key="test_auth"
        )

        mock_office_result = MagicMock()
        mock_office_result.scalars().all.return_value = [office]

        mock_staff_result = MagicMock()
        mock_staff_result.scalars().all.return_value = [staff]

        mock_subscription_result = MagicMock()
        mock_subscription_result.scalars().all.return_value = [push_sub]

        execute_call_count = [0]

        async def execute_side_effect(stmt):
            execute_call_count[0] += 1
            if execute_call_count[0] == 1:
                return mock_office_result  # Offices
            elif execute_call_count[0] == 2:
                return mock_staff_result   # Staffs
            else:
                return mock_subscription_result  # Push subscriptions

        db_session.execute = AsyncMock(side_effect=execute_side_effect)

        mock_get_alerts.return_value = DeadlineAlertResponse(
            alerts=[
                DeadlineAlertItem(
                    id="recipient-1",
                    full_name="利用者1",
                    alert_type="renewal_deadline",
                    message="更新期限が近づいています",
                    days_remaining=5,  # Push閾値内
                    current_cycle_number=1
                )
            ],
            total=1
        )

        mock_send_email.return_value = None
        mock_send_push.return_value = (True, False)  # 成功
        mock_create_log.return_value = None

        result = await send_deadline_alert_emails(db=db_session, dry_run=False)

        assert result["email_sent"] == 1, f"Expected 1 email sent, got {result['email_sent']}"
        assert result["push_sent"] == 1, f"Expected 1 push sent, got {result['push_sent']}"

        # 監査ログが2回呼ばれる: 1回はメール、1回はPush
        assert mock_create_log.call_count == 2, f"Expected 2 audit logs (1 email + 1 push), got {mock_create_log.call_count}"

        # Push監査ログの検証（2回目の呼び出し）
        push_log_call = mock_create_log.call_args_list[1]
        kwargs = push_log_call.kwargs

        assert kwargs["action"] == "push_notification_sent", "Push監査ログのactionが正しい"
        assert kwargs["db"] == db_session
        assert "office_id" in kwargs
        assert "target_id" in kwargs

        details = kwargs["details"]
        assert "push_sent_count" in details, "Push送信件数が記録される"
        assert details["push_sent_count"] == 1
        assert "device_count" in details, "デバイス数が記録される"
        assert details["device_count"] == 1


@pytest.mark.asyncio
async def test_audit_log_push_contains_required_fields(db_session: AsyncSession):
    """
    Push送信の監査ログに必要な情報が含まれることを確認

    検証内容:
    - action: "push_notification_sent"
    - office_id: 事業所ID
    - staff_id: スタッフID
    - details: Push送信詳細（送信件数、デバイス数、失敗件数など）
    """
    with patch('app.tasks.deadline_notification.select') as mock_select, \
         patch('app.tasks.deadline_notification.WelfareRecipientService.get_deadline_alerts') as mock_get_alerts, \
         patch('app.tasks.deadline_notification.send_deadline_alert_email') as mock_send_email, \
         patch('app.tasks.deadline_notification.send_push_notification') as mock_send_push, \
         patch('app.tasks.deadline_notification.crud.audit_log.create_log') as mock_create_log:

        office = Office(id="office-123", name="テスト事業所", deleted_at=None)
        staff = Staff(
            id="staff-456",
            email="test@example.com",
            last_name="山田",
            first_name="太郎",
            deleted_at=None,
            notification_preferences={
                "in_app_notification": True,
                "email_notification": True,
                "system_notification": True,
                "email_threshold_days": 30,
                "push_threshold_days": 10
            }
        )

        # 複数デバイスのPush購読
        push_subs = [
            PushSubscription(
                staff_id=staff.id,
                endpoint=f"https://fcm.googleapis.com/fcm/send/device-{i}",
                p256dh_key="test_p256dh",
                auth_key="test_auth"
            )
            for i in range(3)
        ]

        mock_office_result = MagicMock()
        mock_office_result.scalars().all.return_value = [office]

        mock_staff_result = MagicMock()
        mock_staff_result.scalars().all.return_value = [staff]

        mock_subscription_result = MagicMock()
        mock_subscription_result.scalars().all.return_value = push_subs

        execute_call_count = [0]

        async def execute_side_effect(stmt):
            execute_call_count[0] += 1
            if execute_call_count[0] == 1:
                return mock_office_result
            elif execute_call_count[0] == 2:
                return mock_staff_result
            else:
                return mock_subscription_result

        db_session.execute = AsyncMock(side_effect=execute_side_effect)

        mock_get_alerts.return_value = DeadlineAlertResponse(
            alerts=[
                DeadlineAlertItem(
                    id="recipient-1",
                    full_name="利用者1",
                    alert_type="renewal_deadline",
                    message="更新期限が近づいています",
                    days_remaining=5,
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
        # 3デバイス: 2成功、1失敗
        mock_send_push.side_effect = [
            (True, False),   # Device 1: 成功
            (True, False),   # Device 2: 成功
            (False, False)   # Device 3: 失敗
        ]
        mock_create_log.return_value = None

        await send_deadline_alert_emails(db=db_session, dry_run=False)

        # Push監査ログの検証（2回目の呼び出し）
        push_log_call = mock_create_log.call_args_list[1]
        kwargs = push_log_call.kwargs

        assert kwargs["db"] == db_session
        assert kwargs["action"] == "push_notification_sent"
        assert kwargs["office_id"] == "office-123"
        assert kwargs["target_id"] == "staff-456"

        details = kwargs["details"]
        assert "office_name" in details
        assert details["office_name"] == "テスト事業所"
        assert "staff_name" in details
        assert details["staff_name"] == "山田 太郎"
        assert "push_sent_count" in details
        assert details["push_sent_count"] == 2, "2デバイス成功"
        assert "push_failed_count" in details
        assert details["push_failed_count"] == 1, "1デバイス失敗"
        assert "device_count" in details
        assert details["device_count"] == 3, "合計3デバイス"
        assert "renewal_alert_count" in details
        assert details["renewal_alert_count"] == 1
        assert "assessment_alert_count" in details
        assert details["assessment_alert_count"] == 1


@pytest.mark.asyncio
async def test_audit_log_push_on_dry_run_skip(db_session: AsyncSession):
    """
    dry_runモード時はPush監査ログを作成しないことを確認

    検証内容:
    - dry_run=Trueの場合、Push audit_logが作成されない
    - メール監査ログのみスキップされる（既存の挙動）
    """
    with patch('app.tasks.deadline_notification.select') as mock_select, \
         patch('app.tasks.deadline_notification.WelfareRecipientService.get_deadline_alerts') as mock_get_alerts, \
         patch('app.tasks.deadline_notification.send_push_notification') as mock_send_push, \
         patch('app.tasks.deadline_notification.crud.audit_log.create_log') as mock_create_log:

        office = Office(id="office-1", name="テスト事業所", deleted_at=None)
        staff = Staff(
            id="staff-1",
            email="staff1@example.com",
            last_name="山田",
            first_name="太郎",
            deleted_at=None,
            notification_preferences={
                "in_app_notification": True,
                "email_notification": True,
                "system_notification": True,
                "email_threshold_days": 30,
                "push_threshold_days": 10
            }
        )

        push_sub = PushSubscription(
            staff_id=staff.id,
            endpoint="https://fcm.googleapis.com/fcm/send/test",
            p256dh_key="test_p256dh",
            auth_key="test_auth"
        )

        mock_office_result = MagicMock()
        mock_office_result.scalars().all.return_value = [office]

        mock_staff_result = MagicMock()
        mock_staff_result.scalars().all.return_value = [staff]

        mock_subscription_result = MagicMock()
        mock_subscription_result.scalars().all.return_value = [push_sub]

        execute_call_count = [0]

        async def execute_side_effect(stmt):
            execute_call_count[0] += 1
            if execute_call_count[0] == 1:
                return mock_office_result
            elif execute_call_count[0] == 2:
                return mock_staff_result
            else:
                return mock_subscription_result

        db_session.execute = AsyncMock(side_effect=execute_side_effect)

        mock_get_alerts.return_value = DeadlineAlertResponse(
            alerts=[
                DeadlineAlertItem(
                    id="recipient-1",
                    full_name="利用者1",
                    alert_type="renewal_deadline",
                    message="更新期限が近づいています",
                    days_remaining=5,
                    current_cycle_number=1
                )
            ],
            total=1
        )

        mock_send_push.return_value = (True, False)
        mock_create_log.return_value = None

        result = await send_deadline_alert_emails(db=db_session, dry_run=True)

        assert result["email_sent"] == 1, "dry_runでもカウントは増える"
        assert result["push_sent"] == 1, "dry_runでもカウントは増える"

        # dry_run時は監査ログを一切作成しない
        mock_create_log.assert_not_called()
