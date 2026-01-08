# バッチ処理テスト戦略まとめ

バッチ処理とWebhook連携をテストするための包括的なガイド。

---

## 🎯 2つのテストツール

### 1. Stripe Test Clocks（Stripe公式機能）

**用途**: Webhook連携のテスト

**仕組み**:
- Stripe側の時間を進める
- 実際にWebhookが発火する
- 本番環境に近い状態でテスト

**テストできること**:
- ✅ Webhookの発火タイミング
- ✅ Webhookペイロードの内容
- ✅ `early_payment → active`（Webhook経由）
- ✅ `canceling → canceled`（Webhook経由）

**テストできないこと**:
- ❌ アプリのバッチ処理（`datetime.now()`は変わらない）
- ❌ `free → past_due`（Webhookが存在しない）

### 2. batch_trigger_setup.py（今回作成したスクリプト）

**用途**: バッチ処理のテスト

**仕組み**:
- アプリ側のDBを直接操作
- `trial_end_date`や`scheduled_cancel_at`を変更
- バッチ処理を手動実行

**テストできること**:
- ✅ バッチ処理のロジック
- ✅ `free → past_due`（バッチ処理）
- ✅ `early_payment → active`（バッチ処理）
- ✅ `canceling → canceled`（バッチ処理）
- ✅ Webhookが失敗した場合のフォールバック

**テストできないこと**:
- ❌ Webhookの発火
- ❌ Stripe側の動作

---

## 📊 詳細比較表

| 観点 | Test Clocks | batch_trigger_setup.py |
|------|-------------|------------------------|
| **セットアップ** | やや複雑（Stripe Dashboard必要） | 簡単（コマンド1行） |
| **実行環境** | Stripeテストモード | 開発環境DB |
| **時間の進め方** | Stripe側の時間を進める | DBの日付を変更 |
| **Webhook** | ✅ 実際に発火 | ❌ 発火しない |
| **本番環境との近さ** | ✅ 非常に近い | ⚠️ ロジックのみ |
| **free → past_due** | ❌ テスト不可 | ✅ テスト可能 |
| **early_payment → active** | ✅ Webhookで遷移 | ✅ バッチで遷移 |
| **canceling → canceled** | ✅ Webhookで遷移 | ✅ バッチで遷移 |
| **バッチ処理のテスト** | ❌ 不可 | ✅ 可能 |
| **スケジューラーのテスト** | ❌ 不可 | ✅ 可能 |
| **リセット** | ⚠️ 不可（新規作成必要） | ✅ 簡単 |

---

## 🔄 テスト対象とツールの対応

### Webhook連携のテスト → **Test Clocks**

#### 1. Trial期間中に課金設定（正常系）

```
初期状態: free
   ↓ Stripe Checkoutで課金設定
customer.subscription.created (Webhook)
   ↓
early_payment ✅
   ↓ Test Clockで90日進める
invoice.payment_succeeded (Webhook)
   ↓
active ✅
```

**Test Clocks使用**:
```bash
# Stripe Dashboardで:
1. Test Clock作成
2. 顧客作成（Test Clock紐付け）
3. Subscription作成（trial_end: 90日後）
4. アプリでbilling_status = early_paymentを確認
5. Test Clockで90日進める
6. アプリでbilling_status = activeを確認
```

#### 2. キャンセルのテスト

```
初期状態: active
   ↓ Stripe Dashboardでキャンセル設定
customer.subscription.updated (Webhook)
   ↓
canceling ✅
   ↓ Test Clockで期限まで進める
customer.subscription.deleted (Webhook)
   ↓
canceled ✅
```

**Test Clocks使用**:
```bash
# Stripe Dashboardで:
1. Subscriptionをキャンセル（cancel_at_period_end: true）
2. アプリでbilling_status = cancelingを確認
3. Test Clockで期限まで進める
4. アプリでbilling_status = canceledを確認
```

---

### バッチ処理のテスト → **batch_trigger_setup.py**

#### 1. Trial期限切れ（未課金）

```
初期状態: free
   ↓ Trial期限到達
バッチ処理: check_trial_expiration()
   ↓
past_due ✅
```

**batch_trigger_setup.py使用**:
```bash
# freeステータスのBillingを取得
docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py list

# trial_end_dateを1分後に設定
docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py expire --billing-id <id> --minutes 1

# 1分待機
sleep 60

# バッチ処理実行
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

# 結果確認（free → past_due）
docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py list
```

#### 2. Webhook失敗時のフォールバック（early_payment → active）

```
初期状態: early_payment
   ↓ Webhookが失敗（または遅延）
   ↓ Trial期限到達
バッチ処理: check_trial_expiration()
   ↓
active ✅
```

**batch_trigger_setup.py使用**:
```bash
# early_paymentステータスのBillingを取得
docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py list

# trial_end_dateを過去に設定
docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py expire --billing-id <id> --minutes 1

# 待機＆バッチ処理実行

# 結果確認（early_payment → active）
docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py list
```

#### 3. スケジュールキャンセルのフォールバック（canceling → canceled）

```
初期状態: canceling
   ↓ Webhookが失敗（または遅延）
   ↓ scheduled_cancel_at到達
バッチ処理: check_scheduled_cancellation()
   ↓
canceled ✅
```

**batch_trigger_setup.py使用**:
```bash
# cancelingステータスのBillingを取得
docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py list

# scheduled_cancel_atを過去に設定
docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py expire --billing-id <id> --minutes 1

# 待機＆バッチ処理実行
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

# 結果確認（canceling → canceled）
docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py list
```

---

## 🎮 包括的なテストフロー

### フェーズ1: Webhook連携のテスト（Test Clocks）

**目的**: Stripeとの連携が正しく動作することを確認

```
1. Test Clock作成
2. Trial期間中に課金設定
   → early_payment に遷移することを確認 ✅
3. Test Clockで時間を進める
   → invoice.payment_succeeded Webhook発火 ✅
   → active に遷移することを確認 ✅
4. キャンセル設定
   → canceling に遷移することを確認 ✅
5. Test Clockで期限まで進める
   → customer.subscription.deleted Webhook発火 ✅
   → canceled に遷移することを確認 ✅
```

### フェーズ2: バッチ処理のテスト（batch_trigger_setup.py）

**目的**: Webhook失敗時のフォールバックが動作することを確認

```
1. free状態のBillingでTrial期限超過
   → past_due に遷移することを確認 ✅
2. early_payment状態のBillingでTrial期限超過
   → active に遷移することを確認 ✅
3. canceling状態のBillingで期限超過
   → canceled に遷移することを確認 ✅
```

### フェーズ3: スケジューラーのテスト

**目的**: 定期実行が正しく動作することを確認

```
1. trial_end_dateを翌日0:00に設定
2. 翌日0:00のスケジューラー実行を待つ
   → 自動的にステータスが遷移することを確認 ✅
```

---

## 📝 テストケース一覧

| # | シナリオ | ツール | 期待結果 |
|---|---------|--------|---------|
| 1 | Trial中に課金設定 | Test Clocks | free → early_payment |
| 2 | Trial終了（課金済み） | Test Clocks | early_payment → active |
| 3 | Trial終了（未課金） | batch_trigger | free → past_due |
| 4 | Webhook失敗（課金済み） | batch_trigger | early_payment → active |
| 5 | キャンセル設定 | Test Clocks | active → canceling |
| 6 | キャンセル期限到達 | Test Clocks | canceling → canceled |
| 7 | Webhook失敗（キャンセル） | batch_trigger | canceling → canceled |
| 8 | スケジューラー実行 | batch_trigger | 各種遷移 |

---

## 🎯 推奨されるテスト戦略

### 開発中

**batch_trigger_setup.py**を使用:
- 理由: セットアップが簡単、リセットが容易
- 目的: ロジックの動作確認、バグ修正

### ステージング環境

**Test Clocks**を使用:
- 理由: 本番環境に近い状態
- 目的: Webhook連携の確認、統合テスト

### 本番前の最終確認

**両方**を使用:
- Test Clocks: 正常系の確認
- batch_trigger: 異常系（Webhook失敗）の確認

---

## 🔍 トラブルシューティング

### Test Clocksでテストしたが、アプリの状態が変わらない

**原因**: Webhookが発火していない、またはWebhookハンドラでエラー

**確認方法**:
```bash
# Stripe Webhookログを確認
# Stripe Dashboard → Developers → Webhooks → Logs

# アプリログを確認
docker logs keikakun_app-backend-1 --tail 100 | grep Webhook
```

### batch_triggerでテストしたが、状態が変わらない

**原因**: バッチ処理を実行していない、または期限が未来

**確認方法**:
```bash
# 発動条件を確認
docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py check

# 期限が過去になっているか確認
docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py list
```

---

## 📚 関連ドキュメント

- `README_STRIPE_TEST_CLOCKS.md` - Test Clocksの詳細ガイド
- `README_BATCH_TRIGGER.md` - batch_trigger_setup.pyの使い方
- `README_BATCH_E2E_TEST.md` - E2Eテストスクリプト（未使用推奨）

---

## ✅ まとめ

| テスト内容 | 使用ツール | 理由 |
|-----------|----------|------|
| Webhook連携 | **Test Clocks** | 本番環境に近い |
| バッチ処理 | **batch_trigger_setup.py** | 直接ロジックをテスト |
| フォールバック | **batch_trigger_setup.py** | Webhook失敗を再現 |
| 統合テスト | **両方** | 包括的な確認 |

**推奨アプローチ**:
1. 開発中: batch_trigger_setup.py
2. ステージング: Test Clocks
3. 本番前: 両方

---

**最終更新**: 2025-12-24
