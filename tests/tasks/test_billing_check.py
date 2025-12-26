"""
課金バッチ処理のテスト（TDD）
"""
import pytest
from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.tasks.billing_check import check_trial_expiration, check_scheduled_cancellation
from app import crud
from app.models.enums import BillingStatus


@pytest.mark.asyncio
class TestTrialExpirationCheck:
    """トライアル期間終了チェックのテスト"""

    async def test_expired_trial_updates_to_past_due(
        self,
        db_session,
        office_factory,
        staff_factory
    ):
        """
        トライアル期限切れのBillingがpast_dueに更新される

        Given: trial_end_date が過去 かつ billing_status = 'free'
        When: check_trial_expiration() 実行
        Then: billing_status が 'past_due' に更新される
        """
        # テスト用事務所作成
        office = await office_factory(session=db_session, is_test_data=True)
        await db_session.commit()

        # Billing作成（トライアル期限切れ）
        billing = await crud.billing.create_for_office(
            db=db_session,
            office_id=office.id,
            trial_days=180
        )
        await db_session.commit()

        # trial_end_date を過去に設定（1日前に終了）
        billing.trial_end_date = datetime.now(timezone.utc) - timedelta(days=1)
        billing.billing_status = BillingStatus.free
        await db_session.commit()

        # バッチ処理実行
        expired_count = await check_trial_expiration(db=db_session)

        # 検証
        await db_session.refresh(billing)
        assert billing.billing_status == BillingStatus.past_due
        assert expired_count == 1

    async def test_active_trial_not_updated(
        self,
        db_session,
        office_factory
    ):
        """
        トライアル期間中のBillingは更新されない

        Given: trial_end_date が未来 かつ billing_status = 'free'
        When: check_trial_expiration() 実行
        Then: billing_status は変更されない
        """
        # テスト用事務所作成
        office = await office_factory(session=db_session, is_test_data=True)
        await db_session.commit()

        # Billing作成（トライアル期間中）
        billing = await crud.billing.create_for_office(
            db=db_session,
            office_id=office.id,
            trial_days=180
        )
        await db_session.commit()

        # trial_end_date を未来に設定（残り30日）
        billing.trial_end_date = datetime.now(timezone.utc) + timedelta(days=30)
        billing.billing_status = BillingStatus.free
        await db_session.commit()

        # バッチ処理実行
        expired_count = await check_trial_expiration(db=db_session)

        # 検証
        await db_session.refresh(billing)
        assert billing.billing_status == BillingStatus.free
        assert expired_count == 0

    async def test_early_payment_updates_to_active(
        self,
        db_session,
        office_factory
    ):
        """
        early_payment状態のBillingがトライアル期限切れ時にactiveに更新される

        Given: trial_end_date が過去 かつ billing_status = 'early_payment'
        When: check_trial_expiration() 実行
        Then: billing_status が 'active' に更新される
        """
        # テスト用事務所作成
        office = await office_factory(session=db_session, is_test_data=True)
        await db_session.commit()

        # Billing作成
        billing = await crud.billing.create_for_office(
            db=db_session,
            office_id=office.id,
            trial_days=180
        )
        await db_session.commit()

        # early_payment状態に設定（トライアル期限切れ）
        billing.trial_end_date = datetime.now(timezone.utc) - timedelta(days=1)
        billing.billing_status = BillingStatus.early_payment
        billing.stripe_subscription_id = "sub_test_xxxxx"
        await db_session.commit()

        # バッチ処理実行
        expired_count = await check_trial_expiration(db=db_session)

        # 検証
        await db_session.refresh(billing)
        assert billing.billing_status == BillingStatus.active
        assert expired_count == 1

    async def test_active_billing_not_updated(
        self,
        db_session,
        office_factory
    ):
        """
        active状態のBillingは更新されない

        Given: billing_status = 'active'
        When: check_trial_expiration() 実行
        Then: billing_status は変更されない
        """
        # テスト用事務所作成
        office = await office_factory(session=db_session, is_test_data=True)
        await db_session.commit()

        # Billing作成
        billing = await crud.billing.create_for_office(
            db=db_session,
            office_id=office.id,
            trial_days=180
        )
        await db_session.commit()

        # active状態に設定
        billing.billing_status = BillingStatus.active
        billing.stripe_subscription_id = "sub_test_xxxxx"
        await db_session.commit()

        # バッチ処理実行
        expired_count = await check_trial_expiration(db=db_session)

        # 検証
        await db_session.refresh(billing)
        assert billing.billing_status == BillingStatus.active
        assert expired_count == 0

    async def test_multiple_expired_trials(
        self,
        db_session,
        office_factory
    ):
        """
        複数のトライアル期限切れBillingを一括更新

        Given: 3つのBillingがトライアル期限切れ
        When: check_trial_expiration() 実行
        Then: 3つ全てが past_due に更新される
        """
        # テスト用事務所を3つ作成
        billings = []
        for i in range(3):
            office = await office_factory(session=db_session, is_test_data=True)
            await db_session.commit()

            billing = await crud.billing.create_for_office(
                db=db_session,
                office_id=office.id,
                trial_days=180
            )
            await db_session.commit()

            # trial_end_date を過去に設定
            billing.trial_end_date = datetime.now(timezone.utc) - timedelta(days=i+1)
            billing.billing_status = BillingStatus.free
            billings.append(billing)

        await db_session.commit()

        # バッチ処理実行
        expired_count = await check_trial_expiration(db=db_session)

        # 検証（作成したBillingがすべて past_due に更新されていることを確認）
        assert expired_count >= 3
        for billing in billings:
            await db_session.refresh(billing)
            assert billing.billing_status == BillingStatus.past_due

    async def test_past_due_already_not_updated(
        self,
        db_session,
        office_factory
    ):
        """
        既に past_due 状態のBillingは再度更新されない

        Given: billing_status = 'past_due'
        When: check_trial_expiration() 実行
        Then: billing_status は変更されない（重複処理防止）
        """
        # テスト用事務所作成
        office = await office_factory(session=db_session, is_test_data=True)
        await db_session.commit()

        # Billing作成
        billing = await crud.billing.create_for_office(
            db=db_session,
            office_id=office.id,
            trial_days=180
        )
        await db_session.commit()

        # 既に past_due 状態に設定
        billing.trial_end_date = datetime.now(timezone.utc) - timedelta(days=10)
        billing.billing_status = BillingStatus.past_due
        await db_session.commit()

        # バッチ処理実行
        expired_count = await check_trial_expiration(db=db_session)

        # 検証
        await db_session.refresh(billing)
        assert billing.billing_status == BillingStatus.past_due
        assert expired_count == 0

    async def test_timezone_aware_comparison(
        self,
        db_session,
        office_factory
    ):
        """
        タイムゾーン対応の日時比較が正しく動作する

        Given: trial_end_date がタイムゾーン付きdatetime
        When: check_trial_expiration() 実行
        Then: タイムゾーン考慮した比較が正しく行われる
        """
        # テスト用事務所作成
        office = await office_factory(session=db_session, is_test_data=True)
        await db_session.commit()

        # Billing作成
        billing = await crud.billing.create_for_office(
            db=db_session,
            office_id=office.id,
            trial_days=180
        )
        await db_session.commit()

        # trial_end_date を過去に設定（タイムゾーン付き）
        billing.trial_end_date = datetime.now(timezone.utc) - timedelta(hours=1)
        billing.billing_status = BillingStatus.free
        await db_session.commit()

        # バッチ処理実行（エラーが発生しないこと）
        expired_count = await check_trial_expiration(db=db_session)

        # 検証
        await db_session.refresh(billing)
        assert billing.billing_status == BillingStatus.past_due
        assert expired_count == 1

    async def test_mixed_statuses_batch_update(
        self,
        db_session,
        office_factory
    ):
        """
        free と early_payment が混在する場合の一括更新

        Given:
          - Billing1: free, trial期限切れ
          - Billing2: early_payment, trial期限切れ
        When: check_trial_expiration() 実行
        Then:
          - Billing1: past_due に更新
          - Billing2: active に更新
        """
        # Billing1: free → past_due
        office1 = await office_factory(session=db_session, is_test_data=True)
        await db_session.commit()
        billing1 = await crud.billing.create_for_office(
            db=db_session,
            office_id=office1.id,
            trial_days=180
        )
        await db_session.commit()
        billing1.trial_end_date = datetime.now(timezone.utc) - timedelta(days=1)
        billing1.billing_status = BillingStatus.free

        # Billing2: early_payment → active
        office2 = await office_factory(session=db_session, is_test_data=True)
        await db_session.commit()
        billing2 = await crud.billing.create_for_office(
            db=db_session,
            office_id=office2.id,
            trial_days=180
        )
        await db_session.commit()
        billing2.trial_end_date = datetime.now(timezone.utc) - timedelta(days=2)
        billing2.billing_status = BillingStatus.early_payment
        billing2.stripe_subscription_id = "sub_test_batch"

        await db_session.commit()

        # バッチ処理実行
        expired_count = await check_trial_expiration(db=db_session)

        # 検証
        await db_session.refresh(billing1)
        await db_session.refresh(billing2)
        assert billing1.billing_status == BillingStatus.past_due
        assert billing2.billing_status == BillingStatus.active
        assert expired_count == 2

    async def test_early_payment_during_trial_not_updated(
        self,
        db_session,
        office_factory
    ):
        """
        early_payment状態でトライアル期間中のBillingは更新されない

        Given: trial_end_date が未来 かつ billing_status = 'early_payment'
        When: check_trial_expiration() 実行
        Then: billing_status は変更されない
        """
        # テスト用事務所作成
        office = await office_factory(session=db_session, is_test_data=True)
        await db_session.commit()

        # Billing作成
        billing = await crud.billing.create_for_office(
            db=db_session,
            office_id=office.id,
            trial_days=180
        )
        await db_session.commit()

        # early_payment状態に設定（トライアル期間中）
        billing.trial_end_date = datetime.now(timezone.utc) + timedelta(days=30)
        billing.billing_status = BillingStatus.early_payment
        billing.stripe_subscription_id = "sub_test_active"
        await db_session.commit()

        # バッチ処理実行
        expired_count = await check_trial_expiration(db=db_session)

        # 検証
        await db_session.refresh(billing)
        assert billing.billing_status == BillingStatus.early_payment
        assert expired_count == 0


@pytest.mark.asyncio
class TestScheduledCancellationCheck:
    """スケジュールキャンセル期限チェックのテスト"""

    async def test_expired_scheduled_cancellation_updates_to_canceled(
        self,
        db_session,
        office_factory
    ):
        """
        スケジュールキャンセル期限切れのBillingがcanceledに更新される

        Given: scheduled_cancel_at が過去 かつ billing_status = 'canceling'
        When: check_scheduled_cancellation() 実行
        Then: billing_status が 'canceled' に更新される
        """
        # テスト用事務所作成
        office = await office_factory(session=db_session, is_test_data=True)
        await db_session.commit()

        # Billing作成
        billing = await crud.billing.create_for_office(
            db=db_session,
            office_id=office.id,
            trial_days=180
        )
        await db_session.commit()

        # canceling状態に設定（scheduled_cancel_at が過去）
        billing.billing_status = BillingStatus.canceling
        billing.scheduled_cancel_at = datetime.now(timezone.utc) - timedelta(days=1)
        await db_session.commit()

        # バッチ処理実行
        canceled_count = await check_scheduled_cancellation(db=db_session)

        # 検証
        await db_session.refresh(billing)
        assert billing.billing_status == BillingStatus.canceled
        assert canceled_count == 1

    async def test_active_scheduled_cancellation_not_updated(
        self,
        db_session,
        office_factory
    ):
        """
        scheduled_cancel_at が未来の場合は更新されない

        Given: scheduled_cancel_at が未来 かつ billing_status = 'canceling'
        When: check_scheduled_cancellation() 実行
        Then: billing_status は変更されない
        """
        # テスト用事務所作成
        office = await office_factory(session=db_session, is_test_data=True)
        await db_session.commit()

        # Billing作成
        billing = await crud.billing.create_for_office(
            db=db_session,
            office_id=office.id,
            trial_days=180
        )
        await db_session.commit()

        # canceling状態に設定（scheduled_cancel_at が未来）
        billing.billing_status = BillingStatus.canceling
        billing.scheduled_cancel_at = datetime.now(timezone.utc) + timedelta(days=30)
        await db_session.commit()

        # バッチ処理実行
        canceled_count = await check_scheduled_cancellation(db=db_session)

        # 検証
        await db_session.refresh(billing)
        assert billing.billing_status == BillingStatus.canceling
        assert canceled_count == 0

    async def test_canceling_without_scheduled_date_not_updated(
        self,
        db_session,
        office_factory
    ):
        """
        scheduled_cancel_at が None の場合は更新されない

        Given: scheduled_cancel_at = None かつ billing_status = 'canceling'
        When: check_scheduled_cancellation() 実行
        Then: billing_status は変更されない
        """
        # テスト用事務所作成
        office = await office_factory(session=db_session, is_test_data=True)
        await db_session.commit()

        # Billing作成
        billing = await crud.billing.create_for_office(
            db=db_session,
            office_id=office.id,
            trial_days=180
        )
        await db_session.commit()

        # canceling状態に設定（scheduled_cancel_at = None）
        billing.billing_status = BillingStatus.canceling
        billing.scheduled_cancel_at = None
        await db_session.commit()

        # バッチ処理実行
        canceled_count = await check_scheduled_cancellation(db=db_session)

        # 検証
        await db_session.refresh(billing)
        assert billing.billing_status == BillingStatus.canceling
        assert canceled_count == 0

    async def test_other_statuses_not_updated(
        self,
        db_session,
        office_factory
    ):
        """
        canceling 以外のステータスは更新されない

        Given: billing_status = 'active', 'free', 'past_due' など
        When: check_scheduled_cancellation() 実行
        Then: billing_status は変更されない
        """
        # テスト用事務所作成
        office = await office_factory(session=db_session, is_test_data=True)
        await db_session.commit()

        # Billing作成
        billing = await crud.billing.create_for_office(
            db=db_session,
            office_id=office.id,
            trial_days=180
        )
        await db_session.commit()

        # active状態に設定（scheduled_cancel_at が過去でも更新されない）
        billing.billing_status = BillingStatus.active
        billing.scheduled_cancel_at = datetime.now(timezone.utc) - timedelta(days=1)
        await db_session.commit()

        # バッチ処理実行
        canceled_count = await check_scheduled_cancellation(db=db_session)

        # 検証
        await db_session.refresh(billing)
        assert billing.billing_status == BillingStatus.active
        assert canceled_count == 0

    async def test_multiple_expired_scheduled_cancellations(
        self,
        db_session,
        office_factory
    ):
        """
        複数のスケジュールキャンセル期限切れを一括更新

        Given: 3つのBillingがスケジュールキャンセル期限切れ
        When: check_scheduled_cancellation() 実行
        Then: 3つ全てが canceled に更新される
        """
        # テスト用事務所を3つ作成
        billings = []
        for i in range(3):
            office = await office_factory(session=db_session, is_test_data=True)
            await db_session.commit()

            billing = await crud.billing.create_for_office(
                db=db_session,
                office_id=office.id,
                trial_days=180
            )
            await db_session.commit()

            # canceling状態に設定（scheduled_cancel_at が過去）
            billing.billing_status = BillingStatus.canceling
            billing.scheduled_cancel_at = datetime.now(timezone.utc) - timedelta(days=i+1)
            billings.append(billing)

        await db_session.commit()

        # バッチ処理実行
        canceled_count = await check_scheduled_cancellation(db=db_session)

        # 検証
        assert canceled_count == 3
        for billing in billings:
            await db_session.refresh(billing)
            assert billing.billing_status == BillingStatus.canceled

    async def test_webhook_fallback_scenario(
        self,
        db_session,
        office_factory
    ):
        """
        Webhook失敗シナリオ: バッチ処理がフォールバックとして機能する

        Given:
          - scheduled_cancel_at が25時間前（Webhookが失敗したと想定）
          - billing_status = 'canceling' のまま
        When: check_scheduled_cancellation() 実行
        Then: billing_status が 'canceled' に更新される
        """
        # テスト用事務所作成
        office = await office_factory(session=db_session, is_test_data=True)
        await db_session.commit()

        # Billing作成
        billing = await crud.billing.create_for_office(
            db=db_session,
            office_id=office.id,
            trial_days=180
        )
        await db_session.commit()

        # Webhook失敗を想定（25時間前に期限切れ）
        billing.billing_status = BillingStatus.canceling
        billing.scheduled_cancel_at = datetime.now(timezone.utc) - timedelta(hours=25)
        await db_session.commit()

        # バッチ処理実行（フォールバック）
        canceled_count = await check_scheduled_cancellation(db=db_session)

        # 検証
        await db_session.refresh(billing)
        assert billing.billing_status == BillingStatus.canceled
        assert canceled_count == 1

    async def test_timezone_aware_comparison(
        self,
        db_session,
        office_factory
    ):
        """
        タイムゾーン対応の日時比較が正しく動作する

        Given: scheduled_cancel_at がタイムゾーン付きdatetime
        When: check_scheduled_cancellation() 実行
        Then: タイムゾーン考慮した比較が正しく行われる
        """
        # テスト用事務所作成
        office = await office_factory(session=db_session, is_test_data=True)
        await db_session.commit()

        # Billing作成
        billing = await crud.billing.create_for_office(
            db=db_session,
            office_id=office.id,
            trial_days=180
        )
        await db_session.commit()

        # scheduled_cancel_at を過去に設定（タイムゾーン付き）
        billing.billing_status = BillingStatus.canceling
        billing.scheduled_cancel_at = datetime.now(timezone.utc) - timedelta(hours=1)
        await db_session.commit()

        # バッチ処理実行（エラーが発生しないこと）
        canceled_count = await check_scheduled_cancellation(db=db_session)

        # 検証
        await db_session.refresh(billing)
        assert billing.billing_status == BillingStatus.canceled
        assert canceled_count == 1
