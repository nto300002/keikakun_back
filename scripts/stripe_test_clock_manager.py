"""
Stripe Test Clocksをアプリから操作するスクリプト

Stripe Test Clocksを作成・管理・削除するためのツール。
Webhook連携のテストに使用します。

使い方:
1. Test Clock一覧表示:
   docker exec keikakun_app-backend-1 python3 scripts/stripe_test_clock_manager.py list

2. Test Clock作成:
   docker exec keikakun_app-backend-1 python3 scripts/stripe_test_clock_manager.py create --name "Trial Test 2025-12-24"

3. 時間を進める:
   docker exec keikakun_app-backend-1 python3 scripts/stripe_test_clock_manager.py advance --clock-id <test_clock_id> --days 90

4. Test Clock削除:
   docker exec keikakun_app-backend-1 python3 scripts/stripe_test_clock_manager.py delete --clock-id <test_clock_id>

5. Test Clockに紐づいた顧客を確認:
   docker exec keikakun_app-backend-1 python3 scripts/stripe_test_clock_manager.py customers --clock-id <test_clock_id>
"""
import sys
import os
from datetime import datetime, timedelta, timezone

sys.path.insert(0, '/app')

import stripe
from app.core.config import settings


def print_usage():
    """使い方を表示"""
    print(__doc__)


def list_test_clocks():
    """Test Clockの一覧を表示"""
    try:
        stripe.api_key = settings.STRIPE_SECRET_KEY.get_secret_value() if settings.STRIPE_SECRET_KEY else None

        print(f"\n{'='*80}")
        print(f"Stripe Test Clocks一覧")
        print(f"{'='*80}\n")

        test_clocks = stripe.test_helpers.TestClock.list(limit=20)

        if not test_clocks.data:
            print("⚠️  Test Clocksが見つかりません")
            print("\n💡 新しいTest Clockを作成:")
            print('   docker exec keikakun_app-backend-1 python3 scripts/stripe_test_clock_manager.py create --name "Trial Test"')
            return

        print(f"📋 最新20件を表示\n")

        for i, clock in enumerate(test_clocks.data, 1):
            frozen_time = datetime.fromtimestamp(clock.frozen_time, tz=timezone.utc)
            status = clock.status

            print(f"{i}. Test Clock ID: {clock.id}")
            print(f"   Name: {clock.name}")
            print(f"   Frozen Time: {frozen_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            print(f"   Status: {status}")
            print()

        print(f"{'='*80}\n")
        print("💡 使用例:")
        if test_clocks.data:
            first_clock_id = test_clocks.data[0].id
            print(f"   # 時間を90日進める:")
            print(f"   docker exec keikakun_app-backend-1 python3 scripts/stripe_test_clock_manager.py advance --clock-id {first_clock_id} --days 90")
            print(f"\n   # 顧客を確認:")
            print(f"   docker exec keikakun_app-backend-1 python3 scripts/stripe_test_clock_manager.py customers --clock-id {first_clock_id}")
            print(f"\n   # 削除:")
            print(f"   docker exec keikakun_app-backend-1 python3 scripts/stripe_test_clock_manager.py delete --clock-id {first_clock_id}")

    except Exception as e:
        print(f"❌ エラー: {e}")
        raise


def create_test_clock(name: str):
    """
    Test Clockを作成

    Args:
        name: Test Clock名
    """
    try:
        stripe.api_key = settings.STRIPE_SECRET_KEY.get_secret_value() if settings.STRIPE_SECRET_KEY else None

        now = datetime.now(timezone.utc)
        frozen_time = int(now.timestamp())

        print(f"\n{'='*80}")
        print(f"Test Clock作成")
        print(f"{'='*80}\n")

        print(f"📋 作成情報:")
        print(f"   Name: {name}")
        print(f"   Frozen Time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        print(f"   Unix Timestamp: {frozen_time}\n")

        test_clock = stripe.test_helpers.TestClock.create(
            frozen_time=frozen_time,
            name=name
        )

        print(f"{'='*80}")
        print(f"✅ Test Clock作成完了")
        print(f"{'='*80}\n")

        print(f"📊 作成されたTest Clock:")
        print(f"   Test Clock ID: {test_clock.id}")
        print(f"   Name: {test_clock.name}")
        print(f"   Frozen Time: {datetime.fromtimestamp(test_clock.frozen_time, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z')}")
        print(f"   Status: {test_clock.status}\n")

        print(f"💡 次のステップ:")
        print(f"   1. このTest ClockをStripe CustomerやSubscriptionに紐付ける")
        print(f"      → Stripe Dashboard または Stripe APIで設定")
        print(f"\n   2. 時間を進める:")
        print(f"      docker exec keikakun_app-backend-1 python3 scripts/stripe_test_clock_manager.py advance --clock-id {test_clock.id} --days 90")

    except Exception as e:
        print(f"❌ エラー: {e}")
        raise


def advance_test_clock(clock_id: str, days: int = 0, hours: int = 0, minutes: int = 0):
    """
    Test Clockの時間を進める

    Args:
        clock_id: Test Clock ID
        days: 進める日数
        hours: 進める時間
        minutes: 進める分
    """
    try:
        stripe.api_key = settings.STRIPE_SECRET_KEY.get_secret_value() if settings.STRIPE_SECRET_KEY else None

        test_clock = stripe.test_helpers.TestClock.retrieve(clock_id)

        current_time = datetime.fromtimestamp(test_clock.frozen_time, tz=timezone.utc)
        delta = timedelta(days=days, hours=hours, minutes=minutes)
        new_time = current_time + delta
        new_frozen_time = int(new_time.timestamp())

        print(f"\n{'='*80}")
        print(f"Test Clock時間を進める")
        print(f"{'='*80}\n")

        print(f"📋 Test Clock情報:")
        print(f"   Test Clock ID: {clock_id}")
        print(f"   Name: {test_clock.name}")
        print(f"   Current Time: {current_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        print(f"   New Time: {new_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        print(f"   Time Delta: {days}日 {hours}時間 {minutes}分\n")

        print(f"⏰ 時間を進めています...")

        updated_clock = stripe.test_helpers.TestClock.advance(
            clock_id,
            frozen_time=new_frozen_time
        )

        print(f"\n{'='*80}")
        print(f"✅ 時間を進めました")
        print(f"{'='*80}\n")

        print(f"📊 更新後の状態:")
        print(f"   Frozen Time: {datetime.fromtimestamp(updated_clock.frozen_time, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z')}")
        print(f"   Status: {updated_clock.status}\n")

        print(f"🔍 Webhookが発火したか確認:")
        print(f"   1. Stripe Dashboard → Developers → Webhooks → Logs")
        print(f"   2. アプリログ:")
        print(f"      docker logs keikakun_app-backend-1 --tail 50 | grep Webhook\n")

        print(f"💡 アプリのBillingステータスを確認:")
        print(f"   docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py list")

    except Exception as e:
        print(f"❌ エラー: {e}")
        raise


def delete_test_clock(clock_id: str):
    """
    Test Clockを削除

    Args:
        clock_id: Test Clock ID
    """
    try:
        stripe.api_key = settings.STRIPE_SECRET_KEY.get_secret_value() if settings.STRIPE_SECRET_KEY else None

        test_clock = stripe.test_helpers.TestClock.retrieve(clock_id)

        print(f"\n{'='*80}")
        print(f"Test Clock削除")
        print(f"{'='*80}\n")

        print(f"📋 削除対象:")
        print(f"   Test Clock ID: {clock_id}")
        print(f"   Name: {test_clock.name}")
        print(f"   Status: {test_clock.status}\n")

        stripe.test_helpers.TestClock.delete(clock_id)

        print(f"{'='*80}")
        print(f"✅ Test Clock削除完了")
        print(f"{'='*80}\n")

    except Exception as e:
        print(f"❌ エラー: {e}")
        raise


def list_customers_by_test_clock(clock_id: str):
    """
    Test Clockに紐づいた顧客を一覧表示

    Args:
        clock_id: Test Clock ID
    """
    try:
        stripe.api_key = settings.STRIPE_SECRET_KEY.get_secret_value() if settings.STRIPE_SECRET_KEY else None

        test_clock = stripe.test_helpers.TestClock.retrieve(clock_id)

        print(f"\n{'='*80}")
        print(f"Test Clockに紐づいた顧客一覧")
        print(f"{'='*80}\n")

        print(f"📋 Test Clock情報:")
        print(f"   Test Clock ID: {clock_id}")
        print(f"   Name: {test_clock.name}")
        print(f"   Frozen Time: {datetime.fromtimestamp(test_clock.frozen_time, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z')}\n")

        customers = stripe.Customer.list(test_clock=clock_id, limit=20)

        if not customers.data:
            print("⚠️  このTest Clockに紐づいた顧客が見つかりません\n")
            print("💡 Stripe Dashboardで顧客を作成する際に、このTest Clockを選択してください")
            return

        print(f"👥 顧客一覧 ({len(customers.data)}件):\n")

        for i, customer in enumerate(customers.data, 1):
            print(f"{i}. Customer ID: {customer.id}")
            print(f"   Email: {customer.email}")
            print(f"   Name: {customer.name or 'N/A'}")

            subscriptions = stripe.Subscription.list(customer=customer.id, limit=5)
            if subscriptions.data:
                print(f"   Subscriptions:")
                for sub in subscriptions.data:
                    trial_end = datetime.fromtimestamp(sub.trial_end, tz=timezone.utc) if sub.trial_end else None
                    print(f"      - {sub.id}")
                    print(f"        Status: {sub.status}")
                    if trial_end:
                        print(f"        Trial End: {trial_end.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            print()

        print(f"{'='*80}\n")

    except Exception as e:
        print(f"❌ エラー: {e}")
        raise


def main():
    if len(sys.argv) < 2:
        print_usage()
        return

    command = sys.argv[1]

    if command == "list":
        list_test_clocks()

    elif command == "create":
        if len(sys.argv) < 4 or sys.argv[2] != "--name":
            print("❌ 使い方: create --name <test_clock_name>")
            return

        name = sys.argv[3]
        create_test_clock(name=name)

    elif command == "advance":
        if len(sys.argv) < 4 or sys.argv[2] != "--clock-id":
            print("❌ 使い方: advance --clock-id <test_clock_id> [--days N] [--hours N] [--minutes N]")
            return

        clock_id = sys.argv[3]
        days = 0
        hours = 0
        minutes = 0

        i = 4
        while i < len(sys.argv):
            if sys.argv[i] == "--days" and i + 1 < len(sys.argv):
                days = int(sys.argv[i + 1])
                i += 2
            elif sys.argv[i] == "--hours" and i + 1 < len(sys.argv):
                hours = int(sys.argv[i + 1])
                i += 2
            elif sys.argv[i] == "--minutes" and i + 1 < len(sys.argv):
                minutes = int(sys.argv[i + 1])
                i += 2
            else:
                i += 1

        advance_test_clock(clock_id=clock_id, days=days, hours=hours, minutes=minutes)

    elif command == "delete":
        if len(sys.argv) < 4 or sys.argv[2] != "--clock-id":
            print("❌ 使い方: delete --clock-id <test_clock_id>")
            return

        clock_id = sys.argv[3]
        delete_test_clock(clock_id=clock_id)

    elif command == "customers":
        if len(sys.argv) < 4 or sys.argv[2] != "--clock-id":
            print("❌ 使い方: customers --clock-id <test_clock_id>")
            return

        clock_id = sys.argv[3]
        list_customers_by_test_clock(clock_id=clock_id)

    else:
        print(f"❌ 不明なコマンド: {command}")
        print_usage()


if __name__ == "__main__":
    main()
