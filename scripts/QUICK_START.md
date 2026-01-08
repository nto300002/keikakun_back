# Test Clocks クイックスタート

**最速でテストを開始する方法**

---

## 🚀 3ステップで完了

### ステップ1: セットアップ（30秒）

```bash
# 実行権限を付与（初回のみ）
chmod +x k_back/scripts/*.sh

# 自動セットアップ実行
./k_back/scripts/test_clock_quick_cycle.sh
```

**出力例**:
```
✅ Test Clock作成完了: clock_xxxxx
✅ Customer作成完了: cus_xxxxx
✅ Subscription作成完了: sub_xxxxx
✅ Billing作成完了: billing_xxxxx

次のステップ:
# 時間を進める（7日）
docker exec keikakun_app-backend-1 python3 scripts/stripe_test_clock_manager.py advance --clock-id clock_xxxxx --days 7
```

### ステップ2: テスト実行（10秒）

```bash
# 出力されたコマンドをコピペ、または
./k_back/scripts/test_clock_advance_last.sh 7
```

### ステップ3: 結果確認（10秒）

```bash
# Webhookログ確認
docker logs keikakun_app-backend-1 --tail 100 | grep -i webhook

# Billing状態確認（early_payment → active）
docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py list | tail -20
```

---

## 🧹 クリーンアップ

```bash
# すべてのTest Clocksとテストデータを削除
./k_back/scripts/cleanup_all_test_clocks.sh
```

---

## 📋 利用可能なスクリプト

| スクリプト | 用途 | 所要時間 |
|----------|------|---------|
| `test_clock_quick_cycle.sh` | 完全自動セットアップ | 30秒 |
| `test_clock_one_liner.sh` | Stripe側だけ作成（軽量） | 10秒 |
| `test_clock_advance_last.sh` | 最後のTest Clockを進める | 5秒 |
| `cleanup_all_test_clocks.sh` | すべて削除 | 10秒 |

---

## 🎯 ワークフロー例

### 繰り返しテスト

```bash
# 1回目
./k_back/scripts/test_clock_quick_cycle.sh
./k_back/scripts/test_clock_advance_last.sh 7
# 結果確認...

# クリーンアップ
./k_back/scripts/cleanup_all_test_clocks.sh

# 2回目
./k_back/scripts/test_clock_quick_cycle.sh
./k_back/scripts/test_clock_advance_last.sh 7
# 結果確認...

# 繰り返し...
```

### 並列テスト

```bash
# 3つのTest Clockを同時作成
for i in {1..3}; do
  ./k_back/scripts/test_clock_quick_cycle.sh &
done
wait
```

---

## 💡 Tips

### エイリアス設定

```bash
# ~/.bashrc or ~/.zshrc
alias tcc='./k_back/scripts/test_clock_quick_cycle.sh'
alias tca='./k_back/scripts/test_clock_advance_last.sh'
alias tcd='./k_back/scripts/cleanup_all_test_clocks.sh'

# 使用例
tcc        # セットアップ
tca 7      # 7日進める
tcd        # クリーンアップ
```

### 環境変数

```bash
# Price IDを指定
export STRIPE_PRICE_ID="price_xxxxx"
./k_back/scripts/test_clock_quick_cycle.sh
```

---

## ✅ 完全な例

```bash
# セットアップ
./k_back/scripts/test_clock_quick_cycle.sh

# 時間を進める
./k_back/scripts/test_clock_advance_last.sh 7

# Webhook確認
docker logs keikakun_app-backend-1 --tail 100 | grep "invoice.payment_succeeded"

# Billing確認（activeになっているか）
docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py list | tail -10

# クリーンアップ
./k_back/scripts/cleanup_all_test_clocks.sh

# 完了！
```

**所要時間**: 約1分

---

## 🔗 詳細ドキュメント

- `README_TEST_CLOCKS_QUICK_CYCLE.md`: 完全ガイド
- `README_STRIPE_TEST_CLOCK_MANAGER.md`: Test Clocks詳細
- `MANUAL_STRIPE_TEST_CLOCK_CUSTOMER.md`: 手動手順

---

**最終更新**: 2025-12-25
