"""
BillingService ステータス運用ヘルパーメソッドのTDDテスト

ユーザーが便利に使えるステータス判定・操作メソッドをテスト
"""
import pytest
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
async def billing_factory(db: AsyncSession):
    """様々な状態のBillingを作成するファクトリ"""

    async def create_billing(status: BillingStatus) -> Tuple:
        """
        指定されたステータスのBillingを作成
        Returns: (billing_id, office_id, staff_id)
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
        now = datetime.now(timezone.utc)
        trial_start = now - timedelta(days=200)
        trial_end = now + timedelta(days=30)

        customer_id = f"cus_test_{uuid4().hex[:8]}" if status != BillingStatus.free else None
        subscription_id = f"sub_test_{uuid4().hex[:8]}" if status not in [BillingStatus.free, BillingStatus.canceled] else None

        billing = Billing(
            office_id=office.id,
            billing_status=status,
            stripe_customer_id=customer_id,
            stripe_subscription_id=subscription_id,
            trial_start_date=trial_start,
            trial_end_date=trial_end,
            current_plan_amount=6000
        )
        db.add(billing)
        await db.flush()
        await db.commit()

        return (billing.id, office.id, staff.id)

    return create_billing


class TestBillingStatusChecks:
    """ステータス判定メソッドのテスト"""

    async def test_is_active_subscription(
        self,
        db: AsyncSession,
        billing_factory
    ):
        """
        アクティブなサブスクリプションかを判定
        active, early_payment, canceling は True
        free, past_due, canceled は False
        """
        # active: True
        billing_id, _, _ = await billing_factory(BillingStatus.active)
        billing = await crud.billing.get(db=db, id=billing_id)
        assert crud.billing.is_active_subscription(billing) is True

        # early_payment: True
        billing_id, _, _ = await billing_factory(BillingStatus.early_payment)
        billing = await crud.billing.get(db=db, id=billing_id)
        assert crud.billing.is_active_subscription(billing) is True

        # canceling: True (まだ利用可能)
        billing_id, _, _ = await billing_factory(BillingStatus.canceling)
        billing = await crud.billing.get(db=db, id=billing_id)
        assert crud.billing.is_active_subscription(billing) is True

        # free: False
        billing_id, _, _ = await billing_factory(BillingStatus.free)
        billing = await crud.billing.get(db=db, id=billing_id)
        assert crud.billing.is_active_subscription(billing) is False

        # past_due: False
        billing_id, _, _ = await billing_factory(BillingStatus.past_due)
        billing = await crud.billing.get(db=db, id=billing_id)
        assert crud.billing.is_active_subscription(billing) is False

        # canceled: False
        billing_id, _, _ = await billing_factory(BillingStatus.canceled)
        billing = await crud.billing.get(db=db, id=billing_id)
        assert crud.billing.is_active_subscription(billing) is False

    async def test_is_pending_cancellation(
        self,
        db: AsyncSession,
        billing_factory
    ):
        """
        キャンセル予定かを判定
        canceling のみ True
        """
        # canceling: True
        billing_id, _, _ = await billing_factory(BillingStatus.canceling)
        billing = await crud.billing.get(db=db, id=billing_id)
        assert crud.billing.is_pending_cancellation(billing) is True

        # active: False
        billing_id, _, _ = await billing_factory(BillingStatus.active)
        billing = await crud.billing.get(db=db, id=billing_id)
        assert crud.billing.is_pending_cancellation(billing) is False

        # canceled: False
        billing_id, _, _ = await billing_factory(BillingStatus.canceled)
        billing = await crud.billing.get(db=db, id=billing_id)
        assert crud.billing.is_pending_cancellation(billing) is False

    async def test_can_access_paid_features(
        self,
        db: AsyncSession,
        billing_factory
    ):
        """
        有料機能にアクセスできるかを判定
        early_payment, active, canceling は True
        free, past_due, canceled は False
        """
        # early_payment: True
        billing_id, _, _ = await billing_factory(BillingStatus.early_payment)
        billing = await crud.billing.get(db=db, id=billing_id)
        assert crud.billing.can_access_paid_features(billing) is True

        # active: True
        billing_id, _, _ = await billing_factory(BillingStatus.active)
        billing = await crud.billing.get(db=db, id=billing_id)
        assert crud.billing.can_access_paid_features(billing) is True

        # canceling: True (期間終了まで利用可能)
        billing_id, _, _ = await billing_factory(BillingStatus.canceling)
        billing = await crud.billing.get(db=db, id=billing_id)
        assert crud.billing.can_access_paid_features(billing) is True

        # free: False
        billing_id, _, _ = await billing_factory(BillingStatus.free)
        billing = await crud.billing.get(db=db, id=billing_id)
        assert crud.billing.can_access_paid_features(billing) is False

        # past_due: False
        billing_id, _, _ = await billing_factory(BillingStatus.past_due)
        billing = await crud.billing.get(db=db, id=billing_id)
        assert crud.billing.can_access_paid_features(billing) is False

    async def test_requires_payment_action(
        self,
        db: AsyncSession,
        billing_factory
    ):
        """
        支払いアクションが必要かを判定
        past_due のみ True
        """
        # past_due: True
        billing_id, _, _ = await billing_factory(BillingStatus.past_due)
        billing = await crud.billing.get(db=db, id=billing_id)
        assert crud.billing.requires_payment_action(billing) is True

        # active: False
        billing_id, _, _ = await billing_factory(BillingStatus.active)
        billing = await crud.billing.get(db=db, id=billing_id)
        assert crud.billing.requires_payment_action(billing) is False

        # free: False
        billing_id, _, _ = await billing_factory(BillingStatus.free)
        billing = await crud.billing.get(db=db, id=billing_id)
        assert crud.billing.requires_payment_action(billing) is False


class TestBillingStatusMessages:
    """ステータスメッセージ取得のテスト"""

    async def test_get_status_display_message(
        self,
        db: AsyncSession,
        billing_factory
    ):
        """
        各ステータスの表示メッセージを取得
        """
        test_cases = [
            (BillingStatus.free, "無料トライアル中"),
            (BillingStatus.early_payment, "課金設定済み（無料期間中）"),
            (BillingStatus.active, "課金中"),
            (BillingStatus.past_due, "支払い遅延"),
            (BillingStatus.canceling, "キャンセル予定"),
            (BillingStatus.canceled, "キャンセル済み"),
        ]

        for status, expected_message in test_cases:
            billing_id, _, _ = await billing_factory(status)
            billing = await crud.billing.get(db=db, id=billing_id)

            message = crud.billing.get_status_display_message(billing)
            assert message == expected_message

    async def test_get_cancellation_message(
        self,
        db: AsyncSession,
        billing_factory
    ):
        """
        cancelingステータスの詳細メッセージを取得
        """
        billing_id, _, _ = await billing_factory(BillingStatus.canceling)
        billing = await crud.billing.get(db=db, id=billing_id)

        # trial_end_dateまで利用可能
        message = crud.billing.get_cancellation_message(billing)

        expected_date = billing.trial_end_date.strftime('%Y年%m月%d日')
        assert expected_date in message
        assert "まで利用できます" in message

    async def test_get_next_action_message(
        self,
        db: AsyncSession,
        billing_factory
    ):
        """
        各ステータスでの次のアクションメッセージを取得
        """
        # free: 課金設定を促す
        billing_id, _, _ = await billing_factory(BillingStatus.free)
        billing = await crud.billing.get(db=db, id=billing_id)
        message = crud.billing.get_next_action_message(billing)
        assert "課金設定" in message

        # past_due: 支払い更新を促す
        billing_id, _, _ = await billing_factory(BillingStatus.past_due)
        billing = await crud.billing.get(db=db, id=billing_id)
        message = crud.billing.get_next_action_message(billing)
        assert "支払い方法" in message

        # canceling: キャンセル取り消しを案内
        billing_id, _, _ = await billing_factory(BillingStatus.canceling)
        billing = await crud.billing.get(db=db, id=billing_id)
        message = crud.billing.get_next_action_message(billing)
        assert "取り消し" in message or "再開" in message

        # canceled: 再契約を案内
        billing_id, _, _ = await billing_factory(BillingStatus.canceled)
        billing = await crud.billing.get(db=db, id=billing_id)
        message = crud.billing.get_next_action_message(billing)
        assert "再契約" in message or "再開" in message
