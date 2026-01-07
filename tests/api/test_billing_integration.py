"""
Billing API 統合テスト（実際のStripe APIを使用）

注意: このテストは実際のStripe APIを呼び出すため、
STRIPE_SECRET_KEY、STRIPE_PRICE_ID、STRIPE_WEBHOOK_SECRET が必要です。
"""
from datetime import datetime, timedelta
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
import stripe

from app import crud
from app.models.enums import BillingStatus, StaffRole
from app.core.security import create_access_token
from app.core.config import settings

pytestmark = pytest.mark.asyncio


@pytest.mark.skipif(
    not settings.STRIPE_SECRET_KEY or not settings.STRIPE_PRICE_ID or
    (settings.STRIPE_SECRET_KEY and not settings.STRIPE_SECRET_KEY.get_secret_value().startswith("sk_test_")),
    reason="Stripe環境変数が設定されていないか、テストモードではありません"
)
async def test_create_checkout_session_with_real_stripe_api(
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory
) -> None:
    """
    実際のStripe APIを使用してCheckout Session作成をテスト

    このテストは実際にStripeにリクエストを送信します。
    注意: ライブモードのAPIキーではスキップされます。
    """
    # オーナーユーザーを作成
    staff = await employee_user_factory(role=StaffRole.owner)
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

    # APIリクエスト（実際のStripe APIが呼ばれる）
    response = await async_client.post(
        "/api/v1/billing/create-checkout-session",
        headers={"Authorization": f"Bearer {access_token}"}
    )

    # レスポンス確認
    assert response.status_code == 200
    data = response.json()

    # Stripe Checkout SessionのIDとURLが返される
    assert "session_id" in data
    assert data["session_id"].startswith("cs_test_")
    assert "url" in data
    assert "checkout.stripe.com" in data["url"]

    # Stripeから実際のセッション情報を取得して検証
    session = stripe.checkout.Session.retrieve(
        data["session_id"],
        expand=["subscription"]  # Subscription情報を展開して取得
    )

    # Checkout Sessionの基本情報を検証
    assert session.mode == "subscription"
    assert session.status in ["open", "complete"]

    # automatic_taxが有効化されているか確認
    assert session.automatic_tax is not None
    assert session.automatic_tax["enabled"] is True

    # 注: subscription_data, customer_updateは作成時のパラメータで、
    # レスポンスには含まれません。メタデータとtrial_endの検証は、
    # 実際にSubscriptionが作成された後にSubscription objectから確認する必要があります

    # Stripeカスタマーが作成されているか確認
    assert session.customer is not None
    assert session.customer.startswith("cus_")

    # DBにStripe Customer IDが保存されているか確認
    await db_session.refresh(billing)
    assert billing.stripe_customer_id == session.customer

    # クリーンアップ: テスト用のStripeリソースを削除
    try:
        stripe.Customer.delete(session.customer)
    except Exception as e:
        print(f"クリーンアップエラー: {e}")


@pytest.mark.skipif(
    not settings.STRIPE_SECRET_KEY,
    reason="Stripe環境変数が設定されていません"
)
async def test_webhook_signature_verification_with_real_secret(
    async_client: AsyncClient,
    db_session: AsyncSession,
    employee_user_factory
) -> None:
    """
    実際のSTRIPE_WEBHOOK_SECRETを使用してWebhook署名検証をテスト

    このテストは実際の署名検証ロジックを検証します。
    """
    # ユーザーとオフィスを作成
    staff = await employee_user_factory()
    office_id = staff.office_associations[0].office_id

    # Billing作成
    billing = await crud.billing.create_for_office(
        db=db_session,
        office_id=office_id,
        trial_days=180
    )
    # Stripe Customer IDを設定
    await crud.billing.update_stripe_customer(
        db=db_session,
        billing_id=billing.id,
        stripe_customer_id='cus_test_integration'
    )
    await db_session.commit()

    # 実際のStripe Webhookイベントペイロードを構築
    import json
    import time

    event_payload = {
        "id": "evt_test_webhook",
        "object": "event",
        "api_version": "2023-10-16",
        "created": int(time.time()),
        "type": "customer.subscription.created",
        "data": {
            "object": {
                "id": "sub_test_integration",
                "object": "subscription",
                "customer": "cus_test_integration",
                "metadata": {
                    "office_id": str(office_id),
                    "office_name": "テスト事業所",
                    "created_by_user_id": str(staff.id)
                },
                "current_period_start": int(time.time()),
                "current_period_end": int(time.time()) + 2592000  # +30日
            }
        }
    }

    payload_json = json.dumps(event_payload)

    # Stripe署名を生成（実際のSTRIPE_WEBHOOK_SECRETを使用）
    if settings.STRIPE_WEBHOOK_SECRET:
        timestamp = int(time.time())
        signed_payload = f"{timestamp}.{payload_json}"

        import hmac
        import hashlib
        secret = settings.STRIPE_WEBHOOK_SECRET.get_secret_value()
        signature = hmac.new(
            secret.encode('utf-8'),
            signed_payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        stripe_signature = f"t={timestamp},v1={signature}"

        # Webhook APIリクエスト（実際の署名検証が行われる）
        response = await async_client.post(
            "/api/v1/billing/webhook",
            headers={"Stripe-Signature": stripe_signature},
            content=payload_json.encode('utf-8')
        )

        # レスポンス確認
        assert response.status_code == 200
        assert response.json()["status"] == "success"

        # DB更新を確認
        await db_session.refresh(billing)
        assert billing.stripe_subscription_id == "sub_test_integration"
        # 無料期間中にサブスクリプション作成 → early_payment
        assert billing.billing_status == BillingStatus.early_payment
        assert billing.subscription_start_date is not None
    else:
        pytest.skip("STRIPE_WEBHOOK_SECRETが設定されていません")


@pytest.mark.skipif(
    not settings.STRIPE_SECRET_KEY,
    reason="Stripe環境変数が設定されていません"
)
async def test_invalid_webhook_signature_rejected(
    async_client: AsyncClient
) -> None:
    """
    無効な署名のWebhookが拒否されることを確認
    """
    import json
    import time

    event_payload = {
        "id": "evt_test_invalid",
        "type": "customer.subscription.created",
        "data": {"object": {}}
    }

    # 無効な署名
    invalid_signature = f"t={int(time.time())},v1=invalid_signature_12345"

    response = await async_client.post(
        "/api/v1/billing/webhook",
        headers={"Stripe-Signature": invalid_signature},
        content=json.dumps(event_payload).encode('utf-8')
    )

    # 400エラーが返されることを確認
    assert response.status_code == 400
    assert "Invalid signature" in response.json()["detail"]
