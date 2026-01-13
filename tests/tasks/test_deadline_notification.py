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

    count = await send_deadline_alert_emails(db=db_session, dry_run=True)

    assert count == 1


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

    count = await send_deadline_alert_emails(db=db_session, dry_run=True)

    assert count == 0
