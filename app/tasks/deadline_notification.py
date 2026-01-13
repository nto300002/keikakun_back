"""
期限アラートのメール通知バッチ処理

実行頻度: 毎日 0:00 UTC (9:00 JST)
実行条件: 平日かつ祝日でない場合のみ
"""
import logging
import asyncio
from datetime import datetime, timezone, date
from typing import List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log
)

from app import crud
from app.models.office import Office
from app.models.staff import Staff
from app.models.office import OfficeStaff
from app.services.welfare_recipient_service import WelfareRecipientService
from app.schemas.deadline_alert import DeadlineAlertItem
from app.core.mail import send_deadline_alert_email
from app.core.config import settings
from app.utils.holiday_utils import is_japanese_weekday_and_not_holiday
from app.utils.privacy_utils import mask_email

logger = logging.getLogger(__name__)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(Exception),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True
)
async def _send_email_with_retry(
    staff_email: str,
    staff_name: str,
    office_name: str,
    renewal_alerts: List,
    assessment_alerts: List,
    dashboard_url: str
):
    """
    リトライロジック付きメール送信

    リトライ設定:
    - 最大3回試行（初回 + 2回リトライ）
    - 指数バックオフ: 2秒、4秒、8秒...
    - すべての例外でリトライ
    """
    await send_deadline_alert_email(
        staff_email=staff_email,
        staff_name=staff_name,
        office_name=office_name,
        renewal_alerts=renewal_alerts,
        assessment_alerts=assessment_alerts,
        dashboard_url=dashboard_url
    )


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
    today = datetime.now(timezone.utc).date()
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
    rate_limit_semaphore = asyncio.Semaphore(5)

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
                        f"[DRY RUN] Would send email to {mask_email(staff.email)} "
                        f"({staff.last_name} {staff.first_name})"
                    )
                    email_count += 1
                else:
                    async with rate_limit_semaphore:
                        try:
                            await asyncio.wait_for(
                                _send_email_with_retry(
                                    staff_email=staff.email,
                                    staff_name=f"{staff.last_name} {staff.first_name}",
                                    office_name=office.name,
                                    renewal_alerts=renewal_alerts,
                                    assessment_alerts=assessment_alerts,
                                    dashboard_url=f"{settings.FRONTEND_URL}/dashboard"
                                ),
                                timeout=30.0
                            )
                            logger.info(
                                f"[DEADLINE_NOTIFICATION] Email sent to {mask_email(staff.email)} "
                                f"({staff.last_name} {staff.first_name})"
                            )
                            email_count += 1

                            await crud.audit_log.create_log(
                                db=db,
                                actor_id=None,
                                actor_role="system",
                                action="deadline_notification_sent",
                                target_type="email_notification",
                                target_id=staff.id,
                                office_id=office.id,
                                details={
                                    "recipient_email": staff.email,
                                    "office_name": office.name,
                                    "renewal_alert_count": len(renewal_alerts),
                                    "assessment_alert_count": len(assessment_alerts),
                                    "staff_name": f"{staff.last_name} {staff.first_name}"
                                },
                                auto_commit=False
                            )

                            await asyncio.sleep(0.1)

                        except asyncio.TimeoutError:
                            logger.error(
                                f"[DEADLINE_NOTIFICATION] Timeout sending email to {mask_email(staff.email)} "
                                f"({staff.last_name} {staff.first_name}) - exceeded 30s limit",
                                exc_info=True
                            )
                        except Exception as e:
                            logger.error(
                                f"[DEADLINE_NOTIFICATION] Failed to send email to {mask_email(staff.email)}: {e}",
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
