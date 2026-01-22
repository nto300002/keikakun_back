"""
期限アラートのメール通知バッチ処理

実行頻度: 毎日 0:00 UTC (9:00 JST)
実行条件: 平日かつ祝日でない場合のみ
"""
import logging
import asyncio
import os
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
from app.core.push import send_push_notification
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
) -> dict:
    """
    全事業所の期限アラートメール + Web Push通知を送信（閾値カスタマイズ対応）

    処理内容:
    1. 全事業所を取得
    2. 各事業所ごとに期限アラートを取得（最大閾値30日で取得）
    3. 各スタッフの通知設定に基づいて、個別にアラートをフィルタリングして送信
       - email_notification=trueのスタッフのみメール送信
       - system_notification=trueのスタッフのみWeb Push送信
       - 各スタッフのemail_threshold_days/push_threshold_daysに基づいてアラートをフィルタリング

    Args:
        db: データベースセッション
        dry_run: Trueの場合は送信せず、送信予定件数のみ返す

    Returns:
        dict: 送信結果
            - email_sent: 送信したメール件数
            - push_sent: 送信したWeb Push件数
            - push_failed: 失敗したWeb Push件数

    Examples:
        >>> # 本番実行
        >>> result = await send_deadline_alert_emails(db=db)
        >>> logger.info(f"Sent {result['email_sent']} emails, {result['push_sent']} push notifications")

        >>> # ドライラン（テスト実行）
        >>> result = await send_deadline_alert_emails(db=db, dry_run=True)
        >>> print(f"Would send {result['email_sent']} emails, {result['push_sent']} push notifications")
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

    # テスト環境かどうかをチェック
    is_testing = os.getenv("TESTING") == "1"

    # Office取得クエリ（本番環境のみis_test_dataでフィルタ）
    office_conditions = [Office.deleted_at.is_(None)]
    if not is_testing:
        office_conditions.append(Office.is_test_data == False)

    stmt = select(Office).where(*office_conditions)
    result = await db.execute(stmt)
    offices = result.scalars().all()

    logger.info(f"[DEADLINE_NOTIFICATION] Found {len(offices)} active offices")

    email_count = 0
    push_sent_count = 0
    push_failed_count = 0
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

            all_renewal_alerts: List[DeadlineAlertItem] = []
            all_assessment_alerts: List[DeadlineAlertItem] = []

            for alert in alert_response.alerts:
                if alert.alert_type == "renewal_deadline":
                    all_renewal_alerts.append(alert)
                elif alert.alert_type == "assessment_incomplete":
                    all_assessment_alerts.append(alert)

            logger.info(
                f"[DEADLINE_NOTIFICATION] Office {office.name} "
                f"(ID: {office.id}): {len(all_renewal_alerts)} renewal alerts, "
                f"{len(all_assessment_alerts)} assessment alerts (max threshold: 30 days)"
            )

            # Staff取得クエリ（本番環境のみis_test_dataでフィルタ）
            staff_conditions = [
                OfficeStaff.office_id == office.id,
                Staff.deleted_at.is_(None),
                Staff.email.isnot(None)
            ]
            if not is_testing:
                staff_conditions.append(Staff.is_test_data == False)

            staff_stmt = (
                select(Staff)
                .join(OfficeStaff, OfficeStaff.staff_id == Staff.id)
                .where(*staff_conditions)
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
                f"(ID: {office.id}): Processing {len(staffs)} staff members"
            )

            for staff in staffs:
                # notification_preferencesがNoneの場合はデフォルト値を使用
                notification_prefs = staff.notification_preferences or {
                    "in_app_notification": True,
                    "email_notification": True,
                    "system_notification": False,
                    "email_threshold_days": 30,
                    "push_threshold_days": 10
                }

                email_notification_enabled = notification_prefs.get("email_notification", True)

                if not email_notification_enabled:
                    logger.debug(
                        f"[DEADLINE_NOTIFICATION] Staff {mask_email(staff.email)} "
                        f"({staff.last_name} {staff.first_name}): email_notification disabled, skipping"
                    )
                    continue

                staff_email_threshold = notification_prefs.get("email_threshold_days", 30)

                staff_renewal_alerts = [
                    alert for alert in all_renewal_alerts
                    if alert.days_remaining is not None and alert.days_remaining <= staff_email_threshold
                ]
                # assessment_incomplete alerts: 常に全スタッフに送信（閾値フィルタリングなし）
                # アセスメント未完了は緊急性が高いため、days_remainingに関係なく通知
                staff_assessment_alerts = all_assessment_alerts

                if not staff_renewal_alerts and not staff_assessment_alerts:
                    logger.debug(
                        f"[DEADLINE_NOTIFICATION] Staff {mask_email(staff.email)} "
                        f"({staff.last_name} {staff.first_name}): No alerts within threshold "
                        f"({staff_email_threshold} days), skipping"
                    )
                    continue

                logger.info(
                    f"[DEADLINE_NOTIFICATION] Staff {mask_email(staff.email)} "
                    f"({staff.last_name} {staff.first_name}): {len(staff_renewal_alerts)} renewal alerts, "
                    f"{len(staff_assessment_alerts)} assessment alerts (threshold: {staff_email_threshold} days)"
                )

                if dry_run:
                    logger.info(
                        f"[DRY RUN] Would send email to {mask_email(staff.email)} "
                        f"({staff.last_name} {staff.first_name}) - threshold: {staff_email_threshold} days"
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
                                    renewal_alerts=staff_renewal_alerts,
                                    assessment_alerts=staff_assessment_alerts,
                                    dashboard_url=f"{settings.FRONTEND_URL}/dashboard"
                                ),
                                timeout=30.0
                            )
                            logger.info(
                                f"[DEADLINE_NOTIFICATION] Email sent to {mask_email(staff.email)} "
                                f"({staff.last_name} {staff.first_name}) - threshold: {staff_email_threshold} days"
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
                                    "renewal_alert_count": len(staff_renewal_alerts),
                                    "assessment_alert_count": len(staff_assessment_alerts),
                                    "staff_name": f"{staff.last_name} {staff.first_name}",
                                    "email_threshold_days": staff_email_threshold
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

                # Web Push通知送信（system_notification=trueのスタッフのみ）
                system_notification_enabled = notification_prefs.get("system_notification", False)

                if system_notification_enabled:
                    staff_push_threshold = notification_prefs.get("push_threshold_days", 10)

                    # Push用のアラートをフィルタリング（閾値反映）
                    push_renewal_alerts = [
                        alert for alert in all_renewal_alerts
                        if alert.days_remaining is not None and alert.days_remaining <= staff_push_threshold
                    ]
                    # assessment_incomplete alerts: 常に全スタッフに送信（閾値フィルタリングなし）
                    # アセスメント未完了は緊急性が高いため、days_remainingに関係なく通知
                    push_assessment_alerts = all_assessment_alerts

                    if push_renewal_alerts or push_assessment_alerts:
                        # スタッフの全デバイス（購読）を取得
                        subscriptions = await crud.push_subscription.get_by_staff_id(
                            db=db,
                            staff_id=staff.id
                        )

                        logger.info(
                            f"[WEB_PUSH] Staff {mask_email(staff.email)} "
                            f"({staff.last_name} {staff.first_name}): {len(subscriptions)} device(s), "
                            f"{len(push_renewal_alerts)} renewal alerts, "
                            f"{len(push_assessment_alerts)} assessment alerts "
                            f"(threshold: {staff_push_threshold} days)"
                        )

                        # スタッフごとのPush送信結果カウンター（監査ログ用）
                        staff_push_sent = 0
                        staff_push_failed = 0

                        for sub in subscriptions:
                            if dry_run:
                                logger.info(
                                    f"[DRY RUN] Would send push to device: "
                                    f"{sub.endpoint[:50]}... - threshold: {staff_push_threshold} days"
                                )
                                push_sent_count += 1
                                staff_push_sent += 1
                            else:
                                try:
                                    # Push通知を送信
                                    success, should_delete = await send_push_notification(
                                        subscription_info={
                                            "endpoint": sub.endpoint,
                                            "keys": {
                                                "p256dh": sub.p256dh_key,
                                                "auth": sub.auth_key
                                            }
                                        },
                                        title=f"期限アラート（{office.name}）",
                                        body=f"更新期限: {len(push_renewal_alerts)}件、アセスメント未完了: {len(push_assessment_alerts)}件",
                                        data={
                                            "type": "deadline_alert",
                                            "office_id": str(office.id),
                                            "office_name": office.name,
                                            "renewal_count": len(push_renewal_alerts),
                                            "assessment_count": len(push_assessment_alerts),
                                            "push_threshold_days": staff_push_threshold
                                        }
                                    )

                                    if success:
                                        logger.info(
                                            f"[WEB_PUSH] Push sent successfully to device: "
                                            f"{sub.endpoint[:50]}... - threshold: {staff_push_threshold} days"
                                        )
                                        push_sent_count += 1
                                        staff_push_sent += 1
                                    elif should_delete:
                                        # 購読期限切れの場合、削除する
                                        logger.warning(
                                            f"[WEB_PUSH] Subscription expired (410/404), deleting: {sub.endpoint[:50]}..."
                                        )
                                        await crud.push_subscription.delete_by_endpoint(
                                            db=db,
                                            endpoint=sub.endpoint
                                        )
                                        push_failed_count += 1
                                        staff_push_failed += 1
                                    else:
                                        # その他のエラー（一時的なネットワークエラーなど）
                                        logger.error(
                                            f"[WEB_PUSH] Failed to send push (temporary error): {sub.endpoint[:50]}..."
                                        )
                                        push_failed_count += 1
                                        staff_push_failed += 1

                                except Exception as e:
                                    logger.error(
                                        f"[WEB_PUSH] Failed to send push to device {sub.endpoint[:50]}...: {e}",
                                        exc_info=True
                                    )
                                    push_failed_count += 1
                                    staff_push_failed += 1

                        # Push送信完了後、監査ログを作成（セキュリティ実装）
                        if not dry_run and len(subscriptions) > 0:
                            await crud.audit_log.create_log(
                                db=db,
                                actor_id=None,
                                actor_role="system",
                                action="push_notification_sent",
                                target_type="push_notification",
                                target_id=staff.id,
                                office_id=office.id,
                                details={
                                    "recipient_email": staff.email,
                                    "office_name": office.name,
                                    "staff_name": f"{staff.last_name} {staff.first_name}",
                                    "push_sent_count": staff_push_sent,
                                    "push_failed_count": staff_push_failed,
                                    "device_count": len(subscriptions),
                                    "renewal_alert_count": len(push_renewal_alerts),
                                    "assessment_alert_count": len(push_assessment_alerts),
                                    "push_threshold_days": staff_push_threshold
                                },
                                auto_commit=False
                            )

        except Exception as e:
            logger.error(
                f"[DEADLINE_NOTIFICATION] Error processing office {office.name} "
                f"(ID: {office.id}): {e}",
                exc_info=True
            )

    logger.info(
        f"[DEADLINE_NOTIFICATION] Completed: "
        f"{'Would send' if dry_run else 'Sent'} {email_count} emails, "
        f"{push_sent_count} push notifications "
        f"({push_failed_count} failed)"
    )

    return {
        "email_sent": email_count,
        "push_sent": push_sent_count,
        "push_failed": push_failed_count
    }
