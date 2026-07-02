from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from app.models.enums import BillingStatus


@dataclass(frozen=True)
class SubscriptionCreatedStatusDecision:
    status: BillingStatus
    is_trial_active: bool


class BillingStatusTransitionService:
    """Billing status transition rules without DB or Stripe side effects."""

    def normalize_trial_end_date(
        self,
        trial_end_date: Optional[datetime],
    ) -> Optional[datetime]:
        if not trial_end_date:
            return None

        if trial_end_date.tzinfo is not None:
            return trial_end_date

        return trial_end_date.replace(tzinfo=timezone.utc)

    def is_trial_active(
        self,
        *,
        trial_end_date: Optional[datetime],
        now: datetime,
    ) -> bool:
        normalized_trial_end_date = self.normalize_trial_end_date(trial_end_date)
        normalized_now = self.normalize_trial_end_date(now)

        return bool(
            normalized_trial_end_date
            and normalized_now
            and normalized_trial_end_date > normalized_now
        )

    def determine_subscription_created_status(
        self,
        *,
        trial_end_date: Optional[datetime],
        now: datetime,
    ) -> SubscriptionCreatedStatusDecision:
        is_trial_active = self.is_trial_active(
            trial_end_date=trial_end_date,
            now=now,
        )

        return SubscriptionCreatedStatusDecision(
            status=(
                BillingStatus.early_payment
                if is_trial_active
                else BillingStatus.active
            ),
            is_trial_active=is_trial_active,
        )

    def determine_payment_failed_status(
        self,
        *,
        trial_end_date: Optional[datetime],
        now: datetime,
    ) -> Optional[BillingStatus]:
        if self.is_trial_active(trial_end_date=trial_end_date, now=now):
            return None

        return BillingStatus.payment_failed

    def determine_trial_expiration_status(
        self,
        *,
        current_status: BillingStatus,
    ) -> Optional[BillingStatus]:
        if current_status == BillingStatus.free:
            return BillingStatus.trial_expired

        if current_status == BillingStatus.early_payment:
            return BillingStatus.active

        return None

    def determine_scheduled_cancellation_status(
        self,
        *,
        current_status: BillingStatus,
    ) -> Optional[BillingStatus]:
        if current_status == BillingStatus.canceling:
            return BillingStatus.canceled

        return None

    def should_cancel_trial_expired_immediately(
        self,
        *,
        billing_status: BillingStatus,
        trial_end_date: Optional[datetime],
        last_payment_date: Optional[datetime],
        subscription_start_date: Optional[datetime],
        cancel_at_period_end: bool,
        cancel_at: Optional[int],
        now: datetime,
    ) -> bool:
        has_cancel_signal = bool(cancel_at_period_end or cancel_at)
        if not has_cancel_signal:
            return False

        if billing_status == BillingStatus.trial_expired:
            return True

        return self.is_stale_unpaid_expired_trial(
            billing_status=billing_status,
            trial_end_date=trial_end_date,
            last_payment_date=last_payment_date,
            subscription_start_date=subscription_start_date,
            now=now,
        )

    def is_stale_unpaid_expired_trial(
        self,
        *,
        billing_status: BillingStatus,
        trial_end_date: Optional[datetime],
        last_payment_date: Optional[datetime],
        subscription_start_date: Optional[datetime],
        now: datetime,
    ) -> bool:
        normalized_trial_end_date = self.normalize_trial_end_date(trial_end_date)
        normalized_now = self.normalize_trial_end_date(now)

        return (
            billing_status in [BillingStatus.free, BillingStatus.canceling]
            and normalized_trial_end_date is not None
            and normalized_now is not None
            and normalized_trial_end_date < normalized_now
            and last_payment_date is None
            and subscription_start_date is None
        )

    def determine_canceling_restore_status(
        self,
        *,
        trial_end_date: Optional[datetime],
        has_subscription: bool,
        now: datetime,
    ) -> BillingStatus:
        is_in_trial = self.is_trial_active(
            trial_end_date=trial_end_date,
            now=now,
        )

        if is_in_trial and has_subscription:
            return BillingStatus.early_payment

        if is_in_trial and not has_subscription:
            return BillingStatus.free

        return BillingStatus.active

    def determine_subscription_deleted_status(
        self,
        *,
        has_recent_payment_failed: bool,
    ) -> BillingStatus:
        if has_recent_payment_failed:
            return BillingStatus.payment_failed

        return BillingStatus.canceled
