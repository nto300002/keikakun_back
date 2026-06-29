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
    level=logging.WARNING,
    format='%(levelname)s:%(name)s:%(message)s'
)

# Suppress SQLAlchemy logs
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
logging.getLogger('sqlalchemy.pool').setLevel(logging.WARNING)
logging.getLogger('app').setLevel(logging.WARNING)

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

        unique_id = uuid4().hex
        customer_id = f"cus_test_rollback_{unique_id}"
        event_id = f"evt_test_rollback_{unique_id}"

        # Stripe Customer IDを設定
        await crud.billing.update_stripe_customer(
            db=db,
            billing_id=billing_id,
            stripe_customer_id=customer_id
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
                    event_id=event_id,
                    customer_id=customer_id
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
    async def test_subscription_created_after_payment_succeeded_keeps_early_payment_during_trial(
        self,
        db: AsyncSession,
        setup_office_with_billing: Tuple[UUID, UUID, UUID],
        billing_service: BillingService
    ):
        """
        invoice.payment_succeeded が先に来た後で customer.subscription.created が来ても、
        trial期間中なら early_payment が維持されることを検証。
        """
        office_id, staff_id, billing_id = setup_office_with_billing
        unique_id = uuid4().hex[:8]
        customer_id = f"cus_test_event_order_{unique_id}"
        subscription_id = f"sub_test_event_order_{unique_id}"

        await crud.billing.update_stripe_customer(
            db=db,
            billing_id=billing_id,
            stripe_customer_id=customer_id
        )

        await billing_service.process_payment_succeeded(
            db=db,
            event_id=f"evt_payment_first_{unique_id}",
            customer_id=customer_id
        )

        async with AsyncSessionLocal() as new_db:
            billing_after_payment = await crud.billing.get(db=new_db, id=billing_id)
            assert billing_after_payment.billing_status == BillingStatus.early_payment

            subscription_data = {
                "id": subscription_id,
                "customer": customer_id,
                "metadata": {
                    "office_id": str(office_id),
                    "office_name": "テスト事業所",
                    "created_by_user_id": str(staff_id)
                }
            }

            await billing_service.process_subscription_created(
                db=new_db,
                event_id=f"evt_subscription_after_payment_{unique_id}",
                subscription_data=subscription_data
            )

            billing_after_subscription = await crud.billing.get(db=new_db, id=billing_id)
            assert billing_after_subscription.billing_status == BillingStatus.early_payment
            assert billing_after_subscription.stripe_subscription_id == subscription_id

    @pytest.mark.asyncio
    async def test_process_payment_failed_during_trial_keeps_free_status(
        self,
        db: AsyncSession,
        setup_office_with_billing: Tuple[UUID, UUID, UUID],
        billing_service: BillingService
    ):
        """
        新仕様: trial期間中の支払い失敗ではpast_due/payment_failedへ落とさないことを検証
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
            billing_after = await crud.billing.get(db=new_db, id=billing_id)
            assert billing_after.billing_status == BillingStatus.free

    @pytest.mark.asyncio
    async def test_process_payment_failed_after_trial_sets_payment_failed(
        self,
        db: AsyncSession,
        setup_office_with_billing: Tuple[UUID, UUID, UUID],
        billing_service: BillingService
    ):
        """
        新仕様: trial期間外の支払い失敗はpayment_failedに更新される。
        """
        office_id, staff_id, billing_id = setup_office_with_billing
        unique_id = uuid4().hex[:8]
        customer_id = f"cus_test_payment_failed_after_trial_{unique_id}"

        billing = await crud.billing.get(db=db, id=billing_id)
        await crud.billing.update(
            db=db,
            db_obj=billing,
            obj_in={
                "billing_status": BillingStatus.active,
                "trial_end_date": datetime.now(timezone.utc) - timedelta(days=1),
                "stripe_subscription_id": f"sub_test_payment_failed_{unique_id}",
            },
            auto_commit=False
        )
        await crud.billing.update_stripe_customer(
            db=db,
            billing_id=billing_id,
            stripe_customer_id=customer_id
        )
        await db.commit()

        await billing_service.process_payment_failed(
            db=db,
            event_id=f"evt_test_payment_failed_after_trial_{unique_id}",
            customer_id=customer_id
        )

        async with AsyncSessionLocal() as new_db:
            billing_after = await crud.billing.get(db=new_db, id=billing_id)
            assert billing_after.billing_status == BillingStatus.payment_failed

    @pytest.mark.asyncio
    async def test_process_payment_failed_during_trial_keeps_existing_status(
        self,
        db: AsyncSession,
        setup_office_with_billing: Tuple[UUID, UUID, UUID],
        billing_service: BillingService
    ):
        """
        新仕様: trial期間中の支払い失敗ではpayment_failed/past_dueへ落とさない。
        """
        office_id, staff_id, billing_id = setup_office_with_billing
        unique_id = uuid4().hex[:8]
        customer_id = f"cus_test_payment_failed_during_trial_{unique_id}"

        billing = await crud.billing.get(db=db, id=billing_id)
        await crud.billing.update(
            db=db,
            db_obj=billing,
            obj_in={
                "billing_status": BillingStatus.early_payment,
                "trial_end_date": datetime.now(timezone.utc) + timedelta(days=30),
                "stripe_subscription_id": f"sub_test_trial_payment_failed_{unique_id}",
            },
            auto_commit=False
        )
        await crud.billing.update_stripe_customer(
            db=db,
            billing_id=billing_id,
            stripe_customer_id=customer_id
        )
        await db.commit()

        await billing_service.process_payment_failed(
            db=db,
            event_id=f"evt_test_payment_failed_during_trial_{unique_id}",
            customer_id=customer_id
        )

        async with AsyncSessionLocal() as new_db:
            billing_after = await crud.billing.get(db=new_db, id=billing_id)
            assert billing_after.billing_status == BillingStatus.early_payment

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

    @pytest.mark.asyncio
    async def test_process_subscription_deleted_after_recent_payment_failed_keeps_payment_failed(
        self,
        db: AsyncSession,
        setup_office_with_billing: Tuple[UUID, UUID, UUID],
        billing_service: BillingService
    ):
        """
        支払い失敗直後のStripe自動削除では、ユーザー解約ではなくpayment_failedを優先する。
        """
        office_id, staff_id, billing_id = setup_office_with_billing

        unique_id = uuid4().hex[:8]
        customer_id = f"cus_test_failed_deleted_{unique_id}"

        await crud.billing.update_stripe_customer(
            db=db,
            billing_id=billing_id,
            stripe_customer_id=customer_id
        )
        await crud.billing.update_stripe_subscription(
            db=db,
            billing_id=billing_id,
            stripe_subscription_id=f"sub_test_failed_deleted_{unique_id}"
        )
        await crud.billing.update_status(
            db=db,
            billing_id=billing_id,
            status=BillingStatus.payment_failed
        )

        billing = await crud.billing.get(db=db, id=billing_id)
        await crud.webhook_event.create_event_record(
            db=db,
            event_id=f"evt_recent_payment_failed_{unique_id}",
            event_type="invoice.payment_failed",
            source="stripe",
            billing_id=billing_id,
            office_id=office_id,
            payload={"customer_id": customer_id},
            status="success",
            auto_commit=False
        )
        await db.commit()

        await billing_service.process_subscription_deleted(
            db=db,
            event_id=f"evt_test_deleted_after_failed_{unique_id}",
            customer_id=customer_id
        )

        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as new_db:
            billing_after = await crud.billing.get(db=new_db, id=billing_id)
            assert billing_after.billing_status == BillingStatus.payment_failed


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
    async def test_create_checkout_session_with_customer_excludes_expired_trial_end(
        self,
        db: AsyncSession,
        setup_office_with_billing: Tuple[UUID, UUID, UUID],
        billing_service: BillingService
    ):
        """
        新規Customer作成ルートでは、過去のtrial_endをStripeに渡さないことを検証。
        """
        office_id, staff_id, billing_id = setup_office_with_billing
        unique_id = uuid4().hex
        customer_id = f"cus_mock_expired_trial_{unique_id}"
        checkout_session_id = f"cs_mock_expired_trial_{unique_id}"
        expired_trial_end = datetime.now(timezone.utc) - timedelta(days=1)

        billing = await crud.billing.get(db=db, id=billing_id)
        await crud.billing.update(
            db=db,
            db_obj=billing,
            obj_in={"trial_end_date": expired_trial_end},
            auto_commit=False
        )
        await db.flush()

        mock_customer = Mock()
        mock_customer.id = customer_id

        mock_checkout_session = Mock()
        mock_checkout_session.id = checkout_session_id
        mock_checkout_session.url = "https://checkout.stripe.com/expired-trial"

        with patch('stripe.Customer.create', return_value=mock_customer), \
             patch('stripe.checkout.Session.create', return_value=mock_checkout_session) as mock_create_session:
            result = await billing_service.create_checkout_session_with_customer(
                db=db,
                billing_id=billing_id,
                office_id=office_id,
                office_name="期限切れトライアル事業所",
                user_email="expired-trial@example.com",
                user_id=staff_id,
                trial_end_date=expired_trial_end,
                stripe_secret_key="sk_test_mock",
                stripe_price_id="price_mock_12345",
                frontend_url="http://localhost:3000"
            )

        assert result["session_id"] == checkout_session_id
        assert result["url"] == "https://checkout.stripe.com/expired-trial"

        mock_create_session.assert_called_once()
        subscription_data = mock_create_session.call_args.kwargs["subscription_data"]
        assert "trial_end" not in subscription_data

        billing_after = await crud.billing.get(db=db, id=billing_id)
        assert billing_after.stripe_customer_id == customer_id
        assert billing_after.billing_status == BillingStatus.trial_expired

    @pytest.mark.asyncio
    async def test_create_checkout_session_with_customer_includes_future_trial_end(
        self,
        db: AsyncSession,
        setup_office_with_billing: Tuple[UUID, UUID, UUID],
        billing_service: BillingService
    ):
        """
        新規Customer作成ルートでは、未来のtrial_endを従来どおりStripeに渡すことを検証。
        """
        office_id, staff_id, billing_id = setup_office_with_billing
        unique_id = uuid4().hex
        customer_id = f"cus_mock_future_trial_{unique_id}"
        checkout_session_id = f"cs_mock_future_trial_{unique_id}"
        future_trial_end = datetime.now(timezone.utc) + timedelta(days=30)

        mock_customer = Mock()
        mock_customer.id = customer_id

        mock_checkout_session = Mock()
        mock_checkout_session.id = checkout_session_id
        mock_checkout_session.url = "https://checkout.stripe.com/future-trial"

        with patch('stripe.Customer.create', return_value=mock_customer), \
             patch('stripe.checkout.Session.create', return_value=mock_checkout_session) as mock_create_session:
            result = await billing_service.create_checkout_session_with_customer(
                db=db,
                billing_id=billing_id,
                office_id=office_id,
                office_name="トライアル中事業所",
                user_email="future-trial@example.com",
                user_id=staff_id,
                trial_end_date=future_trial_end,
                stripe_secret_key="sk_test_mock",
                stripe_price_id="price_mock_12345",
                frontend_url="http://localhost:3000"
            )

        assert result["session_id"] == checkout_session_id
        assert result["url"] == "https://checkout.stripe.com/future-trial"

        mock_create_session.assert_called_once()
        subscription_data = mock_create_session.call_args.kwargs["subscription_data"]
        assert subscription_data["trial_end"] == int(future_trial_end.timestamp())

    @pytest.mark.asyncio
    async def test_create_checkout_session_with_customer_accepts_naive_trial_end(
        self,
        db: AsyncSession,
        setup_office_with_billing: Tuple[UUID, UUID, UUID],
        billing_service: BillingService
    ):
        """
        新規Customer作成ルートでは、naive datetimeでも比較エラーにならずtrial_endを渡すことを検証。
        """
        office_id, staff_id, billing_id = setup_office_with_billing
        unique_id = uuid4().hex
        customer_id = f"cus_mock_naive_trial_{unique_id}"
        checkout_session_id = f"cs_mock_naive_trial_{unique_id}"
        naive_trial_end = datetime.now() + timedelta(days=30)

        mock_customer = Mock()
        mock_customer.id = customer_id

        mock_checkout_session = Mock()
        mock_checkout_session.id = checkout_session_id
        mock_checkout_session.url = "https://checkout.stripe.com/naive-trial"

        with patch('stripe.Customer.create', return_value=mock_customer), \
             patch('stripe.checkout.Session.create', return_value=mock_checkout_session) as mock_create_session:
            result = await billing_service.create_checkout_session_with_customer(
                db=db,
                billing_id=billing_id,
                office_id=office_id,
                office_name="naive datetime事業所",
                user_email="naive-trial@example.com",
                user_id=staff_id,
                trial_end_date=naive_trial_end,
                stripe_secret_key="sk_test_mock",
                stripe_price_id="price_mock_12345",
                frontend_url="http://localhost:3000"
            )

        assert result["session_id"] == checkout_session_id
        assert result["url"] == "https://checkout.stripe.com/naive-trial"

        mock_create_session.assert_called_once()
        subscription_data = mock_create_session.call_args.kwargs["subscription_data"]
        assert subscription_data["trial_end"] == int(
            naive_trial_end.replace(tzinfo=timezone.utc).timestamp()
        )

    @pytest.mark.asyncio
    async def test_create_checkout_session_rollback_on_checkout_session_error(
        self,
        db: AsyncSession,
        setup_office_with_billing: Tuple[UUID, UUID, UUID],
        billing_service: BillingService
    ):
        """
        Customer作成後にCheckout Session作成が失敗した場合、DB更新がロールバックされることを検証。
        """
        office_id, staff_id, billing_id = setup_office_with_billing
        unique_id = uuid4().hex
        customer_id = f"cus_mock_checkout_error_{unique_id}"
        expired_trial_end = datetime.now(timezone.utc) - timedelta(days=1)

        billing = await crud.billing.get(db=db, id=billing_id)
        await crud.billing.update(
            db=db,
            db_obj=billing,
            obj_in={
                "billing_status": BillingStatus.free,
                "trial_end_date": expired_trial_end,
            },
            auto_commit=False
        )
        await db.commit()

        mock_customer = Mock()
        mock_customer.id = customer_id

        import stripe
        with patch('stripe.Customer.create', return_value=mock_customer), \
             patch('stripe.checkout.Session.create', side_effect=stripe.error.StripeError("Checkout Error")):
            from fastapi import HTTPException
            with pytest.raises(HTTPException):
                await billing_service.create_checkout_session_with_customer(
                    db=db,
                    billing_id=billing_id,
                    office_id=office_id,
                    office_name="Checkout失敗事業所",
                    user_email="checkout-error@example.com",
                    user_id=staff_id,
                    trial_end_date=expired_trial_end,
                    stripe_secret_key="sk_test_mock",
                    stripe_price_id="price_mock_12345",
                    frontend_url="http://localhost:3000"
                )

        billing_after = await crud.billing.get(db=db, id=billing_id)
        assert billing_after.stripe_customer_id is None
        assert billing_after.billing_status == BillingStatus.free

    @pytest.mark.asyncio
    async def test_create_checkout_session_logs_safe_context_on_stripe_error(
        self,
        db: AsyncSession,
        setup_office_with_billing: Tuple[UUID, UUID, UUID],
        billing_service: BillingService,
        caplog
    ):
        """
        Stripe APIエラー時に、秘匿情報を含めず調査用コンテキストをログ出力することを検証。
        """
        office_id, staff_id, billing_id = setup_office_with_billing
        billing = await crud.billing.get(db=db, id=billing_id)

        secret_key = "sk_test_secret_should_not_be_logged"
        user_email = "sensitive-user@example.com"
        leaked_customer_id = f"cus_leaked_error_{uuid4().hex}"
        stripe_error_message = f"No such customer: {leaked_customer_id}; email={user_email}"

        import stripe
        with caplog.at_level(logging.ERROR, logger="app.services.billing_service"):
            with patch('stripe.Customer.create', side_effect=stripe.error.StripeError(stripe_error_message)):
                from fastapi import HTTPException
                with pytest.raises(HTTPException):
                    await billing_service.create_checkout_session_with_customer(
                        db=db,
                        billing_id=billing_id,
                        office_id=office_id,
                        office_name="ログ検証事業所",
                        user_email=user_email,
                        user_id=staff_id,
                        trial_end_date=billing.trial_end_date,
                        stripe_secret_key=secret_key,
                        stripe_price_id="price_mock_12345",
                        frontend_url="http://localhost:3000"
                    )

        assert f"billing_id={billing_id}" in caplog.text
        assert f"office_id={office_id}" in caplog.text
        assert "checkout_route=new_customer" in caplog.text
        assert "has_stripe_customer_id=False" in caplog.text
        assert "billing_status=free" in caplog.text
        assert "trial_end_date=" in caplog.text
        assert "stripe_error_type=StripeError" in caplog.text
        assert secret_key not in caplog.text
        assert user_email not in caplog.text
        assert leaked_customer_id not in caplog.text
        assert stripe_error_message not in caplog.text

    @pytest.mark.asyncio
    async def test_create_checkout_session_existing_customer_logs_safe_context_on_stripe_error(
        self,
        db: AsyncSession,
        setup_office_with_billing: Tuple[UUID, UUID, UUID],
        billing_service: BillingService,
        caplog
    ):
        """
        既存CustomerありルートのStripe APIエラーでも、非秘匿の調査情報をログ出力することを検証。
        """
        office_id, staff_id, billing_id = setup_office_with_billing
        customer_id = f"cus_existing_log_{uuid4().hex}"

        await crud.billing.update_stripe_customer(
            db=db,
            billing_id=billing_id,
            stripe_customer_id=customer_id
        )
        await db.commit()

        billing = await crud.billing.get(db=db, id=billing_id)
        user_email = "existing-sensitive-user@example.com"
        stripe_error_message = f"No such customer: {customer_id}; email={user_email}"

        import stripe
        with caplog.at_level(logging.ERROR, logger="app.services.billing_service"):
            with patch('stripe.checkout.Session.create', side_effect=stripe.error.StripeError(stripe_error_message)):
                from fastapi import HTTPException
                with pytest.raises(HTTPException):
                    await billing_service.create_checkout_session_for_existing_customer(
                        db=db,
                        billing_id=billing_id,
                        office_id=office_id,
                        office_name="既存Customerログ検証事業所",
                        user_id=staff_id,
                        stripe_customer_id=customer_id,
                        trial_end_date=billing.trial_end_date,
                        stripe_secret_key="sk_test_existing_customer_log",
                        stripe_price_id="price_mock_12345",
                        frontend_url="http://localhost:3000"
                    )

        assert f"billing_id={billing_id}" in caplog.text
        assert f"office_id={office_id}" in caplog.text
        assert "checkout_route=existing_customer" in caplog.text
        assert "has_stripe_customer_id=True" in caplog.text
        assert "billing_status=free" in caplog.text
        assert "trial_end_date=" in caplog.text
        assert "stripe_error_type=StripeError" in caplog.text
        assert customer_id not in caplog.text
        assert user_email not in caplog.text
        assert stripe_error_message not in caplog.text

    @pytest.mark.asyncio
    async def test_create_checkout_session_existing_customer_sets_stripe_api_key(
        self,
        db: AsyncSession,
        setup_office_with_billing: Tuple[UUID, UUID, UUID],
        billing_service: BillingService
    ):
        """
        既存CustomerありルートでもCheckout作成前にStripe APIキーを設定することを検証。
        """
        office_id, staff_id, billing_id = setup_office_with_billing
        customer_id = f"cus_existing_api_key_{uuid4().hex}"
        secret_key = "sk_test_existing_customer_route"

        await crud.billing.update_stripe_customer(
            db=db,
            billing_id=billing_id,
            stripe_customer_id=customer_id
        )
        await db.commit()

        billing = await crud.billing.get(db=db, id=billing_id)
        mock_checkout_session = Mock()
        mock_checkout_session.id = f"cs_existing_api_key_{uuid4().hex}"
        mock_checkout_session.url = "https://checkout.stripe.com/existing-api-key"

        import stripe
        stripe.api_key = None

        with patch('stripe.checkout.Session.create', return_value=mock_checkout_session):
            await billing_service.create_checkout_session_for_existing_customer(
                db=db,
                billing_id=billing_id,
                office_id=office_id,
                office_name="既存Customer APIキー検証事業所",
                user_id=staff_id,
                stripe_customer_id=customer_id,
                trial_end_date=billing.trial_end_date,
                stripe_secret_key=secret_key,
                stripe_price_id="price_mock_12345",
                frontend_url="http://localhost:3000"
            )

        assert stripe.api_key == secret_key

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
        unique_id = uuid4().hex[:12]
        await crud.billing.update(
            db=db,
            db_obj=await crud.billing.get(db=db, id=billing_id),
            obj_in={
                "billing_status": BillingStatus.active,
                "stripe_customer_id": f"cus_test_{unique_id}",
                "stripe_subscription_id": f"sub_test_{unique_id}"
            }
        )
        await db.commit()

        # 削除前の確認
        billing_before = await crud.billing.get(db=db, id=billing_id)
        assert billing_before.billing_status == BillingStatus.active

        # Webhook処理実行
        event_id = f"evt_test_{uuid4().hex[:12]}"
        await billing_service.process_subscription_deleted(
            db=db,
            event_id=event_id,
            customer_id=f"cus_test_{unique_id}"
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
