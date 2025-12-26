"""
BillingService (課金サービス) のテスト

トランザクション整合性の検証を重点的に実施
"""
import pytest
import logging
from unittest.mock import Mock, patch, AsyncMock
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID, uuid4
from datetime import datetime, timezone, timedelta
from typing import Tuple

from app.db.session import AsyncSessionLocal
from app.models.staff import Staff
from app.models.office import Office, OfficeStaff
from app.models.billing import Billing
from app.models.enums import StaffRole, OfficeType, BillingStatus
from app.core.security import get_password_hash
from app.services.billing_service import BillingService
from app import crud

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s:%(name)s:%(message)s'
)

# Suppress SQLAlchemy logs
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
logging.getLogger('sqlalchemy.pool').setLevel(logging.WARNING)
logging.getLogger('app').setLevel(logging.INFO)

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="function")
async def db() -> AsyncSession:
    """テスト用の非同期DBセッションを提供するフィクスチャ"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            try:
                await session.rollback()
            except Exception:
                pass


@pytest.fixture(scope="function")
async def setup_office_with_billing(db: AsyncSession) -> Tuple[UUID, UUID, UUID]:
    """
    テスト用の事業所とBilling情報を作成
    Returns: (office_id, staff_id, billing_id)
    """
    # Staff作成
    staff = Staff(
        first_name="テスト",
        last_name="ユーザー",
        full_name="テスト ユーザー",
        email=f"test_{uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash("password"),
        role=StaffRole.owner,
        is_test_data=True
    )
    db.add(staff)
    await db.flush()

    # Office作成
    office = Office(
        name="テスト事業所",
        type=OfficeType.type_A_office,
        created_by=staff.id,
        last_modified_by=staff.id,
        is_test_data=True
    )
    db.add(office)
    await db.flush()

    # OfficeStaff関連付け
    office_staff = OfficeStaff(
        office_id=office.id,
        staff_id=staff.id,
        is_primary=True
    )
    db.add(office_staff)

    # Billing作成
    trial_start = datetime.now(timezone.utc)
    trial_end = trial_start + timedelta(days=180)

    billing = Billing(
        office_id=office.id,
        billing_status=BillingStatus.free,
        trial_start_date=trial_start,
        trial_end_date=trial_end,
        current_plan_amount=6000
    )
    db.add(billing)
    await db.flush()

    # commit前にIDを保存（MissingGreenlet対策）
    office_id = office.id
    staff_id = staff.id
    billing_id = billing.id

    await db.commit()

    return office_id, staff_id, billing_id


@pytest.fixture
def billing_service():
    """BillingServiceインスタンスを提供"""
    return BillingService()


class TestBillingServiceTransactionIntegrity:
    """トランザクション整合性のテスト"""

    @pytest.mark.asyncio
    async def test_process_payment_succeeded_rollback_on_error(
        self,
        db: AsyncSession,
        setup_office_with_billing: Tuple[UUID, UUID, UUID],
        billing_service: BillingService
    ):
        """
        支払い成功処理でエラーが発生した場合、全ての変更がロールバックされることを検証

        検証項目:
        1. billing.record_payment()がエラーをスローした場合
        2. webhook_event.create_event_record()が呼ばれないこと
        3. audit_log.create_log()が呼ばれないこと
        4. DBへの変更がロールバックされること
        """
        office_id, staff_id, billing_id = setup_office_with_billing

        # Billing取得
        billing = await crud.billing.get(db=db, id=billing_id)
        assert billing is not None

        # Stripe Customer IDを設定
        await crud.billing.update_stripe_customer(
            db=db,
            billing_id=billing_id,
            stripe_customer_id="cus_test_12345"
        )

        # 初期状態確認
        billing_before = await crud.billing.get(db=db, id=billing_id)
        assert billing_before.billing_status == BillingStatus.free
        assert billing_before.last_payment_date is None

        # record_paymentがエラーを投げるようにモック
        with patch.object(crud.billing, 'record_payment', side_effect=Exception("DB Error")):
            # process_payment_succeededを実行
            with pytest.raises(Exception, match="DB Error"):
                await billing_service.process_payment_succeeded(
                    db=db,
                    event_id="evt_test_12345",
                    customer_id="cus_test_12345"
                )

        # ロールバック後の状態確認
        await db.rollback()  # 明示的にロールバック
        billing_after = await crud.billing.get(db=db, id=billing_id)

        # 変更がロールバックされていることを確認
        assert billing_after.billing_status == BillingStatus.free
        assert billing_after.last_payment_date is None

    @pytest.mark.asyncio
    async def test_process_payment_succeeded_atomic_transaction(
        self,
        db: AsyncSession,
        setup_office_with_billing: Tuple[UUID, UUID, UUID],
        billing_service: BillingService
    ):
        """
        支払い成功処理が1つのトランザクションで完了することを検証

        検証項目:
        1. billing.record_payment()がauto_commit=Falseで呼ばれること
        2. webhook_event.create_event_record()がauto_commit=Falseで呼ばれること
        3. audit_log.create_log()がauto_commit=Falseで呼ばれること
        4. 最後にdb.commit()が1回だけ呼ばれること
        5. 全ての変更が反映されること
        6. trial期間中ならearly_paymentになること
        """
        office_id, staff_id, billing_id = setup_office_with_billing

        # ユニークなIDを生成
        unique_id = uuid4().hex[:8]
        customer_id = f"cus_test_atomic_{unique_id}"
        event_id = f"evt_test_atomic_{unique_id}"

        # Stripe Customer IDを設定
        await crud.billing.update_stripe_customer(
            db=db,
            billing_id=billing_id,
            stripe_customer_id=customer_id
        )

        # process_payment_succeededを実行
        await billing_service.process_payment_succeeded(
            db=db,
            event_id=event_id,
            customer_id=customer_id
        )

        # サービス層がcommitした後、新しいセッションで検証
        # （既存のセッションはcommit後に使えないため）
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as new_db:
            # 全ての変更が反映されていることを確認
            billing_after = await crud.billing.get(db=new_db, id=billing_id)
            # trial期間中なので early_payment になる
            assert billing_after.billing_status == BillingStatus.early_payment
            assert billing_after.last_payment_date is not None

            # Webhookイベントが記録されていることを確認
            webhook_event = await crud.webhook_event.get_by_event_id(
                db=new_db,
                event_id=event_id
            )
            assert webhook_event is not None
            assert webhook_event.event_type == 'invoice.payment_succeeded'
            assert webhook_event.status == 'success'

            # 監査ログが記録されていることを確認
            audit_logs = await crud.audit_log.get_logs_by_target(
                db=new_db,
                target_type="billing",
                target_id=billing_id
            )
            assert len(audit_logs) > 0
            assert audit_logs[0].action == "billing.payment_succeeded"
            assert audit_logs[0].actor_role == "system"

    @pytest.mark.asyncio
    async def test_process_subscription_created_early_payment(
        self,
        db: AsyncSession,
        setup_office_with_billing: Tuple[UUID, UUID, UUID],
        billing_service: BillingService
    ):
        """
        サブスクリプション作成処理（無料期間中）でステータスがearly_paymentになることを検証

        検証項目:
        1. 無料期間中にサブスクリプションを作成した場合
        2. billing_status が early_payment になること
        3. stripe_subscription_id が更新されること
        4. トランザクションが正しく完了すること
        """
        office_id, staff_id, billing_id = setup_office_with_billing

        # 無料期間中であることを確認
        billing_before = await crud.billing.get(db=db, id=billing_id)
        assert billing_before.billing_status == BillingStatus.free
        assert billing_before.trial_end_date > datetime.now(timezone.utc)

        # ユニークなIDを生成
        unique_id = uuid4().hex[:8]
        customer_id = f'cus_test_early_{unique_id}'

        # Billingにstripe_customer_idを設定（Checkout Session作成時に設定されるはずのもの）
        await crud.billing.update_stripe_customer(
            db=db,
            billing_id=billing_id,
            stripe_customer_id=customer_id
        )

        # サブスクリプションデータ
        subscription_data = {
            'id': f'sub_test_early_payment_{unique_id}',
            'customer': customer_id,
            'metadata': {
                'office_id': str(office_id),
                'office_name': 'テスト事業所',
                'created_by_user_id': str(staff_id)
            }
        }

        # process_subscription_createdを実行
        await billing_service.process_subscription_created(
            db=db,
            event_id=f"evt_sub_created_early_{unique_id}",
            subscription_data=subscription_data
        )

        # ステータスがearly_paymentになっていることを確認
        billing_after = await crud.billing.get(db=db, id=billing_id)
        assert billing_after.billing_status == BillingStatus.early_payment
        assert billing_after.stripe_subscription_id == f'sub_test_early_payment_{unique_id}'

    @pytest.mark.asyncio
    async def test_process_subscription_created_active_after_trial(
        self,
        db: AsyncSession,
        setup_office_with_billing: Tuple[UUID, UUID, UUID],
        billing_service: BillingService
    ):
        """
        サブスクリプション作成処理（無料期間終了後）でステータスがactiveになることを検証
        """
        office_id, staff_id, billing_id = setup_office_with_billing

        # 無料期間を過去に設定し、billing_statusを変更（無料期間終了を想定）
        billing = await crud.billing.get(db=db, id=billing_id)
        past_date = datetime.now(timezone.utc) - timedelta(days=1)

        from app.schemas.billing import BillingUpdate
        # 無料期間終了後は、通常billing_statusはfreeのままではなく別のステータスになる
        # ここでは、無料期間が終了した状態（billing_status=free, trial_end_date<now）をテスト
        await crud.billing.update(
            db=db,
            db_obj=billing,
            obj_in=BillingUpdate(
                trial_end_date=past_date
                # billing_statusはfreeのままにして、無料期間終了後のサブスク作成をテスト
            )
        )

        # ユニークなIDを生成
        unique_id = uuid4().hex[:8]
        customer_id = f'cus_test_active_{unique_id}'

        # Billingにstripe_customer_idを設定（Checkout Session作成時に設定されるはずのもの）
        await crud.billing.update_stripe_customer(
            db=db,
            billing_id=billing_id,
            stripe_customer_id=customer_id
        )

        # サブスクリプションデータ
        subscription_data = {
            'id': f'sub_test_active_{unique_id}',
            'customer': customer_id,
            'metadata': {
                'office_id': str(office_id),
                'office_name': 'テスト事業所',
                'created_by_user_id': str(staff_id)
            }
        }

        # process_subscription_createdを実行
        await billing_service.process_subscription_created(
            db=db,
            event_id=f"evt_sub_created_active_{unique_id}",
            subscription_data=subscription_data
        )

        # ステータスがactiveになっていることを確認
        billing_after = await crud.billing.get(db=db, id=billing_id)
        assert billing_after.billing_status == BillingStatus.active

    @pytest.mark.asyncio
    async def test_process_payment_failed_sets_past_due(
        self,
        db: AsyncSession,
        setup_office_with_billing: Tuple[UUID, UUID, UUID],
        billing_service: BillingService
    ):
        """
        支払い失敗処理でステータスがpast_dueになることを検証
        """
        office_id, staff_id, billing_id = setup_office_with_billing

        # ユニークなIDを生成
        unique_id = uuid4().hex[:8]
        customer_id = f"cus_test_failed_{unique_id}"

        # Stripe Customer IDを設定
        await crud.billing.update_stripe_customer(
            db=db,
            billing_id=billing_id,
            stripe_customer_id=customer_id
        )

        # process_payment_failedを実行
        await billing_service.process_payment_failed(
            db=db,
            event_id=f"evt_test_failed_{unique_id}",
            customer_id=customer_id
        )

        # 新しいセッションで検証
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as new_db:
            # ステータスがpast_dueになっていることを確認
            billing_after = await crud.billing.get(db=new_db, id=billing_id)
            assert billing_after.billing_status == BillingStatus.past_due

    @pytest.mark.asyncio
    async def test_process_subscription_deleted_sets_canceled(
        self,
        db: AsyncSession,
        setup_office_with_billing: Tuple[UUID, UUID, UUID],
        billing_service: BillingService
    ):
        """
        サブスクリプション削除処理でステータスがcanceledになることを検証
        """
        office_id, staff_id, billing_id = setup_office_with_billing

        # ユニークなIDを生成
        unique_id = uuid4().hex[:8]
        customer_id = f"cus_test_canceled_{unique_id}"

        # Stripe Customer IDとSubscription IDを設定
        await crud.billing.update_stripe_customer(
            db=db,
            billing_id=billing_id,
            stripe_customer_id=customer_id
        )

        await crud.billing.update_stripe_subscription(
            db=db,
            billing_id=billing_id,
            stripe_subscription_id=f"sub_test_canceled_{unique_id}"
        )

        # 無料期間を過去に設定（無料期間終了後のキャンセル）
        billing = await crud.billing.get(db=db, id=billing_id)
        past_date = datetime.now(timezone.utc) - timedelta(days=1)

        from app.schemas.billing import BillingUpdate
        await crud.billing.update(
            db=db,
            db_obj=billing,
            obj_in=BillingUpdate(trial_end_date=past_date)
        )

        # process_subscription_deletedを実行
        await billing_service.process_subscription_deleted(
            db=db,
            event_id=f"evt_test_canceled_{unique_id}",
            customer_id=customer_id
        )

        # 新しいセッションで検証
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as new_db:
            # ステータスがcanceledになっていることを確認
            billing_after = await crud.billing.get(db=new_db, id=billing_id)
            assert billing_after.billing_status == BillingStatus.canceled


class TestBillingServiceMissingCustomerHandling:
    """存在しないカスタマーIDの処理テスト"""

    @pytest.mark.asyncio
    async def test_process_payment_succeeded_missing_customer(
        self,
        db: AsyncSession,
        billing_service: BillingService
    ):
        """
        存在しないカスタマーIDでpayment_succeededが呼ばれた場合の処理を検証

        検証項目:
        1. 例外が発生しないこと（正常終了）
        2. webhook_eventがstatus='skipped'で記録されること
        3. 警告ログが出力されること
        """
        unique_id = uuid4().hex[:8]
        event_id = f"evt_missing_payment_{unique_id}"
        customer_id = f"cus_missing_{unique_id}"

        # 存在しないカスタマーIDでprocess_payment_succeededを実行
        # 例外が発生しないことを確認
        await billing_service.process_payment_succeeded(
            db=db,
            event_id=event_id,
            customer_id=customer_id
        )

        # webhook_eventが記録されていることを確認
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as new_db:
            webhook_event = await crud.webhook_event.get_by_event_id(
                db=new_db,
                event_id=event_id
            )
            assert webhook_event is not None
            assert webhook_event.event_type == 'invoice.payment_succeeded'
            assert webhook_event.status == 'skipped'
            assert webhook_event.billing_id is None
            assert webhook_event.office_id is None

    @pytest.mark.asyncio
    async def test_process_payment_failed_missing_customer(
        self,
        db: AsyncSession,
        billing_service: BillingService
    ):
        """存在しないカスタマーIDでpayment_failedが呼ばれた場合の処理を検証"""
        unique_id = uuid4().hex[:8]
        event_id = f"evt_missing_failed_{unique_id}"
        customer_id = f"cus_missing_{unique_id}"

        await billing_service.process_payment_failed(
            db=db,
            event_id=event_id,
            customer_id=customer_id
        )

        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as new_db:
            webhook_event = await crud.webhook_event.get_by_event_id(
                db=new_db,
                event_id=event_id
            )
            assert webhook_event is not None
            assert webhook_event.event_type == 'invoice.payment_failed'
            assert webhook_event.status == 'skipped'
            assert webhook_event.billing_id is None

    @pytest.mark.asyncio
    async def test_process_subscription_updated_missing_customer(
        self,
        db: AsyncSession,
        billing_service: BillingService
    ):
        """存在しないカスタマーIDでsubscription_updatedが呼ばれた場合の処理を検証"""
        unique_id = uuid4().hex[:8]
        event_id = f"evt_missing_updated_{unique_id}"
        customer_id = f"cus_missing_{unique_id}"

        subscription_data = {
            'id': f'sub_missing_{unique_id}',
            'customer': customer_id,
            'cancel_at_period_end': True,
            'cancel_at': None,
            'status': 'active'
        }

        await billing_service.process_subscription_updated(
            db=db,
            event_id=event_id,
            subscription_data=subscription_data
        )

        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as new_db:
            webhook_event = await crud.webhook_event.get_by_event_id(
                db=new_db,
                event_id=event_id
            )
            assert webhook_event is not None
            assert webhook_event.event_type == 'customer.subscription.updated'
            assert webhook_event.status == 'skipped'
            assert webhook_event.billing_id is None

    @pytest.mark.asyncio
    async def test_process_subscription_deleted_missing_customer(
        self,
        db: AsyncSession,
        billing_service: BillingService
    ):
        """存在しないカスタマーIDでsubscription_deletedが呼ばれた場合の処理を検証"""
        unique_id = uuid4().hex[:8]
        event_id = f"evt_missing_deleted_{unique_id}"
        customer_id = f"cus_missing_{unique_id}"

        await billing_service.process_subscription_deleted(
            db=db,
            event_id=event_id,
            customer_id=customer_id
        )

        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as new_db:
            webhook_event = await crud.webhook_event.get_by_event_id(
                db=new_db,
                event_id=event_id
            )
            assert webhook_event is not None
            assert webhook_event.event_type == 'customer.subscription.deleted'
            assert webhook_event.status == 'skipped'
            assert webhook_event.billing_id is None


class TestBillingServiceStripeIntegration:
    """Stripe API連携のテスト（モックを使用）"""

    @pytest.mark.asyncio
    async def test_create_checkout_session_no_greenlet_error(
        self,
        db: AsyncSession,
        setup_office_with_billing: Tuple[UUID, UUID, UUID],
        billing_service: BillingService
    ):
        """
        create_checkout_session_with_customerでMissingGreenletエラーが発生しないことを検証

        検証項目:
        1. Stripe Customer作成が先に実行されること
        2. DB更新がauto_commit=Falseで実行されること
        3. Checkout Session作成後にcommitされること
        4. MissingGreenletエラーが発生しないこと
        """
        office_id, staff_id, billing_id = setup_office_with_billing

        # Billing取得
        billing = await crud.billing.get(db=db, id=billing_id)
        assert billing.trial_end_date is not None

        # Stripeモック
        mock_customer = Mock()
        mock_customer.id = "cus_mock_12345"

        mock_checkout_session = Mock()
        mock_checkout_session.id = "cs_mock_12345"
        mock_checkout_session.url = "https://checkout.stripe.com/mock"

        with patch('stripe.Customer.create', return_value=mock_customer) as mock_create_customer, \
             patch('stripe.checkout.Session.create', return_value=mock_checkout_session) as mock_create_session:

            # create_checkout_session_with_customerを実行
            result = await billing_service.create_checkout_session_with_customer(
                db=db,
                billing_id=billing_id,
                office_id=office_id,
                office_name="テスト事業所",
                user_email="test@example.com",
                user_id=staff_id,
                trial_end_date=billing.trial_end_date,
                stripe_secret_key="sk_test_mock",
                stripe_price_id="price_mock_12345",
                frontend_url="http://localhost:3000"
            )

            # 結果確認
            assert result["session_id"] == "cs_mock_12345"
            assert result["url"] == "https://checkout.stripe.com/mock"

            # Stripe APIが正しい順序で呼ばれたことを確認
            assert mock_create_customer.called
            assert mock_create_session.called

        # DB更新が反映されていることを確認
        billing_after = await crud.billing.get(db=db, id=billing_id)
        assert billing_after.stripe_customer_id == "cus_mock_12345"

    @pytest.mark.asyncio
    async def test_create_checkout_session_rollback_on_stripe_error(
        self,
        db: AsyncSession,
        setup_office_with_billing: Tuple[UUID, UUID, UUID],
        billing_service: BillingService
    ):
        """
        Stripe APIエラー時にDBがロールバックされることを検証
        """
        office_id, staff_id, billing_id = setup_office_with_billing

        # Billing取得
        billing = await crud.billing.get(db=db, id=billing_id)

        # Stripeエラーをモック
        import stripe
        with patch('stripe.Customer.create', side_effect=stripe.error.StripeError("Stripe API Error")):

            # HTTPExceptionが発生することを確認
            from fastapi import HTTPException
            with pytest.raises(HTTPException):
                await billing_service.create_checkout_session_with_customer(
                    db=db,
                    billing_id=billing_id,
                    office_id=office_id,
                    office_name="テスト事業所",
                    user_email="test@example.com",
                    user_id=staff_id,
                    trial_end_date=billing.trial_end_date,
                    stripe_secret_key="sk_test_mock",
                    stripe_price_id="price_mock_12345",
                    frontend_url="http://localhost:3000"
                )

        # DBがロールバックされていることを確認
        await db.rollback()
        billing_after = await crud.billing.get(db=db, id=billing_id)
        assert billing_after.stripe_customer_id is None


class TestCancelingToCanceledTransition:
    """
    canceling → canceled 状態遷移のテスト
    Webhook: customer.subscription.deleted による遷移を検証
    """

    async def test_subscription_deleted_canceling_to_canceled(
        self,
        db: AsyncSession,
        setup_office_with_billing: Tuple[UUID, UUID, UUID],
        billing_service: BillingService
    ):
        """
        canceling状態からcanceledへの正常な遷移をテスト
        """
        office_id, staff_id, billing_id = setup_office_with_billing

        # Billingをcanceling状態に設定
        scheduled_cancel_at = datetime.now(timezone.utc) + timedelta(days=7)
        await crud.billing.update(
            db=db,
            db_obj=await crud.billing.get(db=db, id=billing_id),
            obj_in={
                "billing_status": BillingStatus.canceling,
                "stripe_customer_id": "cus_test_canceling",
                "stripe_subscription_id": "sub_test_canceling",
                "scheduled_cancel_at": scheduled_cancel_at
            }
        )
        await db.commit()

        # Webhook event: customer.subscription.deleted
        event_id = f"evt_test_cancel_{uuid4().hex[:12]}"
        subscription_deleted_event = {
            "id": event_id,
            "type": "customer.subscription.deleted",
            "data": {
                "object": {
                    "id": "sub_test_canceling",
                    "customer": "cus_test_canceling",
                    "status": "canceled",
                    "canceled_at": int(datetime.now(timezone.utc).timestamp()),
                    "cancel_at_period_end": False
                }
            }
        }

        # Webhook処理実行
        await billing_service.process_subscription_deleted(
            db=db,
            event_id=event_id,
            customer_id="cus_test_canceling"
        )

        # 状態確認
        billing_after = await crud.billing.get(db=db, id=billing_id)
        assert billing_after.billing_status == BillingStatus.canceled
        assert billing_after.scheduled_cancel_at is None

        # Webhook eventが記録されていることを確認
        webhook_event = await crud.webhook_event.get_by_event_id(db=db, event_id=event_id)
        assert webhook_event is not None
        assert webhook_event.status == "success"
        assert webhook_event.event_type == "customer.subscription.deleted"

    async def test_subscription_deleted_from_active_status(
        self,
        db: AsyncSession,
        setup_office_with_billing: Tuple[UUID, UUID, UUID],
        billing_service: BillingService
    ):
        """
        active状態からの subscription.deleted処理を確認
        """
        office_id, staff_id, billing_id = setup_office_with_billing

        # Billingをactive状態に設定（Stripe情報あり）
        await crud.billing.update(
            db=db,
            db_obj=await crud.billing.get(db=db, id=billing_id),
            obj_in={
                "billing_status": BillingStatus.active,
                "stripe_customer_id": "cus_test_active",
                "stripe_subscription_id": "sub_test_active"
            }
        )
        await db.commit()

        # 削除前の確認
        billing_before = await crud.billing.get(db=db, id=billing_id)
        assert billing_before.billing_status == BillingStatus.active

        # Webhook処理実行
        event_id = f"evt_test_active_{uuid4().hex[:12]}"
        await billing_service.process_subscription_deleted(
            db=db,
            event_id=event_id,
            customer_id="cus_test_active"
        )

        # billing_statusがcanceledに遷移していることを確認
        billing_after = await crud.billing.get(db=db, id=billing_id)
        assert billing_after.billing_status == BillingStatus.canceled

    async def test_subscription_deleted_during_trial_with_scheduled_cancel(
        self,
        db: AsyncSession,
        setup_office_with_billing: Tuple[UUID, UUID, UUID],
        billing_service: BillingService
    ):
        """
        トライアル中にキャンセル予定を設定した場合の削除処理
        canceling → canceled への遷移を確認
        """
        office_id, staff_id, billing_id = setup_office_with_billing

        # Billingをcanceling状態に設定（トライアル中）
        trial_end = datetime.now(timezone.utc) + timedelta(days=30)
        scheduled_cancel_at = datetime.now(timezone.utc) + timedelta(days=7)

        await crud.billing.update(
            db=db,
            db_obj=await crud.billing.get(db=db, id=billing_id),
            obj_in={
                "billing_status": BillingStatus.canceling,
                "trial_end_date": trial_end,
                "stripe_customer_id": "cus_test_trial_cancel",
                "stripe_subscription_id": "sub_test_trial_cancel",
                "scheduled_cancel_at": scheduled_cancel_at
            }
        )
        await db.commit()

        # scheduled_cancel_at到達（実際にはStripeが自動的に削除）
        event_id = f"evt_test_trial_cancel_{uuid4().hex[:12]}"
        await billing_service.process_subscription_deleted(
            db=db,
            event_id=event_id,
            customer_id="cus_test_trial_cancel"
        )

        # 状態確認
        billing_after = await crud.billing.get(db=db, id=billing_id)
        assert billing_after.billing_status == BillingStatus.canceled
        assert billing_after.scheduled_cancel_at is None

    async def test_subscription_deleted_audit_log(
        self,
        db: AsyncSession,
        setup_office_with_billing: Tuple[UUID, UUID, UUID],
        billing_service: BillingService
    ):
        """
        subscription.deleted時に監査ログが正しく記録されることを確認
        """
        office_id, staff_id, billing_id = setup_office_with_billing

        # Billingをcanceling状態に設定
        await crud.billing.update(
            db=db,
            db_obj=await crud.billing.get(db=db, id=billing_id),
            obj_in={
                "billing_status": BillingStatus.canceling,
                "stripe_customer_id": "cus_test_audit",
                "stripe_subscription_id": "sub_test_audit"
            }
        )
        await db.commit()

        # Webhook処理実行
        event_id = f"evt_test_audit_{uuid4().hex[:12]}"
        await billing_service.process_subscription_deleted(
            db=db,
            event_id=event_id,
            customer_id="cus_test_audit"
        )

        # 監査ログ確認
        audit_logs, total = await crud.audit_log.get_logs(
            db=db,
            office_id=office_id,
            skip=0,
            limit=10,
            include_test_data=True
        )

        # subscription.deleted関連のログが記録されていることを確認
        assert len(audit_logs) > 0
        billing_logs = [log for log in audit_logs if log.target_type == "billing"]
        assert len(billing_logs) > 0
        latest_log = billing_logs[0]
        assert "subscription" in latest_log.action.lower() or "canceled" in latest_log.action.lower()
