# パフォーマンステストガイド

Gmail期限通知バッチ処理の最適化プロジェクトにおけるパフォーマンステストの実行方法

---

## 📋 概要

このディレクトリには、Gmail期限通知バッチ処理のパフォーマンステストが含まれています。

### テストファイル

- **test_deadline_notification_performance.py**: メインのパフォーマンステスト
  - 500事業所規模の負荷テスト
  - N+1クエリ問題の検出
  - メモリリーク検出
  - 並列処理効率測定

---

## 🚀 実行方法

### 全パフォーマンステストの実行

```bash
# Docker経由で実行
docker exec keikakun_app-backend-1 pytest tests/performance/test_deadline_notification_performance.py -v -m performance

# ローカル実行（開発環境）
pytest tests/performance/test_deadline_notification_performance.py -v -m performance
```

### 特定のテストのみ実行

```bash
# Test 1: 基本パフォーマンステスト（500事業所）
docker exec keikakun_app-backend-1 pytest tests/performance/test_deadline_notification_performance.py::test_deadline_notification_performance_500_offices -v -s

# Test 2: N+1クエリ検出テスト
docker exec keikakun_app-backend-1 pytest tests/performance/test_deadline_notification_performance.py::test_query_efficiency_no_n_plus_1 -v -s

# Test 3: メモリリーク検出テスト
docker exec keikakun_app-backend-1 pytest tests/performance/test_deadline_notification_performance.py::test_memory_efficiency_chunk_processing -v -s

# Test 4: 並列処理効率テスト
docker exec keikakun_app-backend-1 pytest tests/performance/test_deadline_notification_performance.py::test_parallel_processing_speedup -v -s
```

### 詳細ログ付き実行

```bash
# ログレベルをINFOに設定して実行
docker exec keikakun_app-backend-1 pytest tests/performance/test_deadline_notification_performance.py -v -s --log-cli-level=INFO -m performance
```

---

## 📊 テスト一覧

### Test 1: 基本パフォーマンステスト（500事業所）

**目的**: 500事業所規模での処理時間、メモリ使用量、クエリ数を測定

**目標**:
- 処理時間: < 300秒（5分）
- メモリ増加: < 50MB
- DBクエリ数: < 100回

**現状予想（最適化前）**:
- 処理時間: 約1,500秒（25分）⚠️
- メモリ増加: 約500MB ⚠️
- DBクエリ数: 約1,001回 ⚠️

**実行時間**: 約25分（最適化前）

---

### Test 2: クエリ効率テスト（N+1問題検出）

**目的**: N+1クエリ問題が解消されているか検証

**目標**:
- クエリ数が事業所数に比例しない（O(1)）
- 10事業所でクエリ数 < 2回（事業所数の20%）

**理論値（最適化後）**:
- 事業所取得: 1クエリ
- アラート取得: 2クエリ
- スタッフ取得: 1クエリ
- 合計: 4クエリ（定数）

**実行時間**: 約1分

---

### Test 3: メモリ効率テスト（リーク検出）

**目的**: メモリリークがないことを確認

**目標**:
- ピークメモリ増加: < 50MB
- GC後メモリ増加: < 10MB
- メモリリーク率: < 20%

**検証方法**:
1. 処理前のメモリ測定
2. 処理実行（ピークメモリ測定）
3. GC実行
4. GC後のメモリ測定
5. リーク率計算

**実行時間**: 約25分（最適化前）

---

### Test 4: 並列処理効率テスト

**目的**: 並列化により処理速度が向上しているか確認

**目標**:
- 1事業所あたりの処理時間: < 0.1秒
- 推定並列度: >= 10倍

**計算方法**:
```
推定並列度 = 1 / (総処理時間 / 事業所数)
```

**実行時間**: 約25分（最適化前）

---

## 🎯 現在の状態（Phase 1: RED）

**重要**: これらのテストは、**現時点では失敗する（RED状態）のが正常です**。

これはTDD（テスト駆動開発）の「RED → GREEN → REFACTOR」サイクルの最初のステップです。

### 期待される失敗

1. **test_deadline_notification_performance_500_offices**
   ```
   AssertionError: 処理時間が目標を超過: 1500.0秒 > 300秒
   ```

2. **test_query_efficiency_no_n_plus_1**
   ```
   AssertionError: N+1クエリ問題が検出されました: 21回 >= 2回
   ```

3. **test_memory_efficiency_chunk_processing**
   ```
   AssertionError: ピークメモリ増加が目標を超過: 500.0MB > 50MB
   ```

4. **test_parallel_processing_speedup**
   ```
   AssertionError: 推定並列度が目標未達: 1.0倍 < 10倍
   ```

---

## 📈 パフォーマンス改善の進捗追跡

### Phase 1: RED（現在）

- [ ] パフォーマンステスト追加
- [ ] ベースライン測定
- [ ] 全テスト失敗を確認

### Phase 2: GREEN（バッチクエリ実装後）

- [ ] N+1クエリ問題解消
- [ ] test_query_efficiency_no_n_plus_1 がパス
- [ ] クエリ数: 1,001回 → 4回

### Phase 3: GREEN（並列処理実装後）

- [ ] 並列処理実装
- [ ] test_parallel_processing_speedup がパス
- [ ] 処理時間: 1,500秒 → 180秒

### Phase 4: 全テストGREEN

- [ ] 全パフォーマンステストがパス
- [ ] 500事業所で5分以内に完了
- [ ] メモリ使用量50MB以下

---

## 🔧 トラブルシューティング

### テストデータ生成に時間がかかる

**問題**: 500事業所のテストデータ生成に5分以上かかる

**対策**:
- 小規模テスト（10事業所）で先に動作確認
- バッチINSERTの最適化
- トランザクションサイズの調整

### メモリ不足エラー

**問題**: `MemoryError` が発生する

**対策**:
- Dockerのメモリ制限を増やす
- チャンク処理の単位を小さくする
- テストデータサイズを減らす

### タイムアウトエラー

**問題**: `TimeoutError` が発生する

**対策**:
- `@pytest.mark.timeout(600)` の値を増やす
- 小規模テストで先に動作確認
- CI/CDでは大規模テストをスキップ

---

## 📝 テスト結果の記録

### ベースライン測定結果（Phase 1）

実行日: YYYY-MM-DD

| メトリクス | 測定値 | 目標値 | 達成状況 |
|-----------|--------|--------|---------|
| 処理時間（500事業所） | XXX秒 | 300秒 | ❌ |
| DBクエリ数 | XXX回 | 100回 | ❌ |
| メモリ使用量 | XXX MB | 50MB | ❌ |
| 推定並列度 | XXX倍 | 10倍 | ❌ |

### Phase 2 測定結果（バッチクエリ実装後）

実行日: YYYY-MM-DD

| メトリクス | 測定値 | 改善率 | 達成状況 |
|-----------|--------|--------|---------|
| DBクエリ数 | XXX回 | XXX倍 | ✅/❌ |

### Phase 3 測定結果（並列処理実装後）

実行日: YYYY-MM-DD

| メトリクス | 測定値 | 改善率 | 達成状況 |
|-----------|--------|--------|---------|
| 処理時間 | XXX秒 | XXX倍 | ✅/❌ |
| 推定並列度 | XXX倍 | - | ✅/❌ |

---

## 🔗 関連ドキュメント

- [パフォーマンス要件仕様書](../../../md_files_design_note/performance/performance_requirements.md)
- [実装計画](../../../md_files_design_note/performance/implementation_plan.md)
- [テスト仕様書](../../../md_files_design_note/performance/test_specifications.md)

---

**最終更新**: 2026-02-09
**作成者**: Claude Sonnet 4.5
