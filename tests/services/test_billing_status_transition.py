from datetime import datetime, timedelta, timezone

from app.models.enums import BillingStatus
from app.services.billing.status_transition import BillingStatusTransitionService


def test_normalize_trial_end_date_treats_naive_datetime_as_utc():
    service = BillingStatusTransitionService()
    naive_trial_end = datetime(2026, 1, 1, 9, 0, 0)

    normalized = service.normalize_trial_end_date(naive_trial_end)

    assert normalized == datetime(2026, 1, 1, 9, 0, 0, tzinfo=timezone.utc)


def test_subscription_created_status_is_early_payment_during_trial():
    service = BillingStatusTransitionService()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    result = service.determine_subscription_created_status(
        trial_end_date=now + timedelta(days=1),
        now=now,
    )

    assert result.status == BillingStatus.early_payment
    assert result.is_trial_active is True


def test_subscription_created_status_is_active_after_trial_or_without_trial_end():
    service = BillingStatusTransitionService()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    expired_result = service.determine_subscription_created_status(
        trial_end_date=now - timedelta(seconds=1),
        now=now,
    )
    no_trial_end_result = service.determine_subscription_created_status(
        trial_end_date=None,
        now=now,
    )

    assert expired_result.status == BillingStatus.active
    assert expired_result.is_trial_active is False
    assert no_trial_end_result.status == BillingStatus.active
    assert no_trial_end_result.is_trial_active is False


def test_payment_failed_during_trial_keeps_current_status():
    service = BillingStatusTransitionService()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    assert (
        service.determine_payment_failed_status(
            trial_end_date=now + timedelta(days=1),
            now=now,
        )
        is None
    )


def test_payment_failed_after_trial_sets_payment_failed():
    service = BillingStatusTransitionService()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    assert service.determine_payment_failed_status(
        trial_end_date=now - timedelta(seconds=1),
        now=now,
    ) == BillingStatus.payment_failed
    assert service.determine_payment_failed_status(
        trial_end_date=None,
        now=now,
    ) == BillingStatus.payment_failed


def test_trial_expiration_status_transition_rules_are_centralized():
    service = BillingStatusTransitionService()

    assert service.determine_trial_expiration_status(
        current_status=BillingStatus.free,
    ) == BillingStatus.trial_expired
    assert service.determine_trial_expiration_status(
        current_status=BillingStatus.early_payment,
    ) == BillingStatus.active

    for status in [
        BillingStatus.active,
        BillingStatus.past_due,
        BillingStatus.trial_expired,
        BillingStatus.payment_failed,
        BillingStatus.canceling,
        BillingStatus.canceled,
    ]:
        assert service.determine_trial_expiration_status(
            current_status=status,
        ) is None


def test_scheduled_cancellation_status_transition_rules_are_centralized():
    service = BillingStatusTransitionService()

    assert service.determine_scheduled_cancellation_status(
        current_status=BillingStatus.canceling,
    ) == BillingStatus.canceled

    for status in [
        BillingStatus.free,
        BillingStatus.early_payment,
        BillingStatus.active,
        BillingStatus.past_due,
        BillingStatus.trial_expired,
        BillingStatus.payment_failed,
        BillingStatus.canceled,
    ]:
        assert service.determine_scheduled_cancellation_status(
            current_status=status,
        ) is None


def test_trial_expired_cancel_signal_cancels_immediately():
    service = BillingStatusTransitionService()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    assert service.should_cancel_trial_expired_immediately(
        billing_status=BillingStatus.trial_expired,
        trial_end_date=now - timedelta(days=1),
        last_payment_date=None,
        subscription_start_date=None,
        cancel_at_period_end=True,
        cancel_at=None,
        now=now,
    )


def test_stale_unpaid_expired_trial_cancel_signal_cancels_immediately():
    service = BillingStatusTransitionService()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    for status in [BillingStatus.free, BillingStatus.canceling]:
        assert service.should_cancel_trial_expired_immediately(
            billing_status=status,
            trial_end_date=now - timedelta(days=1),
            last_payment_date=None,
            subscription_start_date=None,
            cancel_at_period_end=False,
            cancel_at=int((now + timedelta(days=30)).timestamp()),
            now=now,
        )


def test_active_billing_cancel_signal_does_not_cancel_immediately():
    service = BillingStatusTransitionService()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    assert not service.should_cancel_trial_expired_immediately(
        billing_status=BillingStatus.active,
        trial_end_date=now - timedelta(days=1),
        last_payment_date=now - timedelta(days=10),
        subscription_start_date=now - timedelta(days=30),
        cancel_at_period_end=True,
        cancel_at=None,
        now=now,
    )


def test_canceling_restore_status_uses_trial_and_subscription_state():
    service = BillingStatusTransitionService()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    assert service.determine_canceling_restore_status(
        trial_end_date=now + timedelta(days=1),
        has_subscription=True,
        now=now,
    ) == BillingStatus.early_payment
    assert service.determine_canceling_restore_status(
        trial_end_date=now + timedelta(days=1),
        has_subscription=False,
        now=now,
    ) == BillingStatus.free
    assert service.determine_canceling_restore_status(
        trial_end_date=now - timedelta(seconds=1),
        has_subscription=True,
        now=now,
    ) == BillingStatus.active


def test_subscription_deleted_preserves_recent_payment_failed_status():
    service = BillingStatusTransitionService()

    assert service.determine_subscription_deleted_status(
        has_recent_payment_failed=True,
    ) == BillingStatus.payment_failed
    assert service.determine_subscription_deleted_status(
        has_recent_payment_failed=False,
    ) == BillingStatus.canceled
