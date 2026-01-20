"""
スケジューラーテスト用スクリプト - Web Push通知

現在時刻の5秒後にWeb Push通知を送信するテストスクリプト。
実際のバッチ処理（期限アラート通知など）の動作確認用。

JWTトークン不要でPush通知が送信できることを確認します。
"""
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.push_subscription import PushSubscription
from app.models.staff import Staff
from app.core.push import send_push_notification
from app.schemas.push_subscription import PushSubscriptionInfo


async def send_test_notifications():
    """
    全てのアクティブな購読にテスト通知を送信

    JWTトークンを使わず、DBから直接購読情報を取得して送信。
    実際のバッチ処理と同じ方法で動作します。
    """
    print("=" * 80)
    print("スケジューラーテスト - Web Push通知")
    print("=" * 80)
    print()

    async with AsyncSessionLocal() as db:
        # 全ての購読情報を取得（JWTトークン不要）
        stmt = select(PushSubscription, Staff).join(
            Staff, PushSubscription.staff_id == Staff.id
        )
        result = await db.execute(stmt)
        subscriptions_with_staff = result.all()

        if not subscriptions_with_staff:
            print("❌ 購読情報が見つかりません")
            print()
            print("先にブラウザでPush通知を購読してください:")
            print("1. http://localhost:3000 にログイン")
            print("2. ブラウザの通知許可をオン")
            print("3. ブラウザが自動的にPush購読を登録")
            print()
            return

        print(f"📊 購読情報: {len(subscriptions_with_staff)}件")
        print()

        success_count = 0
        failure_count = 0

        for subscription, staff in subscriptions_with_staff:
            print(f"📤 送信中: {staff.last_name} {staff.first_name} ({staff.email})")
            print(f"   Endpoint: {subscription.endpoint[:60]}...")

            # PushSubscriptionInfoに変換
            subscription_info = PushSubscriptionInfo.from_db_model(subscription)

            # Push通知を送信（JWTトークン不要）
            success, should_delete = await send_push_notification(
                subscription_info=subscription_info.model_dump(),
                title="🧪 スケジューラーテスト",
                body=f"{staff.last_name} {staff.first_name}さん、スケジューラーからのテスト通知です！現在時刻: {datetime.now(timezone.utc).strftime('%H:%M:%S')}",
                icon="/icon-192.png",
                badge="/icon-192.png",
                data={
                    "type": "scheduler_test",
                    "timestamp": str(datetime.now(timezone.utc)),
                    "staff_id": str(staff.id)
                }
            )

            if success:
                success_count += 1
                print("   ✅ 送信成功")
            elif should_delete:
                failure_count += 1
                print("   ❌ 410 Gone - 購読が無効（自動削除）")
                await db.delete(subscription)
                await db.commit()
            else:
                failure_count += 1
                print("   ❌ 送信失敗")

            print()

        print("=" * 80)
        print("📊 送信結果")
        print("=" * 80)
        print(f"成功: {success_count}件")
        print(f"失敗: {failure_count}件")
        print(f"合計: {len(subscriptions_with_staff)}件")
        print()


async def scheduled_test(delay_seconds: int = 5):
    """
    指定秒数後にテスト通知を送信

    Args:
        delay_seconds: 待機時間（秒）
    """
    now = datetime.now(timezone.utc)
    scheduled_time = now.replace(microsecond=0)

    print("=" * 80)
    print("⏰ スケジュール設定")
    print("=" * 80)
    print(f"現在時刻:     {now.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"実行予定時刻: {delay_seconds}秒後")
    print(f"待機中...")
    print()

    # 指定秒数待機
    await asyncio.sleep(delay_seconds)

    print("=" * 80)
    print(f"⏰ {delay_seconds}秒経過 - 通知送信開始")
    print("=" * 80)
    print()

    # 通知送信
    await send_test_notifications()

    print("=" * 80)
    print("✅ テスト完了")
    print("=" * 80)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="スケジューラーテスト - Web Push通知")
    parser.add_argument(
        "--delay",
        type=int,
        default=5,
        help="通知送信までの待機時間（秒）デフォルト: 5秒"
    )
    parser.add_argument(
        "--now",
        action="store_true",
        help="待機せずに即座に送信"
    )

    args = parser.parse_args()

    if args.now:
        print("即座に送信モード")
        print()
        asyncio.run(send_test_notifications())
    else:
        asyncio.run(scheduled_test(delay_seconds=args.delay))
