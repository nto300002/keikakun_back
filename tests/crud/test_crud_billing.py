"""
Billing CRUD のテスト
"""
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
import pytest
from uuid import UUID

from app import crud
from app.models.enums import BillingStatus
from app.schemas.billing import BillingCreate, BillingUpdate

pytestmark = pytest.mark.asyncio


async def test_create_billing_for_office(
    db_session: AsyncSession,
    office_factory
) -> None:
    """事業所用のBilling作成テスト"""
    office = await office_factory()

    # Billing作成（無料期間180日）
    billing = await crud.billing.create_for_office(
        db=db_session,
        office_id=office.id,
        trial_days=180
    )

    assert billing.id is not None
    assert billing.office_id == office.id
    assert billing.billing_status == BillingStatus.free
    assert billing.current_plan_amount == 6000
    assert billing.trial_start_date is not None
    assert billing.trial_end_date is not None

    # 無料期間が180日であることを確認
    trial_duration = billing.trial_end_date - billing.trial_start_date
    assert trial_duration.days == 180


async def test_get_billing_by_office_id(
    db_session: AsyncSession,
    office_factory
) -> None:
    """事業所IDでBilling取得テスト"""
    office = await office_factory()

    # Billing作成
    created_billing = await crud.billing.create_for_office(
        db=db_session,
        office_id=office.id
    )
    await db_session.commit()

    # 取得
    billing = await crud.billing.get_by_office_id(
        db=db_session,
        office_id=office.id
    )

    assert billing is not None
    assert billing.id == created_billing.id
    assert billing.office_id == office.id


async def test_get_billing_by_stripe_customer_id(
    db_session: AsyncSession,
    office_factory
) -> None:
    """Stripe Customer IDでBilling取得テスト"""
    office = await office_factory()

    # Billing作成
    billing_data = BillingCreate(
        office_id=office.id,
        stripe_customer_id="cus_test_123",
        billing_status=BillingStatus.free,
        trial_start_date=datetime.utcnow(),
        trial_end_date=datetime.utcnow() + timedelta(days=180),
        current_plan_amount=6000
    )
    created_billing = await crud.billing.create(db=db_session, obj_in=billing_data)
    await db_session.commit()

    # Stripe Customer IDで取得
    billing = await crud.billing.get_by_stripe_customer_id(
        db=db_session,
        stripe_customer_id="cus_test_123"
    )

    assert billing is not None
    assert billing.id == created_billing.id
    assert billing.stripe_customer_id == "cus_test_123"


async def test_update_billing_status(
    db_session: AsyncSession,
    office_factory
) -> None:
    """課金ステータス更新テスト"""
    office = await office_factory()

    # Billing作成（free）
    billing = await crud.billing.create_for_office(
        db=db_session,
        office_id=office.id
    )
    await db_session.commit()

    assert billing.billing_status == BillingStatus.free

    # ステータスを active に更新
    updated_billing = await crud.billing.update_status(
        db=db_session,
        billing_id=billing.id,
        status=BillingStatus.active
    )

    assert updated_billing.billing_status == BillingStatus.active


async def test_update_stripe_customer(
    db_session: AsyncSession,
    office_factory
) -> None:
    """Stripe Customer ID更新テスト"""
    office = await office_factory()

    # Billing作成
    billing = await crud.billing.create_for_office(
        db=db_session,
        office_id=office.id
    )
    await db_session.commit()

    assert billing.stripe_customer_id is None

    # Stripe Customer IDを更新
    updated_billing = await crud.billing.update_stripe_customer(
        db=db_session,
        billing_id=billing.id,
        stripe_customer_id="cus_new_456"
    )

    assert updated_billing.stripe_customer_id == "cus_new_456"


async def test_update_stripe_subscription(
    db_session: AsyncSession,
    office_factory
) -> None:
    """Stripe Subscription情報更新テスト"""
    office = await office_factory()

    # Billing作成
    billing = await crud.billing.create_for_office(
        db=db_session,
        office_id=office.id
    )
    await db_session.commit()

    # Stripe Subscription情報を更新
    subscription_start = datetime.utcnow()
    next_billing = subscription_start + timedelta(days=30)

    updated_billing = await crud.billing.update_stripe_subscription(
        db=db_session,
        billing_id=billing.id,
        stripe_subscription_id="sub_test_789",
        subscription_start_date=subscription_start,
        next_billing_date=next_billing
    )

    assert updated_billing.stripe_subscription_id == "sub_test_789"
    assert updated_billing.subscription_start_date is not None
    assert updated_billing.next_billing_date is not None


async def test_record_payment(
    db_session: AsyncSession,
    office_factory
) -> None:
    """支払い記録更新テスト（trial期間終了後）"""
    office = await office_factory()

    # Billing作成（past_due状態、trial期間終了）
    now = datetime.now(timezone.utc)
    billing_data = BillingCreate(
        office_id=office.id,
        billing_status=BillingStatus.past_due,
        trial_start_date=now - timedelta(days=190),
        trial_end_date=now - timedelta(days=10),  # 10日前に終了
        current_plan_amount=6000
    )
    billing = await crud.billing.create(db=db_session, obj_in=billing_data)
    await db_session.commit()

    assert billing.billing_status == BillingStatus.past_due
    assert billing.last_payment_date is None

    # 支払い記録
    payment_date = now
    updated_billing = await crud.billing.record_payment(
        db=db_session,
        billing_id=billing.id,
        payment_date=payment_date
    )

    # Trial期間終了後なので active になる
    assert updated_billing.billing_status == BillingStatus.active
    assert updated_billing.last_payment_date is not None


async def test_billing_cascade_delete(
    db_session: AsyncSession,
    office_factory
) -> None:
    """Office削除時にBillingもカスケード削除されることを確認"""
    office = await office_factory()

    # Billing作成
    billing = await crud.billing.create_for_office(
        db=db_session,
        office_id=office.id
    )
    await db_session.commit()

    billing_id = billing.id

    # Officeを削除
    await crud.office.remove(db=db_session, id=office.id)
    await db_session.commit()

    # Billingも削除されているか確認
    deleted_billing = await crud.billing.get(db=db_session, id=billing_id)
    assert deleted_billing is None


# ==========================================
# early_payment 機能のテスト
# ==========================================

async def test_create_billing_with_early_payment_status(
    db_session: AsyncSession,
    office_factory
) -> None:
    """early_payment状態のBillingが作成できることを確認"""
    office = await office_factory()

    # early_payment状態のBilling作成
    now = datetime.now(timezone.utc)
    billing_data = BillingCreate(
        office_id=office.id,
        billing_status=BillingStatus.early_payment,
        stripe_customer_id="cus_early_123",
        stripe_subscription_id="sub_early_456",
        trial_start_date=now,
        trial_end_date=now + timedelta(days=90),  # 残り90日
        subscription_start_date=now,
        current_plan_amount=6000
    )
    billing = await crud.billing.create(db=db_session, obj_in=billing_data)
    await db_session.commit()

    assert billing.id is not None
    assert billing.billing_status == BillingStatus.early_payment
    assert billing.stripe_customer_id == "cus_early_123"
    assert billing.stripe_subscription_id == "sub_early_456"
    assert billing.trial_end_date is not None


async def test_update_status_from_free_to_early_payment(
    db_session: AsyncSession,
    office_factory
) -> None:
    """freeからearly_paymentへのステータス更新テスト"""
    office = await office_factory()

    # Billing作成（free、トライアル期間180日）
    billing = await crud.billing.create_for_office(
        db=db_session,
        office_id=office.id,
        trial_days=180
    )
    await db_session.commit()

    assert billing.billing_status == BillingStatus.free
    initial_trial_end = billing.trial_end_date

    # early_paymentに更新（無料期間中に課金設定完了）
    updated_billing = await crud.billing.update_status(
        db=db_session,
        billing_id=billing.id,
        status=BillingStatus.early_payment
    )

    assert updated_billing.billing_status == BillingStatus.early_payment
    # トライアル終了日は変更されない
    assert updated_billing.trial_end_date == initial_trial_end


async def test_update_status_from_early_payment_to_active(
    db_session: AsyncSession,
    office_factory
) -> None:
    """early_paymentからactiveへのステータス更新テスト（トライアル期限経過後）"""
    office = await office_factory()

    # early_payment状態のBilling作成（トライアル期限が過去）
    now = datetime.now(timezone.utc)
    past_date = now - timedelta(days=1)
    billing_data = BillingCreate(
        office_id=office.id,
        billing_status=BillingStatus.early_payment,
        stripe_customer_id="cus_early_789",
        stripe_subscription_id="sub_early_101",
        trial_start_date=now - timedelta(days=181),
        trial_end_date=past_date,  # トライアル期限が過去
        subscription_start_date=now - timedelta(days=90),
        current_plan_amount=6000
    )
    billing = await crud.billing.create(db=db_session, obj_in=billing_data)
    await db_session.commit()

    assert billing.billing_status == BillingStatus.early_payment
    assert billing.trial_end_date < datetime.now(timezone.utc)

    # activeに更新（トライアル期限経過後の自動遷移を想定）
    updated_billing = await crud.billing.update_status(
        db=db_session,
        billing_id=billing.id,
        status=BillingStatus.active
    )

    assert updated_billing.billing_status == BillingStatus.active


async def test_early_payment_with_subscription_update(
    db_session: AsyncSession,
    office_factory
) -> None:
    """early_payment状態でのSubscription情報更新テスト"""
    office = await office_factory()

    # free状態のBilling作成
    billing = await crud.billing.create_for_office(
        db=db_session,
        office_id=office.id,
        trial_days=120  # 残り120日
    )
    await db_session.commit()

    # Subscription情報を更新（課金設定完了）
    subscription_start = datetime.now(timezone.utc)
    next_billing = billing.trial_end_date + timedelta(days=1)  # トライアル終了翌日

    updated_billing = await crud.billing.update_stripe_subscription(
        db=db_session,
        billing_id=billing.id,
        stripe_subscription_id="sub_early_new",
        subscription_start_date=subscription_start,
        next_billing_date=next_billing
    )

    # Subscription情報が更新されていることを確認
    assert updated_billing.stripe_subscription_id == "sub_early_new"
    # タイムゾーン情報が異なる可能性があるため、時刻だけを比較
    assert updated_billing.subscription_start_date.replace(tzinfo=None) == subscription_start.replace(tzinfo=None)
    assert updated_billing.next_billing_date.replace(tzinfo=None) == next_billing.replace(tzinfo=None)

    # この時点でステータスをearly_paymentに更新
    final_billing = await crud.billing.update_status(
        db=db_session,
        billing_id=billing.id,
        status=BillingStatus.early_payment
    )

    assert final_billing.billing_status == BillingStatus.early_payment
    assert final_billing.stripe_subscription_id == "sub_early_new"


# ==========================================
# record_payment() の trial期間対応テスト
# ==========================================

async def test_record_payment_during_trial_period(
    db_session: AsyncSession,
    office_factory
) -> None:
    """
    Trial期間中の支払い記録 → early_payment

    初回課金時にinvoice.payment_succeededが送信された場合、
    trial期間中ならearly_paymentになるべき
    """
    office = await office_factory()

    # Billing作成（free、trial期間中）
    now = datetime.now(timezone.utc)
    billing_data = BillingCreate(
        office_id=office.id,
        billing_status=BillingStatus.free,
        trial_start_date=now,
        trial_end_date=now + timedelta(days=90),  # 残り90日
        current_plan_amount=6000
    )
    billing = await crud.billing.create(db=db_session, obj_in=billing_data)
    await db_session.commit()

    assert billing.billing_status == BillingStatus.free
    assert billing.trial_end_date > now

    # 支払い記録（trial期間中）
    payment_date = now
    updated_billing = await crud.billing.record_payment(
        db=db_session,
        billing_id=billing.id,
        payment_date=payment_date
    )

    # Trial期間中なので early_payment になる
    assert updated_billing.billing_status == BillingStatus.early_payment
    assert updated_billing.last_payment_date is not None


async def test_record_payment_after_trial_period(
    db_session: AsyncSession,
    office_factory
) -> None:
    """
    Trial期間終了後の支払い記録 → active

    trial_end_date が過去の場合は active になるべき
    """
    office = await office_factory()

    # Billing作成（free、trial期間終了）
    now = datetime.now(timezone.utc)
    billing_data = BillingCreate(
        office_id=office.id,
        billing_status=BillingStatus.free,
        trial_start_date=now - timedelta(days=190),
        trial_end_date=now - timedelta(days=1),  # 1日前に終了
        current_plan_amount=6000
    )
    billing = await crud.billing.create(db=db_session, obj_in=billing_data)
    await db_session.commit()

    assert billing.billing_status == BillingStatus.free
    assert billing.trial_end_date < now

    # 支払い記録（trial期間終了後）
    payment_date = now
    updated_billing = await crud.billing.record_payment(
        db=db_session,
        billing_id=billing.id,
        payment_date=payment_date
    )

    # Trial期間終了後なので active になる
    assert updated_billing.billing_status == BillingStatus.active
    assert updated_billing.last_payment_date is not None


async def test_record_payment_from_past_due_during_trial(
    db_session: AsyncSession,
    office_factory
) -> None:
    """
    past_due状態からの支払い記録（trial期間中） → early_payment

    past_due から復旧する場合でも、trial期間中ならearly_paymentになるべき
    """
    office = await office_factory()

    # Billing作成（past_due、trial期間中）
    now = datetime.now(timezone.utc)
    billing_data = BillingCreate(
        office_id=office.id,
        billing_status=BillingStatus.past_due,
        trial_start_date=now,
        trial_end_date=now + timedelta(days=60),  # 残り60日
        current_plan_amount=6000
    )
    billing = await crud.billing.create(db=db_session, obj_in=billing_data)
    await db_session.commit()

    assert billing.billing_status == BillingStatus.past_due
    assert billing.trial_end_date > now

    # 支払い記録（trial期間中）
    payment_date = now
    updated_billing = await crud.billing.record_payment(
        db=db_session,
        billing_id=billing.id,
        payment_date=payment_date
    )

    # Trial期間中なので early_payment になる
    assert updated_billing.billing_status == BillingStatus.early_payment
    assert updated_billing.last_payment_date is not None
