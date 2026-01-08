"""
Billing状態リセットスクリプト

目的: 指定されたOfficeのBillingを初期状態（billing_status=free、無料期間中）にリセットする

実行方法:
    # すべてのBillingをリセット
    python tests/scripts/reset_billing_state.py --all

    # 特定のOffice IDをリセット
    python tests/scripts/reset_billing_state.py --office-id <UUID>

    # 最新のBillingをリセット
    python tests/scripts/reset_billing_state.py --latest

    # Dry-run（実際には更新しない）
    python tests/scripts/reset_billing_state.py --all --dry-run

警告: テスト環境でのみ実行してください
"""
import asyncio
import sys
import os
import argparse
from datetime import datetime, timezone, timedelta
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# プロジェクトルートをPYTHONPATHに追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from app.db.session import AsyncSessionLocal
from app.models.billing import Billing
from app.models.enums import BillingStatus


async def reset_billing(db: AsyncSession, billing: Billing, dry_run: bool = False):
    """Billingを初期状態にリセット"""

    print(f"\n{'[DRY-RUN] ' if dry_run else ''}Office: {billing.office_id}")
    print(f"  現在のステータス: {billing.billing_status}")
    print(f"  Customer ID: {billing.stripe_customer_id}")
    print(f"  Subscription ID: {billing.stripe_subscription_id}")

    if dry_run:
        print(f"  → リセット後のステータス: free")
        print(f"  → 無料期間: 180日後まで")
        print(f"  → Customer ID: None")
        print(f"  → Subscription ID: None")
        return

    # リセット処理
    now = datetime.now(timezone.utc)
    trial_end = now + timedelta(days=180)

    billing.billing_status = BillingStatus.free
    billing.stripe_customer_id = None
    billing.stripe_subscription_id = None
    billing.trial_start_date = now
    billing.trial_end_date = trial_end
    billing.subscription_start_date = None
    billing.next_billing_date = None
    billing.last_payment_date = None

    db.add(billing)
    await db.commit()
    await db.refresh(billing)

    print(f"  ✅ リセット完了")
    print(f"     ステータス: {billing.billing_status}")
    print(f"     無料期間終了: {billing.trial_end_date}")


async def reset_all_billings(dry_run: bool = False):
    """すべてのBillingをリセット"""
    async with AsyncSessionLocal() as db:
        stmt = select(Billing)
        result = await db.execute(stmt)
        billings = result.scalars().all()

        if not billings:
            print("⚠️  Billingレコードが見つかりません")
            return

        print(f"{'[DRY-RUN] ' if dry_run else ''}合計 {len(billings)} 件のBillingをリセットします")

        for billing in billings:
            await reset_billing(db, billing, dry_run)

        if not dry_run:
            print(f"\n✅ {len(billings)} 件のリセットが完了しました")
        else:
            print(f"\n[DRY-RUN] 実際にリセットする場合は --dry-run を外してください")


async def reset_by_office_id(office_id: str, dry_run: bool = False):
    """特定のOffice IDのBillingをリセット"""
    async with AsyncSessionLocal() as db:
        try:
            office_uuid = UUID(office_id)
        except ValueError:
            print(f"❌ 無効なUUID: {office_id}")
            return

        stmt = select(Billing).where(Billing.office_id == office_uuid)
        result = await db.execute(stmt)
        billing = result.scalars().first()

        if not billing:
            print(f"⚠️  Office ID {office_id} のBillingが見つかりません")
            return

        await reset_billing(db, billing, dry_run)

        if not dry_run:
            print(f"\n✅ リセット完了")


async def reset_latest(dry_run: bool = False):
    """最新のBillingをリセット"""
    async with AsyncSessionLocal() as db:
        stmt = select(Billing).order_by(Billing.created_at.desc()).limit(1)
        result = await db.execute(stmt)
        billing = result.scalars().first()

        if not billing:
            print("⚠️  Billingレコードが見つかりません")
            return

        print(f"最新のBilling (作成日: {billing.created_at})")
        await reset_billing(db, billing, dry_run)

        if not dry_run:
            print(f"\n✅ リセット完了")


async def show_current_state():
    """現在のBilling状態を表示"""
    async with AsyncSessionLocal() as db:
        stmt = select(Billing)
        result = await db.execute(stmt)
        billings = result.scalars().all()

        if not billings:
            print("⚠️  Billingレコードが見つかりません")
            return

        print(f"\n=== 現在のBilling状態 (合計: {len(billings)}) ===\n")

        for billing in billings:
            now = datetime.now(timezone.utc)
            days_remaining = (billing.trial_end_date - now).days

            print(f"Office: {billing.office_id}")
            print(f"  ステータス: {billing.billing_status}")
            print(f"  無料期間: {billing.trial_end_date} (残り {days_remaining} 日)")
            print(f"  Customer ID: {billing.stripe_customer_id or '未設定'}")
            print(f"  Subscription ID: {billing.stripe_subscription_id or '未設定'}")
            print()


def main():
    parser = argparse.ArgumentParser(description="Billing状態をリセット")
    parser.add_argument('--all', action='store_true', help='すべてのBillingをリセット')
    parser.add_argument('--office-id', type=str, help='特定のOffice IDをリセット')
    parser.add_argument('--latest', action='store_true', help='最新のBillingをリセット')
    parser.add_argument('--show', action='store_true', help='現在の状態を表示')
    parser.add_argument('--dry-run', action='store_true', help='実際には更新せずに表示のみ')

    args = parser.parse_args()

    if args.show:
        asyncio.run(show_current_state())
    elif args.all:
        asyncio.run(reset_all_billings(args.dry_run))
    elif args.office_id:
        asyncio.run(reset_by_office_id(args.office_id, args.dry_run))
    elif args.latest:
        asyncio.run(reset_latest(args.dry_run))
    else:
        parser.print_help()
        print("\n例:")
        print("  python tests/scripts/reset_billing_state.py --show")
        print("  python tests/scripts/reset_billing_state.py --all --dry-run")
        print("  python tests/scripts/reset_billing_state.py --latest")


if __name__ == "__main__":
    main()
