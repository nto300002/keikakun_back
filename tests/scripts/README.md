# Billing状態管理スクリプト

## 概要

課金フローのE2Eテストやデバッグのために、Billing状態を自由に操作できるスクリプト群です。

## スクリプト一覧

### 1. `reset_billing_state.py` - 状態リセット

Billingを初期状態（`billing_status=free`、無料期間180日）にリセットします。

#### 使い方

```bash
# 現在の状態を確認
docker exec keikakun_app-backend-1 python tests/scripts/reset_billing_state.py --show

# 最新のBillingをリセット（dry-run）
docker exec keikakun_app-backend-1 python tests/scripts/reset_billing_state.py --latest --dry-run

# 最新のBillingをリセット（実行）
docker exec keikakun_app-backend-1 python tests/scripts/reset_billing_state.py --latest

# すべてのBillingをリセット
docker exec keikakun_app-backend-1 python tests/scripts/reset_billing_state.py --all

# 特定のOffice IDをリセット
docker exec keikakun_app-backend-1 python tests/scripts/reset_billing_state.py --office-id <UUID>
```

#### リセット後の状態

- `billing_status`: `free`
- `stripe_customer_id`: `None`
- `stripe_subscription_id`: `None`
- `trial_start_date`: 現在時刻
- `trial_end_date`: 180日後
- `subscription_start_date`: `None`
- `next_billing_date`: `None`
- `last_payment_date`: `None`

---

### 2. `setup_edge_case_states.py` - エッジケース状態作成

7つのエッジケースに対応する状態を作成します。

#### エッジケース一覧

| # | ケース名 | billing_status | 無料期間 | 説明 |
|---|---------|---------------|---------|------|
| 0 | **初期状態（事務所登録直後）** | `free` | +180日 | **事務所登録時のデフォルト状態** |
| 1 | トライアル期間が終わる前に課金 | `early_payment` | +30日 | 無料期間中に課金登録 |
| 2 | トライアル期間を過ぎても課金されない | `past_due` | -5日 | 無料期間終了後も課金なし |
| 3 | トライアル期間を過ぎてから課金 | `free` | -10日 | 無料期間終了後、未課金 |
| 4 | トライアル期間の終了日に課金 | `free` | 今日 | ギリギリのタイミング |
| 5 | 課金登録後、トライアル期間終了前にキャンセル | `free` | +20日 | キャンセル後にfreeに戻る |
| 6 | トライアル期間終了後、最初の課金が失敗 | `past_due` | -3日 | 初回請求失敗 |
| 7 | EARLY_PAYMENT状態でトライアル期間を過ぎる | `early_payment` | 今日 | まもなくactive遷移 |

#### 使い方

```bash
# エッジケース一覧を表示
docker exec keikakun_app-backend-1 python tests/scripts/setup_edge_case_states.py --list

# 現在の状態を確認
docker exec keikakun_app-backend-1 python tests/scripts/setup_edge_case_states.py --show

# ケース0を設定（初期状態にリセット）
docker exec keikakun_app-backend-1 python tests/scripts/setup_edge_case_states.py --case 0

# ケース1を設定（dry-run）
docker exec keikakun_app-backend-1 python tests/scripts/setup_edge_case_states.py --case 1 --dry-run

# ケース2を設定（最新のBillingに適用）
docker exec keikakun_app-backend-1 python tests/scripts/setup_edge_case_states.py --case 2

# ケース3を特定のOffice IDに設定
docker exec keikakun_app-backend-1 python tests/scripts/setup_edge_case_states.py --case 3 --office-id <UUID>

# すべてのケースを設定（複数Officeに分散）
docker exec keikakun_app-backend-1 python tests/scripts/setup_edge_case_states.py --all
```

---

## 典型的なワークフロー

### ケース0: 初期状態（事務所登録直後）にリセット

```bash
# 1. 現在の状態を確認
docker exec keikakun_app-backend-1 python tests/scripts/setup_edge_case_states.py --show

# 2. ケース0を設定（初期状態にリセット）
docker exec keikakun_app-backend-1 python tests/scripts/setup_edge_case_states.py --case 0

# 3. 状態を確認
docker exec keikakun_app-backend-1 python tests/scripts/setup_edge_case_states.py --show

# 期待される状態:
# - billing_status: free
# - trial_end_date: 180日後
# - Customer ID: なし
# - Subscription ID: なし

# 4. フロントエンドでUIを確認
# http://localhost:3000/admin?tab=plan
# → 無料トライアル期間バナーが表示される
# → 「課金登録」ボタンが表示される
```

---

### ケース1: トライアル期間中に課金するケース（early_payment）をテスト

```bash
# 1. 現在の状態を確認
docker exec keikakun_app-backend-1 python tests/scripts/reset_billing_state.py --show

# 2. 状態をリセット（または、ケース0を設定）
docker exec keikakun_app-backend-1 python tests/scripts/setup_edge_case_states.py --case 0

# 3. エッジケース1を設定（dry-run で確認）
docker exec keikakun_app-backend-1 python tests/scripts/setup_edge_case_states.py --case 1 --dry-run

# 4. エッジケース1を設定
docker exec keikakun_app-backend-1 python tests/scripts/setup_edge_case_states.py --case 1

# 5. 状態を確認
docker exec keikakun_app-backend-1 python tests/scripts/setup_edge_case_states.py --show

# 6. フロントエンドでUIを確認
# http://localhost:3000/admin?tab=plan
```

---

### ケース2: トライアル期間終了後も課金されないケース（past_due）をテスト

```bash
# 1. 状態をリセット
docker exec keikakun_app-backend-1 python tests/scripts/reset_billing_state.py --latest

# 2. エッジケース2を設定
docker exec keikakun_app-backend-1 python tests/scripts/setup_edge_case_states.py --case 2

# 3. 状態を確認
docker exec keikakun_app-backend-1 python tests/scripts/setup_edge_case_states.py --show

# 期待される状態:
# - billing_status: past_due
# - trial_end_date: 5日前に終了
# - Customer ID: なし
# - Subscription ID: なし

# 4. フロントエンドでPastDueModalが表示されることを確認
# http://localhost:3000/admin?tab=plan
```

---

### ケース7: EARLY_PAYMENT → ACTIVE自動遷移をテスト

```bash
# 1. エッジケース7を設定
docker exec keikakun_app-backend-1 python tests/scripts/setup_edge_case_states.py --case 7

# 2. Stripe CLIでinvoice.payment_succeededイベントを送信
stripe trigger invoice.payment_succeeded

# 3. billing_statusがactiveに遷移したことを確認
docker exec keikakun_app-backend-1 python tests/scripts/setup_edge_case_states.py --show
```

---

## 注意事項

### ⚠️ テスト環境でのみ実行

これらのスクリプトは**テスト環境（dev_test）でのみ実行**してください。本番環境で実行すると、実際の課金データが破壊されます。

### 環境変数の確認

スクリプト実行前に、以下を確認してください:

```bash
# TEST_DATABASE_URLが設定されているか
docker exec keikakun_app-backend-1 python -c "
import os
print('TEST_DATABASE_URL:', os.getenv('TEST_DATABASE_URL'))
print('TESTING:', os.getenv('TESTING'))
"
```

### Dry-runモードの活用

初めてのケースを試す場合は、必ず`--dry-run`で動作を確認してから実行してください。

```bash
# Good: まずdry-runで確認
docker exec keikakun_app-backend-1 python tests/scripts/setup_edge_case_states.py --case 1 --dry-run

# その後、実行
docker exec keikakun_app-backend-1 python tests/scripts/setup_edge_case_states.py --case 1
```

---

## トラブルシューティング

### 問題: "Billingレコードが見つかりません"

**原因**: データベースにBillingレコードが存在しない

**解決策**:
```bash
# 新しいOfficeを作成してBillingを生成
# または、既存のテストデータをセットアップ
```

---

### 問題: エッジケース設定後もフロントエンドに反映されない

**原因**: キャッシュまたはセッション

**解決策**:
```bash
# 1. ブラウザのキャッシュをクリア
# 2. ログアウト → ログイン
# 3. ページをリロード（Cmd+Shift+R）
```

---

### 問題: Stripe Webhookが来ない

**原因**: Stripe CLIが起動していない

**解決策**:
```bash
# Stripe CLIを起動
stripe listen --forward-to localhost:8000/api/v1/billing/webhook

# Webhook Secretを.envに設定
# STRIPE_WEBHOOK_SECRET=whsec_xxxxx

# Dockerコンテナを再起動
docker-compose restart backend
```

---

## 関連ドキュメント

- [エッジケース実装率分析](../../../md_files_design_note/task/1_pay_to_play/edge_case_implementation_analysis.md)
- [E2E サブスクリプションフロー修正](../../../md_files_design_note/e2e_subscription_flow_fix.md)
- [Billing Service](../../app/services/billing_service.py)
- [Billing API](../../app/api/v1/endpoints/billing.py)

---

**作成日**: 2025-12-16
**作成者**: Claude Sonnet 4.5
