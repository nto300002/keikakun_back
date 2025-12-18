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
    - trial_end_date < now かつ billing_status = 'free' のレコードを抽出
    - billing_status を 'past_due' に更新
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
    # - billing_status = 'free' （無料トライアル中）
    # - trial_end_date < now （期限切れ）
    query = select(Billing).where(
        Billing.billing_status == BillingStatus.free,
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
        await crud.billing.update_status(
            db=db,
            billing_id=billing.id,
            status=BillingStatus.past_due
        )

        logger.info(
            f"Trial expired: office_id={billing.office_id}, "
            f"billing_id={billing.id}, "
            f"trial_end_date={billing.trial_end_date}"
        )

        updated_count += 1

    # コミット
    if updated_count > 0:
        await db.commit()
        logger.info(f"Updated {updated_count} expired trials to past_due")

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
