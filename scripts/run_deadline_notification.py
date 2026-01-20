"""
期限アラート通知バッチ処理の手動実行スクリプト

使い方:
1. ドライラン（送信せず、送信予定のみ表示）:
   docker exec keikakun_app-backend-1 python3 scripts/run_deadline_notification.py --dry-run

2. 本番実行（実際にメール + Web Push送信）:
   docker exec keikakun_app-backend-1 python3 scripts/run_deadline_notification.py

3. 休日スキップを無視して強制実行:
   docker exec keikakun_app-backend-1 python3 scripts/run_deadline_notification.py --force

注意:
- 本番実行時は実際にメールとWeb Push通知が送信されます
- スタッフの通知設定（notification_preferences）に基づいて送信されます
- 閾値設定（email_threshold_days, push_threshold_days）が反映されます
"""
import asyncio
import sys
from datetime import datetime, timezone

sys.path.insert(0, '/app')

from app.db.session import AsyncSessionLocal
from app.tasks.deadline_notification import send_deadline_alert_emails
from app.utils.holiday_utils import is_japanese_weekday_and_not_holiday


async def run_notification_batch(dry_run: bool = False, force: bool = False):
    """
    期限アラート通知バッチを実行

    Args:
        dry_run: Trueの場合は送信せず、送信予定のみ表示
        force: Trueの場合は休日判定をスキップして強制実行
    """
    async with AsyncSessionLocal() as db:
        try:
            now = datetime.now(timezone.utc)
            jst_time = datetime.now(timezone.utc).astimezone()

            print(f"\n{'='*70}")
            print(f"期限アラート通知バッチ処理")
            print(f"{'='*70}")
            print(f"実行時刻（UTC）: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            print(f"実行時刻（JST）: {jst_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            print(f"実行モード: {'🔍 ドライラン（テスト）' if dry_run else '🚀 本番実行'}")

            # 休日判定
            today = now.date()
            is_business_day = is_japanese_weekday_and_not_holiday(today)
            print(f"休日判定: {'✅ 平日' if is_business_day else '⚠️ 休日・祝日'}")

            if not is_business_day and not force:
                print(f"\n⚠️  今日は休日・祝日のため、バッチ処理をスキップします")
                print(f"   強制実行する場合は --force オプションを使用してください:")
                print(f"   docker exec keikakun_app-backend-1 python3 scripts/run_deadline_notification.py --force")
                print(f"{'='*70}\n")
                return

            if force and not is_business_day:
                print(f"⚠️  --force オプションにより休日・祝日でも実行します")

            print(f"{'='*70}\n")

            # バッチ処理実行
            print("📨 バッチ処理を開始します...\n")

            result = await send_deadline_alert_emails(db=db, dry_run=dry_run)

            # 結果表示
            print(f"\n{'='*70}")
            print(f"✅ バッチ処理完了")
            print(f"{'='*70}\n")

            print(f"📊 実行結果:")
            print(f"   メール送信: {result['email_sent']}件")
            print(f"   Web Push送信: {result['push_sent']}件")
            print(f"   Web Push失敗: {result['push_failed']}件")

            if dry_run:
                print(f"\n💡 ドライランモードで実行されました")
                print(f"   実際には送信されていません")
                print(f"\n   本番実行する場合は:")
                print(f"   docker exec keikakun_app-backend-1 python3 scripts/run_deadline_notification.py")
            else:
                print(f"\n✅ 通知が送信されました")
                if result['push_failed'] > 0:
                    print(f"   ⚠️ {result['push_failed']}件のWeb Push送信に失敗しました")
                    print(f"   期限切れの購読は自動的に削除されています")

            print(f"{'='*70}\n")

        except Exception as e:
            print(f"\n{'='*70}")
            print(f"❌ エラーが発生しました")
            print(f"{'='*70}")
            print(f"エラー内容: {e}")
            print(f"{'='*70}\n")
            raise


def print_usage():
    """使い方を表示"""
    print(__doc__)


async def main():
    """メイン関数"""
    dry_run = False
    force = False

    # コマンドライン引数を解析
    if len(sys.argv) > 1:
        if "--help" in sys.argv or "-h" in sys.argv:
            print_usage()
            return

        if "--dry-run" in sys.argv:
            dry_run = True

        if "--force" in sys.argv:
            force = True

    await run_notification_batch(dry_run=dry_run, force=force)


if __name__ == "__main__":
    asyncio.run(main())
