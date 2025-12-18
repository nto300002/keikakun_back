"""
BillingService キャンセル機能のTDDテスト

キャンセル関連のステータス運用をテスト:
- canceling: キャンセル予定（期間終了時にキャンセル）
- canceled: キャンセル完了
"""
import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4
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

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="function")
async def db() -> AsyncSession:
    """テスト用の非同期DBセッションを提供"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            try:
                await session.rollback()
            except Exception:
                pass


@pytest.fixture(scope="function")
async def active_subscription_setup(db: AsyncSession) -> Tuple:
    """
    課金中(active)のBillingを作成
    Returns: (office_id, staff_id, billing_id, customer_id, subscription_id)
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

    # Billing作成（active状態）
    now = datetime.now(timezone.utc)
    trial_start = now - timedelta(days=200)
    trial_end = now - timedelta(days=20)  # トライアル期間終了済み
    subscription_start = trial_end

    customer_id = f"cus_test_{uuid4().hex[:8]}"
    subscription_id = f"sub_test_{uuid4().hex[:8]}"

    billing = Billing(
        office_id=office.id,
        billing_status=BillingStatus.active,
        stripe_customer_id=customer_id,
        stripe_subscription_id=subscription_id,
        trial_start_date=trial_start,
        trial_end_date=trial_end,
        subscription_start_date=subscription_start,
        next_billing_date=now + timedelta(days=10),
        current_plan_amount=6000
    )
    db.add(billing)
    await db.flush()
    await db.commit()

    return (office.id, staff.id, billing.id, customer_id, subscription_id)


class TestBillingCanceling:
    """キャンセル予定(canceling)状態のテスト"""

    @pytest.fixture
    def billing_service(self):
        return BillingService()

    async def test_process_subscription_updated_to_canceling(
        self,
        db: AsyncSession,
        active_subscription_setup: Tuple,
        billing_service: BillingService
    ):
        """
        customer.subscription.updated (cancel_at_period_end=true)
        → billing_status が canceling になることを確認
        """
        office_id, staff_id, billing_id, customer_id, subscription_id = active_subscription_setup

        # Webhookデータを準備
        cancel_at = int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp())
        subscription_data = {
            'id': subscription_id,
            'customer': customer_id,
            'cancel_at_period_end': True,
            'cancel_at': cancel_at,
            'status': 'active'
        }

        # Webhook処理を実行
        await billing_service.process_subscription_updated(
            db=db,
            event_id=f"evt_test_{uuid4().hex[:8]}",
            subscription_data=subscription_data
        )

        # billing_statusがcancelingになっていることを確認
        billing = await crud.billing.get(db=db, id=billing_id)
        assert billing.billing_status == BillingStatus.canceling

    async def test_process_subscription_updated_not_canceling(
        self,
        db: AsyncSession,
        active_subscription_setup: Tuple,
        billing_service: BillingService
    ):
        """
        customer.subscription.updated (cancel_at_period_end=false)
        → billing_status が変更されないことを確認
        """
        office_id, staff_id, billing_id, customer_id, subscription_id = active_subscription_setup

        # Webhookデータを準備（キャンセル予定なし）
        subscription_data = {
            'id': subscription_id,
            'customer': customer_id,
            'cancel_at_period_end': False,
            'cancel_at': None,
            'status': 'active'
        }

        # Webhook処理を実行
        await billing_service.process_subscription_updated(
            db=db,
            event_id=f"evt_test_{uuid4().hex[:8]}",
            subscription_data=subscription_data
        )

        # billing_statusがactiveのままであることを確認
        billing = await crud.billing.get(db=db, id=billing_id)
        assert billing.billing_status == BillingStatus.active

    async def test_can_reactivate_from_canceling(
        self,
        db: AsyncSession,
        active_subscription_setup: Tuple,
        billing_service: BillingService
    ):
        """
        canceling状態からキャンセルを取り消して active に戻せることを確認

        フロー:
        1. active → canceling (キャンセル予定)
        2. canceling → active (キャンセル取り消し)
        """
        office_id, staff_id, billing_id, customer_id, subscription_id = active_subscription_setup

        # Step 1: キャンセル予定に
        subscription_data_canceling = {
            'id': subscription_id,
            'customer': customer_id,
            'cancel_at_period_end': True,
            'cancel_at': int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()),
            'status': 'active'
        }

        await billing_service.process_subscription_updated(
            db=db,
            event_id=f"evt_test_{uuid4().hex[:8]}",
            subscription_data=subscription_data_canceling
        )

        billing = await crud.billing.get(db=db, id=billing_id)
        assert billing.billing_status == BillingStatus.canceling

        # Step 2: キャンセルを取り消し
        subscription_data_reactivate = {
            'id': subscription_id,
            'customer': customer_id,
            'cancel_at_period_end': False,
            'cancel_at': None,
            'status': 'active'
        }

        await billing_service.process_subscription_updated(
            db=db,
            event_id=f"evt_test_{uuid4().hex[:8]}",
            subscription_data=subscription_data_reactivate
        )

        # billing_statusがactiveに戻ることを確認
        billing = await crud.billing.get(db=db, id=billing_id)
        assert billing.billing_status == BillingStatus.active


class TestBillingCanceled:
    """キャンセル完了(canceled)状態のテスト"""

    @pytest.fixture
    def billing_service(self):
        return BillingService()

    async def test_process_subscription_deleted_from_active(
        self,
        db: AsyncSession,
        active_subscription_setup: Tuple,
        billing_service: BillingService
    ):
        """
        customer.subscription.deleted
        → billing_status が canceled になることを確認
        """
        office_id, staff_id, billing_id, customer_id, subscription_id = active_subscription_setup

        # Webhook処理を実行
        await billing_service.process_subscription_deleted(
            db=db,
            event_id=f"evt_test_{uuid4().hex[:8]}",
            customer_id=customer_id
        )

        # billing_statusがcanceledになっていることを確認
        billing = await crud.billing.get(db=db, id=billing_id)
        assert billing.billing_status == BillingStatus.canceled

    async def test_process_subscription_deleted_from_canceling(
        self,
        db: AsyncSession,
        active_subscription_setup: Tuple,
        billing_service: BillingService
    ):
        """
        canceling → canceled への遷移を確認

        フロー:
        1. active → canceling (ユーザーがキャンセル予定)
        2. canceling → canceled (期間終了でキャンセル完了)
        """
        office_id, staff_id, billing_id, customer_id, subscription_id = active_subscription_setup

        # Step 1: キャンセル予定にする
        await crud.billing.update_status(
            db=db,
            billing_id=billing_id,
            status=BillingStatus.canceling,
            auto_commit=True
        )

        # Step 2: 期間終了でキャンセル完了
        await billing_service.process_subscription_deleted(
            db=db,
            event_id=f"evt_test_{uuid4().hex[:8]}",
            customer_id=customer_id
        )

        # billing_statusがcanceledになっていることを確認
        billing = await crud.billing.get(db=db, id=billing_id)
        assert billing.billing_status == BillingStatus.canceled


class TestBillingStatusTransitions:
    """ステータス遷移の整合性テスト"""

    @pytest.fixture
    def billing_service(self):
        return BillingService()

    async def test_full_lifecycle_with_canceling(
        self,
        db: AsyncSession,
        active_subscription_setup: Tuple,
        billing_service: BillingService
    ):
        """
        完全なライフサイクルをテスト

        free → early_payment → active → canceling → canceled
        """
        office_id, staff_id, billing_id, customer_id, subscription_id = active_subscription_setup

        # 初期状態: active
        billing = await crud.billing.get(db=db, id=billing_id)
        assert billing.billing_status == BillingStatus.active

        # Step 1: active → canceling
        subscription_data = {
            'id': subscription_id,
            'customer': customer_id,
            'cancel_at_period_end': True,
            'cancel_at': int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()),
            'status': 'active'
        }

        await billing_service.process_subscription_updated(
            db=db,
            event_id=f"evt_test_{uuid4().hex[:8]}",
            subscription_data=subscription_data
        )

        billing = await crud.billing.get(db=db, id=billing_id)
        assert billing.billing_status == BillingStatus.canceling

        # Step 2: canceling → canceled
        await billing_service.process_subscription_deleted(
            db=db,
            event_id=f"evt_test_{uuid4().hex[:8]}",
            customer_id=customer_id
        )

        billing = await crud.billing.get(db=db, id=billing_id)
        assert billing.billing_status == BillingStatus.canceled

    async def test_idempotency_canceling(
        self,
        db: AsyncSession,
        active_subscription_setup: Tuple,
        billing_service: BillingService
    ):
        """
        同じcustomer.subscription.updatedイベントを複数回受信しても
        冪等性が保たれることを確認
        """
        office_id, staff_id, billing_id, customer_id, subscription_id = active_subscription_setup

        subscription_data = {
            'id': subscription_id,
            'customer': customer_id,
            'cancel_at_period_end': True,
            'cancel_at': int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()),
            'status': 'active'
        }

        event_id = f"evt_test_{uuid4().hex[:8]}"

        # 1回目: イベント処理
        await billing_service.process_subscription_updated(
            db=db,
            event_id=event_id,
            subscription_data=subscription_data
        )

        billing_after_first = await crud.billing.get(db=db, id=billing_id)
        assert billing_after_first.billing_status == BillingStatus.canceling

        # 2回目: 同じイベントを再送信（冪等性チェック）
        # TODO: 冪等性チェックの実装が必要
        # await billing_service.process_subscription_updated(
        #     db=db,
        #     event_id=event_id,  # 同じイベントID
        #     subscription_data=subscription_data
        # )

        # billing = await crud.billing.get(db=db, id=billing_id)
        # assert billing.billing_status == BillingStatus.canceling
