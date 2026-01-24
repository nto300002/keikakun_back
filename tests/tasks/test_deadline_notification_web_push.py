"""
期限アラート通知バッチ処理のWeb Pushテスト
"""
import pytest
import pytest_asyncio
from datetime import date, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import AsyncMock, patch, MagicMock

from app.tasks.deadline_notification import send_deadline_alert_emails
from app.models.office import Office, OfficeStaff
from app.models.staff import Staff
from app.models.welfare_recipient import WelfareRecipient
from app.models.support_plan_cycle import SupportPlanCycle
from app.models.push_subscription import PushSubscription
from app import crud


@pytest.fixture(autouse=True)
def mock_weekday_check():
    """
    すべてのテストで週末・祝日チェックをスキップ
    テストは曜日に関係なく実行できるようにする
    """
    with patch('app.tasks.deadline_notification.is_japanese_weekday_and_not_holiday', return_value=True):
        yield


@pytest.mark.asyncio
async def test_push_sent_when_system_notification_enabled(
    db_session: AsyncSession,
    office_factory,
    staff_factory,
    welfare_recipient_factory,
    test_admin_user: Staff
):
    """
    system_notification=trueの場合、Web Push通知が送信されることを確認

    前提条件:
    - スタッフのsystem_notification=true
    - 期限アラート対象の利用者が存在
    - Push購読が登録されている

    期待結果:
    - Push送信関数が呼ばれる
    - push_sentカウントが増加
    """
    # テストデータ準備
    office = await office_factory(creator=test_admin_user)

    staff = await staff_factory(office_id=office.id, email="test.staff@example.com")
    staff.notification_preferences = {
        "in_app_notification": True,
        "email_notification": True,
        "system_notification": True,  # Web Push有効
        "email_threshold_days": 30,
        "push_threshold_days": 10
    }
    await db_session.flush()

    # Push購読を登録
    subscription = PushSubscription(
        staff_id=staff.id,
        endpoint="https://fcm.googleapis.com/fcm/send/test-endpoint-123",
        p256dh_key="BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQ",
        auth_key="tBHItJI5svbpez7KI4CCXg"
    )
    db_session.add(subscription)
    await db_session.flush()

    # アラート対象の利用者作成
    recipient = await welfare_recipient_factory(office_id=office.id)
    cycle = SupportPlanCycle(
        welfare_recipient_id=recipient.id,
        office_id=office.id,
        next_renewal_deadline=date.today() + timedelta(days=5),  # 5日後（10日以内）
        is_latest_cycle=True,
        cycle_number=1,
        next_plan_start_date=7
    )
    db_session.add(cycle)
    await db_session.flush()

    # Push送信をモック（インポート先をパッチ）
    with patch('app.tasks.deadline_notification.send_push_notification', new_callable=AsyncMock) as mock_push:
        mock_push.return_value = (True, False)  # (success, should_delete)

        # バッチ実行
        result = await send_deadline_alert_emails(db=db_session, dry_run=False)

    # アサーション
    assert result["email_sent"] == 1, "メールが1件送信される"
    assert result["push_sent"] == 1, "Pushが1件送信される"
    assert result["push_failed"] == 0, "Push失敗なし"

    # Push送信関数が呼ばれたことを確認
    mock_push.assert_called_once()

    # 呼び出し引数を検証
    call_args = mock_push.call_args
    assert call_args.kwargs["title"] == f"期限アラート（{office.name}）"
    assert "更新期限: 1件" in call_args.kwargs["body"]


@pytest.mark.asyncio
async def test_push_skipped_when_system_notification_disabled(
    db_session: AsyncSession,
    office_factory,
    staff_factory,
    welfare_recipient_factory,
    test_admin_user: Staff
):
    """
    system_notification=falseの場合、Web Push通知が送信されないことを確認

    前提条件:
    - スタッフのsystem_notification=false
    - 期限アラート対象の利用者が存在

    期待結果:
    - Push送信関数が呼ばれない
    - push_sentカウントが0
    """
    # テストデータ準備
    office = await office_factory(creator=test_admin_user)

    staff = await staff_factory(office_id=office.id, email="test.staff@example.com")
    staff.notification_preferences = {
        "in_app_notification": True,
        "email_notification": True,
        "system_notification": False,  # Web Push無効
        "email_threshold_days": 30,
        "push_threshold_days": 10
    }
    await db_session.flush()

    # アラート対象の利用者作成
    recipient = await welfare_recipient_factory(office_id=office.id)
    cycle = SupportPlanCycle(
        welfare_recipient_id=recipient.id,
        office_id=office.id,
        next_renewal_deadline=date.today() + timedelta(days=5),
        is_latest_cycle=True,
        cycle_number=1,
        next_plan_start_date=7
    )
    db_session.add(cycle)
    await db_session.flush()

    # Push送信をモック
    with patch('app.tasks.deadline_notification.send_push_notification', new_callable=AsyncMock) as mock_push:
        # バッチ実行
        result = await send_deadline_alert_emails(db=db_session, dry_run=False)

    # アサーション
    assert result["email_sent"] == 1, "メールは送信される"
    assert result["push_sent"] == 0, "Pushは送信されない"
    assert result["push_failed"] == 0, "Push失敗もなし"

    # Push送信関数が呼ばれていないことを確認
    mock_push.assert_not_called()


@pytest.mark.asyncio
async def test_push_threshold_filtering(
    db_session: AsyncSession,
    office_factory,
    staff_factory,
    welfare_recipient_factory,
    test_admin_user: Staff
):
    """
    push_threshold_daysが正しく適用されることを確認

    前提条件:
    - スタッフのpush_threshold_days=10
    - 利用者A: 5日後（閾値内）
    - 利用者B: 15日後（閾値外）

    期待結果:
    - 利用者Aのみにpush送信される
    - push_sentカウントが1
    """
    # テストデータ準備
    office = await office_factory(creator=test_admin_user)

    staff = await staff_factory(office_id=office.id, email="test.staff@example.com")
    staff.notification_preferences = {
        "in_app_notification": True,
        "email_notification": True,
        "system_notification": True,
        "email_threshold_days": 30,  # メールは30日
        "push_threshold_days": 10   # Pushは10日
    }
    await db_session.flush()

    # Push購読を登録
    subscription = PushSubscription(
        staff_id=staff.id,
        endpoint="https://fcm.googleapis.com/fcm/send/test-endpoint-123",
        p256dh_key="BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQ",
        auth_key="tBHItJI5svbpez7KI4CCXg"
    )
    db_session.add(subscription)
    await db_session.flush()

    # 利用者A: 5日後（Push対象）
    recipient_a = await welfare_recipient_factory(office_id=office.id, first_name="太郎", last_name="山田")
    cycle_a = SupportPlanCycle(
        welfare_recipient_id=recipient_a.id,
        office_id=office.id,
        next_renewal_deadline=date.today() + timedelta(days=5),
        is_latest_cycle=True,
        cycle_number=1,
        next_plan_start_date=7
    )
    db_session.add(cycle_a)

    # 利用者B: 15日後（Push対象外、メールのみ）
    recipient_b = await welfare_recipient_factory(office_id=office.id, first_name="花子", last_name="佐藤")
    cycle_b = SupportPlanCycle(
        welfare_recipient_id=recipient_b.id,
        office_id=office.id,
        next_renewal_deadline=date.today() + timedelta(days=15),
        is_latest_cycle=True,
        cycle_number=1,
        next_plan_start_date=7
    )
    db_session.add(cycle_b)
    await db_session.flush()

    # Push送信をモック
    with patch('app.tasks.deadline_notification.send_push_notification', new_callable=AsyncMock) as mock_push:
        mock_push.return_value = (True, False)

        # バッチ実行
        result = await send_deadline_alert_emails(db=db_session, dry_run=False)

    # アサーション
    assert result["email_sent"] == 1, "メールは1件（両方の利用者を含む）"
    assert result["push_sent"] == 1, "Pushは1件（利用者Aのみ）"
    assert result["push_failed"] == 0, "Push失敗なし"

    # Push送信関数が1回だけ呼ばれたことを確認
    assert mock_push.call_count == 1

    # 呼び出し引数を検証（利用者Aのみ含まれる）
    call_args = mock_push.call_args
    assert "更新期限: 1件" in call_args.kwargs["body"], "Push通知には利用者Aのみ含まれる"


@pytest.mark.asyncio
async def test_push_multiple_devices(
    db_session: AsyncSession,
    office_factory,
    staff_factory,
    welfare_recipient_factory,
    test_admin_user: Staff
):
    """
    複数デバイスに全て送信されることを確認

    前提条件:
    - スタッフが3つのデバイスで購読登録
    - 期限アラート対象の利用者が存在

    期待結果:
    - 3つ全てのデバイスにPush送信される
    - push_sentカウントが3
    """
    # テストデータ準備
    office = await office_factory(creator=test_admin_user)

    staff = await staff_factory(office_id=office.id, email="test.staff@example.com")
    staff.notification_preferences = {
        "in_app_notification": True,
        "email_notification": True,
        "system_notification": True,
        "email_threshold_days": 30,
        "push_threshold_days": 10
    }
    await db_session.flush()

    # 3つのデバイスでPush購読を登録
    devices = [
        PushSubscription(
            staff_id=staff.id,
            endpoint=f"https://fcm.googleapis.com/fcm/send/device-{i}",
            p256dh_key="BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQ",
            auth_key="tBHItJI5svbpez7KI4CCXg",
            user_agent=f"Device {i}"
        )
        for i in range(1, 4)
    ]
    for device in devices:
        db_session.add(device)
    await db_session.flush()

    # アラート対象の利用者作成
    recipient = await welfare_recipient_factory(office_id=office.id)
    cycle = SupportPlanCycle(
        welfare_recipient_id=recipient.id,
        office_id=office.id,
        next_renewal_deadline=date.today() + timedelta(days=5),
        is_latest_cycle=True,
        cycle_number=1,
        next_plan_start_date=7
    )
    db_session.add(cycle)
    await db_session.flush()

    # Push送信をモック
    with patch('app.tasks.deadline_notification.send_push_notification', new_callable=AsyncMock) as mock_push:
        mock_push.return_value = (True, False)

        # バッチ実行
        result = await send_deadline_alert_emails(db=db_session, dry_run=False)

    # アサーション
    assert result["email_sent"] == 1, "メールが1件送信される"
    assert result["push_sent"] == 3, "3つのデバイス全てにPush送信される"
    assert result["push_failed"] == 0, "Push失敗なし"

    # Push送信関数が3回呼ばれたことを確認
    assert mock_push.call_count == 3

    # 各デバイスへの呼び出しを確認
    for i, call in enumerate(mock_push.call_args_list, start=1):
        assert f"device-{i}" in call.kwargs["subscription_info"]["endpoint"]


@pytest.mark.asyncio
async def test_push_subscription_cleanup_on_expired(
    db_session: AsyncSession,
    office_factory,
    staff_factory,
    welfare_recipient_factory,
    test_admin_user: Staff
):
    """
    410/404エラー時に購読が削除されることを確認

    前提条件:
    - スタッフが2つのデバイスで購読登録
    - 1つのデバイスが期限切れ（410 Gone）

    期待結果:
    - 期限切れデバイスの購読がDBから削除される
    - push_sentカウントが1（成功したデバイスのみ）
    - push_failedカウントが1（期限切れデバイス）
    """
    # テストデータ準備
    office = await office_factory(creator=test_admin_user)

    staff = await staff_factory(office_id=office.id, email="test.staff@example.com")
    staff.notification_preferences = {
        "in_app_notification": True,
        "email_notification": True,
        "system_notification": True,
        "email_threshold_days": 30,
        "push_threshold_days": 10
    }
    await db_session.flush()

    # 2つのデバイスでPush購読を登録
    device_active = PushSubscription(
        staff_id=staff.id,
        endpoint="https://fcm.googleapis.com/fcm/send/device-active",
        p256dh_key="BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQ",
        auth_key="tBHItJI5svbpez7KI4CCXg"
    )
    device_expired = PushSubscription(
        staff_id=staff.id,
        endpoint="https://fcm.googleapis.com/fcm/send/device-expired",
        p256dh_key="BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQ",
        auth_key="tBHItJI5svbpez7KI4CCXg"
    )
    db_session.add(device_active)
    db_session.add(device_expired)
    await db_session.flush()

    # アラート対象の利用者作成
    recipient = await welfare_recipient_factory(office_id=office.id)
    cycle = SupportPlanCycle(
        welfare_recipient_id=recipient.id,
        office_id=office.id,
        next_renewal_deadline=date.today() + timedelta(days=5),
        is_latest_cycle=True,
        cycle_number=1,
        next_plan_start_date=7
    )
    db_session.add(cycle)
    await db_session.flush()

    # Push送信をモック（期限切れデバイスはshould_delete=Trueを返す）
    async def mock_push_side_effect(*args, **kwargs):
        endpoint = kwargs["subscription_info"]["endpoint"]
        if "device-expired" in endpoint:
            return (False, True)  # 失敗、削除すべき
        else:
            return (True, False)  # 成功

    with patch('app.tasks.deadline_notification.send_push_notification', new_callable=AsyncMock) as mock_push:
        mock_push.side_effect = mock_push_side_effect

        # バッチ実行
        result = await send_deadline_alert_emails(db=db_session, dry_run=False)

    # アサーション
    assert result["email_sent"] == 1, "メールが1件送信される"
    assert result["push_sent"] == 1, "1デバイスにPush送信成功"
    assert result["push_failed"] == 1, "1デバイスでPush失敗"

    # 期限切れデバイスの購読が削除されたことを確認
    await db_session.refresh(staff)
    remaining_subs = await crud.push_subscription.get_by_staff_id(db=db_session, staff_id=staff.id)
    assert len(remaining_subs) == 1, "購読が1つだけ残る"
    assert remaining_subs[0].endpoint == "https://fcm.googleapis.com/fcm/send/device-active"


@pytest.mark.asyncio
async def test_push_failure_does_not_affect_email(
    db_session: AsyncSession,
    office_factory,
    staff_factory,
    welfare_recipient_factory,
    test_admin_user: Staff
):
    """
    Push送信失敗してもメール送信は成功することを確認

    前提条件:
    - スタッフがPush購読登録
    - Push送信が失敗（一時的エラー）

    期待結果:
    - メール送信は成功
    - push_failedカウントが1
    - email_sentカウントが1
    """
    # テストデータ準備
    office = await office_factory(creator=test_admin_user)

    staff = await staff_factory(office_id=office.id, email="test.staff@example.com")
    staff.notification_preferences = {
        "in_app_notification": True,
        "email_notification": True,
        "system_notification": True,
        "email_threshold_days": 30,
        "push_threshold_days": 10
    }
    await db_session.flush()

    # Push購読を登録
    subscription = PushSubscription(
        staff_id=staff.id,
        endpoint="https://fcm.googleapis.com/fcm/send/test-endpoint-123",
        p256dh_key="BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQ",
        auth_key="tBHItJI5svbpez7KI4CCXg"
    )
    db_session.add(subscription)
    await db_session.flush()

    # アラート対象の利用者作成
    recipient = await welfare_recipient_factory(office_id=office.id)
    cycle = SupportPlanCycle(
        welfare_recipient_id=recipient.id,
        office_id=office.id,
        next_renewal_deadline=date.today() + timedelta(days=5),
        is_latest_cycle=True,
        cycle_number=1,
        next_plan_start_date=7
    )
    db_session.add(cycle)
    await db_session.flush()

    # Push送信をモック（一時的エラー）
    with patch('app.tasks.deadline_notification.send_push_notification', new_callable=AsyncMock) as mock_push:
        mock_push.return_value = (False, False)  # 失敗、削除不要

        # バッチ実行
        result = await send_deadline_alert_emails(db=db_session, dry_run=False)

    # アサーション
    assert result["email_sent"] == 1, "メールは送信される"
    assert result["push_sent"] == 0, "Push送信は失敗"
    assert result["push_failed"] == 1, "Push失敗カウントが1"

    # 購読は削除されていないことを確認（一時的エラーなので）
    await db_session.refresh(staff)
    remaining_subs = await crud.push_subscription.get_by_staff_id(db=db_session, staff_id=staff.id)
    assert len(remaining_subs) == 1, "購読はそのまま残る"


@pytest.mark.asyncio
async def test_dry_run_skips_push_sending(
    db_session: AsyncSession,
    office_factory,
    staff_factory,
    welfare_recipient_factory,
    test_admin_user: Staff
):
    """
    dry_run=trueの場合、Push送信がスキップされることを確認

    前提条件:
    - dry_run=true
    - スタッフがPush購読登録

    期待結果:
    - Push送信関数が呼ばれない
    - push_sentカウントが1（dry_runでもカウント）
    """
    # テストデータ準備
    office = await office_factory(creator=test_admin_user)

    staff = await staff_factory(office_id=office.id, email="test.staff@example.com")
    staff.notification_preferences = {
        "in_app_notification": True,
        "email_notification": True,
        "system_notification": True,
        "email_threshold_days": 30,
        "push_threshold_days": 10
    }
    await db_session.flush()

    # Push購読を登録
    subscription = PushSubscription(
        staff_id=staff.id,
        endpoint="https://fcm.googleapis.com/fcm/send/test-endpoint-123",
        p256dh_key="BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQ",
        auth_key="tBHItJI5svbpez7KI4CCXg"
    )
    db_session.add(subscription)
    await db_session.flush()

    # アラート対象の利用者作成
    recipient = await welfare_recipient_factory(office_id=office.id)
    cycle = SupportPlanCycle(
        welfare_recipient_id=recipient.id,
        office_id=office.id,
        next_renewal_deadline=date.today() + timedelta(days=5),
        is_latest_cycle=True,
        cycle_number=1,
        next_plan_start_date=7
    )
    db_session.add(cycle)
    await db_session.flush()

    # Push送信をモック
    with patch('app.tasks.deadline_notification.send_push_notification', new_callable=AsyncMock) as mock_push:
        # バッチ実行（dry_run=True）
        result = await send_deadline_alert_emails(db=db_session, dry_run=True)

    # アサーション
    assert result["email_sent"] == 1, "メールカウントは1（dry_runでもカウント）"
    assert result["push_sent"] == 1, "Pushカウントは1（dry_runでもカウント）"
    assert result["push_failed"] == 0, "Push失敗なし"

    # Push送信関数が呼ばれていないことを確認（dry_run）
    mock_push.assert_not_called()
