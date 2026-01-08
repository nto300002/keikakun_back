# Stripe Test Clocksを使ったテストガイド

Stripe Test Clocksを使って、トライアル期間終了やサブスクリプションのライフサイクルをテストする方法。

---

## 🕐 Stripe Test Clocksとは

Stripe Test Clocksは、テスト環境で時間を進めることができる機能です。

**公式ドキュメント**:
- https://stripe.com/docs/billing/testing/test-clocks

**できること**:
- ✅ トライアル期間終了のシミュレーション
- ✅ 定期課金のシミュレーション
- ✅ スケジュールされたキャンセルのシミュレーション
- ✅ Webhookの発火確認

**できないこと**:
- ❌ アプリ側のバッチ処理のテスト（`datetime.now()`は変わらない）

---

## 🚀 基本的な使い方

### ステップ1: Test Clockの作成

Stripe Dashboardで:
1. テストモードに切り替え
2. 「Billing」→「Test Clocks」に移動
3. 「Create test clock」をクリック
4. 名前を入力（例: "Trial Test 2025-12-24"）
5. 開始時刻を設定（デフォルトは現在時刻）

### ステップ2: Test Clockに紐づいた顧客とサブスクリプションを作成

#### オプションA: Stripe Dashboardで作成

1. 「Customers」→「Create customer」
2. **重要**: 「Test clock」フィールドで先ほど作成したTest Clockを選択
3. 顧客を作成
4. 「Subscriptions」→「Create subscription」
5. トライアル期間を設定（例: 90日）

#### オプションB: Stripe APIで作成（アプリから）

```python
import stripe

# Test Clockを作成
test_clock = stripe.test_helpers.TestClock.create(
    frozen_time=1640995200,  # Unix timestamp
    name="Trial Test"
)

# Test Clockに紐づいた顧客を作成
customer = stripe.Customer.create(
    test_clock=test_clock.id,
    email="test@example.com"
)

# サブスクリプションを作成（90日のトライアル）
subscription = stripe.Subscription.create(
    customer=customer.id,
    items=[{"price": "price_xxxxx"}],
    trial_end=int((datetime.now() + timedelta(days=90)).timestamp())
)
```

### ステップ3: 時間を進める

Stripe Dashboardで:
1. 「Test Clocks」に移動
2. 作成したTest Clockを選択
3. 「Advance time」をクリック
4. 進めたい時間を入力（例: 90日）
5. 「Advance clock」をクリック

**または、APIで**:
```python
stripe.test_helpers.TestClock.advance(
    test_clock.id,
    frozen_time=int((datetime.now() + timedelta(days=90)).timestamp())
)
```

### ステップ4: Webhookの確認

時間を進めると、Stripeから以下のWebhookが発火されます:

1. **トライアル終了時**:
   - `invoice.created`
   - `invoice.finalized`
   - `invoice.payment_succeeded`（課金成功時）
   - `customer.subscription.updated`（status: trialing → active）

2. **キャンセル時**:
   - `customer.subscription.updated`（cancel_at_period_end: true）
   - `customer.subscription.deleted`（キャンセル実行時）

**Webhookログの確認**:
- Stripe Dashboard → 「Developers」→「Webhooks」→「Logs」

**アプリのログ確認**:
```bash
docker logs keikakun_app-backend-1 --tail 50 | grep Webhook
```

---

## 🧪 テストシナリオ例

### シナリオ1: Trial期間中に課金設定（early_payment）

```
1. Test Clockを作成（現在時刻）
2. 顧客を作成（Test Clock紐付け）
3. アプリで顧客のBillingを確認
   → billing_status = free

4. Stripe CheckoutでSubscription作成（trial_end: 90日後）
   → Webhook: customer.subscription.created
   → アプリ: billing_status = early_payment ✅

5. Test Clockで90日進める
   → Webhook: invoice.payment_succeeded
   → アプリ: record_payment() → billing_status = active ✅
```

**検証ポイント**:
- ✅ Subscription作成時に`early_payment`になる
- ✅ Trial終了後に`active`になる
- ✅ Webhookが正しく発火する

### シナリオ2: キャンセルのテスト

```
1. Test Clockを作成
2. Subscriptionを作成（trial_end: 30日後）
3. 即座にキャンセル設定（cancel_at_period_end = true）
   → Webhook: customer.subscription.updated
   → アプリ: billing_status = canceling ✅

4. Test Clockで30日進める
   → Webhook: customer.subscription.deleted
   → アプリ: billing_status = canceled ✅
```

**検証ポイント**:
- ✅ キャンセル設定時に`canceling`になる
- ✅ 期限到達時に`canceled`になる
- ✅ `scheduled_cancel_at`が正しく設定される

---

## 🔧 アプリ側の実装確認ポイント

### 1. Webhookハンドラが正しく動作するか

```bash
# Webhookログを確認
docker logs keikakun_app-backend-1 --tail 100 | grep "Webhook:"

# 期待されるログ:
# [Webhook:evt_xxxxx] Subscription created for customer cus_xxxxx, status=early_payment
# [Webhook:evt_yyyyy] Payment succeeded for customer cus_xxxxx, billing_status=active
```

### 2. Billingステータスが正しく遷移するか

```bash
# Billingを確認
docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py list
```

### 3. Stripe Customerとの紐付けが正しいか

```sql
SELECT
    b.id,
    b.office_id,
    b.billing_status,
    b.stripe_customer_id,
    b.stripe_subscription_id,
    b.trial_end_date
FROM billings b
WHERE b.stripe_customer_id = 'cus_xxxxx';
```

---

## ⚠️ Test Clocksの制限事項

### 1. アプリのバッチ処理はテストできない

**理由**:
- Test Clocksは**Stripe側の時間**のみを進める
- アプリ側の`datetime.now()`は変わらない

**例**:
```python
# このバッチ処理はTest Clocksの影響を受けない
now = datetime.now(timezone.utc)  # ← 実際の現在時刻
is_expired = billing.trial_end_date < now  # ← Test Clocksでは変わらない
```

**対処法**:
- バッチ処理のテストには`scripts/batch_trigger_setup.py`を使用

### 2. 時間を戻すことはできない

Test Clocksで一度進めた時間は戻せません。

**対処法**:
- 新しいTest Clockを作成
- または、テストごとに異なるTest Clockを使用

### 3. 本番環境では使用できない

Test Clocksはテストモードのみで利用可能です。

---

## 📊 Test Clocks vs バッチ処理テスト

| テスト内容 | Test Clocks | batch_trigger_setup.py |
|----------|-------------|------------------------|
| Webhook発火 | ✅ 実際に発火 | ❌ 手動トリガー必要 |
| early_payment → active | ✅ Webhookで遷移 | ✅ バッチで遷移 |
| free → past_due | ❌ Webhookなし | ✅ バッチで遷移 |
| canceling → canceled | ✅ Webhookで遷移 | ✅ バッチで遷移 |
| 本番環境に近い | ✅ 非常に近い | ⚠️ ロジックのみ |
| セットアップ | ⚠️ やや複雑 | ✅ 簡単 |

---

## 🎯 推奨テスト戦略

### フェーズ1: Webhook連携のテスト（Test Clocks）

1. Test Clockでサブスクリプション作成
2. 時間を進めてWebhook発火を確認
3. アプリのステータス遷移を確認

### フェーズ2: バッチ処理のテスト（batch_trigger_setup.py）

1. trial_end_dateを過去に設定
2. バッチ処理を手動実行
3. ステータス遷移を確認

### フェーズ3: 統合テスト

1. Test Clocksで正常系を確認
2. バッチ処理でフォールバックを確認
3. 両方のパスが正しく動作することを確認

---

## 💡 Tips

### Test Clocksの一覧を確認

```bash
stripe test-clocks list
```

### Test Clocksを削除

```bash
stripe test-clocks delete <test_clock_id>
```

### Test Clockに紐づいた顧客を確認

```bash
stripe customers list --test-clock=<test_clock_id>
```

---

## 🔗 参考リンク

- [Stripe Test Clocks Documentation](https://stripe.com/docs/billing/testing/test-clocks)
- [Testing Subscriptions](https://stripe.com/docs/billing/testing)
- [Webhook Testing](https://stripe.com/docs/webhooks/test)

---

**最終更新**: 2025-12-24
