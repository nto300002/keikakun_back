"""
WebPushExceptionの構造を確認するテストスクリプト

使い方:
    docker exec keikakun_app-backend-1 python3 scripts/test_webpush_exception.py
"""
import sys
sys.path.insert(0, '/app')

from pywebpush import webpush, WebPushException
from app.core.config import settings
import json


async def test_webpush_exception():
    """実際に410エラーを発生させてWebPushExceptionの構造を確認"""
    from app.db.session import AsyncSessionLocal
    from sqlalchemy import select
    from app.models.push_subscription import PushSubscription

    print("\n" + "=" * 70)
    print("WebPushException構造テスト")
    print("=" * 70 + "\n")

    # DBから実際の購読を取得
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(PushSubscription))
        subscriptions = result.scalars().all()

        if not subscriptions:
            print("❌ 購読データが存在しません")
            return

        # 最初の購読を使用
        sub = subscriptions[0]
        print(f"📋 テスト対象購読:")
        print("   エンドポイント: <hidden>")
        print(f"   スタッフID: {sub.staff_id}\n")

        invalid_subscription = {
            "endpoint": sub.endpoint,
            "keys": {
                "p256dh": sub.p256dh_key,
                "auth": sub.auth_key
            }
        }

    payload = {
        "title": "テスト通知",
        "body": "WebPushExceptionのテスト",
        "data": {"type": "test"}
    }

    try:
        webpush(
            subscription_info=invalid_subscription,
            data=json.dumps(payload),
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": settings.VAPID_SUBJECT}
        )
        print("❌ エラーが発生しませんでした（想定外）")

    except WebPushException as e:
        print("✅ WebPushExceptionが発生しました\n")

        print("📋 Exception詳細:")
        print(f"   error_type: {type(e).__name__}")
        print("   e.message: <hidden>")
        http_info = getattr(e, "response", None)
        print(f"   has_http_info: {http_info is not None}")
        print()

        print(f"\n📋 Truthiness check:")
        print(f"   bool(http_info): {bool(http_info)}")
        print(f"   http_info is None: {http_info is None}")
        print(f"   http_info is not None: {http_info is not None}")
        print()

        if http_info is not None:
            print("📋 HTTP詳細:")
            print(f"   type(http_info): {type(http_info)}")
            print(f"   has_status_code: {hasattr(http_info, 'status_code')}")

            if hasattr(http_info, 'status_code'):
                print(f"   http_info.status_code: {http_info.status_code}")
                print(f"   type(http_info.status_code): {type(http_info.status_code)}")
                print()

                print("📋 条件チェック:")
                print(f"   http_info.status_code in [404, 410]: {http_info.status_code in [404, 410]}")
                print(f"   http_info.status_code == 410: {http_info.status_code == 410}")
                print()

                if http_info.status_code in [404, 410]:
                    print("✅ 410/404エラーとして認識できました！")
                    print("   → should_delete = True を返すべき")
                else:
                    print(f"❌ status_code {http_info.status_code} は 410/404 ではありません")
            else:
                print("   ❌ status_code属性が存在しません")

                print("   HTTP情報の属性出力は安全のため省略")
        else:
            print("❌ http_info is None")

        print("\n" + "=" * 70)

    except Exception as e:
        print(f"❌ 予期しないエラー: {type(e).__name__}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_webpush_exception())
