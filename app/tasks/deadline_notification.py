"""
期限アラートのメール通知バッチ処理

実行頻度: 毎日 0:00 UTC (9:00 JST)
実行条件: 平日かつ祝日でない場合のみ
"""
import logging
from datetime import datetime, timezone, date
from typing import List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import crud
from app.models.office import Office
from app.models.staff import Staff
from app.models.office import OfficeStaff
from app.services.welfare_recipient_service import WelfareRecipientService
from app.schemas.deadline_alert import DeadlineAlertItem
from app.core.mail import send_deadline_alert_email
from app.core.config import settings
from app.utils.holiday_utils import is_japanese_weekday_and_not_holiday

logger = logging.getLogger(__name__)


async def send_deadline_alert_emails(
    db: AsyncSession,
    dry_run: bool = False
) -> int:
    """
    全事業所の期限アラートメールを送信

    処理内容:
    1. 全事業所を取得
    2. 各事業所ごとに期限アラートを取得
    3. アラートがある場合、該当事業所の全スタッフにメール送信

    Args:
        db: データベースセッション
        dry_run: Trueの場合は送信せず、送信予定件数のみ返す

    Returns:
        int: 送信したメール件数

    Examples:
        >>> # 本番実行
        >>> count = await send_deadline_alert_emails(db=db)
        >>> logger.info(f"Sent {count} deadline alert emails")

        >>> # ドライラン（テスト実行）
        >>> count = await send_deadline_alert_emails(db=db, dry_run=True)
        >>> print(f"Would send {count} deadline alert emails")
    """
    today = date.today()
    if not is_japanese_weekday_and_not_holiday(today):
        logger.info(
            f"[DEADLINE_NOTIFICATION] Skipping email notification: "
            f"today is weekend or holiday ({today})"
        )
        return 0

    logger.info(
        f"[DEADLINE_NOTIFICATION] Starting deadline alert email notification"
    )

    stmt = select(Office).where(Office.deleted_at.is_(None))
    result = await db.execute(stmt)
    offices = result.scalars().all()

    logger.info(f"[DEADLINE_NOTIFICATION] Found {len(offices)} active offices")

    email_count = 0

    for office in offices:
        try:
            alert_response = await WelfareRecipientService.get_deadline_alerts(
                db=db,
                office_id=office.id,
                threshold_days=30,
                limit=None,
                offset=0
            )

            if alert_response.total == 0:
                logger.debug(
                    f"[DEADLINE_NOTIFICATION] Office {office.name} "
                    f"(ID: {office.id}): No alerts, skipping"
                )
                continue

            renewal_alerts: List[DeadlineAlertItem] = []
            assessment_alerts: List[DeadlineAlertItem] = []

            for alert in alert_response.alerts:
                if alert.alert_type == "renewal_deadline":
                    renewal_alerts.append(alert)
                elif alert.alert_type == "assessment_incomplete":
                    assessment_alerts.append(alert)

            logger.info(
                f"[DEADLINE_NOTIFICATION] Office {office.name} "
                f"(ID: {office.id}): {len(renewal_alerts)} renewal alerts, "
                f"{len(assessment_alerts)} assessment alerts"
            )

            staff_stmt = (
                select(Staff)
                .join(OfficeStaff, OfficeStaff.staff_id == Staff.id)
                .where(
                    OfficeStaff.office_id == office.id,
                    Staff.deleted_at.is_(None),
                    Staff.email.isnot(None)
                )
            )
            staff_result = await db.execute(staff_stmt)
            staffs = staff_result.scalars().all()

            if not staffs:
                logger.warning(
                    f"[DEADLINE_NOTIFICATION] Office {office.name} "
                    f"(ID: {office.id}): No staff with email address, skipping"
                )
                continue

            logger.info(
                f"[DEADLINE_NOTIFICATION] Office {office.name} "
                f"(ID: {office.id}): Sending to {len(staffs)} staff members"
            )

            for staff in staffs:
                if dry_run:
                    logger.info(
                        f"[DRY RUN] Would send email to {staff.email} "
                        f"({staff.last_name} {staff.first_name})"
                    )
                    email_count += 1
                else:
                    try:
                        await send_deadline_alert_email(
                            staff_email=staff.email,
                            staff_name=f"{staff.last_name} {staff.first_name}",
                            office_name=office.name,
                            renewal_alerts=renewal_alerts,
                            assessment_alerts=assessment_alerts,
                            dashboard_url=f"{settings.FRONTEND_URL}/dashboard"
                        )
                        logger.info(
                            f"[DEADLINE_NOTIFICATION] Email sent to {staff.email} "
                            f"({staff.last_name} {staff.first_name})"
                        )
                        email_count += 1
                    except Exception as e:
                        logger.error(
                            f"[DEADLINE_NOTIFICATION] Failed to send email to {staff.email}: {e}",
                            exc_info=True
                        )

        except Exception as e:
            logger.error(
                f"[DEADLINE_NOTIFICATION] Error processing office {office.name} "
                f"(ID: {office.id}): {e}",
                exc_info=True
            )

    logger.info(
        f"[DEADLINE_NOTIFICATION] Completed: "
        f"{'Would send' if dry_run else 'Sent'} {email_count} emails"
    )

    return email_count
