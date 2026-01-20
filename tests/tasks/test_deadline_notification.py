"""
期限アラート通知バッチ処理のテスト
"""
import pytest
import pytest_asyncio
from datetime import date, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from app.tasks.deadline_notification import send_deadline_alert_emails
from app.models.office import Office, OfficeStaff
from app.models.staff import Staff
from app.models.welfare_recipient import WelfareRecipient
from app.models.support_plan_cycle import SupportPlanCycle


@pytest.mark.asyncio
async def test_send_deadline_alert_emails_dry_run(
    db_session: AsyncSession,
    office_factory,
    welfare_recipient_factory,
    test_admin_user: Staff
):
    """
    dry_runモードで正しく送信予定件数を返すことを確認
    """
    office = await office_factory(creator=test_admin_user)
    db_session.add(OfficeStaff(staff_id=test_admin_user.id, office_id=office.id, is_primary=True))
    await db_session.flush()

    recipient = await welfare_recipient_factory(office_id=office.id)
    cycle = SupportPlanCycle(
        welfare_recipient_id=recipient.id,
        office_id=office.id,
        next_renewal_deadline=date.today() + timedelta(days=15),
        is_latest_cycle=True,
        cycle_number=1,
        next_plan_start_date=7
    )
    db_session.add(cycle)
    await db_session.flush()

    result = await send_deadline_alert_emails(db=db_session, dry_run=True)

    assert result["email_sent"] == 1


@pytest.mark.asyncio
async def test_send_deadline_alert_emails_no_alerts(
    db_session: AsyncSession,
    office_factory,
    test_admin_user: Staff
):
    """
    アラートがない場合、メールを送信しないことを確認
    """
    office = await office_factory(creator=test_admin_user)
    db_session.add(OfficeStaff(staff_id=test_admin_user.id, office_id=office.id, is_primary=True))
    await db_session.flush()

    result = await send_deadline_alert_emails(db=db_session, dry_run=True)

    assert result["email_sent"] == 0


@pytest.mark.asyncio
async def test_send_deadline_alert_emails_with_threshold_filtering(
    db_session: AsyncSession,
    office_factory,
    staff_factory,
    welfare_recipient_factory,
    test_admin_user: Staff
):
    """
    スタッフの閾値設定に基づいてアラートがフィルタリングされることを確認
    - Staff A: email_threshold_days=10 → 15日後のアラートは送信されない
    - Staff B: email_threshold_days=20 → 15日後のアラートは送信される
    """
    office = await office_factory(creator=test_admin_user)

    staff_a = await staff_factory(office_id=office.id, email="staff.a@example.com")
    staff_a.notification_preferences = {
        "in_app_notification": True,
        "email_notification": True,
        "system_notification": False,
        "email_threshold_days": 10,
        "push_threshold_days": 10
    }

    staff_b = await staff_factory(office_id=office.id, email="staff.b@example.com")
    staff_b.notification_preferences = {
        "in_app_notification": True,
        "email_notification": True,
        "system_notification": False,
        "email_threshold_days": 20,
        "push_threshold_days": 10
    }

    await db_session.flush()

    recipient = await welfare_recipient_factory(office_id=office.id)
    cycle = SupportPlanCycle(
        welfare_recipient_id=recipient.id,
        office_id=office.id,
        next_renewal_deadline=date.today() + timedelta(days=15),
        is_latest_cycle=True,
        cycle_number=1,
        next_plan_start_date=22
    )
    db_session.add(cycle)
    await db_session.flush()

    result = await send_deadline_alert_emails(db=db_session, dry_run=True)

    assert result["email_sent"] == 1


@pytest.mark.asyncio
async def test_send_deadline_alert_emails_email_notification_disabled(
    db_session: AsyncSession,
    office_factory,
    staff_factory,
    welfare_recipient_factory,
    test_admin_user: Staff
):
    """
    email_notification=falseのスタッフにはメールが送信されないことを確認
    """
    office = await office_factory(creator=test_admin_user)

    staff_disabled = await staff_factory(office_id=office.id, email="staff.disabled@example.com")
    staff_disabled.notification_preferences = {
        "in_app_notification": True,
        "email_notification": False,
        "system_notification": False,
        "email_threshold_days": 30,
        "push_threshold_days": 10
    }

    await db_session.flush()

    recipient = await welfare_recipient_factory(office_id=office.id)
    cycle = SupportPlanCycle(
        welfare_recipient_id=recipient.id,
        office_id=office.id,
        next_renewal_deadline=date.today() + timedelta(days=15),
        is_latest_cycle=True,
        cycle_number=1,
        next_plan_start_date=22
    )
    db_session.add(cycle)
    await db_session.flush()

    result = await send_deadline_alert_emails(db=db_session, dry_run=True)

    assert result["email_sent"] == 0


@pytest.mark.asyncio
async def test_send_deadline_alert_emails_multiple_thresholds(
    db_session: AsyncSession,
    office_factory,
    staff_factory,
    welfare_recipient_factory,
    test_admin_user: Staff
):
    """
    複数のスタッフが異なる閾値を持つ場合、それぞれ正しくフィルタリングされることを確認
    - 5日後のアラート → 5日閾値のスタッフのみ受信
    - 15日後のアラート → 20日・30日閾値のスタッフが受信
    """
    office = await office_factory(creator=test_admin_user)

    staff_5d = await staff_factory(office_id=office.id, email="staff.5d@example.com")
    staff_5d.notification_preferences = {
        "in_app_notification": True,
        "email_notification": True,
        "system_notification": False,
        "email_threshold_days": 5,
        "push_threshold_days": 10
    }

    staff_10d = await staff_factory(office_id=office.id, email="staff.10d@example.com")
    staff_10d.notification_preferences = {
        "in_app_notification": True,
        "email_notification": True,
        "system_notification": False,
        "email_threshold_days": 10,
        "push_threshold_days": 10
    }

    staff_20d = await staff_factory(office_id=office.id, email="staff.20d@example.com")
    staff_20d.notification_preferences = {
        "in_app_notification": True,
        "email_notification": True,
        "system_notification": False,
        "email_threshold_days": 20,
        "push_threshold_days": 10
    }

    staff_30d = await staff_factory(office_id=office.id, email="staff.30d@example.com")
    staff_30d.notification_preferences = {
        "in_app_notification": True,
        "email_notification": True,
        "system_notification": False,
        "email_threshold_days": 30,
        "push_threshold_days": 10
    }

    await db_session.flush()

    recipient = await welfare_recipient_factory(office_id=office.id)
    cycle = SupportPlanCycle(
        welfare_recipient_id=recipient.id,
        office_id=office.id,
        next_renewal_deadline=date.today() + timedelta(days=15),
        is_latest_cycle=True,
        cycle_number=1,
        next_plan_start_date=22
    )
    db_session.add(cycle)
    await db_session.flush()

    result = await send_deadline_alert_emails(db=db_session, dry_run=True)

    assert result["email_sent"] == 2


@pytest.mark.asyncio
async def test_send_deadline_alert_emails_default_threshold(
    db_session: AsyncSession,
    office_factory,
    staff_factory,
    welfare_recipient_factory,
    test_admin_user: Staff
):
    """
    notification_preferencesにemail_threshold_daysがない場合、デフォルト30日が使用されることを確認
    """
    office = await office_factory(creator=test_admin_user)

    staff_no_threshold = await staff_factory(office_id=office.id, email="staff.no.threshold@example.com")
    staff_no_threshold.notification_preferences = {
        "in_app_notification": True,
        "email_notification": True,
        "system_notification": False
    }

    await db_session.flush()

    recipient = await welfare_recipient_factory(office_id=office.id)
    cycle = SupportPlanCycle(
        welfare_recipient_id=recipient.id,
        office_id=office.id,
        next_renewal_deadline=date.today() + timedelta(days=25),
        is_latest_cycle=True,
        cycle_number=1,
        next_plan_start_date=32
    )
    db_session.add(cycle)
    await db_session.flush()

    result = await send_deadline_alert_emails(db=db_session, dry_run=True)

    assert result["email_sent"] == 1
