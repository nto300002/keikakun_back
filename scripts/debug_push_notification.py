"""
Web Push通知が送信されない原因を調査するデバッグスクリプト

使い方:
docker exec keikakun_app-backend-1 python3 scripts/debug_push_notification.py
"""
import asyncio
import sys
from datetime import datetime, timezone
from sqlalchemy import select, func

sys.path.insert(0, '/app')

from app.db.session import AsyncSessionLocal
from app.models.push_subscription import PushSubscription
from app.models.staff import Staff
from app.models.office import Office, OfficeStaff
from app.models.welfare_recipient import WelfareRecipient
from app.services.welfare_recipient_service import WelfareRecipientService
from app.utils.privacy_utils import mask_email


async def debug_push_notification():
    """Web Push通知が送信されない原因を調査"""
    async with AsyncSessionLocal() as db:
        try:
            print(f"\n{'='*70}")
            print(f"Web Push通知デバッグ情報")
            print(f"{'='*70}")
            print(f"調査時刻: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z')}")
            print(f"{'='*70}\n")

            # 1. Push購読の確認
            print("1️⃣  Push購読データの確認")
            print("-" * 70)
            subscription_count = await db.scalar(select(func.count()).select_from(PushSubscription))
            print(f"   総購読件数: {subscription_count}件")

            if subscription_count > 0:
                # 購読詳細を取得
                result = await db.execute(
                    select(PushSubscription, Staff)
                    .join(Staff, PushSubscription.staff_id == Staff.id)
                )
                subscriptions = result.all()

                print(f"\n   📋 購読詳細:")
                for i, (sub, staff) in enumerate(subscriptions, 1):
                    print(f"   {i}. スタッフ: {staff.last_name} {staff.first_name} ({mask_email(staff.email)})")
                    print(f"      購読ID: {sub.id}")
                    print(f"      エンドポイント: {sub.endpoint[:50]}...")
                    print(f"      作成日時: {sub.created_at}")
            else:
                print(f"\n   ⚠️  購読データが登録されていません")
                print(f"   → これが原因でWeb Push通知が送信されません")
                print(f"\n   💡 解決策:")
                print(f"      1. フロントエンドでログイン")
                print(f"      2. プロフィール → 通知設定")
                print(f"      3. システム通知（Web Push）をONにする")

            print()

            # 2. スタッフの通知設定確認
            print("2️⃣  スタッフの通知設定確認")
            print("-" * 70)
            staff_result = await db.execute(
                select(Staff).where(Staff.deleted_at.is_(None))
            )
            staffs = staff_result.scalars().all()
            print(f"   総スタッフ数: {len(staffs)}人")

            system_notification_enabled_count = 0
            email_notification_enabled_count = 0

            print(f"\n   📋 通知設定詳細:")
            for i, staff in enumerate(staffs, 1):
                notification_prefs = staff.notification_preferences or {
                    "in_app_notification": True,
                    "email_notification": True,
                    "system_notification": False,
                    "email_threshold_days": 30,
                    "push_threshold_days": 10
                }

                system_enabled = notification_prefs.get("system_notification", False)
                email_enabled = notification_prefs.get("email_notification", True)
                push_threshold = notification_prefs.get("push_threshold_days", 10)
                email_threshold = notification_prefs.get("email_threshold_days", 30)

                if system_enabled:
                    system_notification_enabled_count += 1
                if email_enabled:
                    email_notification_enabled_count += 1

                system_icon = "✅" if system_enabled else "❌"
                email_icon = "✅" if email_enabled else "❌"

                print(f"   {i}. {staff.last_name} {staff.first_name} ({mask_email(staff.email)})")
                print(f"      メール通知: {email_icon} (閾値: {email_threshold}日前)")
                print(f"      システム通知: {system_icon} (閾値: {push_threshold}日前)")

            print(f"\n   📊 サマリー:")
            print(f"      メール通知ON: {email_notification_enabled_count}人")
            print(f"      システム通知ON: {system_notification_enabled_count}人")

            if system_notification_enabled_count == 0:
                print(f"\n   ⚠️  システム通知を有効にしているスタッフがいません")
                print(f"   → これが原因でWeb Push通知が送信されません")

            print()

            # 3. 事業所と期限アラート確認
            print("3️⃣  事業所と期限アラートの確認")
            print("-" * 70)
            office_result = await db.execute(
                select(Office).where(Office.deleted_at.is_(None))
            )
            offices = office_result.scalars().all()
            print(f"   総事業所数: {len(offices)}件")

            total_alerts = 0

            if len(offices) > 0:
                print(f"\n   📋 事業所別アラート詳細:")
                for i, office in enumerate(offices, 1):
                    # 期限アラートを取得（最大閾値30日で取得）
                    try:
                        alert_response = await WelfareRecipientService.get_deadline_alerts(
                            db=db,
                            office_id=office.id,
                            threshold_days=30,
                            limit=None,
                            offset=0
                        )

                        renewal_count = sum(1 for alert in alert_response.alerts if alert.alert_type == "renewal_deadline")
                        assessment_count = sum(1 for alert in alert_response.alerts if alert.alert_type == "assessment_incomplete")
                        total_alerts += alert_response.total

                        alert_icon = "🔔" if alert_response.total > 0 else "✅"

                        print(f"   {alert_icon} {i}. {office.name}")
                        print(f"      事業所ID: {office.id}")
                        print(f"      更新期限アラート: {renewal_count}件")
                        print(f"      アセスメント未完了: {assessment_count}件")
                        print(f"      合計: {alert_response.total}件")

                        # スタッフ数確認
                        staff_count_result = await db.execute(
                            select(func.count())
                            .select_from(Staff)
                            .join(OfficeStaff, OfficeStaff.staff_id == Staff.id)
                            .where(
                                OfficeStaff.office_id == office.id,
                                Staff.deleted_at.is_(None),
                                Staff.email.isnot(None)
                            )
                        )
                        staff_count = staff_count_result.scalar()
                        print(f"      所属スタッフ数: {staff_count}人")

                    except Exception as e:
                        print(f"   ❌ {i}. {office.name}")
                        print(f"      エラー: {e}")

                print(f"\n   📊 サマリー:")
                print(f"      総アラート数: {total_alerts}件")

                if total_alerts == 0:
                    print(f"\n   ℹ️  現在、期限が近い利用者がいません")
                    print(f"   → これが原因でWeb Push通知が送信されません")
            else:
                print(f"\n   ⚠️  事業所が登録されていません")

            print()

            # 4. 総合診断
            print("4️⃣  総合診断")
            print("-" * 70)

            issues = []

            if subscription_count == 0:
                issues.append("❌ Push購読データが登録されていない")

            if system_notification_enabled_count == 0:
                issues.append("❌ システム通知を有効にしているスタッフがいない")

            if total_alerts == 0:
                issues.append("ℹ️  期限が近い利用者がいない（正常）")

            if len(staffs) == 0:
                issues.append("❌ スタッフが登録されていない")

            if len(offices) == 0:
                issues.append("❌ 事業所が登録されていない")

            if issues:
                print(f"   🔍 検出された問題:")
                for issue in issues:
                    print(f"      {issue}")

                print(f"\n   💡 Web Push通知を送信するために必要な条件:")
                print(f"      1. ✅ 事業所が登録されている")
                print(f"      2. ✅ スタッフが登録されている")
                print(f"      3. ✅ スタッフがシステム通知を有効にしている")
                print(f"      4. ✅ Push購読データが登録されている")
                print(f"      5. ✅ 期限が近い利用者が存在する")
                print(f"      6. ✅ 閾値設定により対象アラートがフィルタリングされていない")
            else:
                print(f"   ✅ すべての条件が満たされています")

            print(f"\n{'='*70}\n")

        except Exception as e:
            print(f"\n❌ エラーが発生しました: {e}")
            import traceback
            traceback.print_exc()
            raise


if __name__ == "__main__":
    asyncio.run(debug_push_notification())
