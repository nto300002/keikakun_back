# 本番環境 E2E テストガイド - Stripe課金機能

このガイドでは、本番環境でのStripe課金機能のE2Eテスト方法を説明します。

## ⚠️ 重要な注意事項

### 本番環境でのテストリスク

1. **実際の課金が発生する**: テスト用のクレジットカードは使用できません
2. **顧客データが作成される**: 実際の顧客レコードがStripeに保存されます
3. **Webhookイベントが発火する**: 本番データベースが更新されます
4. **税金計算が実行される**: 実際の税率が適用されます

### 推奨アプローチ

**本番環境で直接テストするのではなく、以下のいずれかを使用してください**:

1. ✅ **テストモード（推奨）**: Stripeのテストモードで完全なE2Eテスト
2. ✅ **ステージング環境**: 本番と同じ構成のステージング環境を用意
3. ⚠️ **本番環境での限定テスト**: やむを得ない場合のみ、慎重に実施

---

## 方法1: Stripeテストモードでの完全E2Eテスト（推奨）

### メリット
- 実際の課金が発生しない
- テスト用カード番号が使える
- 何度でもテスト可能
- 本番環境と同じフローをテストできる

### 手順

#### ステップ1: テストモード環境変数の準備

```bash
# バックエンド .env (テストモード)
STRIPE_SECRET_KEY=sk_test_YOUR_STRIPE_TEST_SECRET_KEY
STRIPE_WEBHOOK_SECRET=whsec_YOUR_WEBHOOK_SECRET  # テストモード用Webhook Secret
STRIPE_PRICE_ID=price_YOUR_PRICE_ID  # テストモード用Price ID
FRONTEND_URL=https://staging.yourdomain.com  # またはlocalhost

# フロントエンド .env.local (テストモード)
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=pk_test_YOUR_STRIPE_PUBLISHABLE_KEY
```

#### ステップ2: Stripeダッシュボードでテストモードに切り替え

1. Stripeダッシュボードにログイン
2. 右上のトグルを「テストモード」に切り替え
3. Webhookエンドポイントを登録（テストモード用）

#### ステップ3: テスト用カード番号を使用

Stripeが提供するテスト用カード番号:

| カード番号 | 用途 |
|---------|------|
| `4242 4242 4242 4242` | 成功する支払い |
| `4000 0025 0000 3155` | 3D Secure認証が必要 |
| `4000 0000 0000 9995` | 残高不足で失敗 |
| `4000 0000 0000 0002` | カード拒否（汎用エラー） |

- CVV: 任意の3桁（例: `123`）
- 有効期限: 未来の日付（例: `12/34`）
- 郵便番号: 任意（例: `12345`）

#### ステップ4: E2Eテストシナリオ

##### シナリオ1: 新規サブスクリプション登録

```
1. ユーザー登録
   ↓
2. 無料トライアル開始（180日）
   ↓
3. 管理画面 → プランタブ
   ↓
4. 「サブスクリプションに登録」ボタンをクリック
   ↓
5. Stripe Checkoutページにリダイレクト
   ↓
6. テストカード番号を入力: 4242 4242 4242 4242
   ↓
7. 支払い完了
   ↓
8. アプリにリダイレクト（success=true）
   ↓
9. 課金ステータスが「active」に変更されることを確認
```

**確認ポイント**:
- [ ] Stripeダッシュボードで顧客が作成されている
- [ ] Stripeダッシュボードでサブスクリプションが作成されている
- [ ] DBのbillingsテーブルで`billing_status = active`
- [ ] DBのbillingsテーブルで`stripe_customer_id`と`stripe_subscription_id`が保存されている
- [ ] トライアル終了日が正しく設定されている

##### シナリオ2: Webhook イベント受信

```
1. Stripe CLI でWebhookをフォワード:
   stripe listen --forward-to https://your-backend.com/api/v1/billing/webhook

2. テストイベントを送信:
   stripe trigger customer.subscription.created
   stripe trigger invoice.payment_succeeded
   stripe trigger invoice.payment_failed
   stripe trigger customer.subscription.deleted

3. バックエンドログで正しく処理されていることを確認

4. DBで課金ステータスが正しく更新されていることを確認
```

**確認ポイント**:
- [ ] `customer.subscription.created` → `billing_status = active`
- [ ] `invoice.payment_succeeded` → `last_payment_date`が更新される
- [ ] `invoice.payment_failed` → `billing_status = past_due`
- [ ] `customer.subscription.deleted` → `billing_status = canceled`

##### シナリオ3: 支払い方法変更

```
1. 管理画面 → プランタブ
   ↓
2. 「支払い方法の変更・解約」ボタンをクリック
   ↓
3. Stripe Customer Portalが新しいタブで開く
   ↓
4. 「支払い方法を更新」をクリック
   ↓
5. 新しいカード情報を入力（テストカード）
   ↓
6. 保存
   ↓
7. Stripeダッシュボードで支払い方法が更新されていることを確認
```

##### シナリオ4: サブスクリプションキャンセル

```
1. Stripe Customer Portalを開く
   ↓
2. 「サブスクリプションをキャンセル」をクリック
   ↓
3. キャンセル理由を選択
   ↓
4. 確認
   ↓
5. Webhookで`customer.subscription.deleted`が送信される
   ↓
6. 課金ステータスが「canceled」に変更されることを確認
```

---

## 方法2: ステージング環境でのテスト

### 推奨構成

```
本番環境          ステージング環境
-----------      ----------------
Production DB    Staging DB
↓                ↓
Production API   Staging API (テストモード)
↓                ↓
Production Web   Staging Web
```

### セットアップ

#### 1. ステージング環境のデプロイ

```bash
# Cloud Runにステージング環境をデプロイ
gcloud run deploy keikakun-backend-staging \
  --source . \
  --region asia-northeast1 \
  --set-env-vars STRIPE_SECRET_KEY=sk_test_...,STRIPE_WEBHOOK_SECRET=whsec_test_...
```

#### 2. Stripeダッシュボードでステージング用Webhookを登録

```
Webhook URL: https://keikakun-backend-staging-xxxxx.run.app/api/v1/billing/webhook
```

#### 3. ステージング環境でE2Eテストを実施

本番環境と同じフローで、テストカードを使用してテスト。

---

## 方法3: 本番環境での限定テスト（非推奨）

### ⚠️ 実施前の確認事項

- [ ] テストモードで十分にテストを実施した
- [ ] ステークホルダーの承認を得た
- [ ] テスト後のクリーンアップ手順を準備した
- [ ] 実際の課金が発生することを理解している

### 手順

#### ステップ1: テスト用アカウントを作成

本番環境で専用のテストアカウントを作成:

```
メールアドレス: test-billing@yourdomain.com
事業所名: テスト事業所（削除予定）
```

#### ステップ2: 少額のサブスクリプション登録

実際のクレジットカードを使用して、最小単位でテスト:

1. Checkout Sessionで実際のカードを入力
2. 即座にCustomer Portalでキャンセル
3. Stripeダッシュボードで返金処理

#### ステップ3: テストデータのクリーンアップ

```python
# Python Stripe SDK でクリーンアップ
import stripe
stripe.api_key = "sk_live_..."

# Subscription削除
stripe.Subscription.delete("sub_xxxxx")

# Customer削除
stripe.Customer.delete("cus_xxxxx")
```

```sql
-- DBからテストデータ削除
DELETE FROM billings WHERE office_id = 'テスト事業所のUUID';
DELETE FROM offices WHERE name = 'テスト事業所（削除予定）';
```

---

## E2Eテストチェックリスト

### 課金フロー

- [ ] 新規ユーザー登録時にBillingレコードが作成される
- [ ] トライアル期間が180日で設定される
- [ ] Checkout Sessionが正常に作成される
- [ ] Stripe Checkoutページにリダイレクトされる
- [ ] 支払い完了後、アプリにリダイレクトされる
- [ ] 課金ステータスが「active」に更新される

### Webhook処理

- [ ] `customer.subscription.created` イベントが処理される
- [ ] `invoice.payment_succeeded` イベントが処理される
- [ ] `invoice.payment_failed` イベントが処理される
- [ ] `customer.subscription.deleted` イベントが処理される
- [ ] Webhook署名検証が正しく動作する
- [ ] 冪等性が保証されている（同じイベントを複数回受信しても問題ない）

### UI/UX

- [ ] 無料トライアル残り日数バナーが表示される
- [ ] 管理画面「プラン」タブで課金ステータスが確認できる
- [ ] 支払い遅延時にモーダルが表示される
- [ ] 書き込み操作のボタンが適切に無効化される
- [ ] Customer Portalが正常に開く

### セキュリティ

- [ ] Webhook署名検証が実装されている
- [ ] 無効な署名のWebhookが拒否される
- [ ] オーナー以外はCheckout Session作成APIにアクセスできない
- [ ] 課金ステータスが`past_due`または`canceled`の場合、書き込み操作が制限される

---

## トラブルシューティング

### Webhookが受信されない

**確認ポイント**:
1. Stripeダッシュボードでエンドポイントが正しく登録されているか
2. エンドポイントURLがHTTPSか（HTTPは拒否される）
3. バックエンドがデプロイされているか
4. ファイアウォールでブロックされていないか

**デバッグ方法**:
```bash
# Stripe CLIでリアルタイムログを確認
stripe listen --forward-to https://your-backend.com/api/v1/billing/webhook

# Stripeダッシュボード → Webhook → イベントログを確認
```

### Checkout Sessionが作成されない

**確認ポイント**:
1. `STRIPE_SECRET_KEY`が正しく設定されているか
2. `STRIPE_PRICE_ID`が存在するか
3. バックエンドログにエラーが出ていないか

**デバッグ方法**:
```python
# Stripe SDK で Price ID を確認
import stripe
stripe.api_key = "sk_test_..."

price = stripe.Price.retrieve("price_xxxxx")
print(price)
```

### 課金ステータスが更新されない

**確認ポイント**:
1. Webhookが正常に受信されているか
2. DBトランザクションがコミットされているか
3. エラーログが出ていないか

**デバッグ方法**:
```sql
-- DBの課金ステータスを確認
SELECT id, office_id, billing_status, stripe_customer_id, stripe_subscription_id, updated_at
FROM billings
ORDER BY updated_at DESC
LIMIT 10;
```

---

## 推奨テストフロー（まとめ）

### フェーズ1: ローカル開発（Stripe CLI）

```bash
# Stripe CLIでWebhookをフォワード
stripe listen --forward-to localhost:8000/api/v1/billing/webhook

# テストイベントを送信
stripe trigger customer.subscription.created
```

### フェーズ2: テストモードでの完全E2E

1. ステージング環境またはローカルでテストモード環境変数を設定
2. テストカード番号を使用してCheckout完了
3. Webhookイベントが正しく処理されることを確認

### フェーズ3: ステージング環境での統合テスト

1. 本番環境と同じ構成のステージング環境を用意
2. テストモードで完全なフローをテスト
3. 自動テストスクリプトを実行

### フェーズ4: 本番環境リリース

1. テストモードで十分にテストした後、本番環境変数に切り替え
2. 小規模なベータテストを実施（社内ユーザーなど）
3. 段階的にユーザーに公開

---

## 参考資料

- [Stripe Testing](https://stripe.com/docs/testing)
- [Stripe Webhooks Best Practices](https://stripe.com/docs/webhooks/best-practices)
- [Stripe CLI](https://stripe.com/docs/stripe-cli)

---

**作成日**: 2025年12月12日
**最終更新**: 2025年12月12日
