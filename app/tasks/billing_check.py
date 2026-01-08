"""
課金関連の定期チェックタスク
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.models.billing import Billing
from app.models.enums import BillingStatus

logger = logging.getLogger(__name__)


async def check_trial_expiration(
    db: AsyncSession,
    dry_run: bool = False
) -> int:
    """
    トライアル期間終了チェック（定期実行タスク）

    処理内容:
    - trial_end_date < now かつ billing_status が 'free' または 'early_payment' のレコードを抽出
    - billing_status を以下のように更新:
      - free → past_due（無料期間終了、未課金）
      - early_payment → active（無料期間終了、課金済み）
    - 処理件数を返す

    実行頻度: 毎日0:00 UTC（推奨）

    Args:
        db: データベースセッション
        dry_run: Trueの場合は更新せず、対象件数のみ返す（テスト用）

    Returns:
        int: 更新したBillingの件数

    Examples:
        >>> # 本番実行
        >>> expired_count = await check_trial_expiration(db=db)
        >>> logger.info(f"Updated {expired_count} expired trials")

        >>> # ドライラン（テスト実行）
        >>> expired_count = await check_trial_expiration(db=db, dry_run=True)
        >>> print(f"Would update {expired_count} expired trials")
    """
    now = datetime.now(timezone.utc)

    # トライアル期限切れのBillingを取得
    # 条件:
    # - billing_status in ('free', 'early_payment')
    # - trial_end_date < now （期限切れ）
    query = select(Billing).where(
        Billing.billing_status.in_([BillingStatus.free, BillingStatus.early_payment]),
        Billing.trial_end_date < now
    )

    result = await db.execute(query)
    expired_billings = result.scalars().all()

    if dry_run:
        logger.info(
            f"[DRY RUN] Would update {len(expired_billings)} expired trials"
        )
        return len(expired_billings)

    # ステータス更新
    updated_count = 0
    for billing in expired_billings:
        # 遷移先を判定
        if billing.billing_status == BillingStatus.free:
            new_status = BillingStatus.past_due
        elif billing.billing_status == BillingStatus.early_payment:
            new_status = BillingStatus.active
        else:
            continue

        await crud.billing.update_status(
            db=db,
            billing_id=billing.id,
            status=new_status,
            auto_commit=False
        )

        logger.info(
            f"Trial expired: office_id={billing.office_id}, "
            f"billing_id={billing.id}, "
            f"trial_end_date={billing.trial_end_date}, "
            f"{billing.billing_status.value} → {new_status.value}"
        )

        updated_count += 1

    # コミット
    if updated_count > 0:
        await db.commit()
        logger.info(f"Updated {updated_count} expired trials")

    return updated_count


async def check_scheduled_cancellation(
    db: AsyncSession,
    dry_run: bool = False
) -> int:
    """
    スケジュールされたキャンセルの期限チェック（定期実行タスク）

    処理内容:
    - scheduled_cancel_at < now かつ billing_status = 'canceling' のレコードを抽出
    - billing_status を 'canceled' に更新
    - 処理件数を返す

    実行頻度: 毎日0:05 UTC（推奨）

    Args:
        db: データベースセッション
        dry_run: Trueの場合は更新せず、対象件数のみ返す（テスト用）

    Returns:
        int: 更新したBillingの件数

    Examples:
        >>> # 本番実行
        >>> canceled_count = await check_scheduled_cancellation(db=db)
        >>> logger.info(f"Updated {canceled_count} scheduled cancellations")

        >>> # ドライラン（テスト実行）
        >>> canceled_count = await check_scheduled_cancellation(db=db, dry_run=True)
        >>> print(f"Would update {canceled_count} scheduled cancellations")
    """
    now = datetime.now(timezone.utc)

    # スケジュールキャンセルが過去日付のBillingを取得
    query = select(Billing).where(
        Billing.billing_status == BillingStatus.canceling,
        Billing.scheduled_cancel_at.isnot(None),
        Billing.scheduled_cancel_at < now
    )

    result = await db.execute(query)
    expired_cancellations = result.scalars().all()

    if dry_run:
        logger.info(
            f"[DRY RUN] Would update {len(expired_cancellations)} expired scheduled cancellations"
        )
        return len(expired_cancellations)

    # ステータス更新
    updated_count = 0
    for billing in expired_cancellations:
        await crud.billing.update_status(
            db=db,
            billing_id=billing.id,
            status=BillingStatus.canceled,
            auto_commit=False
        )

        logger.warning(
            f"Scheduled cancellation expired (Webhook may have been missed): "
            f"office_id={billing.office_id}, "
            f"billing_id={billing.id}, "
            f"scheduled_cancel_at={billing.scheduled_cancel_at}"
        )

        updated_count += 1

    # コミット
    if updated_count > 0:
        await db.commit()
        logger.info(f"Updated {updated_count} expired scheduled cancellations to canceled")

    return updated_count


async def get_expiring_trials(
    db: AsyncSession,
    days_before: int = 7
) -> list[Billing]:
    """
    まもなくトライアル期間が終了するBillingを取得

    Args:
        db: データベースセッション
        days_before: 何日前から通知するか（デフォルト7日）

    Returns:
        list[Billing]: まもなく期限切れになるBillingのリスト

    Examples:
        >>> # 7日以内に期限切れになるBillingを取得
        >>> expiring_billings = await get_expiring_trials(db=db, days_before=7)
        >>> for billing in expiring_billings:
        >>>     await send_trial_expiring_notification(billing.office_id)
    """
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    threshold_date = now + timedelta(days=days_before)

    query = select(Billing).where(
        Billing.billing_status == BillingStatus.free,
        Billing.trial_end_date > now,
        Billing.trial_end_date <= threshold_date
    )

    result = await db.execute(query)
    return result.scalars().all()
