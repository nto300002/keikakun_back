# Stripe Test Clock Manager - アプリからの時間操作ガイド

アプリからStripe Test Clocksを操作して、Webhook連携をテストするためのツール。

---

## 🎯 機能

このスクリプトを使って、**アプリからStripeの時間を操作**できます:

✅ **Test Clock作成**: 新しいTest Clockを作成
✅ **時間を進める**: Test Clockの時間を任意の期間進める
✅ **顧客確認**: Test Clockに紐づいた顧客とSubscriptionを一覧表示
✅ **削除**: 不要なTest Clockを削除

---

## 📋 基本的な使い方

### 1. Test Clock一覧表示

```bash
docker exec keikakun_app-backend-1 python3 scripts/stripe_test_clock_manager.py list
```

**出力例**:
```
================================================================================
Stripe Test Clocks一覧
================================================================================

📋 最新20件を表示

1. Test Clock ID: clock_1ShK2mBxyBErCNcAIzGFQtil
   Name: cancel_test_1766451944
   Frozen Time: 2026-06-21 01:16:27 UTC
   Status: ready

2. Test Clock ID: clock_1ShK2IBxyBErCNcAboRUHTRP
   Name: None
   Frozen Time: 2025-12-23 01:05:14 UTC
   Status: ready
```

---

### 2. Test Clock作成

```bash
docker exec keikakun_app-backend-1 python3 scripts/stripe_test_clock_manager.py create --name "Trial Test 2025-12-24"
```

**出力例**:
```
================================================================================
Test Clock作成
================================================================================

📋 作成情報:
   Name: Trial Test 2025-12-24
   Frozen Time: 2025-12-24 02:12:38 UTC
   Unix Timestamp: 1766542358

================================================================================
✅ Test Clock作成完了
================================================================================

📊 作成されたTest Clock:
   Test Clock ID: clock_1ShhZ5BxyBErCNcAc3vT1Ir1
   Name: Trial Test 2025-12-24
   Frozen Time: 2025-12-24 02:12:38 UTC
   Status: ready
```

**重要**: 作成したTest ClockをStripe CustomerやSubscriptionに紐付ける必要があります。

---

### 3. 時間を進める

```bash
# 90日進める
docker exec keikakun_app-backend-1 python3 scripts/stripe_test_clock_manager.py advance --clock-id <test_clock_id> --days 90

# 1時間進める
docker exec keikakun_app-backend-1 python3 scripts/stripe_test_clock_manager.py advance --clock-id <test_clock_id> --hours 1

# 30分進める
docker exec keikakun_app-backend-1 python3 scripts/stripe_test_clock_manager.py advance --clock-id <test_clock_id> --minutes 30

# 組み合わせ: 90日1時間30分進める
docker exec keikakun_app-backend-1 python3 scripts/stripe_test_clock_manager.py advance --clock-id <test_clock_id> --days 90 --hours 1 --minutes 30
```

**出力例**:
```
================================================================================
Test Clock時間を進める
================================================================================

📋 Test Clock情報:
   Test Clock ID: clock_1ShhZ5BxyBErCNcAc3vT1Ir1
   Name: Trial Test 2025-12-24
   Current Time: 2025-12-24 02:12:38 UTC
   New Time: 2026-03-24 02:12:38 UTC
   Time Delta: 90日 0時間 0分

⏰ 時間を進めています...

================================================================================
✅ 時間を進めました
================================================================================

📊 更新後の状態:
   Frozen Time: 2026-03-24 02:12:38 UTC
   Status: advancing
```

**重要**: 時間を進めると、StripeからWebhookが発火します。

---

### 4. Test Clockに紐づいた顧客を確認

```bash
docker exec keikakun_app-backend-1 python3 scripts/stripe_test_clock_manager.py customers --clock-id <test_clock_id>
```

**出力例**:
```
================================================================================
Test Clockに紐づいた顧客一覧
================================================================================

📋 Test Clock情報:
   Test Clock ID: clock_1ShhZ5BxyBErCNcAc3vT1Ir1
   Name: Trial Test 2025-12-24
   Frozen Time: 2026-03-24 02:12:38 UTC

👥 顧客一覧 (2件):

1. Customer ID: cus_xxxxx
   Email: test@example.com
   Name: テスト事業所
   Subscriptions:
      - sub_yyyyy
        Status: active
        Trial End: 2026-03-24 00:00:00 UTC

2. Customer ID: cus_zzzzz
   Email: test2@example.com
   Name: テスト事業所2
   Subscriptions:
      - sub_wwwww
        Status: trialing
        Trial End: 2026-06-22 00:00:00 UTC
```

---

### 5. Test Clock削除

```bash
docker exec keikakun_app-backend-1 python3 scripts/stripe_test_clock_manager.py delete --clock-id <test_clock_id>
```

**出力例**:
```
================================================================================
Test Clock削除
================================================================================

📋 削除対象:
   Test Clock ID: clock_1ShhZ5BxyBErCNcAc3vT1Ir1
   Name: Trial Test 2025-12-24
   Status: ready

================================================================================
✅ Test Clock削除完了
================================================================================
```

**注意**: Test Clockを削除すると、紐づいたCustomerやSubscriptionも削除される可能性があります。

---

## 🧪 E2Eテストフロー例

### シナリオ: Trial期間中に課金設定 → Trial終了 → active遷移

```bash
# 1. Test Clock作成
docker exec keikakun_app-backend-1 python3 scripts/stripe_test_clock_manager.py create --name "Trial Test $(date +%Y%m%d)"

# 出力からTest Clock IDをコピー: clock_xxxxx

# 2. Stripe DashboardまたはアプリでCustomerとSubscriptionを作成
# - Test Clock: clock_xxxxx を選択
# - Trial期間: 90日

# 3. アプリでBillingステータスを確認
docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py list
# → billing_status: early_payment を確認

# 4. Test Clockで90日進める
docker exec keikakun_app-backend-1 python3 scripts/stripe_test_clock_manager.py advance --clock-id clock_xxxxx --days 90

# 5. Webhookが発火したか確認
docker logs keikakun_app-backend-1 --tail 50 | grep Webhook
# 期待されるWebhook:
# - invoice.payment_succeeded

# 6. アプリでBillingステータスを確認
docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py list
# → billing_status: active に遷移していることを確認 ✅

# 7. クリーンアップ
docker exec keikakun_app-backend-1 python3 scripts/stripe_test_clock_manager.py delete --clock-id clock_xxxxx
```

---

## 🔄 Test Clocks vs batch_trigger_setup.py

| 観点 | Test Clocks Manager | batch_trigger_setup.py |
|------|---------------------|------------------------|
| **操作対象** | Stripe側の時間 | アプリDBの日付 |
| **Webhook発火** | ✅ 実際に発火する | ❌ 発火しない |
| **テスト対象** | Webhook連携 | バッチ処理 |
| **本番環境に近い** | ✅ 非常に近い | ⚠️ ロジックのみ |
| **free → past_due** | ❌ Webhookなし | ✅ テスト可能 |
| **early_payment → active** | ✅ Webhookで遷移 | ✅ バッチで遷移 |
| **canceling → canceled** | ✅ Webhookで遷移 | ✅ バッチで遷移 |
| **使い分け** | Webhook正常系テスト | Webhook失敗時のフォールバックテスト |

---

## 💡 Tips

### Stripe Dashboardでの操作と併用

Test Clockは以下の操作と組み合わせると効果的です:

1. **Stripe Dashboardで顧客を作成**:
   - Customers → Create customer
   - Test clock: 作成したTest Clockを選択

2. **Stripe Dashboardでサブスクリプション作成**:
   - Subscriptions → Create subscription
   - Trial期間を設定（例: 90日）

3. **アプリから時間を進める**:
   - このスクリプトで時間を進める
   - Webhookが発火 → アプリの状態が更新される

### Webhook発火の確認方法

```bash
# Stripe Webhook Logs (Stripe Dashboard)
# → Developers → Webhooks → Logs

# アプリログ
docker logs keikakun_app-backend-1 --tail 100 | grep Webhook

# 期待されるログ:
# [Webhook:evt_xxxxx] Subscription created for customer cus_xxxxx, status=early_payment
# [Webhook:evt_yyyyy] Payment succeeded for customer cus_xxxxx, billing_status=active
```

### Test Clockのステータス

- **ready**: 時間を進める準備ができている
- **advancing**: 時間を進めている最中
- **internal_failure**: エラーが発生（Stripeに問い合わせ）

---

## ⚠️ 注意事項

1. **Test Clocksはテストモードのみ**:
   - 本番環境では使用できません

2. **時間を戻すことはできない**:
   - Test Clocksで一度進めた時間は戻せません
   - 新しいTest Clockを作成する必要があります

3. **顧客とSubscriptionの紐付けが必要**:
   - Test Clockを作成しただけでは何も起きません
   - CustomerやSubscriptionを作成時にTest Clockを選択する必要があります

4. **Webhook Endpointの設定を確認**:
   - Stripe Dashboard → Developers → Webhooks
   - エンドポイントが正しく設定されているか確認

---

## 🔗 関連ドキュメント

- `README_TESTING_STRATEGY.md`: 包括的なテスト戦略（Test Clocks vs batch_trigger_setup.py）
- `README_STRIPE_TEST_CLOCKS.md`: Stripe Test Clocksの詳細ガイド（Stripe Dashboard操作）
- `README_BATCH_TRIGGER.md`: batch_trigger_setup.pyの使い方（バッチ処理テスト）

---

## 🎯 まとめ

### このスクリプトで可能なこと

✅ アプリからStripeの時間を操作
✅ Webhookを実際に発火させる
✅ 本番環境に近い状態でテスト
✅ Test Clocksの管理を自動化

### 推奨されるテスト戦略

**Webhook連携のテスト**:
→ **Test Clocks Manager**を使用

**バッチ処理のテスト**:
→ **batch_trigger_setup.py**を使用

**包括的なテスト**:
→ **両方**を使用

---

**最終更新**: 2025-12-24
