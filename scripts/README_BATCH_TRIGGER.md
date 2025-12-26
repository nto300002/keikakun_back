# バッチ処理発動条件セットアップガイド

開発環境の実際のデータを使って、バッチ処理の発動条件をテストするためのツールです。

---

## 🎯 テストできるバッチ処理

1. **free → past_due**: Trial期限切れ（未課金）
2. **early_payment → active**: Trial期限切れ（課金済み）
3. **canceling → canceled**: キャンセル期限到達

---

## 📋 基本的な使い方

### ステップ1: 既存データを確認

```bash
docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py list
```

**出力例**:
```
================================================================================
既存Billingデータ一覧
================================================================================

📋 最新20件を表示

1. Billing ID: 123e4567-e89b-12d3-a456-426614174000
   Office ID: 234e5678-e89b-12d3-a456-426614174001
   Status: free
   Trial End: 2025-12-24 10:00:00 (✅ 残り90日)
   Cancel At: N/A (N/A)
   Stripe Sub: N/A

2. Billing ID: 345e6789-e89b-12d3-a456-426614174002
   Office ID: 456e7890-e89b-12d3-a456-426614174003
   Status: early_payment
   Trial End: 2025-12-24 15:00:00 (✅ 残り90日)
   Cancel At: N/A (N/A)
   Stripe Sub: sub_xxxxx

3. Billing ID: 567e8901-e89b-12d3-a456-426614174004
   Office ID: 678e9012-e89b-12d3-a456-426614174005
   Status: canceling
   Trial End: 2026-01-01 00:00:00 (✅ 残り120日)
   Cancel At: 2025-12-25 00:00:00 (✅ 残り1日)
   Stripe Sub: sub_yyyyy
```

---

### ステップ2: 期限を1分後に設定（期限超過を作り出す）

```bash
# Billing IDを指定して、1分後に期限切れにする
docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py expire --billing-id <billing_id> --minutes 1
```

**ケース別の動作**:

#### ケース1: free → past_due
```bash
# freeステータスのBillingのtrial_end_dateを1分後に設定
docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py expire --billing-id 123e4567-e89b-12d3-a456-426614174000 --minutes 1
```

**出力例**:
```
================================================================================
期限設定: 1分後に期限切れ
================================================================================

📋 Billing情報:
   Billing ID: 123e4567-e89b-12d3-a456-426614174000
   Office ID: 234e5678-e89b-12d3-a456-426614174001
   Current Status: free
   現在時刻: 2025-12-24 00:50:00 UTC
   期限時刻: 2025-12-24 00:51:00 UTC

🎯 バッチ処理ケース: free → past_due
   trial_end_date を 2025-12-24 00:51:00 に設定

================================================================================
✅ 期限設定完了
================================================================================

⏰ 1分後にバッチ処理が発動します:
   期待される遷移: free → past_due
```

#### ケース2: early_payment → active
```bash
# early_paymentステータスのBillingのtrial_end_dateを1分後に設定
docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py expire --billing-id 345e6789-e89b-12d3-a456-426614174002 --minutes 1
```

**出力例**:
```
🎯 バッチ処理ケース: early_payment → active
   trial_end_date を 2025-12-24 00:51:00 に設定

⏰ 1分後にバッチ処理が発動します:
   期待される遷移: early_payment → active
```

#### ケース3: canceling → canceled
```bash
# cancelingステータスのBillingのscheduled_cancel_atを1分後に設定
docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py expire --billing-id 567e8901-e89b-12d3-a456-426614174004 --minutes 1
```

**出力例**:
```
🎯 バッチ処理ケース: canceling → canceled
   scheduled_cancel_at を 2025-12-24 00:51:00 に設定

⏰ 1分後にバッチ処理が発動します:
   期待される遷移: canceling → canceled
```

---

### ステップ3: バッチ処理発動条件を確認

```bash
docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py check
```

**出力例**:
```
================================================================================
バッチ処理発動条件チェック
現在時刻: 2025-12-24 00:52:00 UTC
================================================================================

1️⃣  Trial期限切れ（free → past_due）:
   ✅ 発動条件を満たすBilling: 1件
      - Billing ID: 123e4567-e89b-12d3-a456-426614174000
        Trial End: 2025-12-24 00:51:00

2️⃣  Trial期限切れ（early_payment → active）:
   ✅ 発動条件を満たすBilling: 1件
      - Billing ID: 345e6789-e89b-12d3-a456-426614174002
        Trial End: 2025-12-24 00:51:00

3️⃣  スケジュールキャンセル期限切れ（canceling → canceled）:
   ✅ 発動条件を満たすBilling: 1件
      - Billing ID: 567e8901-e89b-12d3-a456-426614174004
        Cancel At: 2025-12-24 00:51:00

================================================================================
📊 合計: 3件のBillingがバッチ処理の発動条件を満たしています
================================================================================
```

---

### ステップ4: スケジューラーを待つ（または手動実行）

#### オプションA: スケジューラーを待つ

スケジューラーは毎日以下の時刻に自動実行されます:
- **Trial期限チェック**: 毎日 0:00 UTC
- **Cancel期限チェック**: 毎日 0:05 UTC

次の実行時刻まで待ちます。

#### オプションB: 手動でバッチ処理を実行

すぐに結果を確認したい場合は、以下のコマンドでバッチ処理を手動実行できます:

```bash
# Trial期限チェック（free → past_due, early_payment → active）
docker exec keikakun_app-backend-1 python3 -c "
import asyncio
from app.db.session import AsyncSessionLocal
from app.tasks.billing_check import check_trial_expiration

async def main():
    async with AsyncSessionLocal() as db:
        count = await check_trial_expiration(db=db)
        print(f'Updated {count} billing(s)')

asyncio.run(main())
"

# Cancel期限チェック（canceling → canceled）
docker exec keikakun_app-backend-1 python3 -c "
import asyncio
from app.db.session import AsyncSessionLocal
from app.tasks.billing_check import check_scheduled_cancellation

async def main():
    async with AsyncSessionLocal() as db:
        count = await check_scheduled_cancellation(db=db)
        print(f'Updated {count} billing(s)')

asyncio.run(main())
"
```

---

### ステップ5: 結果を確認

```bash
# Billingデータを再度確認
docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py list
```

ステータスが変更されていることを確認:
- free → **past_due** ✅
- early_payment → **active** ✅
- canceling → **canceled** ✅

---

### ステップ6: 期限をリセット（元に戻す）

```bash
# 期限を90日後に戻す
docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py reset --billing-id <billing_id>
```

**出力例**:
```
================================================================================
期限リセット: 90日後に設定
================================================================================

📋 Billing情報:
   Billing ID: 123e4567-e89b-12d3-a456-426614174000
   Office ID: 234e5678-e89b-12d3-a456-426614174001
   Current Status: past_due
   現在時刻: 2025-12-24 00:55:00 UTC
   新期限: 2026-03-24 00:55:00 UTC

🔄 trial_end_date を未来に設定

================================================================================
✅ 期限リセット完了
================================================================================

📊 バッチ処理は発動しません（期限まで90日）
```

---

## 🎮 完全なテストフロー例

```bash
# 1. データ確認
docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py list

# 2. freeステータスのBillingを1分後に期限切れにする
docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py expire --billing-id <billing_id_1> --minutes 1

# 3. early_paymentステータスのBillingを1分後に期限切れにする
docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py expire --billing-id <billing_id_2> --minutes 1

# 4. cancelingステータスのBillingを1分後に期限切れにする
docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py expire --billing-id <billing_id_3> --minutes 1

# 5. 発動条件を確認
docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py check

# 6. 1分待つ
sleep 60

# 7. バッチ処理を手動実行
docker exec keikakun_app-backend-1 python3 -c "import asyncio; from app.db.session import AsyncSessionLocal; from app.tasks.billing_check import check_trial_expiration; asyncio.run((lambda: AsyncSessionLocal().__aenter__())()).then(lambda db: check_trial_expiration(db=db))"

docker exec keikakun_app-backend-1 python3 -c "import asyncio; from app.db.session import AsyncSessionLocal; from app.tasks.billing_check import check_scheduled_cancellation; asyncio.run((lambda: AsyncSessionLocal().__aenter__())()).then(lambda db: check_scheduled_cancellation(db=db))"

# 8. 結果確認
docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py list

# 9. リセット
docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py reset --billing-id <billing_id_1>
docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py reset --billing-id <billing_id_2>
docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py reset --billing-id <billing_id_3>
```

---

## 💡 Tips

### より長い時間でテストしたい場合

```bash
# 5分後に期限切れ
docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py expire --billing-id <billing_id> --minutes 5

# 60分後に期限切れ
docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py expire --billing-id <billing_id> --minutes 60
```

### データベースで直接確認

```sql
-- 発動条件を満たすBillingを確認
SELECT
    id,
    office_id,
    billing_status,
    trial_end_date,
    scheduled_cancel_at,
    NOW() as current_time
FROM billings
WHERE
    (billing_status = 'free' AND trial_end_date < NOW())
    OR (billing_status = 'early_payment' AND trial_end_date < NOW())
    OR (billing_status = 'canceling' AND scheduled_cancel_at < NOW());
```

---

## ⚠️ 注意事項

1. **本番環境では絶対に実行しないでください**
   - このスクリプトは開発環境専用です

2. **テスト後は必ずリセットしてください**
   - 期限を元に戻さないと、意図しないバッチ処理が発動する可能性があります

3. **複数のBillingを同時にテストする場合**
   - 一度に多くのBillingを期限切れにすると、バッチ処理の負荷が高くなります
   - 少数ずつテストすることをおすすめします

---

**最終更新**: 2025-12-24
