# バッチ処理 E2Eテストガイド

バッチ処理の動作を手動で確認するためのスクリプトです。

---

## 📋 テストシナリオ

このスクリプトは以下の3つのバッチ処理をテストします:

1. **free → past_due**: 無料期間終了時に未課金のユーザー
2. **early_payment → active**: 無料期間終了時に課金済みのユーザー
3. **canceling → canceled**: キャンセル予定日到達時のユーザー

---

## 🚀 使い方

### ステップ1: テストデータ作成

```bash
# 1分後に期限切れとなるテストデータを作成
docker exec keikakun_app-backend-1 python3 scripts/test_batch_processing.py setup --minutes 1
```

**オプション**:
- `--minutes N`: N分後に期限切れにする（デフォルト: 1分）

**出力例**:
```
====================================================================
テストデータ作成開始
現在時刻: 2025-12-23 06:00:00 UTC
期限時刻: 2025-12-23 06:01:00 UTC (1分後)
====================================================================

1️⃣  free → past_due テストデータ作成中...
   ✅ Office: E2E_TEST_BATCH_20251223_060000_FREE_TO_PAST_DUE
      Billing ID: ...
      Status: free → past_due

2️⃣  early_payment → active テストデータ作成中...
   ✅ Office: E2E_TEST_BATCH_20251223_060000_EARLY_TO_ACTIVE
      Billing ID: ...
      Status: early_payment → active

3️⃣  canceling → canceled テストデータ作成中...
   ✅ Office: E2E_TEST_BATCH_20251223_060000_CANCELING_TO_CANCELED
      Billing ID: ...
      Status: canceling → canceled

====================================================================
✅ テストデータ作成完了
====================================================================

⏰ 1分後に以下のコマンドを実行してください:
   docker exec keikakun_app-backend-1 python3 scripts/test_batch_processing.py run
```

---

### ステップ2: 待機

**指定した時間（デフォルト1分）待ちます。**

⏰ タイマーを設定するか、時計を確認してください。

---

### ステップ3: バッチ処理実行

```bash
# バッチ処理を手動実行
docker exec keikakun_app-backend-1 python3 scripts/test_batch_processing.py run
```

**出力例**:
```
====================================================================
バッチ処理実行開始
実行時刻: 2025-12-23 06:01:30 UTC
====================================================================

1️⃣  Trial期間終了チェック実行中...
   ✅ 更新件数: 2

2️⃣  スケジュールキャンセルチェック実行中...
   ✅ 更新件数: 1

====================================================================
✅ バッチ処理完了
====================================================================

📊 処理結果:
   Trial期間終了: 2件
   スケジュールキャンセル: 1件

🔍 結果を確認するには:
   docker exec keikakun_app-backend-1 python3 scripts/test_batch_processing.py verify
```

---

### ステップ4: 結果確認

```bash
# バッチ処理の結果を検証
docker exec keikakun_app-backend-1 python3 scripts/test_batch_processing.py verify
```

**出力例**:
```
====================================================================
結果検証開始
検証時刻: 2025-12-23 06:02:00 UTC
====================================================================

📋 検証対象: 3件

✅ 1. E2E_TEST_BATCH_20251223_060000_FREE_TO_PAST_DUE
   Office ID: ...
   Billing ID: ...
   Expected Status: past_due
   Actual Status: past_due
   Result: PASS

✅ 2. E2E_TEST_BATCH_20251223_060000_EARLY_TO_ACTIVE
   Office ID: ...
   Billing ID: ...
   Expected Status: active
   Actual Status: active
   Result: PASS

✅ 3. E2E_TEST_BATCH_20251223_060000_CANCELING_TO_CANCELED
   Office ID: ...
   Billing ID: ...
   Expected Status: canceled
   Actual Status: canceled
   Result: PASS

====================================================================
✅ すべてのテストが成功しました
====================================================================
```

---

### ステップ5: クリーンアップ

```bash
# テストデータを削除
docker exec keikakun_app-backend-1 python3 scripts/test_batch_processing.py cleanup
```

**出力例**:
```
====================================================================
テストデータクリーンアップ開始
====================================================================

🗑️  削除対象: 3件

1. E2E_TEST_BATCH_20251223_060000_FREE_TO_PAST_DUE
   Office ID: ...
2. E2E_TEST_BATCH_20251223_060000_EARLY_TO_ACTIVE
   Office ID: ...
3. E2E_TEST_BATCH_20251223_060000_CANCELING_TO_CANCELED
   Office ID: ...

====================================================================
✅ クリーンアップ完了
====================================================================
```

---

## 📊 簡易実行（全ステップ一括）

```bash
# 1. テストデータ作成（1分後に期限切れ）
docker exec keikakun_app-backend-1 python3 scripts/test_batch_processing.py setup --minutes 1

# 2. 1分待機
sleep 60

# 3. バッチ処理実行
docker exec keikakun_app-backend-1 python3 scripts/test_batch_processing.py run

# 4. 結果確認
docker exec keikakun_app-backend-1 python3 scripts/test_batch_processing.py verify

# 5. クリーンアップ
docker exec keikakun_app-backend-1 python3 scripts/test_batch_processing.py cleanup
```

---

## 🔍 データベースで直接確認

テストデータの状態をSQLで直接確認することもできます:

```sql
-- テストデータのOfficeとBillingを確認
SELECT
    o.office_name,
    o.id as office_id,
    b.id as billing_id,
    b.billing_status,
    b.trial_end_date,
    b.scheduled_cancel_at
FROM offices o
LEFT JOIN billings b ON o.id = b.office_id
WHERE o.office_name LIKE 'E2E_TEST_BATCH_%'
ORDER BY o.created_at DESC;
```

---

## ⚠️ 注意事項

1. **本番環境では実行しないでください**
   - このスクリプトはテストデータを作成します
   - 必ず開発環境またはステージング環境で実行してください

2. **テストデータは必ずクリーンアップしてください**
   - `cleanup` コマンドでテストデータを削除してください

3. **タイミングについて**
   - バッチ処理は期限切れになった「後」に実行してください
   - 例: 1分後に設定した場合、少なくとも1分以上待ってから実行

4. **複数回実行する場合**
   - 前回のテストデータを `cleanup` で削除してから新しいテストを実行してください

---

## 🐛 トラブルシューティング

### テストが失敗する場合

1. **時間を待ったか確認**
   - 期限時刻より前にバッチ処理を実行していませんか？
   - もう一度 `run` コマンドを実行してみてください

2. **データベース接続確認**
   - バックエンドコンテナが起動しているか確認
   - `docker ps` でコンテナの状態を確認

3. **ログ確認**
   - バッチ処理実行時のログを確認
   - `docker logs keikakun_app-backend-1 --tail 50`

### テストデータが残っている場合

```bash
# すべてのテストデータを強制クリーンアップ
docker exec keikakun_app-backend-1 python3 scripts/test_batch_processing.py cleanup
```

---

## 📝 カスタマイズ

### より長い期間でテストしたい場合

```bash
# 5分後に期限切れ
docker exec keikakun_app-backend-1 python3 scripts/test_batch_processing.py setup --minutes 5

# 60分後に期限切れ
docker exec keikakun_app-backend-1 python3 scripts/test_batch_processing.py setup --minutes 60
```

---

**最終更新**: 2025-12-23
