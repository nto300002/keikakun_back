# オートスケーリング設定追加のデプロイ手順

**作成日**: 2026-02-10
**対象**: cloudbuild.yml のオートスケーリング設定追加
**影響範囲**: Cloud Runのリソース設定のみ（環境変数、コードは変更なし）

---

## 📋 変更内容

### cloudbuild.yml に追加された設定

```yaml
# オートスケーリング設定（7項目を追加）
- '--min-instances=0'        # 夜間課金ゼロ
- '--max-instances=5'        # ピーク時対応
- '--cpu=2'                  # 2 vCPU
- '--memory=1Gi'             # 1 GiB RAM
- '--no-cpu-throttling'      # 常時CPU
- '--timeout=600'            # 10分
- '--concurrency=80'         # 並行リクエスト数
```

**重要**: 環境変数、コード、データベースは一切変更なし

---

## ✅ 整合性チェック

### デプロイの整合性分析

#### 1. データベースの整合性
- ✅ **変更なし** - マイグレーション不要
- ✅ **既存データへの影響**: なし

#### 2. API互換性
- ✅ **変更なし** - APIレスポンス形式は同じ
- ✅ **後方互換性**: 完全に維持

#### 3. 環境変数
- ✅ **変更なし** - 既存の環境変数をそのまま使用

#### 4. 実行中のリクエストへの影響
- ✅ **グレースフルシャットダウン**: Cloud Runのデフォルト動作（30秒待機）
- ✅ **セッション**: JWTトークン（ステートレス）のため影響なし

#### 5. ロールバック可能性
- ✅ **即座にロールバック可能**: リソース設定のみの変更
- ✅ **データ損失リスク**: ゼロ

#### 6. 外部サービスとの整合性
- ✅ **NeonDB**: 設定変更不要（既存の接続プール設定で動作）
- ✅ **S3**: 影響なし
- ✅ **SES**: 影響なし

---

## 🎯 デプロイ手順

### 事前準備（デプロイ1日前）

#### 1. Cloud Schedulerの設定（朝のウォームアップ）

minScale=0のため、朝のピーク前にウォームアップが必要です。

```bash
# Cloud Schedulerジョブ作成
gcloud scheduler jobs create http morning-warmup \
    --schedule="50 7 * * 1-5" \
    --uri="https://YOUR_CLOUD_RUN_URL/api/v1/health" \
    --http-method=GET \
    --location=asia-northeast1 \
    --time-zone="Asia/Tokyo" \
    --description="朝のピーク前にウォームアップ（平日のみ）"

# 確認
gcloud scheduler jobs describe morning-warmup --location=asia-northeast1

# テスト実行
gcloud scheduler jobs run morning-warmup --location=asia-northeast1
```

**重要**: `YOUR_CLOUD_RUN_URL` を実際のURLに置き換えてください。

**確認方法**:
```bash
# Cloud Run URLを取得
gcloud run services describe k-back \
    --region=asia-northeast1 \
    --format="value(status.url)"

# 出力例: https://k-back-xxxxx-an.a.run.app
```

---

#### 2. 現在の設定を確認

```bash
# 現在のリビジョンを確認（ロールバック用）
gcloud run revisions list --service=k-back --region=asia-northeast1

# 現在の設定を確認
gcloud run services describe k-back --region=asia-northeast1 \
    --format="yaml(spec.template.spec.containers[0].resources.limits)"
```

**出力例**:
```yaml
spec:
  template:
    spec:
      containers:
      - resources:
          limits:
            cpu: '1'
            memory: 512Mi
```

---

### デプロイ実行（デプロイ日）

#### 推奨タイミング
- ✅ **平日 10:00-17:00**
- ❌ **朝8:00-9:00は避ける**（ピーク時）
- ❌ **金曜日夕方は避ける**（週末対応できない）

---

#### ステップ1: ブランチ確認

```bash
# mainブランチであることを確認
git branch

# 最新の状態を取得
git pull origin main
```

---

#### ステップ2: 変更内容の確認

```bash
# cloudbuild.ymlの変更を確認
git diff HEAD~1 k_back/cloudbuild.yml

# 期待される変更: オートスケーリング設定の7行が追加されている
```

---

#### ステップ3: コミット＆プッシュ

```bash
cd /Users/naotoyasuda/workspase/keikakun_app

# cloudbuild.ymlをステージング
git add k_back/cloudbuild.yml

# コミット
git commit -m "feat: Cloud Runにオートスケーリング設定を追加

- min-instances=0: 夜間課金ゼロ（コスト削減）
- max-instances=5: ピーク時対応
- cpu=2, memory=1Gi: バッチ処理対応
- no-cpu-throttling: 常時CPU（バッチ処理）
- timeout=600: 10分（バッチ処理）
- concurrency=80: FastAPI最適値

整合性チェック:
- データベース変更なし
- API互換性維持
- 環境変数変更なし
- ロールバック可能

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"

# プッシュ（GitHub Actionsが自動実行される）
git push origin main
```

---

#### ステップ4: GitHub Actionsの監視

1. **GitHub Actionsページを開く**
   - https://github.com/YOUR_USERNAME/keikakun_app/actions

2. **ワークフローの進行を監視**
   - `CD for Backend` ワークフローが自動実行される
   - 各ステップの進行状況を確認

3. **ログを確認**
   - Pytestが成功しているか
   - Cloud Buildが成功しているか
   - Cloud Runデプロイが成功しているか

---

#### ステップ5: デプロイ完了確認

```bash
# 新しいリビジョンが作成されたことを確認
gcloud run revisions list --service=k-back --region=asia-northeast1

# 最新リビジョンが100%トラフィックを受けていることを確認
gcloud run services describe k-back --region=asia-northeast1 \
    --format="table(
        status.latestReadyRevisionName,
        status.traffic[0].revisionName,
        status.traffic[0].percent
    )"

# オートスケーリング設定が反映されていることを確認
gcloud run services describe k-back --region=asia-northeast1 \
    --format="yaml(spec.template)" | grep -A 10 "annotations"
```

**期待される出力**:
```yaml
metadata:
  annotations:
    autoscaling.knative.dev/minScale: "0"
    autoscaling.knative.dev/maxScale: "5"
    run.googleapis.com/cpu-throttling: "false"
```

---

### デプロイ後の確認（5-10分）

#### 1. ヘルスチェック

```bash
# ヘルスチェックエンドポイントを確認
curl https://YOUR_CLOUD_RUN_URL/api/v1/health

# 期待される出力:
# {"status":"healthy","database":"connected"}
```

---

#### 2. 主要エンドポイントのテスト

**ブラウザまたはPostmanで以下を確認**:

1. **ログイン**
   - POST `/api/v1/auth/login`
   - レスポンス時間: < 200ms

2. **個別支援計画一覧**
   - GET `/api/v1/support-plans`
   - レスポンス時間: < 200ms

3. **Googleカレンダー連携**
   - GET `/api/v1/calendar/events`
   - レスポンス時間: < 500ms

---

#### 3. エラーログの確認

```bash
# 最新のログを確認（エラーのみ）
gcloud run services logs read k-back \
    --region=asia-northeast1 \
    --limit=50 \
    --format=json | jq 'select(.severity=="ERROR")'

# エラーがなければ出力なし
```

---

#### 4. メトリクスの確認

**Cloud Consoleで確認**:

1. **Cloud Run** → **k-back** → **メトリクス**
2. 以下を確認:
   - ✅ レスポンス時間（P95）: < 100ms
   - ✅ エラー率: < 0.1%
   - ✅ CPU使用率: < 70%
   - ✅ メモリ使用率: < 70%
   - ✅ インスタンス数: 0-2（通常時）

---

### デプロイ後の継続監視（1時間）

#### 10分ごとに確認

```bash
# エラーログをチェック
gcloud run services logs read k-back \
    --region=asia-northeast1 \
    --limit=20 \
    --format=json | jq 'select(.severity=="ERROR" or .severity=="WARNING")'

# インスタンス数を確認
gcloud run services describe k-back --region=asia-northeast1 \
    --format="value(status.traffic[0].revisionName)"
```

#### Slackアラートを監視

- エラー率の急増
- レスポンス時間の悪化
- ユーザーからの問い合わせ

---

## 🚨 ロールバック手順

### ロールバックが必要な場合

以下の場合は**即座にロールバック**:

1. **エラー率 > 5%** が5分継続
2. **レスポンス時間（P95） > 1秒** が5分継続
3. **ユーザーから重大なバグ報告** が3件以上
4. **インスタンスが起動しない**（minScale=0の影響）

---

### ロールバック実行

```bash
# ステップ1: 1つ前のリビジョンを確認
gcloud run revisions list --service=k-back --region=asia-northeast1

# 出力例:
# REVISION                    ACTIVE  SERVICE  DEPLOYED                 DEPLOYED BY
# k-back-00003-new            yes     k-back   2026-02-10 10:15:00 UTC  user@example.com
# k-back-00002-old                    k-back   2026-02-09 15:30:00 UTC  user@example.com

# ステップ2: 1つ前のリビジョンに即座に切り替え
gcloud run services update-traffic k-back \
    --to-revisions=k-back-00002-old=100 \
    --region=asia-northeast1

# ステップ3: 確認
gcloud run services describe k-back --region=asia-northeast1 \
    --format="value(status.traffic[0].revisionName)"

# ステップ4: ヘルスチェック
curl https://YOUR_CLOUD_RUN_URL/api/v1/health
```

**所要時間**: 約30秒

---

### ロールバック後の対応

1. **原因調査**
   - エラーログを詳細に確認
   - メトリクスを分析

2. **Slack通知**
   - チームに状況を共有
   - 原因と対応を報告

3. **再デプロイ計画**
   - 問題を修正
   - 再度デプロイを計画

---

## 📊 デプロイ後の振り返り（翌日）

### 確認項目

#### 1. コストの変化

```bash
# Cloud Billing Reportsで確認
# https://console.cloud.google.com/billing/
```

**期待される変化**:
- Cloud Run月額コスト: $125-200 → **$46**（約63%削減）

---

#### 2. パフォーマンスの変化

**Cloud Monitoringで確認**:

| メトリクス | 変更前 | 変更後 | 判定 |
|-----------|--------|--------|------|
| レスポンス時間（P95） | < 100ms | < 100ms | ✅ 維持 |
| エラー率 | < 0.1% | < 0.1% | ✅ 維持 |
| インスタンス数（通常時） | 1 | 0-1 | ✅ 最適化 |
| インスタンス数（ピーク時） | 1-2 | 1-2 | ✅ 維持 |

---

#### 3. コールドスタートの発生頻度

```bash
# Cloud Logsで「コールドスタート」を検索
gcloud logging read \
    'resource.type="cloud_run_revision" AND "cold start"' \
    --limit=20 \
    --format=json
```

**期待される結果**:
- 朝7:50のウォームアップ後はコールドスタートなし
- 夜間（18:00-7:50）はコールドスタート許容

---

#### 4. Cloud Schedulerの動作確認

```bash
# 朝のウォームアップジョブの実行履歴を確認
gcloud scheduler jobs describe morning-warmup --location=asia-northeast1

# 実行ログを確認
gcloud logging read \
    'resource.type="cloud_scheduler_job" AND resource.labels.job_id="morning-warmup"' \
    --limit=10 \
    --format=json
```

**期待される結果**:
- 平日7:50に正常実行
- ステータスコード: 200

---

## ✅ 完了チェックリスト

### デプロイ前
- [ ] Cloud Schedulerジョブを作成（朝のウォームアップ）
- [ ] 現在のリビジョンを確認（ロールバック用）
- [ ] デプロイタイミングを確認（平日10:00-17:00）

### デプロイ実行
- [ ] cloudbuild.ymlの変更を確認
- [ ] コミット＆プッシュ
- [ ] GitHub Actionsの監視
- [ ] デプロイ完了確認

### デプロイ後（5-10分）
- [ ] ヘルスチェック
- [ ] 主要エンドポイントのテスト
- [ ] エラーログ確認
- [ ] メトリクス確認

### デプロイ後（1時間）
- [ ] 継続的な監視
- [ ] Slackアラート監視
- [ ] ユーザーからの問い合わせ確認

### 翌日
- [ ] コストの変化を確認
- [ ] パフォーマンスの変化を確認
- [ ] コールドスタート頻度を確認
- [ ] Cloud Schedulerの動作確認

---

## 📚 参考ドキュメント

- [オートスケーリング戦略とデプロイガイド](./DEPLOYMENT.md)
- [デプロイ時の整合性を保つための原則](../md_files_design_note/design/deployment_consistency.md)
- [オートスケーリング設定ガイド](../md_files_design_note/design/autoscaling_configuration.md)

---

**作成日**: 2026-02-10
**作成者**: Claude Sonnet 4.5
**次のアクション**: Cloud Schedulerジョブを作成してからデプロイ
