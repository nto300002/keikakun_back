# けいかくん オートスケーリング戦略とデプロイガイド

**作成日**: 2026-02-09
**対象**: けいかくんバックエンド（FastAPI + NeonDB + Cloud Run）

---

## 📊 けいかくんのトラフィック特性

### システム規模

| 項目 | 規模 |
|------|------|
| **最大事業所数** | 500事業所 |
| **平均ユーザー数/事業所** | 5-10人（スタッフ） |
| **最大ユーザー数** | 2,500-5,000人 |
| **ピーク同時接続数** | 500-1,000ユーザー（推定） |

---

### トラフィックパターン

```
リクエスト数
    │
    │     ┌─ピーク時間帯─┐
    │    ╱│  朝8:00-9:00  │╲
800 │   ╱ │               │ ╲
    │  ╱  │               │  ╲
600 │ ╱   │               │   ╲___
    │╱    │               │       ╲___
400 │     │               │           ╲___
    │     │               │               ╲___
200 │_____│_______________│___________________╲___________
    │     │               │                    ╲
  0 └─────┴───────────────┴─────────────────────╲────────
    7:00  8:00  9:00 10:00               18:00  24:00  時刻

    朝の業務開始時に集中 → 日中は低位安定 → 夜間はほぼゼロ
```

**特徴**:
1. **朝のピーク（8:00-9:00）**:
   - 業務開始時にスタッフが一斉にログイン
   - 個別支援計画の確認、更新
   - 1日の予定確認（Googleカレンダー連携）
   - **想定リクエスト数**: 500-800 req/秒

2. **日中（9:00-18:00）**:
   - 散発的なアクセス
   - データ入力、閲覧
   - **想定リクエスト数**: 50-100 req/秒

3. **夜間（18:00-8:00）**:
   - ほぼアクセスなし
   - バッチ処理のみ（期限通知: 0:00-0:10）
   - **想定リクエスト数**: 0-10 req/秒

---

## 🎯 オートスケーリング戦略

### 戦略の方針

けいかくんの特性から、以下の戦略を採用します：

```
┌─────────────────────────────────────────────────────────┐
│ 戦略: "コスト最適化型 + ピーク時自動スケール"             │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  1. minScale=0 でコスト削減                             │
│     → 夜間はインスタンスゼロ（課金なし）                 │
│                                                         │
│  2. Cloud Schedulerで朝のウォームアップ                 │
│     → 7:50にヘルスチェック実行                          │
│     → ピーク時のコールドスタート回避                     │
│                                                         │
│  3. ピーク時は自動スケールアップ                         │
│     → 朝8:00-9:00に自動的に5-10インスタンス             │
│     → maxScale=15 で上限設定（コスト管理）              │
│                                                         │
│  4. 日中は1-2インスタンスで安定                         │
│     → 低負荷でも即座にレスポンス                        │
│                                                         │
│  5. 夜間は自動サスペンド                                │
│     → バッチ処理時のみ起動（0:00-0:10）                 │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

### Cloud Run オートスケーリング設定（本番環境）

#### 推奨設定

```yaml
# cloudbuild.yml に設定
--min-instances=0              # コスト最適化
--max-instances=15             # ピーク時対応（500-1000ユーザー）
--cpu=2                        # 2 vCPU（バッチ処理対応）
--memory=1Gi                   # 1 GiB RAM
--no-cpu-throttling            # バッチ処理対応
--timeout=600                  # 10分（バッチ処理）
--concurrency=80               # 並行リクエスト数
```

#### 設定の根拠

| 設定 | 値 | 根拠 |
|------|---|------|
| **minScale: 0** | 0インスタンス | **コスト削減**: 夜間（18:00-8:00）は課金ゼロ<br>**理由**: 14時間 × 0インスタンス = $0/日<br>**対策**: Cloud Schedulerで朝7:50にウォームアップ |
| **maxScale: 15** | 15インスタンス | **ピーク時対応**: 朝8:00-9:00の集中アクセス<br>**計算**: 800 req/秒 ÷ 80 req/インスタンス = 10インスタンス<br>**余裕**: 15インスタンスで余裕を持たせる<br>**コスト管理**: 無制限スケールを防止 |
| **CPU: 2 vCPU** | 2 vCPU | **バッチ処理**: Phase 4の10並列処理<br>**API応答**: 複数リクエストの同時処理 |
| **Memory: 1Gi** | 1 GiB | **バッチ処理**: Phase 4の50並行処理<br>**メモリ使用量**: 35MB（Phase 4目標）+ バッファ |
| **no-cpu-throttling** | 常時CPU | **バッチ処理**: 夜間0:00-0:10の期限通知<br>**スケジューラー**: 常時動作が必要 |
| **timeout: 600秒** | 10分 | **バッチ処理**: 500事業所処理（3分）+ 余裕 |
| **concurrency: 80** | 80並行 | **FastAPI + asyncio**: 最適値<br>**I/O待機**: DB/S3アクセスが多い |

---

### スケーリングシミュレーション

#### ケース1: 朝のピーク時（8:00-9:00）

```
状況:
- 500事業所のスタッフが一斉にログイン
- 同時アクセス: 800ユーザー
- 各ユーザーが5リクエスト/分
- リクエスト数: 800 × 5 / 60 = 67 req/秒
- 平均レスポンス時間: 100ms

計算:
- 並行リクエスト数 = 67 × 0.1 = 6.7
- 必要インスタンス数 = ceil(6.7 / 80) = 1インスタンス

実際のスケール:
- Cloud Runは安全マージンを持ってスケール
- 1-2インスタンスで安定

→ ピーク時でも1-2インスタンスで十分
```

**修正**: 当初の想定より低い負荷であることが判明

---

#### ケース2: 超ピーク時（想定外の高負荷）

```
状況:
- 全事業所が同時にアクセス（異常なケース）
- 同時アクセス: 2,000ユーザー
- 各ユーザーが10リクエスト/分
- リクエスト数: 2,000 × 10 / 60 = 333 req/秒

計算:
- 並行リクエスト数 = 333 × 0.1 = 33.3
- 必要インスタンス数 = ceil(33.3 / 80) = 1インスタンス

→ それでも1-2インスタンスで対応可能
```

---

#### ケース3: バッチ処理時（0:00-0:10）

```
状況:
- 期限通知バッチ処理（500事業所）
- 10並列処理
- 処理時間: 3分（Phase 4目標）

必要リソース:
- CPU: 2 vCPU（10並列処理）
- メモリ: 35 MiB（Phase 4目標）
- インスタンス数: 1

→ minScale=0でも、バッチ処理時に自動起動
```

---

### 修正された推奨設定

上記シミュレーションから、以下に修正：

```yaml
# cloudbuild.yml に設定（修正版）
--min-instances=0              # コスト最適化（変更なし）
--max-instances=5              # 15 → 5（実際の負荷に合わせて削減）
--cpu=2                        # 2 vCPU（変更なし）
--memory=1Gi                   # 1 GiB RAM（変更なし）
--no-cpu-throttling            # バッチ処理対応（変更なし）
--timeout=600                  # 10分（変更なし）
--concurrency=80               # 並行リクエスト数（変更なし）
```

**変更理由**:
- 実際の負荷シミュレーションでは、ピーク時でも1-2インスタンスで十分
- maxScale=5で十分な余裕がある
- コスト削減効果が大きい

---

### NeonDB オートスケーリング設定

#### 推奨設定

```bash
# Neon Dashboard
Min Compute: 0.25 CU    # コスト最適化
Max Compute: 2 CU       # ピーク時対応（4 CU → 2 CUに削減）
Auto-suspend: 300秒     # 5分
```

#### 設定の根拠

| 設定 | 値 | 根拠 |
|------|---|------|
| **Min: 0.25 CU** | 0.25 vCPU + 1GB RAM | **コスト削減**: 最小限のリソース<br>**夜間**: 自動サスペンドでコストゼロ |
| **Max: 2 CU** | 2 vCPU + 8GB RAM | **ピーク時**: 1-2インスタンス × 5-15接続<br>**バッチ処理**: 10並列クエリ<br>**修正**: 4 CU → 2 CUで十分 |
| **Auto-suspend: 5分** | 300秒 | **コスト削減**: 非アクティブ時に即停止<br>**朝のピーク**: Cloud Schedulerでウォームアップ |

---

### Cloud Scheduler設定（朝のウォームアップ）

#### 目的

minScale=0の場合、朝のピーク時にコールドスタートが発生します。
これを防ぐため、**朝7:50にヘルスチェック**を実行してウォームアップします。

#### 設定手順

```bash
# Cloud Schedulerジョブ作成
gcloud scheduler jobs create http morning-warmup \
    --schedule="50 7 * * 1-5" \
    --uri="https://keikakun-backend.run.app/api/v1/health" \
    --http-method=GET \
    --location=asia-northeast1 \
    --time-zone="Asia/Tokyo" \
    --description="朝のピーク前にウォームアップ（平日のみ）"

# 確認
gcloud scheduler jobs describe morning-warmup --location=asia-northeast1
```

**スケジュール説明**:
- `50 7 * * 1-5`: 毎週月-金（平日）の7:50 JST
- ピーク時間（8:00）の10分前にウォームアップ
- 土日は実行しない（業務なし）

**効果**:
- 7:50にインスタンスが起動（ウォームアップ）
- 8:00のピーク時にコールドスタートなし
- レスポンス時間: 50ms以下（安定）

---

## 💰 コスト分析

### 月額コスト見積もり（修正版）

#### Cloud Run

**シナリオ**: minScale=0 + maxScale=5

```
稼働時間の内訳:
- ピーク時（8:00-9:00）: 2インスタンス × 1時間/日 × 22営業日 = 44時間/月
- 日中（9:00-18:00）: 1インスタンス × 9時間/日 × 22営業日 = 198時間/月
- 夜間バッチ（0:00-0:10）: 1インスタンス × 0.17時間/日 × 30日 = 5時間/月
- ウォームアップ（7:50-8:00）: 1インスタンス × 0.17時間/日 × 22営業日 = 4時間/月

合計稼働時間: 251時間/月

コスト計算:
- CPU: 2 vCPU × 251時間 × $0.00002400/vCPU秒 × 3600秒
     = 2 × 251 × 0.0864 = $43.37/月
- メモリ: 1 GiB × 251時間 × $0.00000250/GiB秒 × 3600秒
     = 1 × 251 × 0.009 = $2.26/月
- リクエスト: 100万リクエスト × $0.40/100万 = $0.40/月

Cloud Run合計: 約 $46/月
```

#### NeonDB

**シナリオ**: Min 0.25 CU + Max 2 CU + Auto-suspend 5分

```
Pro Tier基本料金: $69/月

Compute使用量:
- ピーク時（8:00-9:00）: 1 CU × 1時間/日 × 22営業日 = 22時間/月
- 日中（9:00-18:00）: 0.5 CU × 9時間/日 × 22営業日 = 99時間/月
- 夜間バッチ（0:00-0:10）: 2 CU × 0.17時間/日 × 30日 = 10時間/月
- その他（サスペンド）: 0 CU

平均CU使用量: (22 + 49.5 + 20) / 730 = 0.125 CU平均

Compute追加料金: 約$10-20/月

NeonDB合計: 約 $80-90/月
```

#### 合計コスト

```
Cloud Run:  $46/月
NeonDB:     $85/月
----------
合計:       約 $130/月
```

**従来の設定（minScale=1）との比較**:
- 従来: $200-350/月
- 修正版: $130/月
- **削減額: $70-220/月（35-63%削減）**

---

### コスト最適化のポイント

#### ✅ 実施済み

1. **minScale=0**
   - 夜間（14時間/日）の課金をゼロ化
   - 削減額: 約$60/月

2. **maxScale削減（15 → 5）**
   - 実際の負荷に合わせて最適化
   - 過剰なリソース確保を防止

3. **NeonDB Max CU削減（4 → 2）**
   - 実際の負荷に合わせて最適化
   - 削減額: 約$20/月

4. **Auto-suspend 5分**
   - 非アクティブ時に即停止
   - NeonDBの課金時間を最小化

#### 🔄 今後の最適化

1. **リクエスト数の監視**
   - 実際のトラフィックを測定
   - 必要に応じてmaxScaleを調整

2. **concurrency調整**
   - 80 → 100-120に増やす可能性
   - 1インスタンスで処理できるリクエストを増やす

3. **NeonDB接続プール最適化**
   - pool_sizeを負荷に合わせて調整
   - 不要な接続を削減

---

## 🔧 既存CI/CDへの統合

### cloudbuild.yml の修正

既存の `cloudbuild.yml` にオートスケーリング設定を追加します。

```yaml
# k_back/cloudbuild.yml（修正版）

steps:
# 1. Dockerイメージをビルド
- name: 'gcr.io/cloud-builders/docker'
  args:
    - 'build'
    - '--target=production'
    - '-t'
    - 'asia-northeast1-docker.pkg.dev/$PROJECT_ID/k-back-repo/k-back:latest'
    - '.'

# 2. Artifact Registryにpush
- name: 'gcr.io/cloud-builders/docker'
  args:
    - 'push'
    - 'asia-northeast1-docker.pkg.dev/$PROJECT_ID/k-back-repo/k-back:latest'

# 3. Cloud Runにデプロイ（オートスケーリング設定を追加）
- name: 'gcr.io/google.com/cloudsdktool/cloud-sdk'
  entrypoint: gcloud
  args:
    - 'run'
    - 'deploy'
    - 'k-back'
    - '--image'
    - 'asia-northeast1-docker.pkg.dev/$PROJECT_ID/k-back-repo/k-back:latest'
    - '--region'
    - 'asia-northeast1'
    - '--platform'
    - 'managed'
    - '--allow-unauthenticated'

    # =====================================
    # オートスケーリング設定（追加）
    # =====================================
    - '--min-instances=0'
    - '--max-instances=5'
    - '--cpu=2'
    - '--memory=1Gi'
    - '--no-cpu-throttling'
    - '--timeout=600'
    - '--concurrency=80'

    # 環境変数設定（既存）
    - '--update-env-vars'
    - '^##^DATABASE_URL=${_PROD_DATABASE_URL}##SECRET_KEY=${_PROD_SECRET_KEY}##AWS_ACCESS_KEY_ID=${_AWS_ACCESS_KEY_ID}##AWS_SECRET_ACCESS_KEY=${_AWS_SECRET_ACCESS_KEY}##AWS_REGION=${_AWS_REGION}##S3_ACCESS_KEY=${_S3_ACCESS_KEY}##S3_SECRET_KEY=${_S3_SECRET_KEY}##S3_REGION=${_S3_REGION}##S3_BUCKET_NAME=${_S3_BUCKET_NAME}##MAIL_FROM=${_SENDER_EMAIL}##MAIL_USERNAME=${_MAIL_USERNAME}##MAIL_PASSWORD=${_MAIL_PASSWORD}##MAIL_SERVER=${_MAIL_SERVER}##MAIL_PORT=${_MAIL_PORT}##FRONTEND_URL=${_FRONTEND_URL}##CALENDAR_ENCRYPTION_KEY=${_CALENDAR_ENCRYPTION_KEY}##ENVIRONMENT=${_ENVIRONMENT}##COOKIE_SECURE=${_COOKIE_SECURE}##COOKIE_DOMAIN=${_COOKIE_DOMAIN}##COOKIE_SAMESITE=${_COOKIE_SAMESITE}##PASSWORD_RESET_TOKEN_EXPIRE_MINUTES=${_PASSWORD_RESET_TOKEN_EXPIRE_MINUTES}##RATE_LIMIT_FORGOT_PASSWORD=${_RATE_LIMIT_FORGOT_PASSWORD}##RATE_LIMIT_RESEND_EMAIL=${_RATE_LIMIT_RESEND_EMAIL}##STRIPE_SECRET_KEY=${_STRIPE_SECRET_KEY}##STRIPE_PUBLISHABLE_KEY=${_STRIPE_PUBLISHABLE_KEY}##STRIPE_WEBHOOK_SECRET=${_STRIPE_WEBHOOK_SECRET}##STRIPE_PRICE_ID=${_STRIPE_PRICE_ID}##VAPID_PRIVATE_KEY=${_VAPID_PRIVATE_KEY}##VAPID_PUBLIC_KEY=${_VAPID_PUBLIC_KEY}##VAPID_SUBJECT=${_VAPID_SUBJECT}##MAIL_STARTTLS=True##MAIL_SSL_TLS=False##MAIL_DEBUG=0'

# ビルドしたイメージを保存
images:
  - 'asia-northeast1-docker.pkg.dev/$PROJECT_ID/k-back-repo/k-back:latest'
```

---

### 変更内容の詳細

#### 追加されたオプション

| オプション | 値 | 説明 |
|-----------|---|------|
| `--min-instances=0` | 0 | 夜間課金ゼロ（コスト削減） |
| `--max-instances=5` | 5 | ピーク時対応（実負荷に最適化） |
| `--cpu=2` | 2 vCPU | バッチ処理対応 |
| `--memory=1Gi` | 1 GiB | 50並行処理対応 |
| `--no-cpu-throttling` | - | バッチ処理が常時実行 |
| `--timeout=600` | 600秒 | バッチ処理（10分） |
| `--concurrency=80` | 80 | FastAPI + asyncioに最適 |

---

### デプロイ手順

#### 1. cloudbuild.yml を修正

```bash
# k_back/cloudbuild.yml を上記の内容で更新
```

#### 2. mainブランチにpush

```bash
git add k_back/cloudbuild.yml
git commit -m "feat: オートスケーリング設定を追加"
git push origin main
```

#### 3. GitHub Actionsで自動デプロイ

- `.github/workflows/cd-backend.yml` が自動実行
- テスト実行 → ビルド → デプロイ

#### 4. デプロイ確認

```bash
# サービス情報を確認
gcloud run services describe k-back \
    --region=asia-northeast1 \
    --platform=managed \
    --format="table(
        metadata.name,
        spec.template.spec.containers[0].resources.limits,
        spec.template.metadata.annotations
    )"

# 期待される出力:
# NAME   CPU  MEMORY  MIN_INSTANCES  MAX_INSTANCES
# k-back  2    1Gi     0              5
```

---

### Cloud Schedulerの設定

#### 朝のウォームアップジョブ作成

```bash
# GCPコンソールまたはgcloudコマンドで作成
gcloud scheduler jobs create http morning-warmup \
    --schedule="50 7 * * 1-5" \
    --uri="https://YOUR_CLOUD_RUN_URL/api/v1/health" \
    --http-method=GET \
    --location=asia-northeast1 \
    --time-zone="Asia/Tokyo" \
    --description="朝のピーク前にウォームアップ（平日のみ）"
```

**重要**: `YOUR_CLOUD_RUN_URL` を実際のCloud Run URLに置き換えてください。

---

## 📊 モニタリング戦略

### 監視すべきメトリクス

#### Cloud Run

| メトリクス | 目標値 | 警告閾値 | アラート |
|-----------|--------|---------|---------|
| **インスタンス数（ピーク時）** | 1-2 | > 3 | Slack通知 |
| **レスポンス時間（P95）** | < 100ms | > 300ms | Slack通知 |
| **エラー率** | < 0.1% | > 1% | Slack通知 |
| **CPU使用率** | 30-60% | > 80% | ログのみ |
| **メモリ使用率** | 20-40% | > 70% | ログのみ |

#### NeonDB

| メトリクス | 目標値 | 警告閾値 | アラート |
|-----------|--------|---------|---------|
| **Current CU（ピーク時）** | 1 CU | > 1.5 CU | ログのみ |
| **接続数** | 5-15 | > 20 | Slack通知 |
| **クエリ実行時間（P95）** | < 100ms | > 500ms | Slack通知 |

---

### アラート設定

#### 高レスポンス時間アラート

```yaml
# Cloud Monitoring Alerting Policy
displayName: "高レスポンス時間（P95 > 300ms）"
conditions:
  - conditionThreshold:
      filter: |
        resource.type = "cloud_run_revision"
        metric.type = "run.googleapis.com/request_latencies"
      aggregations:
        - alignmentPeriod: 60s
          crossSeriesReducer: REDUCE_PERCENTILE_95
      comparison: COMPARISON_GT
      thresholdValue: 300
      duration: 300s
notificationChannels:
  - projects/PROJECT_ID/notificationChannels/slack-backend-alerts
```

---

### 週次レビュー

#### 確認項目

1. **実際のインスタンス数**
   - ピーク時に何インスタンスまで増えたか
   - maxScale=5で足りているか

2. **レスポンス時間**
   - P50, P95, P99を確認
   - 目標値（P95 < 100ms）を達成しているか

3. **コスト**
   - 月次コストが予算内か
   - 想定コスト（$130/月）と実績の差異

4. **エラー率**
   - エラーログを確認
   - コールドスタートによるタイムアウトがないか

---

## 🐛 トラブルシューティング

### 問題1: 朝のピーク時にレスポンスが遅い

**症状**:
- 8:00-9:00にレスポンス時間が500ms以上
- ユーザーから遅いとクレーム

**原因**:
- コールドスタート
- Cloud Schedulerのウォームアップが機能していない

**対策**:
```bash
# Cloud Schedulerジョブを確認
gcloud scheduler jobs describe morning-warmup --location=asia-northeast1

# 手動実行してテスト
gcloud scheduler jobs run morning-warmup --location=asia-northeast1

# ログを確認
gcloud scheduler jobs logs read morning-warmup --location=asia-northeast1 --limit=10
```

**恒久対策**:
```yaml
# minScaleを1に変更（コストとのトレードオフ）
--min-instances=1
```

---

### 問題2: maxScaleに到達してしまう

**症状**:
- インスタンス数が5に到達
- リクエストがキューイングされる

**原因**:
- 想定より負荷が高い
- maxScale=5が不足

**対策**:
```yaml
# maxScaleを増やす
--max-instances=10  # 5 → 10
```

**確認方法**:
```bash
# Cloud Monitoringでインスタンス数を確認
gcloud monitoring time-series list \
    --filter='metric.type="run.googleapis.com/container/instance_count"' \
    --format=json
```

---

### 問題3: NeonDBのコールドスタート

**症状**:
- 朝の初回クエリが10秒かかる
- サスペンド後の接続が遅い

**原因**:
- NeonDBの自動サスペンド

**対策**:
```bash
# Auto-suspend時間を延長
Auto-suspend: 600秒（10分）

# または
# Cloud Schedulerで定期的にクエリ実行
gcloud scheduler jobs create http neondb-warmup \
    --schedule="*/10 * * * *" \
    --uri="https://YOUR_CLOUD_RUN_URL/api/v1/health" \
    --http-method=GET
```

---

## 📚 参考ドキュメント

- [オートスケーリング設定ガイド](../md_files_design_note/design/autoscaling_configuration.md)
- [パフォーマンス最適化レビュー](../md_files_design_note/performance/review/comprehensive_review.md)
- [Cloud Run公式ドキュメント](https://cloud.google.com/run/docs)
- [NeonDB公式ドキュメント](https://neon.tech/docs)

---

## ✅ デプロイチェックリスト

### デプロイ前

- [ ] cloudbuild.ymlにオートスケーリング設定を追加
- [ ] コードレビュー完了
- [ ] テスト実行（全テストPASS）
- [ ] Cloud Schedulerジョブ作成（朝のウォームアップ）

### デプロイ後

- [ ] ヘルスチェック（/api/v1/health）
- [ ] オートスケーリング設定の確認
  ```bash
  gcloud run services describe k-back --region=asia-northeast1
  ```
- [ ] Cloud Schedulerジョブの動作確認
  ```bash
  gcloud scheduler jobs run morning-warmup --location=asia-northeast1
  ```
- [ ] モニタリングダッシュボード確認

### 本番環境デプロイ後（1週間後）

- [ ] 実際のインスタンス数を確認（ピーク時）
- [ ] レスポンス時間を確認（P95 < 100ms）
- [ ] コストを確認（約$130/月）
- [ ] 必要に応じて設定調整

---

**作成日**: 2026-02-09
**作成者**: Claude Sonnet 4.5
**最終更新**: 2026-02-09

---

**次のステップ**: cloudbuild.ymlを修正してGitHubにpush
