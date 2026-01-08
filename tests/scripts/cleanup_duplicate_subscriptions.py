"""
重複Subscription削除スクリプト

目的: 1つのCustomerに複数のSubscriptionが紐づいている異常状態をクリーンアップ

正常な状態: 1 Office : 1 Billing : 1 Customer : 1 Subscription

実行方法:
    # 重複状況を確認
    python tests/scripts/cleanup_duplicate_subscriptions.py --show

    # Dry-run（実際には削除しない）
    python tests/scripts/cleanup_duplicate_subscriptions.py --cleanup --dry-run

    # 実際にクリーンアップを実行
    python tests/scripts/cleanup_duplicate_subscriptions.py --cleanup

    # 特定のCustomer IDのみクリーンアップ
    python tests/scripts/cleanup_duplicate_subscriptions.py --cleanup --customer-id cus_xxx

    # 全てのSubscriptionを削除（重複に関係なく）
    python tests/scripts/cleanup_duplicate_subscriptions.py --delete-all --dry-run
    python tests/scripts/cleanup_duplicate_subscriptions.py --delete-all

警告: Stripeの本番APIを使用します。テスト環境で実行してください。
"""
import asyncio
import sys
import os
import argparse
from datetime import datetime, timezone
from typing import List, Dict
import stripe

# プロジェクトルートをPYTHONPATHに追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from app.db.session import AsyncSessionLocal
from app.models.billing import Billing
from sqlalchemy import select


async def analyze_duplicates() -> Dict:
    """重複Subscriptionの状況を分析"""

    stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

    async with AsyncSessionLocal() as db:
        # すべてのBillingを取得
        stmt = select(Billing)
        result = await db.execute(stmt)
        billings = result.scalars().all()

        print(f"\n=== 重複Subscription分析 (Billing: {len(billings)}件) ===\n")

        duplicates = {}
        total_subscriptions = 0

        for billing in billings:
            if not billing.stripe_customer_id:
                continue

            # StripeからSubscription一覧を取得
            try:
                subscriptions = stripe.Subscription.list(
                    customer=billing.stripe_customer_id,
                    limit=100
                )

                sub_count = len(subscriptions.data)
                total_subscriptions += sub_count

                if sub_count > 1:
                    duplicates[billing.stripe_customer_id] = {
                        'office_id': billing.office_id,
                        'billing_id': billing.id,
                        'billing_status': billing.billing_status,
                        'current_sub_id': billing.stripe_subscription_id,
                        'subscriptions': subscriptions.data
                    }

                marker = "🔥" if sub_count > 1 else "✅"
                print(f"{marker} Office: {billing.office_id}")
                print(f"   Customer: {billing.stripe_customer_id}")
                print(f"   DB Subscription ID: {billing.stripe_subscription_id or '未設定'}")
                print(f"   Stripe Subscriptions: {sub_count}件")

                if sub_count > 1:
                    print(f"   ⚠️  重複あり:")
                    for i, sub in enumerate(subscriptions.data, 1):
                        created = datetime.fromtimestamp(sub.created, tz=timezone.utc)
                        active_marker = "←DB" if sub.id == billing.stripe_subscription_id else ""
                        print(f"      {i}. {sub.id} ({sub.status}) - {created.strftime('%Y-%m-%d %H:%M')} {active_marker}")

                print()

            except stripe.error.InvalidRequestError as e:
                print(f"❌ Customer {billing.stripe_customer_id}: {e}")
                print()

        return {
            'duplicates': duplicates,
            'total_billings': len(billings),
            'total_subscriptions': total_subscriptions,
            'duplicate_count': len(duplicates)
        }


async def cleanup_duplicates(customer_id: str = None, dry_run: bool = False):
    """重複Subscriptionをクリーンアップ"""

    stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

    async with AsyncSessionLocal() as db:
        # Billingを取得
        if customer_id:
            stmt = select(Billing).where(Billing.stripe_customer_id == customer_id)
        else:
            stmt = select(Billing).where(Billing.stripe_customer_id.isnot(None))

        result = await db.execute(stmt)
        billings = result.scalars().all()

        print(f"\n{'[DRY-RUN] ' if dry_run else ''}=== 重複Subscriptionクリーンアップ ===\n")

        total_deleted = 0

        for billing in billings:
            try:
                subscriptions = stripe.Subscription.list(
                    customer=billing.stripe_customer_id,
                    limit=100
                )

                sub_list = subscriptions.data

                if len(sub_list) <= 1:
                    continue

                print(f"🔥 Customer: {billing.stripe_customer_id}")
                print(f"   Office: {billing.office_id}")
                print(f"   Subscriptions: {len(sub_list)}件")

                # 保持するSubscriptionを決定
                # 優先順位: 1. DBに記録されているもの 2. 最新のもの
                keep_sub = None

                if billing.stripe_subscription_id:
                    # DBに記録されているSubscriptionを保持
                    keep_sub = next((s for s in sub_list if s.id == billing.stripe_subscription_id), None)

                if not keep_sub:
                    # 最新のSubscriptionを保持
                    keep_sub = max(sub_list, key=lambda s: s.created)

                print(f"   ✅ 保持: {keep_sub.id} ({keep_sub.status})")

                # 他のSubscriptionを削除
                for sub in sub_list:
                    if sub.id == keep_sub.id:
                        continue

                    print(f"   ❌ 削除: {sub.id} ({sub.status})", end="")

                    if not dry_run:
                        try:
                            stripe.Subscription.delete(sub.id)
                            total_deleted += 1
                            print(" → 削除完了")
                        except Exception as e:
                            print(f" → エラー: {e}")
                    else:
                        print(" → [DRY-RUN]")
                        total_deleted += 1

                # DBのsubscription_idを更新
                if billing.stripe_subscription_id != keep_sub.id:
                    print(f"   🔄 DB更新: {billing.stripe_subscription_id or 'None'} → {keep_sub.id}", end="")

                    if not dry_run:
                        from app import crud
                        await crud.billing.update_stripe_subscription(
                            db=db,
                            billing_id=billing.id,
                            stripe_subscription_id=keep_sub.id,
                            subscription_start_date=datetime.fromtimestamp(keep_sub.created, tz=timezone.utc)
                        )
                        print(" → 更新完了")
                    else:
                        print(" → [DRY-RUN]")

                print()

            except Exception as e:
                print(f"❌ エラー: {e}\n")

        if total_deleted > 0:
            if dry_run:
                print(f"[DRY-RUN] {total_deleted}件のSubscriptionを削除予定")
            else:
                print(f"✅ {total_deleted}件のSubscriptionを削除しました")
        else:
            print("✅ 重複Subscriptionはありませんでした")


async def delete_all_subscriptions(customer_id: str = None, dry_run: bool = False):
    """全てのSubscriptionを削除"""

    stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

    async with AsyncSessionLocal() as db:
        # Billingを取得
        if customer_id:
            stmt = select(Billing).where(Billing.stripe_customer_id == customer_id)
        else:
            stmt = select(Billing).where(Billing.stripe_customer_id.isnot(None))

        result = await db.execute(stmt)
        billings = result.scalars().all()

        print(f"\n{'[DRY-RUN] ' if dry_run else ''}=== 全Subscription削除 ===\n")

        total_deleted = 0

        for billing in billings:
            try:
                subscriptions = stripe.Subscription.list(
                    customer=billing.stripe_customer_id,
                    limit=100
                )

                sub_list = subscriptions.data

                if len(sub_list) == 0:
                    continue

                print(f"🔥 Customer: {billing.stripe_customer_id}")
                print(f"   Office: {billing.office_id}")
                print(f"   Subscriptions: {len(sub_list)}件")

                # 全てのSubscriptionを削除
                for sub in sub_list:
                    print(f"   ❌ 削除: {sub.id} ({sub.status})", end="")

                    if not dry_run:
                        try:
                            stripe.Subscription.delete(sub.id)
                            total_deleted += 1
                            print(" → 削除完了")
                        except Exception as e:
                            print(f" → エラー: {e}")
                    else:
                        print(" → [DRY-RUN]")
                        total_deleted += 1

                # DBのsubscription_idをクリア
                if billing.stripe_subscription_id:
                    print(f"   🔄 DB更新: {billing.stripe_subscription_id} → None", end="")

                    if not dry_run:
                        from app import crud
                        await crud.billing.update_stripe_subscription(
                            db=db,
                            billing_id=billing.id,
                            stripe_subscription_id=None,
                            subscription_start_date=None
                        )
                        print(" → 更新完了")
                    else:
                        print(" → [DRY-RUN]")

                print()

            except Exception as e:
                print(f"❌ エラー: {e}\n")

        if total_deleted > 0:
            if dry_run:
                print(f"[DRY-RUN] {total_deleted}件のSubscriptionを削除予定")
            else:
                print(f"✅ {total_deleted}件のSubscriptionを削除しました")
        else:
            print("✅ 削除対象のSubscriptionはありませんでした")


def main():
    parser = argparse.ArgumentParser(description="重複Subscriptionをクリーンアップ")
    parser.add_argument('--show', action='store_true', help='重複状況を表示')
    parser.add_argument('--cleanup', action='store_true', help='クリーンアップを実行')
    parser.add_argument('--delete-all', action='store_true', help='全てのSubscriptionを削除')
    parser.add_argument('--customer-id', type=str, help='特定のCustomer IDのみ処理')
    parser.add_argument('--dry-run', action='store_true', help='実際には削除せずに表示のみ')

    args = parser.parse_args()

    if args.show:
        result = asyncio.run(analyze_duplicates())
        print(f"\n=== サマリー ===")
        print(f"総Billing数: {result['total_billings']}")
        print(f"総Subscription数: {result['total_subscriptions']}")
        print(f"重複Customer数: {result['duplicate_count']}")
        if result['duplicate_count'] > 0:
            print(f"\n⚠️  {result['duplicate_count']}件のCustomerに重複があります")
    elif args.delete_all:
        asyncio.run(delete_all_subscriptions(args.customer_id, args.dry_run))
    elif args.cleanup:
        asyncio.run(cleanup_duplicates(args.customer_id, args.dry_run))
    else:
        parser.print_help()
        print("\n例:")
        print("  python tests/scripts/cleanup_duplicate_subscriptions.py --show")
        print("  python tests/scripts/cleanup_duplicate_subscriptions.py --cleanup --dry-run")
        print("  python tests/scripts/cleanup_duplicate_subscriptions.py --cleanup")
        print("  python tests/scripts/cleanup_duplicate_subscriptions.py --delete-all --dry-run")
        print("  python tests/scripts/cleanup_duplicate_subscriptions.py --delete-all")


if __name__ == "__main__":
    main()
