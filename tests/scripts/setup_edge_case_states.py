"""
Billingエッジケース状態作成スクリプト

目的: 課金フローの各エッジケースに対応する状態を作成し、E2Eテストやデバッグに使用する

エッジケース:
0. 初期状態（事務所登録直後） (free, trial 180 days)
1. トライアル期間が終わる前に課金するケース (early_payment)
2. トライアル期間を過ぎても課金されないケース (past_due)
3. トライアル期間を過ぎてから課金したケース (free, trial expired)
4. トライアル期間の終了日に課金したケース (free, trial ending today)
5. 課金登録後、トライアル期間終了前にキャンセル (canceled with trial remaining)
6. トライアル期間終了後、最初の課金が失敗 (past_due)
7. EARLY_PAYMENT状態でトライアル期間を過ぎる (early_payment → active遷移待ち)

実行方法:
    # 現在の状態を表示
    python tests/scripts/setup_edge_case_states.py --show

    # 初期状態（事務所登録直後）に戻す
    python tests/scripts/setup_edge_case_states.py --case 0

    # 特定のエッジケースを設定
    python tests/scripts/setup_edge_case_states.py --case 1

    # すべてのエッジケースを設定（複数Officeが必要）
    python tests/scripts/setup_edge_case_states.py --all

    # Dry-run
    python tests/scripts/setup_edge_case_states.py --case 2 --dry-run

    # 特定のOffice IDに設定
    python tests/scripts/setup_edge_case_states.py --case 3 --office-id <UUID>

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


# エッジケース定義
EDGE_CASES = {
    0: {
        "name": "初期状態（事務所登録直後）",
        "description": "billing_status=free、無料お試し期間180日の初期状態",
        "billing_status": BillingStatus.free,
        "trial_offset_days": 180,  # 無料期間は180日後まで
        "has_customer": False,
        "has_subscription": False,
        "note": "※ 事務所登録時のデフォルト状態",
    },
    1: {
        "name": "トライアル期間が終わる前に課金するケース",
        "description": "無料期間中に課金登録し、early_payment状態になる",
        "billing_status": BillingStatus.early_payment,
        "trial_offset_days": 30,  # 無料期間は30日後まで
        "has_customer": True,
        "has_subscription": True,
        "subscription_start_offset": 0,  # サブスクは開始済み
    },
    2: {
        "name": "トライアル期間を過ぎても課金されないケース",
        "description": "無料期間が終了したがpast_due状態（バッチ処理想定）",
        "billing_status": BillingStatus.past_due,
        "trial_offset_days": -5,  # 無料期間は5日前に終了
        "has_customer": False,
        "has_subscription": False,
    },
    3: {
        "name": "トライアル期間を過ぎてから課金したケース",
        "description": "無料期間終了後、free状態のまま（課金登録前）",
        "billing_status": BillingStatus.free,
        "trial_offset_days": -10,  # 無料期間は10日前に終了
        "has_customer": False,
        "has_subscription": False,
    },
    4: {
        "name": "トライアル期間の終了日に課金したケース",
        "description": "無料期間が今日終了する（ギリギリのタイミング）",
        "billing_status": BillingStatus.free,
        "trial_offset_days": 0,  # 無料期間は今日まで（数時間後に終了）
        "trial_offset_hours": 6,  # 6時間後に終了
        "has_customer": False,
        "has_subscription": False,
    },
    5: {
        "name": "課金登録後、トライアル期間終了前にキャンセル",
        "description": "early_paymentからキャンセルし、freeに戻った状態",
        "billing_status": BillingStatus.free,
        "trial_offset_days": 20,  # 無料期間はまだ20日残っている
        "has_customer": True,  # Customer IDは残っている
        "has_subscription": False,  # Subscriptionはキャンセル済み
        "note": "※ キャンセル後にfreeに戻る実装が前提",
    },
    6: {
        "name": "トライアル期間終了後、最初の課金が失敗",
        "description": "課金登録済みだが、初回請求が失敗してpast_due",
        "billing_status": BillingStatus.past_due,
        "trial_offset_days": -3,  # 無料期間は3日前に終了
        "has_customer": True,
        "has_subscription": True,
        "subscription_start_offset": -3,  # サブスクは3日前に開始（失敗）
        "note": "※ Stripeの自動リトライ待ち",
    },
    7: {
        "name": "EARLY_PAYMENT状態でトライアル期間を過ぎる",
        "description": "early_paymentで、まもなくactiveに自動遷移する状態",
        "billing_status": BillingStatus.early_payment,
        "trial_offset_days": 0,  # 無料期間が今日終了
        "trial_offset_hours": 2,  # 2時間後に終了
        "has_customer": True,
        "has_subscription": True,
        "subscription_start_offset": -30,  # サブスクは30日前に開始
        "note": "※ Stripeが自動課金 → invoice.payment_succeeded → active遷移",
    },
}


async def setup_edge_case(
    db: AsyncSession,
    billing: Billing,
    case_num: int,
    dry_run: bool = False
):
    """エッジケースの状態を設定"""

    if case_num not in EDGE_CASES:
        print(f"❌ 無効なケース番号: {case_num}")
        return

    case = EDGE_CASES[case_num]

    print(f"\n{'[DRY-RUN] ' if dry_run else ''}=== ケース {case_num}: {case['name']} ===")
    print(f"説明: {case['description']}")
    if 'note' in case:
        print(f"注意: {case['note']}")

    print(f"\nOffice: {billing.office_id}")
    print(f"  現在のステータス: {billing.billing_status}")

    # 計算
    now = datetime.now(timezone.utc)
    trial_offset = timedelta(days=case.get('trial_offset_days', 0))
    if 'trial_offset_hours' in case:
        trial_offset += timedelta(hours=case['trial_offset_hours'])

    trial_end = now + trial_offset

    if dry_run:
        print(f"\n  → 設定後のステータス: {case['billing_status']}")
        print(f"  → 無料期間終了: {trial_end} (残り {(trial_end - now).days} 日)")
        print(f"  → Customer ID: {'設定あり' if case['has_customer'] else 'なし'}")
        print(f"  → Subscription ID: {'設定あり' if case['has_subscription'] else 'なし'}")
        return

    # 状態を設定
    billing.billing_status = case['billing_status']
    billing.trial_end_date = trial_end

    if case['has_customer']:
        if not billing.stripe_customer_id:
            billing.stripe_customer_id = f"cus_edge_case_{case_num}_test"
    else:
        billing.stripe_customer_id = None

    if case['has_subscription']:
        if not billing.stripe_subscription_id:
            billing.stripe_subscription_id = f"sub_edge_case_{case_num}_test"

        if 'subscription_start_offset' in case:
            sub_start = now + timedelta(days=case['subscription_start_offset'])
            billing.subscription_start_date = sub_start
    else:
        billing.stripe_subscription_id = None
        billing.subscription_start_date = None

    # past_dueの場合
    if case['billing_status'] == BillingStatus.past_due:
        billing.next_billing_date = None  # 支払い待ち
        billing.last_payment_date = None

    db.add(billing)
    await db.commit()
    await db.refresh(billing)

    print(f"\n  ✅ 設定完了")
    print(f"     ステータス: {billing.billing_status}")
    print(f"     無料期間終了: {billing.trial_end_date}")
    print(f"     Customer ID: {billing.stripe_customer_id or 'なし'}")
    print(f"     Subscription ID: {billing.stripe_subscription_id or 'なし'}")


async def setup_by_case(case_num: int, office_id: str = None, dry_run: bool = False):
    """特定のケースを設定"""
    async with AsyncSessionLocal() as db:
        if office_id:
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
        else:
            # 最新のBillingを使用
            stmt = select(Billing).order_by(Billing.created_at.desc()).limit(1)
            result = await db.execute(stmt)
            billing = result.scalars().first()

            if not billing:
                print("⚠️  Billingレコードが見つかりません")
                return

            print(f"最新のBilling (Office: {billing.office_id}) を使用します")

        await setup_edge_case(db, billing, case_num, dry_run)


async def setup_all_cases(dry_run: bool = False):
    """すべてのケースを設定（複数Officeに分散）"""
    async with AsyncSessionLocal() as db:
        stmt = select(Billing).order_by(Billing.created_at.desc())
        result = await db.execute(stmt)
        billings = result.scalars().all()

        if not billings:
            print("⚠️  Billingレコードが見つかりません")
            return

        if len(billings) < len(EDGE_CASES):
            print(f"⚠️  エッジケース {len(EDGE_CASES)} 件に対して、Billingが {len(billings)} 件しかありません")
            print(f"    各ケースを個別に設定することをお勧めします")
            return

        print(f"{'[DRY-RUN] ' if dry_run else ''}合計 {len(EDGE_CASES)} 件のエッジケースを設定します\n")

        for i, (case_num, case) in enumerate(EDGE_CASES.items()):
            if i < len(billings):
                await setup_edge_case(db, billings[i], case_num, dry_run)

        if not dry_run:
            print(f"\n✅ すべてのエッジケースの設定が完了しました")


async def show_edge_cases():
    """エッジケース一覧を表示"""
    print("\n=== Billingエッジケース一覧 ===\n")

    for case_num, case in EDGE_CASES.items():
        print(f"{case_num}. {case['name']}")
        print(f"   説明: {case['description']}")
        print(f"   ステータス: {case['billing_status']}")
        print(f"   無料期間: {case.get('trial_offset_days', 0)} 日後まで")
        if 'note' in case:
            print(f"   注意: {case['note']}")
        print()


async def show_current_state():
    """現在の状態を表示"""
    async with AsyncSessionLocal() as db:
        stmt = select(Billing).order_by(Billing.created_at.desc())
        result = await db.execute(stmt)
        billings = result.scalars().all()

        if not billings:
            print("⚠️  Billingレコードが見つかりません")
            return

        print(f"\n=== 現在のBilling状態 (合計: {len(billings)}) ===\n")

        for i, billing in enumerate(billings, 1):
            now = datetime.now(timezone.utc)
            days_remaining = (billing.trial_end_date - now).days

            print(f"{i}. Office: {billing.office_id}")
            print(f"   ステータス: {billing.billing_status}")
            print(f"   無料期間: {billing.trial_end_date} (残り {days_remaining} 日)")
            print(f"   Customer ID: {billing.stripe_customer_id or 'なし'}")
            print(f"   Subscription ID: {billing.stripe_subscription_id or 'なし'}")
            print()


def main():
    parser = argparse.ArgumentParser(description="Billingエッジケース状態を設定")
    parser.add_argument('--case', type=int, choices=range(0, 8), help='設定するケース番号 (0-7)')
    parser.add_argument('--all', action='store_true', help='すべてのケースを設定')
    parser.add_argument('--office-id', type=str, help='特定のOffice IDに設定')
    parser.add_argument('--list', action='store_true', help='エッジケース一覧を表示')
    parser.add_argument('--show', action='store_true', help='現在の状態を表示')
    parser.add_argument('--dry-run', action='store_true', help='実際には更新せずに表示のみ')

    args = parser.parse_args()

    if args.list:
        asyncio.run(show_edge_cases())
    elif args.show:
        asyncio.run(show_current_state())
    elif args.case is not None:  # case 0を許可するため、is not Noneを使用
        asyncio.run(setup_by_case(args.case, args.office_id, args.dry_run))
    elif args.all:
        asyncio.run(setup_all_cases(args.dry_run))
    else:
        parser.print_help()
        print("\n例:")
        print("  python tests/scripts/setup_edge_case_states.py --list")
        print("  python tests/scripts/setup_edge_case_states.py --show")
        print("  python tests/scripts/setup_edge_case_states.py --case 0  # 初期状態にリセット")
        print("  python tests/scripts/setup_edge_case_states.py --case 1")
        print("  python tests/scripts/setup_edge_case_states.py --case 2 --dry-run")
        print("  python tests/scripts/setup_edge_case_states.py --case 3 --office-id <UUID>")


if __name__ == "__main__":
    main()
