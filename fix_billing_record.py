"""
Billing レコード手動修正スクリプト

Webhook未処理により stripe_subscription_id が空のままになっている
billingレコードを手動で修正します。

使用方法:
    python fix_billing_record.py

対象:
    - billing_id: daae3740-ee95-4967-a34d-9eca0d487dc9
    - stripe_subscription_id: sub_1SeTwqBzu2Qn9OhyvVYRyZGL
    - 期待されるbilling_status: early_payment
"""
import asyncio
from datetime import datetime, timezone
from uuid import UUID

from app.db.session import AsyncSessionLocal
from app import crud
from app.models.enums import BillingStatus


async def fix_billing_record():
    """
    Webhook未処理のbillingレコードを手動で修正
    """
    billing_id = UUID("daae3740-ee95-4967-a34d-9eca0d487dc9")
    stripe_subscription_id = "sub_1SeTwqBzu2Qn9OhyvVYRyZGL"

    async with AsyncSessionLocal() as db:
        try:
            # billing レコードを取得
            billing = await crud.billing.get(db=db, id=billing_id)

            if not billing:
                print(f"❌ Billing record not found: {billing_id}")
                return

            # billing_statusの値を安全に取得
            billing_status_value = billing.billing_status.value if hasattr(billing.billing_status, 'value') else billing.billing_status

            print("=" * 60)
            print("📋 Current state:")
            print("=" * 60)
            print(f"   - billing_id: {billing.id}")
            print(f"   - office_id: {billing.office_id}")
            print(f"   - stripe_customer_id: {billing.stripe_customer_id}")
            print(f"   - stripe_subscription_id: {billing.stripe_subscription_id or '(empty)'}")
            print(f"   - billing_status: {billing_status_value}")
            print(f"   - subscription_start_date: {billing.subscription_start_date or '(not set)'}")
            print(f"   - trial_end_date: {billing.trial_end_date}")
            print()

            # 既に更新済みかチェック
            if billing.stripe_subscription_id == stripe_subscription_id:
                print("✅ Already fixed! No action needed.")
                print(f"   - stripe_subscription_id is already set to: {stripe_subscription_id}")
                return

            # 確認メッセージ
            print("🔧 Applying fix...")
            print(f"   - Setting stripe_subscription_id to: {stripe_subscription_id}")
            print(f"   - Setting billing_status to: early_payment")
            print(f"   - Setting subscription_start_date to: {datetime.now(timezone.utc)}")
            print()

            # stripe_subscription_idを更新
            await crud.billing.update_stripe_subscription(
                db=db,
                billing_id=billing_id,
                stripe_subscription_id=stripe_subscription_id,
                subscription_start_date=datetime.now(timezone.utc)
            )

            # billing_statusを early_payment に更新
            # (無料期間中にサブスクリプション登録したため)
            await crud.billing.update_status(
                db=db,
                billing_id=billing_id,
                status=BillingStatus.early_payment
            )

            await db.commit()

            # 更新後の状態を確認
            await db.refresh(billing)

            # billing_statusの値を安全に取得
            updated_billing_status = billing.billing_status.value if hasattr(billing.billing_status, 'value') else billing.billing_status

            print("=" * 60)
            print("✅ Update completed successfully!")
            print("=" * 60)
            print(f"   - billing_id: {billing.id}")
            print(f"   - stripe_customer_id: {billing.stripe_customer_id}")
            print(f"   - stripe_subscription_id: {billing.stripe_subscription_id}")
            print(f"   - billing_status: {updated_billing_status}")
            print(f"   - subscription_start_date: {billing.subscription_start_date}")
            print(f"   - trial_end_date: {billing.trial_end_date}")
            print()
            print("🎉 Billing record has been fixed!")
            print()
            print("📝 Next steps:")
            print("   1. Verify in DB: SELECT * FROM billings WHERE id = 'daae3740-ee95-4967-a34d-9eca0d487dc9';")
            print("   2. Test API: GET /api/v1/billing/status")
            print("   3. Check frontend: http://localhost:3000/admin/plan")

        except Exception as e:
            await db.rollback()
            print("=" * 60)
            print("❌ Error occurred during fix:")
            print("=" * 60)
            print(f"   {type(e).__name__}: {e}")
            print()
            raise


if __name__ == "__main__":
    print()
    print("🚀 Starting billing record fix...")
    print()
    asyncio.run(fix_billing_record())
