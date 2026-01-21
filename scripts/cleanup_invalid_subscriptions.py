"""
無効なPush購読をクリーンアップするスクリプト

使い方:
    docker exec keikakun_app-backend-1 python3 scripts/cleanup_invalid_subscriptions.py
"""
import asyncio
import sys

sys.path.insert(0, '/app')

from app.db.session import AsyncSessionLocal
from app import crud
from app.core.push import send_push_notification


async def cleanup_invalid_subscriptions():
    """無効なPush購読をDBから削除"""
    async with AsyncSessionLocal() as db:
        try:
            print("\n" + "=" * 70)
            print("無効なPush購読のクリーンアップ")
            print("=" * 70 + "\n")

            # 全購読を取得
            from sqlalchemy import select
            from app.models.push_subscription import PushSubscription

            result = await db.execute(select(PushSubscription))
            all_subscriptions = result.scalars().all()

            if not all_subscriptions:
                print("ℹ️  購読データが存在しません")
                print("=" * 70 + "\n")
                return

            print(f"📋 購読データ: {len(all_subscriptions)}件\n")

            valid_count = 0
            invalid_count = 0
            error_count = 0

            for i, sub in enumerate(all_subscriptions, 1):
                print(f"{i}. エンドポイント: {sub.endpoint[:50]}...")
                print(f"   スタッフID: {sub.staff_id}")

                try:
                    # テストメッセージを送信して有効性を確認
                    success, should_delete = await send_push_notification(
                        subscription_info={
                            "endpoint": sub.endpoint,
                            "keys": {
                                "p256dh": sub.p256dh_key,
                                "auth": sub.auth_key
                            }
                        },
                        title="購読確認テスト",
                        body="この通知は購読の有効性を確認するためのものです",
                        data={"type": "test", "test": True}
                    )

                    if success:
                        print(f"   ✅ 有効な購読\n")
                        valid_count += 1
                    elif should_delete:
                        print(f"   ❌ 無効な購読（410/404エラー） → 削除中...")
                        await crud.push_subscription.delete_by_endpoint(
                            db=db,
                            endpoint=sub.endpoint
                        )
                        print(f"   🗑️  削除完了\n")
                        invalid_count += 1
                    else:
                        print(f"   ⚠️  一時的なエラー（保持）\n")
                        error_count += 1

                except Exception as e:
                    print(f"   ❌ エラー: {e}\n")
                    error_count += 1

            print("=" * 70)
            print("📊 クリーンアップ完了")
            print("=" * 70 + "\n")
            print(f"   有効な購読: {valid_count}件")
            print(f"   削除した購読: {invalid_count}件")
            print(f"   エラー: {error_count}件\n")

            print("💡 次のステップ:")
            print("   1. ブラウザでサイトデータをクリア")
            print("   2. 再ログイン")
            print("   3. プロフィール → 通知設定 → システム通知をON")
            print("   4. バッチ処理を実行:")
            print("      docker exec keikakun_app-backend-1 python3 scripts/run_deadline_notification.py")
            print("")

        except Exception as e:
            print(f"❌ エラーが発生しました: {e}")
            import traceback
            traceback.print_exc()
            raise


if __name__ == "__main__":
    asyncio.run(cleanup_invalid_subscriptions())
