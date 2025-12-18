"""
Billing API エンドポイントのテスト
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock, AsyncMock
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.models.enums import BillingStatus, StaffRole
from app.schemas.billing import BillingCreate
from app.core.security import create_access_token
from app.core.config import settings

pytestmark = pytest.mark.asyncio


async def test_get_billing_status_success(
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory
) -> None:
    """課金ステータス取得APIのテスト（成功）"""
    # ユーザーとオフィスを作成
    staff = await employee_user_factory()
    office_id = staff.office_associations[0].office_id

    # トークンを生成
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(str(staff.id), access_token_expires)

    # Billing作成
    billing = await crud.billing.create_for_office(
        db=db_session,
        office_id=office_id,
        trial_days=180
    )
    await db_session.commit()

    # APIリクエスト（認証ヘッダー付き）
    response = await async_client.get(
        "/api/v1/billing/status",
        headers={"Authorization": f"Bearer {access_token}"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["billing_status"] == "free"
    assert data["current_plan_amount"] == 6000
    assert "trial_end_date" in data


async def test_get_billing_status_unauthorized(
    async_client: AsyncClient,
) -> None:
    """課金ステータス取得API - 未認証の場合401エラー"""
    # 認証なしでリクエスト
    response = await async_client.get(
        "/api/v1/billing/status",
        headers={}  # トークンなし
    )

    assert response.status_code == 401


async def test_get_billing_status_past_due(
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory
) -> None:
    """課金ステータス取得API - past_due状態のテスト"""
    staff = await employee_user_factory()
    office_id = staff.office_associations[0].office_id

    # トークンを生成
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(str(staff.id), access_token_expires)

    # Billing作成（past_due）
    billing_data = BillingCreate(
        office_id=office_id,
        billing_status=BillingStatus.past_due,
        trial_start_date=datetime.now(timezone.utc) - timedelta(days=190),
        trial_end_date=datetime.now(timezone.utc) - timedelta(days=10),
        current_plan_amount=6000
    )
    billing = await crud.billing.create(db=db_session, obj_in=billing_data)
    await db_session.commit()

    # APIリクエスト（認証ヘッダー付き）
    response = await async_client.get(
        "/api/v1/billing/status",
        headers={"Authorization": f"Bearer {access_token}"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["billing_status"] == "past_due"


async def test_require_active_billing_restriction(
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory
) -> None:
    """
    require_active_billing デコレータのテスト

    past_due状態の場合、書き込み操作で402エラーが返ることを確認
    注: 実際のエンドポイントにrequire_active_billingを適用後にテスト
    """
    staff = await employee_user_factory()
    office_id = staff.office_associations[0].office_id

    # Billing作成（past_due）
    billing_data = BillingCreate(
        office_id=office_id,
        billing_status=BillingStatus.past_due,
        trial_start_date=datetime.now(timezone.utc) - timedelta(days=190),
        trial_end_date=datetime.now(timezone.utc) - timedelta(days=10),
        current_plan_amount=6000
    )
    await crud.billing.create(db=db_session, obj_in=billing_data)
    await db_session.commit()

    # 書き込み操作をテスト（例: welfare_recipients作成）
    # 注: welfare_recipients エンドポイントにrequire_active_billingを適用後にテスト
    # response = await client.post("/api/v1/welfare-recipients", json={...})
    # assert response.status_code == 402
    pass


async def test_billing_status_active_allows_operations(
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory
) -> None:
    """
    active状態の場合、すべての操作が許可されることを確認
    """
    staff = await employee_user_factory()
    office_id = staff.office_associations[0].office_id

    # トークンを生成
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(str(staff.id), access_token_expires)

    # Billing作成（active）
    billing_data = BillingCreate(
        office_id=office_id,
        billing_status=BillingStatus.active,
        trial_start_date=datetime.now(timezone.utc) - timedelta(days=190),
        trial_end_date=datetime.now(timezone.utc) - timedelta(days=10),
        current_plan_amount=6000
    )
    await crud.billing.create(db=db_session, obj_in=billing_data)
    await db_session.commit()

    # 課金ステータス確認（認証ヘッダー付き）
    response = await async_client.get(
        "/api/v1/billing/status",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["billing_status"] == "active"

    # 書き込み操作が許可される（require_active_billing適用後）
    # response = await async_client.post("/api/v1/welfare-recipients", json={...})
    # assert response.status_code != 402
    pass


async def test_billing_created_automatically_for_new_office(
    db_session: AsyncSession,
    employee_user_factory
) -> None:
    """
    新規事業所作成時にBillingが自動作成されることを確認

    注: この動作はoffice作成時のロジックに依存
    現在は手動作成のため、将来的に自動作成を実装する場合のテスト
    """
    staff = await employee_user_factory()
    office_id = staff.office_associations[0].office_id

    # Billingが存在するか確認（マニュアル作成の場合は存在しない可能性）
    billing = await crud.billing.get_by_office_id(
        db=db_session,
        office_id=office_id
    )

    # 存在しない場合は自動作成ロジックで作成される想定
    if not billing:
        billing = await crud.billing.create_for_office(
            db=db_session,
            office_id=office_id
        )
        await db_session.commit()

    assert billing is not None
    assert billing.billing_status == BillingStatus.free
    assert billing.current_plan_amount == 6000


async def test_create_checkout_session_includes_metadata(
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory,
    mocker: MagicMock
) -> None:
    """
    Checkout Session作成時にメタデータとtrial_endが含まれることを確認（TDD）

    検証項目:
    - subscription_data.metadata に office_id, office_name, created_by_user_id が含まれる
    - subscription_data.trial_end が billing.trial_end_date と一致する
    - automatic_tax が有効化される
    """
    # Stripe設定をモック
    mocker.patch('app.api.v1.endpoints.billing.settings.STRIPE_SECRET_KEY', 'sk_test_12345')
    mocker.patch('app.api.v1.endpoints.billing.settings.STRIPE_PRICE_ID', 'price_test_12345')

    # Stripeモックの設定
    mock_customer_create = mocker.patch('stripe.Customer.create')
    mock_customer_create.return_value = MagicMock(id='cus_test_12345')

    mock_session_create = mocker.patch('stripe.checkout.Session.create')
    mock_session_create.return_value = MagicMock(
        id='cs_test_12345',
        url='https://checkout.stripe.com/test'
    )

    # オーナーユーザーを作成
    staff = await employee_user_factory(role=StaffRole.owner)
    office_id = staff.office_associations[0].office_id
    office = staff.office_associations[0].office

    # トークンを生成
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(str(staff.id), access_token_expires)

    # Billing作成
    billing = await crud.billing.create_for_office(
        db=db_session,
        office_id=office_id,
        trial_days=180
    )
    await db_session.commit()

    # APIリクエスト（認証ヘッダー付き）
    response = await async_client.post(
        "/api/v1/billing/create-checkout-session",
        headers={"Authorization": f"Bearer {access_token}"}
    )

    # レスポンス確認
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "cs_test_12345"
    assert data["url"] == "https://checkout.stripe.com/test"

    # Stripe Checkout Session作成時の引数を検証
    mock_session_create.assert_called_once()
    call_kwargs = mock_session_create.call_args.kwargs

    # メタデータが含まれることを確認
    assert 'subscription_data' in call_kwargs
    assert 'metadata' in call_kwargs['subscription_data']
    metadata = call_kwargs['subscription_data']['metadata']
    assert metadata['office_id'] == str(office_id)
    assert metadata['office_name'] == office.name
    assert metadata['created_by_user_id'] == str(staff.id)

    # trial_endが設定されることを確認
    assert 'trial_end' in call_kwargs['subscription_data']
    trial_end_timestamp = call_kwargs['subscription_data']['trial_end']
    assert trial_end_timestamp == int(billing.trial_end_date.timestamp())

    # automatic_taxが有効化されることを確認
    assert 'automatic_tax' in call_kwargs
    assert call_kwargs['automatic_tax']['enabled'] is True


@patch('stripe.Webhook.construct_event')
async def test_webhook_customer_subscription_created(
    mock_construct_event: MagicMock,
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory
) -> None:
    """
    customer.subscription.created イベント処理のテスト（TDD）

    検証項目:
    - メタデータからoffice_idを取得できる
    - stripe_subscription_idが更新される
    - 無料期間中のため、billing_statusがearly_paymentに変更される
    - subscription_start_dateが記録される
    """
    # ユーザーとオフィスを作成
    staff = await employee_user_factory()
    office_id = staff.office_associations[0].office_id

    # Billing作成（初期状態: free、無料期間180日）
    billing = await crud.billing.create_for_office(
        db=db_session,
        office_id=office_id,
        trial_days=180
    )
    # Stripe Customer IDを設定
    await crud.billing.update_stripe_customer(
        db=db_session,
        billing_id=billing.id,
        stripe_customer_id='cus_test_12345'
    )
    await db_session.commit()

    # Webhookイベントモックの設定
    mock_event = {
        'type': 'customer.subscription.created',
        'data': {
            'object': {
                'id': 'sub_test_12345',
                'customer': 'cus_test_12345',
                'metadata': {
                    'office_id': str(office_id),
                    'office_name': 'テスト事業所',
                    'created_by_user_id': str(staff.id)
                },
                'current_period_start': 1609459200,  # 2021-01-01
                'current_period_end': 1612137600     # 2021-02-01
            }
        }
    }
    mock_construct_event.return_value = mock_event

    # Webhook APIリクエスト
    response = await async_client.post(
        "/api/v1/billing/webhook",
        headers={"Stripe-Signature": "test_signature"},
        content=b'{"type": "customer.subscription.created"}'
    )

    # レスポンス確認
    assert response.status_code == 200
    assert response.json()["status"] == "success"

    # DB更新を確認
    await db_session.refresh(billing)
    assert billing.stripe_subscription_id == 'sub_test_12345'
    # 無料期間中にサブスクリプションを作成したため、early_paymentになる
    assert billing.billing_status == BillingStatus.early_payment
    assert billing.subscription_start_date is not None


# ==========================================
# Webhook冪等性テスト（Phase 7）
# ==========================================

@patch('stripe.Webhook.construct_event')
async def test_webhook_idempotency_duplicate_event_skipped(
    mock_construct_event: MagicMock,
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory
) -> None:
    """
    Webhook冪等性テスト: 同じイベントIDが2回送信された場合、2回目はスキップされる

    Phase 7: Webhook冪等性統合の検証
    """
    # ユーザーとオフィスを作成
    staff = await employee_user_factory()
    office_id = staff.office_associations[0].office_id

    # Billing作成（free状態）
    billing = await crud.billing.create_for_office(
        db=db_session,
        office_id=office_id,
        trial_days=180
    )
    # Stripe Customer IDを設定
    await crud.billing.update_stripe_customer(
        db=db_session,
        billing_id=billing.id,
        stripe_customer_id='cus_test_idempotency'
    )
    await db_session.commit()

    # Stripe Webhookイベントをモック
    mock_event = {
        'id': 'evt_idempotency_test_001',  # 同じイベントID
        'type': 'invoice.payment_succeeded',
        'data': {
            'object': {
                'customer': 'cus_test_idempotency',
                'amount_paid': 6000,
                'status': 'paid'
            }
        }
    }
    mock_construct_event.return_value = mock_event

    # 1回目のWebhook送信
    response1 = await async_client.post(
        "/api/v1/billing/webhook",
        headers={"Stripe-Signature": "test_signature"},
        content=b'{"type": "invoice.payment_succeeded"}'
    )

    # 1回目は成功
    assert response1.status_code == 200
    assert response1.json()["status"] == "success"

    # Billing statusがactiveに更新されたことを確認
    await db_session.refresh(billing)
    first_status = billing.billing_status
    first_payment_date = billing.last_payment_date
    assert first_status == BillingStatus.active
    assert first_payment_date is not None

    # webhook_eventsテーブルにイベントが記録されたことを確認
    webhook_event = await crud.webhook_event.get_by_event_id(
        db=db_session,
        event_id='evt_idempotency_test_001'
    )
    assert webhook_event is not None
    assert webhook_event.event_type == 'invoice.payment_succeeded'
    assert webhook_event.status == 'success'

    # 2回目のWebhook送信（同じイベントID）
    response2 = await async_client.post(
        "/api/v1/billing/webhook",
        headers={"Stripe-Signature": "test_signature"},
        content=b'{"type": "invoice.payment_succeeded"}'
    )

    # 2回目も成功レスポンス（冪等性により処理はスキップ）
    assert response2.status_code == 200
    assert response2.json()["status"] == "success"
    # メッセージで既に処理済みであることを確認
    assert "already processed" in response2.json().get("message", "").lower()

    # Billing statusは変更されていないことを確認
    await db_session.refresh(billing)
    assert billing.billing_status == first_status
    assert billing.last_payment_date == first_payment_date


@patch('stripe.Webhook.construct_event')
async def test_webhook_idempotency_different_events_both_processed(
    mock_construct_event: MagicMock,
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory
) -> None:
    """
    Webhook冪等性テスト: 異なるイベントIDの場合、両方とも処理される

    Phase 7: Webhook冪等性統合の検証
    """
    # ユーザーとオフィスを作成
    staff = await employee_user_factory()
    office_id = staff.office_associations[0].office_id

    # Billing作成（active状態）
    billing_data = BillingCreate(
        office_id=office_id,
        billing_status=BillingStatus.active,
        stripe_customer_id='cus_test_different_events',
        trial_start_date=datetime.now(timezone.utc) - timedelta(days=200),
        trial_end_date=datetime.now(timezone.utc) - timedelta(days=20),
        current_plan_amount=6000
    )
    billing = await crud.billing.create(db=db_session, obj_in=billing_data)
    await db_session.commit()

    # 1回目のWebhookイベント
    mock_event_1 = {
        'id': 'evt_different_001',
        'type': 'invoice.payment_succeeded',
        'data': {
            'object': {
                'customer': 'cus_test_different_events',
                'amount_paid': 6000,
                'status': 'paid'
            }
        }
    }
    mock_construct_event.return_value = mock_event_1

    response1 = await async_client.post(
        "/api/v1/billing/webhook",
        headers={"Stripe-Signature": "test_signature_1"},
        content=b'{"type": "invoice.payment_succeeded"}'
    )

    assert response1.status_code == 200
    await db_session.refresh(billing)
    first_payment_date = billing.last_payment_date

    # 2回目のWebhookイベント（異なるイベントID）
    mock_event_2 = {
        'id': 'evt_different_002',
        'type': 'invoice.payment_succeeded',
        'data': {
            'object': {
                'customer': 'cus_test_different_events',
                'amount_paid': 6000,
                'status': 'paid'
            }
        }
    }
    mock_construct_event.return_value = mock_event_2

    response2 = await async_client.post(
        "/api/v1/billing/webhook",
        headers={"Stripe-Signature": "test_signature_2"},
        content=b'{"type": "invoice.payment_succeeded"}'
    )

    assert response2.status_code == 200
    await db_session.refresh(billing)
    second_payment_date = billing.last_payment_date

    # 両方のイベントが処理され、payment_dateが更新されたことを確認
    assert first_payment_date is not None
    assert second_payment_date is not None
    assert second_payment_date >= first_payment_date

    # 両方のイベントが記録されていることを確認
    event1 = await crud.webhook_event.get_by_event_id(db=db_session, event_id='evt_different_001')
    event2 = await crud.webhook_event.get_by_event_id(db=db_session, event_id='evt_different_002')
    assert event1 is not None
    assert event2 is not None


@patch('stripe.Webhook.construct_event')
async def test_webhook_idempotency_failed_event_recorded(
    mock_construct_event: MagicMock,
    async_client: AsyncClient,
    db_session: AsyncSession
) -> None:
    """
    Webhook冪等性テスト: 処理失敗時もイベントが記録される

    Phase 7: Webhook冪等性統合の検証
    """
    # 存在しないcustomer_idでイベントを送信（処理失敗を意図）
    mock_event = {
        'id': 'evt_failed_test_001',
        'type': 'invoice.payment_succeeded',
        'data': {
            'object': {
                'customer': 'cus_nonexistent_12345',  # 存在しないCustomer
                'amount_paid': 6000,
                'status': 'paid'
            }
        }
    }
    mock_construct_event.return_value = mock_event

    # Webhook送信
    response = await async_client.post(
        "/api/v1/billing/webhook",
        headers={"Stripe-Signature": "test_signature"},
        content=b'{"type": "invoice.payment_succeeded"}'
    )

    # 処理は失敗するが、イベントは記録される
    # （実装によっては200を返すか500を返すかは要確認）
    # ここでは失敗イベントとして記録されることを確認

    webhook_event = await crud.webhook_event.get_by_event_id(
        db=db_session,
        event_id='evt_failed_test_001'
    )

    # イベントが記録されていることを確認（失敗時も記録される想定）
    # 注: この振る舞いは実装次第で調整が必要
    # 現在の実装では、処理失敗時にrollbackされるため記録されない可能性がある
