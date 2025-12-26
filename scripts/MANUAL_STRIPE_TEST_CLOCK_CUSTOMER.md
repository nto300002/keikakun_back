# Stripe Dashboard: Test Clock付きCustomer作成マニュアル

**目的**: Stripe DashboardでTest Clock付きのCustomerとSubscriptionを作成し、Webhookテストの準備をする

**所要時間**: 約5分

---

## 📋 事前準備

### 必要なもの

- ✅ Stripeアカウント（テストモード）
- ✅ Stripe Dashboard アクセス権限
- ✅ Price ID（アプリで使用しているプランのID）

### Price IDの確認方法

```bash
# .envファイルから確認
cat k_back/.env | grep STRIPE_PRICE_ID
```

または

**Stripe Dashboard → Products → あなたのプラン → Pricing**

---

## 🎯 全体の流れ

```
1. Stripe Dashboardにログイン
   ↓
2. Test Clockを作成
   ↓
3. Test Clock付きCustomerを作成
   ↓
4. Subscriptionを作成（Trial期間設定）
   ↓
5. アプリDBと連携
```

---

## ステップ1: Stripe Dashboardにログイン

### 1-1. Stripe Dashboardを開く

```
https://dashboard.stripe.com/
```

### 1-2. テストモードに切り替え

**重要**: 必ずテストモードで作業してください

- 画面右上のトグルスイッチを確認
- 「**Test mode**」になっていることを確認
- もし「Live mode」の場合、クリックしてテストモードに切り替え

**確認方法**:
- URL: `https://dashboard.stripe.com/test/...` (testが含まれる)
- 画面右上: 「Test mode」のバッジが表示

---

## ステップ2: Test Clockを作成

### 2-1. Test Clocksページに移動

**ナビゲーション**:

```
Stripe Dashboard (左サイドバー)
  → Billing
    → Test clocks
```

または、直接URLで開く:
```
https://dashboard.stripe.com/test/billing/subscriptions/test-clocks
```

### 2-2. 「Create test clock」をクリック

画面右上の青いボタン「**+ Create test clock**」をクリック

### 2-3. Test Clock情報を入力

**フォーム**:

| フィールド | 入力内容 | 例 |
|-----------|---------|-----|
| **Name** | Test Clockの名前（任意） | `E2E Test 2025-12-25` |
| **Start time** | 開始時刻（デフォルトのまま推奨） | `Current time` のまま |

**入力例**:
```
Name: E2E Webhook Test 2025-12-25 10:00
Start time: Current time (2025-12-25 10:00:00 UTC)
```

### 2-4. 「Create」をクリック

### 2-5. Test Clock IDをコピー

作成されたTest Clockの詳細ページが表示されます。

**Test Clock IDをコピー**:
- 画面上部に表示される `clock_xxxxxxxxxxxxx` の形式のID
- 右側の「コピー」アイコンをクリック

**例**:
```
Test Clock ID: clock_1ShhZ5BxyBErCNcAc3vT1Ir1
```

**メモ帳に保存しておく**（後で使用）

---

## ステップ3: Test Clock付きCustomerを作成

### 3-1. Customersページに移動

**ナビゲーション**:

```
Stripe Dashboard (左サイドバー)
  → Customers
```

または、直接URLで開く:
```
https://dashboard.stripe.com/test/customers
```

### 3-2. 「Add customer」をクリック

画面右上の青いボタン「**+ Add customer**」をクリック

### 3-3. Customer情報を入力

**必須フィールド**:

| フィールド | 入力内容 | 例 |
|-----------|---------|-----|
| **Email** | テスト用メールアドレス | `e2e-test-20251225@example.com` |
| **Name** | 顧客名（任意） | `E2E Test Customer` |
| **Test clock** | 先ほど作成したTest Clock | `E2E Webhook Test 2025-12-25 10:00` |

**重要**:
- **Test clock**フィールドを必ず選択してください
- ドロップダウンから先ほど作成したTest Clockを選択

**入力例**:
```
Email: e2e-test-20251225@example.com
Name: E2E Test Customer
Description: (空欄でOK)
Test clock: E2E Webhook Test 2025-12-25 10:00 ← 選択
```

**その他のフィールド**:
- Description: 空欄でOK
- Phone: 空欄でOK
- Address: 空欄でOK
- Tax IDs: 空欄でOK

### 3-4. 「Add customer」をクリック（下部の青いボタン）

### 3-5. Customer IDをコピー

作成されたCustomerの詳細ページが表示されます。

**Customer IDをコピー**:
- 画面上部に表示される `cus_xxxxxxxxxxxxx` の形式のID
- 右側の「コピー」アイコンをクリック

**例**:
```
Customer ID: cus_RHqY8x0ZaBcDef
```

**メモ帳に保存しておく**（後で使用）

---

## ステップ4: Subscriptionを作成（Trial期間設定）

### 4-1. Customer詳細ページでSubscriptionsセクションに移動

**現在表示されているページ**: Customer詳細ページ

**下にスクロール**して「**Subscriptions**」セクションを探す

### 4-2. 「Create subscription」をクリック

「**+ Create subscription**」ボタンをクリック

### 4-3. Subscription情報を入力

**Product & Pricing**:

1. **「Add product」または検索ボックスをクリック**
2. あなたのプランを検索して選択
   - 例: 「月額6,000円プラン」
3. Quantity: `1` のまま

**Trial Settings**:

1. 「**Add trial period**」をクリック
2. Trial期間を設定:
   - **Trial period**: `7` days（テストしやすい短い期間を推奨）
   - または `3` days、`1` days など

**入力例**:
```
Product: 月額6,000円プラン (price_xxxxx)
Quantity: 1
Trial period: 7 days
```

**その他の設定**:
- Default payment method: 空欄でOK（テストなので）
- Start date: `Immediately` のまま
- Billing cycle: デフォルトのまま

### 4-4. 「Start subscription」をクリック（下部の青いボタン）

### 4-5. Subscription IDをコピー

作成されたSubscriptionの詳細が表示されます。

**Subscription IDをコピー**:
- `sub_xxxxxxxxxxxxx` の形式のID
- 右側の「コピー」アイコンをクリック

**例**:
```
Subscription ID: sub_1ShhZ5BxyBErCNcATO1ys9DU
```

**メモ帳に保存しておく**（後で使用）

---

## ステップ5: 作成した情報を確認

### 5-1. メモした情報を整理

以下の情報をメモしているか確認:

```
Test Clock ID:    clock_1ShhZ5BxyBErCNcAc3vT1Ir1
Customer ID:      cus_RHqY8x0ZaBcDef
Subscription ID:  sub_1ShhZ5BxyBErCNcATO1ys9DU
Email:            e2e-test-20251225@example.com
Trial period:     7 days
```

### 5-2. Test Clockの状態を確認

**Stripe Dashboard → Billing → Test clocks → 作成したTest Clock**

**確認項目**:
- Status: `Ready`
- Frozen time: 現在時刻
- Customers: `1`
- Subscriptions: `1`

---

## ステップ6: アプリDBと連携

### オプションA: 既存のBillingに紐付ける

既存のOffice/BillingがあるがStripe情報だけ更新したい場合

```sql
-- Billing IDを確認
SELECT id, office_id, billing_status, stripe_customer_id
FROM billings
WHERE office_id = '<your_office_id>';

-- Stripe情報を更新
UPDATE billings
SET
    stripe_customer_id = 'cus_RHqY8x0ZaBcDef',
    stripe_subscription_id = 'sub_1ShhZ5BxyBErCNcATO1ys9DU',
    billing_status = 'early_payment',
    trial_end_date = NOW() + INTERVAL '7 days'
WHERE id = '<billing_id>';
```

### オプションB: 新規にOffice/Billingを作成

完全に独立したテストデータを作成したい場合

```bash
docker exec -it keikakun_app-backend-1 python3 << 'EOF'
import asyncio
from uuid import uuid4
from datetime import datetime, timedelta, timezone
from app.db.session import AsyncSessionLocal
from app.models.office import Office
from app.models.billing import Billing
from app.models.enums import BillingStatus, OfficeType

async def create_test_data():
    async with AsyncSessionLocal() as db:
        # 1. テスト用Officeを作成
        office = Office(
            id=uuid4(),
            name='E2E Test Office 2025-12-25',
            type=OfficeType.VISITING_CARE,
            phone_number='000-0000-9999',
            is_test_data=True
        )
        db.add(office)
        await db.flush()

        # 2. Billingを作成
        billing = Billing(
            id=uuid4(),
            office_id=office.id,
            billing_status=BillingStatus.early_payment,
            trial_start_date=datetime.now(timezone.utc),
            trial_end_date=datetime.now(timezone.utc) + timedelta(days=7),
            current_plan_amount=6000,
            stripe_customer_id='cus_RHqY8x0ZaBcDef',  # ← Stripe Dashboard
            stripe_subscription_id='sub_1ShhZ5BxyBErCNcATO1ys9DU'  # ← Stripe Dashboard
        )
        db.add(billing)

        await db.commit()
        await db.refresh(office)
        await db.refresh(billing)

        print(f'✅ テストデータ作成完了')
        print(f'   Office ID: {office.id}')
        print(f'   Billing ID: {billing.id}')
        print(f'   Stripe Customer: {billing.stripe_customer_id}')
        print(f'   Stripe Subscription: {billing.stripe_subscription_id}')

asyncio.run(create_test_data())
EOF
```

---

## ステップ7: 動作確認

### 7-1. アプリでBillingステータスを確認

```bash
docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py list
```

**期待される出力**:
```
Billing ID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
Status: early_payment ✅
Trial End: 2026-01-01 00:00:00 (✅ 残り7日)
Stripe Sub: sub_1ShhZ5BxyBErCNcATO1ys9DU ✅
```

### 7-2. Stripe Subscriptionの状態を確認

**Stripe Dashboard → Customers → 作成したCustomer → Subscriptions**

**確認項目**:
- Status: `Trialing`
- Trial ends: 7日後の日時
- Test clock: リンクが表示されている

---

## ステップ8: 時間を進めてWebhookテスト

### 8-1. Test Clockで時間を進める

#### 方法A: Stripe Dashboard経由

1. **Stripe Dashboard → Billing → Test clocks → 作成したTest Clock**
2. 「**Advance time**」ボタンをクリック
3. 進める時間を入力:
   - Days: `7`
   - Hours: `0`
   - Minutes: `0`
4. 「**Advance clock**」をクリック

#### 方法B: アプリのスクリプト経由（推奨）

```bash
docker exec keikakun_app-backend-1 python3 scripts/stripe_test_clock_manager.py advance \
  --clock-id clock_1ShhZ5BxyBErCNcAc3vT1Ir1 \
  --days 7
```

### 8-2. Webhookが発火したか確認

**Stripe Dashboard → Developers → Webhooks → Logs**

**期待されるWebhook**（発火順）:
1. `invoice.created` - インボイス作成
2. `invoice.finalized` - インボイス確定
3. **`invoice.payment_succeeded`** - 支払い成功 ← これ！
4. `customer.subscription.updated` - Subscription更新（trialing → active）

### 8-3. アプリログを確認

```bash
docker logs keikakun_app-backend-1 --tail 100 | grep -i webhook
```

**期待されるログ**:
```
[Webhook:evt_xxxxx] Payment succeeded for customer cus_RHqY8x0ZaBcDef, billing_status=active
```

### 8-4. アプリのBillingステータスを確認

```bash
docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py list
```

**期待される結果**:
```
Billing ID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
Status: active ✅ (early_payment → activeに遷移)
Trial End: 2026-01-01 00:00:00 (⏰ 期限切れ)
Stripe Sub: sub_1ShhZ5BxyBErCNcATO1ys9DU
```

---

## 🧹 クリーンアップ

### Test Clockを削除

#### 方法A: Stripe Dashboard

1. **Stripe Dashboard → Billing → Test clocks**
2. 削除したいTest Clockをクリック
3. 右上の「**Delete test clock**」をクリック
4. 確認ダイアログで「Delete」をクリック

#### 方法B: アプリのスクリプト

```bash
docker exec keikakun_app-backend-1 python3 scripts/stripe_test_clock_manager.py delete \
  --clock-id clock_1ShhZ5BxyBErCNcAc3vT1Ir1
```

**注意**: Test Clockを削除すると、紐付いたCustomerとSubscriptionも削除されます。

### テストデータを削除（アプリDB）

```sql
-- Billingを削除
DELETE FROM billings WHERE id = '<billing_id>';

-- Officeを削除
DELETE FROM offices WHERE id = '<office_id>';
```

または

```bash
docker exec -it keikakun_app-backend-1 psql $DATABASE_URL -c "
DELETE FROM billings WHERE stripe_customer_id = 'cus_RHqY8x0ZaBcDef';
DELETE FROM offices WHERE is_test_data = true AND name LIKE 'E2E Test%';
"
```

---

## ❓ トラブルシューティング

### Test clockフィールドが表示されない

**原因**: Stripe Dashboardのバージョンが古い

**解決策**:
1. ブラウザのキャッシュをクリア
2. ページをリロード
3. または、APIで作成:
   ```bash
   docker exec keikakun_app-backend-1 python3 scripts/stripe_test_clock_manager.py create --name "Test"
   ```

### Subscriptionが作成できない

**原因**: Price IDが見つからない

**解決策**:
1. **Stripe Dashboard → Products**で正しいプランを確認
2. Price IDをコピー
3. もう一度Subscription作成

### Webhookが発火しない

**確認事項**:
1. **Webhook Endpointが設定されているか**
   - Stripe Dashboard → Developers → Webhooks
   - エンドポイントURL: `https://your-app.com/api/v1/billing/webhook`
   - イベント: `invoice.payment_succeeded`など

2. **Test Clockで時間を進めたか**
   - Test Clocksページで「Status: Advanced」になっているか確認

3. **アプリが起動しているか**
   ```bash
   docker ps | grep backend
   ```

---

## 📋 チェックリスト

テストを開始する前に、以下を確認:

- [ ] Stripe Dashboardにログイン（Test mode）
- [ ] Test Clockを作成（ID: `clock_xxxxx`）
- [ ] Test Clock付きCustomerを作成（ID: `cus_xxxxx`）
- [ ] Subscriptionを作成（ID: `sub_xxxxx`、Trial: 7日）
- [ ] アプリDBにBilling作成またはStripe ID更新
- [ ] Billingステータスが`early_payment`であることを確認
- [ ] Test Clockで時間を進める（7日）
- [ ] Webhookログを確認（`invoice.payment_succeeded`）
- [ ] Billingステータスが`active`に遷移したことを確認

---

## 🎯 まとめ

### 手順の流れ

```
1. Stripe Dashboard → Billing → Test clocks → Create
   ↓
2. Test Clock ID をコピー: clock_xxxxx
   ↓
3. Stripe Dashboard → Customers → Add customer
   ↓
4. Test clock フィールドで clock_xxxxx を選択
   ↓
5. Customer ID をコピー: cus_xxxxx
   ↓
6. Create subscription（Trial: 7日）
   ↓
7. Subscription ID をコピー: sub_xxxxx
   ↓
8. アプリDBに Billing 作成 or Stripe ID 更新
   ↓
9. Test Clockで時間を進める（7日）
   ↓
10. Webhook 発火 → billing_status: active ✅
```

### 所要時間

- Test Clock作成: 1分
- Customer作成: 2分
- Subscription作成: 2分
- アプリDB連携: 1分
- **合計: 約5分**

---

## 🔗 関連ドキュメント

- [Stripe Test Clocks Documentation](https://docs.stripe.com/billing/testing/test-clocks)
- `k_back/scripts/README_STRIPE_TEST_CLOCK_MANAGER.md`
- `webhook_test_with_test_clocks.md`

---

**最終更新**: 2025-12-25
