"""
バッチ処理の発動条件を作り出すスクリプト

使い方:
1. 既存のBillingデータを確認:
   docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py list

2. 期限を1分後に設定（期限超過を作り出す）:
   docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py expire --billing-id <billing_id> --minutes 1

3. 期限を未来に戻す（リセット）:
   docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py reset --billing-id <billing_id>

4. バッチ処理が発動するか確認:
   docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py check
"""
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from uuid import UUID

sys.path.insert(0, '/app')

from app.db.session import AsyncSessionLocal
from app import crud
from app.models.billing import Billing
from app.models.enums import BillingStatus


async def list_billings():
    """既存のBillingデータを一覧表示"""
    async with AsyncSessionLocal() as db:
        try:
            print(f"\n{'='*80}")
            print(f"既存Billingデータ一覧")
            print(f"{'='*80}\n")

            # すべてのBillingを取得
            result = await db.execute(
                select(Billing).order_by(Billing.created_at.desc()).limit(20)
            )
            billings = result.scalars().all()

            if not billings:
                print("⚠️  Billingデータが見つかりません")
                return

            print(f"📋 最新20件を表示\n")

            for i, billing in enumerate(billings, 1):
                now = datetime.now(timezone.utc)

                # Trial期限のステータス
                if billing.trial_end_date:
                    trial_status = "⏰ 期限切れ" if billing.trial_end_date < now else f"✅ 残り{(billing.trial_end_date - now).days}日"
                else:
                    trial_status = "N/A"

                # Cancel期限のステータス
                if billing.scheduled_cancel_at:
                    cancel_status = "⏰ 期限切れ" if billing.scheduled_cancel_at < now else f"✅ 残り{(billing.scheduled_cancel_at - now).days}日"
                else:
                    cancel_status = "N/A"

                print(f"{i}. Billing ID: {billing.id}")
                print(f"   Office ID: {billing.office_id}")
                print(f"   Status: {billing.billing_status.value}")
                print(f"   Trial End: {billing.trial_end_date.strftime('%Y-%m-%d %H:%M:%S') if billing.trial_end_date else 'N/A'} ({trial_status})")
                print(f"   Cancel At: {billing.scheduled_cancel_at.strftime('%Y-%m-%d %H:%M:%S') if billing.scheduled_cancel_at else 'N/A'} ({cancel_status})")
                print(f"   Stripe subscription_present: {bool(billing.stripe_subscription_id)}")
                print()

            print(f"{'='*80}\n")
            print("💡 使用例:")
            print(f"   # 期限を1分後に設定:")
            print(f"   docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py expire --billing-id {billings[0].id} --minutes 1")

        except Exception as e:
            print(f"❌ エラー: {e}")
            raise


async def set_expiry(billing_id: str, minutes: int):
    """
    Billingの期限を指定分後に設定（期限超過を作り出す）

    Args:
        billing_id: Billing ID
        minutes: 何分後に設定するか
    """
    async with AsyncSessionLocal() as db:
        try:
            billing_uuid = UUID(billing_id)
            billing = await crud.billing.get(db=db, id=billing_uuid)

            if not billing:
                print(f"❌ Billing ID {billing_id} が見つかりません")
                return

            now = datetime.now(timezone.utc)
            expiry_time = now + timedelta(minutes=minutes)

            print(f"\n{'='*80}")
            print(f"期限設定: {minutes}分後に期限切れ")
            print(f"{'='*80}\n")

            print(f"📋 Billing情報:")
            print(f"   Billing ID: {billing.id}")
            print(f"   Office ID: {billing.office_id}")
            print(f"   Current Status: {billing.billing_status.value}")
            print(f"   現在時刻: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            print(f"   期限時刻: {expiry_time.strftime('%Y-%m-%d %H:%M:%S %Z')}\n")

            # バッチ処理のケース判定
            if billing.billing_status == BillingStatus.free:
                # ケース1: free → past_due
                print(f"🎯 バッチ処理ケース: free → past_due")
                print(f"   trial_end_date を {expiry_time.strftime('%Y-%m-%d %H:%M:%S')} に設定\n")
                billing.trial_end_date = expiry_time
                expected = "past_due"

            elif billing.billing_status == BillingStatus.early_payment:
                # ケース2: early_payment → active
                print(f"🎯 バッチ処理ケース: early_payment → active")
                print(f"   trial_end_date を {expiry_time.strftime('%Y-%m-%d %H:%M:%S')} に設定\n")
                billing.trial_end_date = expiry_time
                expected = "active"

            elif billing.billing_status == BillingStatus.canceling:
                # ケース3: canceling → canceled
                print(f"🎯 バッチ処理ケース: canceling → canceled")
                print(f"   scheduled_cancel_at を {expiry_time.strftime('%Y-%m-%d %H:%M:%S')} に設定\n")
                billing.scheduled_cancel_at = expiry_time
                expected = "canceled"

            else:
                print(f"⚠️  このステータス（{billing.billing_status.value}）はバッチ処理の対象外です")
                print(f"   対象ステータス: free, early_payment, canceling")
                return

            await db.commit()

            print(f"{'='*80}")
            print(f"✅ 期限設定完了")
            print(f"{'='*80}\n")

            print(f"⏰ {minutes}分後にバッチ処理が発動します:")
            print(f"   期待される遷移: {billing.billing_status.value} → {expected}\n")

            print(f"🔍 バッチ処理発動条件を確認:")
            print(f"   docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py check\n")

            print(f"🔄 期限をリセット:")
            print(f"   docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py reset --billing-id {billing_id}")

        except ValueError:
            print(f"❌ 無効なBilling ID: {billing_id}")
        except Exception as e:
            await db.rollback()
            print(f"❌ エラー: {e}")
            raise


async def reset_expiry(billing_id: str):
    """
    Billingの期限を未来に戻す（リセット）

    Args:
        billing_id: Billing ID
    """
    async with AsyncSessionLocal() as db:
        try:
            billing_uuid = UUID(billing_id)
            billing = await crud.billing.get(db=db, id=billing_uuid)

            if not billing:
                print(f"❌ Billing ID {billing_id} が見つかりません")
                return

            now = datetime.now(timezone.utc)
            future_time = now + timedelta(days=90)

            print(f"\n{'='*80}")
            print(f"期限リセット: 90日後に設定")
            print(f"{'='*80}\n")

            print(f"📋 Billing情報:")
            print(f"   Billing ID: {billing.id}")
            print(f"   Office ID: {billing.office_id}")
            print(f"   Current Status: {billing.billing_status.value}")
            print(f"   現在時刻: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            print(f"   新期限: {future_time.strftime('%Y-%m-%d %H:%M:%S %Z')}\n")

            # バッチ処理のケース判定
            if billing.billing_status in [BillingStatus.free, BillingStatus.early_payment]:
                print(f"🔄 trial_end_date を未来に設定\n")
                billing.trial_end_date = future_time

            elif billing.billing_status == BillingStatus.canceling:
                print(f"🔄 scheduled_cancel_at を未来に設定\n")
                billing.scheduled_cancel_at = future_time

            else:
                print(f"⚠️  このステータス（{billing.billing_status.value}）は期限リセット不要です")
                return

            await db.commit()

            print(f"{'='*80}")
            print(f"✅ 期限リセット完了")
            print(f"{'='*80}\n")

            print(f"📊 バッチ処理は発動しません（期限まで90日）")

        except ValueError:
            print(f"❌ 無効なBilling ID: {billing_id}")
        except Exception as e:
            await db.rollback()
            print(f"❌ エラー: {e}")
            raise


async def check_batch_triggers():
    """バッチ処理が発動する条件を満たすBillingを確認"""
    async with AsyncSessionLocal() as db:
        try:
            now = datetime.now(timezone.utc)

            print(f"\n{'='*80}")
            print(f"バッチ処理発動条件チェック")
            print(f"現在時刻: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            print(f"{'='*80}\n")

            # ケース1: free → past_due
            print("1️⃣  Trial期限切れ（free → past_due）:")
            result1 = await db.execute(
                select(Billing).where(
                    Billing.billing_status == BillingStatus.free,
                    Billing.trial_end_date < now
                )
            )
            free_expired = result1.scalars().all()

            if free_expired:
                print(f"   ✅ 発動条件を満たすBilling: {len(free_expired)}件")
                for billing in free_expired[:5]:
                    print(f"      - Billing ID: {billing.id}")
                    print(f"        Trial End: {billing.trial_end_date.strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                print(f"   ⚪ 発動条件を満たすBilling: なし")
            print()

            # ケース2: early_payment → active
            print("2️⃣  Trial期限切れ（early_payment → active）:")
            result2 = await db.execute(
                select(Billing).where(
                    Billing.billing_status == BillingStatus.early_payment,
                    Billing.trial_end_date < now
                )
            )
            early_expired = result2.scalars().all()

            if early_expired:
                print(f"   ✅ 発動条件を満たすBilling: {len(early_expired)}件")
                for billing in early_expired[:5]:
                    print(f"      - Billing ID: {billing.id}")
                    print(f"        Trial End: {billing.trial_end_date.strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                print(f"   ⚪ 発動条件を満たすBilling: なし")
            print()

            # ケース3: canceling → canceled
            print("3️⃣  スケジュールキャンセル期限切れ（canceling → canceled）:")
            result3 = await db.execute(
                select(Billing).where(
                    Billing.billing_status == BillingStatus.canceling,
                    Billing.scheduled_cancel_at.isnot(None),
                    Billing.scheduled_cancel_at < now
                )
            )
            cancel_expired = result3.scalars().all()

            if cancel_expired:
                print(f"   ✅ 発動条件を満たすBilling: {len(cancel_expired)}件")
                for billing in cancel_expired[:5]:
                    print(f"      - Billing ID: {billing.id}")
                    print(f"        Cancel At: {billing.scheduled_cancel_at.strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                print(f"   ⚪ 発動条件を満たすBilling: なし")
            print()

            total = len(free_expired) + len(early_expired) + len(cancel_expired)

            print(f"{'='*80}")
            print(f"📊 合計: {total}件のBillingがバッチ処理の発動条件を満たしています")
            print(f"{'='*80}\n")

            if total > 0:
                print("💡 バッチ処理を手動実行:")
                print("   # Trial期限チェック")
                print("   docker exec keikakun_app-backend-1 python3 -c \"import asyncio; from app.db.session import AsyncSessionLocal; from app.tasks.billing_check import check_trial_expiration; asyncio.run((lambda: AsyncSessionLocal().__aenter__())()).then(lambda db: check_trial_expiration(db=db))\"")
                print()
                print("   # Cancel期限チェック")
                print("   docker exec keikakun_app-backend-1 python3 -c \"import asyncio; from app.db.session import AsyncSessionLocal; from app.tasks.billing_check import check_scheduled_cancellation; asyncio.run((lambda: AsyncSessionLocal().__aenter__())()).then(lambda db: check_scheduled_cancellation(db=db))\"")

        except Exception as e:
            print(f"❌ エラー: {e}")
            raise


def print_usage():
    """使い方を表示"""
    print(__doc__)


async def main():
    if len(sys.argv) < 2:
        print_usage()
        return

    command = sys.argv[1]

    if command == "list":
        await list_billings()

    elif command == "expire":
        if len(sys.argv) < 4 or sys.argv[2] != "--billing-id":
            print("❌ 使い方: expire --billing-id <billing_id> [--minutes N]")
            return

        billing_id = sys.argv[3]
        minutes = 1

        if len(sys.argv) > 4 and sys.argv[4] == "--minutes" and len(sys.argv) > 5:
            minutes = int(sys.argv[5])

        await set_expiry(billing_id=billing_id, minutes=minutes)

    elif command == "reset":
        if len(sys.argv) < 4 or sys.argv[2] != "--billing-id":
            print("❌ 使い方: reset --billing-id <billing_id>")
            return

        billing_id = sys.argv[3]
        await reset_expiry(billing_id=billing_id)

    elif command == "check":
        await check_batch_triggers()

    else:
        print(f"❌ 不明なコマンド: {command}")
        print_usage()


if __name__ == "__main__":
    asyncio.run(main())
