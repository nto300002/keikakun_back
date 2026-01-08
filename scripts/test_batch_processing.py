"""
バッチ処理のE2Eテストスクリプト

使い方:
1. テストデータ作成:
   docker exec keikakun_app-backend-1 python3 scripts/test_batch_processing.py setup --minutes 1

2. 1分待つ

3. バッチ処理実行:
   docker exec keikakun_app-backend-1 python3 scripts/test_batch_processing.py run

4. 結果確認:
   docker exec keikakun_app-backend-1 python3 scripts/test_batch_processing.py verify

5. クリーンアップ:
   docker exec keikakun_app-backend-1 python3 scripts/test_batch_processing.py cleanup
"""
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from uuid import uuid4

sys.path.insert(0, '/app')

from app.db.session import AsyncSessionLocal
from app import crud
from app.models.billing import Billing
from app.models.office import Office
from app.models.enums import BillingStatus
from app.schemas.billing import BillingCreate
from app.tasks.billing_check import check_trial_expiration, check_scheduled_cancellation


TEST_OFFICE_NAME_PREFIX = "E2E_TEST_BATCH_"
TEST_MARKER = f"{TEST_OFFICE_NAME_PREFIX}{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"


async def setup_test_data(minutes: int = 1):
    """
    テストデータを作成

    Args:
        minutes: 何分後に期限切れにするか（デフォルト1分）
    """
    async with AsyncSessionLocal() as db:
        try:
            now = datetime.now(timezone.utc)
            expiry_time = now + timedelta(minutes=minutes)

            print(f"\n{'='*60}")
            print(f"テストデータ作成開始")
            print(f"現在時刻: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            print(f"期限時刻: {expiry_time.strftime('%Y-%m-%d %H:%M:%S %Z')} ({minutes}分後)")
            print(f"{'='*60}\n")

            test_offices = []

            # 1. free → past_due のテスト用
            print("1️⃣  free → past_due テストデータ作成中...")
            office1 = Office(
                id=uuid4(),
                name=f"{TEST_MARKER}_FREE_TO_PAST_DUE",
                phone_number="000-0000-0001",
                is_test_data=True
            )
            db.add(office1)
            await db.flush()

            billing1 = await crud.billing.create_for_office(
                db=db,
                office_id=office1.id,
                trial_days=1
            )
            # trial_end_dateを指定時間後に設定
            billing1.trial_end_date = expiry_time
            billing1.billing_status = BillingStatus.free
            test_offices.append({
                "office_id": str(office1.id),
                "office_name": office1.name,
                "billing_id": str(billing1.id),
                "current_status": "free",
                "expected_status": "past_due",
                "expiry_time": expiry_time
            })
            print(f"   ✅ Office: {office1.name}")
            print(f"      Billing ID: {billing1.id}")
            print(f"      Status: free → past_due\n")

            # 2. early_payment → active のテスト用
            print("2️⃣  early_payment → active テストデータ作成中...")
            office2 = Office(
                id=uuid4(),
                name=f"{TEST_MARKER}_EARLY_TO_ACTIVE",
                phone_number="000-0000-0002",
                is_test_data=True
            )
            db.add(office2)
            await db.flush()

            billing2 = await crud.billing.create_for_office(
                db=db,
                office_id=office2.id,
                trial_days=1
            )
            billing2.trial_end_date = expiry_time
            billing2.billing_status = BillingStatus.early_payment
            billing2.stripe_customer_id = f"cus_e2e_test_{uuid4().hex[:10]}"
            billing2.stripe_subscription_id = f"sub_e2e_test_{uuid4().hex[:10]}"
            test_offices.append({
                "office_id": str(office2.id),
                "office_name": office2.name,
                "billing_id": str(billing2.id),
                "current_status": "early_payment",
                "expected_status": "active",
                "expiry_time": expiry_time
            })
            print(f"   ✅ Office: {office2.name}")
            print(f"      Billing ID: {billing2.id}")
            print(f"      Status: early_payment → active\n")

            # 3. canceling → canceled のテスト用
            print("3️⃣  canceling → canceled テストデータ作成中...")
            office3 = Office(
                id=uuid4(),
                name=f"{TEST_MARKER}_CANCELING_TO_CANCELED",
                phone_number="000-0000-0003",
                is_test_data=True
            )
            db.add(office3)
            await db.flush()

            billing3 = await crud.billing.create_for_office(
                db=db,
                office_id=office3.id,
                trial_days=180
            )
            billing3.billing_status = BillingStatus.canceling
            billing3.scheduled_cancel_at = expiry_time
            billing3.stripe_customer_id = f"cus_e2e_test_{uuid4().hex[:10]}"
            billing3.stripe_subscription_id = f"sub_e2e_test_{uuid4().hex[:10]}"
            test_offices.append({
                "office_id": str(office3.id),
                "office_name": office3.name,
                "billing_id": str(billing3.id),
                "current_status": "canceling",
                "expected_status": "canceled",
                "expiry_time": expiry_time
            })
            print(f"   ✅ Office: {office3.name}")
            print(f"      Billing ID: {billing3.id}")
            print(f"      Status: canceling → canceled\n")

            await db.commit()

            print(f"{'='*60}")
            print(f"✅ テストデータ作成完了")
            print(f"{'='*60}\n")

            print("📋 作成されたテストデータ:")
            for i, office in enumerate(test_offices, 1):
                print(f"\n{i}. {office['office_name']}")
                print(f"   Office ID: {office['office_id']}")
                print(f"   Billing ID: {office['billing_id']}")
                print(f"   Current Status: {office['current_status']}")
                print(f"   Expected Status: {office['expected_status']}")

            print(f"\n⏰ {minutes}分後に以下のコマンドを実行してください:")
            print(f"   docker exec keikakun_app-backend-1 python3 scripts/test_batch_processing.py run")

        except Exception as e:
            await db.rollback()
            print(f"❌ エラー: {e}")
            raise


async def run_batch_processing():
    """バッチ処理を実行"""
    async with AsyncSessionLocal() as db:
        try:
            print(f"\n{'='*60}")
            print(f"バッチ処理実行開始")
            print(f"実行時刻: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z')}")
            print(f"{'='*60}\n")

            # 1. Trial期間終了チェック
            print("1️⃣  Trial期間終了チェック実行中...")
            trial_count = await check_trial_expiration(db=db)
            print(f"   ✅ 更新件数: {trial_count}\n")

            # 2. スケジュールキャンセルチェック
            print("2️⃣  スケジュールキャンセルチェック実行中...")
            cancel_count = await check_scheduled_cancellation(db=db)
            print(f"   ✅ 更新件数: {cancel_count}\n")

            print(f"{'='*60}")
            print(f"✅ バッチ処理完了")
            print(f"{'='*60}\n")

            print(f"📊 処理結果:")
            print(f"   Trial期間終了: {trial_count}件")
            print(f"   スケジュールキャンセル: {cancel_count}件")

            print(f"\n🔍 結果を確認するには:")
            print(f"   docker exec keikakun_app-backend-1 python3 scripts/test_batch_processing.py verify")

        except Exception as e:
            print(f"❌ エラー: {e}")
            raise


async def verify_results():
    """結果を検証"""
    async with AsyncSessionLocal() as db:
        try:
            print(f"\n{'='*60}")
            print(f"結果検証開始")
            print(f"検証時刻: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z')}")
            print(f"{'='*60}\n")

            # テストデータのOfficeを取得
            result = await db.execute(
                select(Office).where(
                    Office.name.like(f"{TEST_OFFICE_NAME_PREFIX}%"),
                    Office.is_test_data == True
                ).order_by(Office.created_at.desc())
            )
            test_offices = result.scalars().all()

            if not test_offices:
                print("⚠️  テストデータが見つかりません")
                return

            print(f"📋 検証対象: {len(test_offices)}件\n")

            all_passed = True

            for i, office in enumerate(test_offices, 1):
                # Billingを取得
                billing = await crud.billing.get_by_office_id(db=db, office_id=office.id)

                # 期待される状態を判定
                if "FREE_TO_PAST_DUE" in office.name:
                    expected = BillingStatus.past_due
                elif "EARLY_TO_ACTIVE" in office.name:
                    expected = BillingStatus.active
                elif "CANCELING_TO_CANCELED" in office.name:
                    expected = BillingStatus.canceled
                else:
                    expected = None

                # 結果判定
                if billing and billing.billing_status == expected:
                    status_icon = "✅"
                    result_text = "PASS"
                else:
                    status_icon = "❌"
                    result_text = "FAIL"
                    all_passed = False

                print(f"{status_icon} {i}. {office.name}")
                print(f"   Office ID: {office.id}")
                print(f"   Billing ID: {billing.id if billing else 'N/A'}")
                print(f"   Expected Status: {expected.value if expected else 'N/A'}")
                print(f"   Actual Status: {billing.billing_status.value if billing else 'N/A'}")
                print(f"   Result: {result_text}\n")

            print(f"{'='*60}")
            if all_passed:
                print(f"✅ すべてのテストが成功しました")
            else:
                print(f"❌ 一部のテストが失敗しました")
            print(f"{'='*60}\n")

            print(f"🧹 クリーンアップするには:")
            print(f"   docker exec keikakun_app-backend-1 python3 scripts/test_batch_processing.py cleanup")

        except Exception as e:
            print(f"❌ エラー: {e}")
            raise


async def cleanup_test_data():
    """テストデータをクリーンアップ"""
    async with AsyncSessionLocal() as db:
        try:
            print(f"\n{'='*60}")
            print(f"テストデータクリーンアップ開始")
            print(f"{'='*60}\n")

            # テストデータのOfficeを取得
            result = await db.execute(
                select(Office).where(
                    Office.name.like(f"{TEST_OFFICE_NAME_PREFIX}%"),
                    Office.is_test_data == True
                )
            )
            test_offices = result.scalars().all()

            if not test_offices:
                print("⚠️  削除対象のテストデータが見つかりません")
                return

            print(f"🗑️  削除対象: {len(test_offices)}件\n")

            for i, office in enumerate(test_offices, 1):
                print(f"{i}. {office.name}")
                print(f"   Office ID: {office.id}")

                # Officeを削除（BillingはCascadeで削除される）
                await db.delete(office)

            await db.commit()

            print(f"\n{'='*60}")
            print(f"✅ クリーンアップ完了")
            print(f"{'='*60}\n")

        except Exception as e:
            await db.rollback()
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

    if command == "setup":
        minutes = 1
        if len(sys.argv) > 2 and sys.argv[2] == "--minutes" and len(sys.argv) > 3:
            minutes = int(sys.argv[3])
        await setup_test_data(minutes=minutes)

    elif command == "run":
        await run_batch_processing()

    elif command == "verify":
        await verify_results()

    elif command == "cleanup":
        await cleanup_test_data()

    else:
        print(f"❌ 不明なコマンド: {command}")
        print_usage()


if __name__ == "__main__":
    asyncio.run(main())
