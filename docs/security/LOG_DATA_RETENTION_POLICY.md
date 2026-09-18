# 監査ログの保存・閲覧方針（#230）

## 保存する情報

- 監査対象の `action`、`target_type`、必要な `target_id`、`office_id`、実行結果
- `details` は action ごとの allowlist にある項目だけを保存する
- allowlist にない action、キー、nested値は保存時に `<redacted>` とする
- UUID・外部サービスIDは、details内では原値を保存せず `<present>` にする

監査テーブルの `staff_id`、`target_id`、`office_id` は検索・関連付けに必要な構造化カラムとして保持する。API表示・detailsへの再掲は別途最小化する。

## IPアドレスとUser-Agent

- IPアドレスはIPv4を `/24`、IPv6を `/64` のネットワーク表現に変換し、ホストアドレスを保存しない
- User-AgentはSHA-256の先頭16桁に `ua:` を付けた相関用ハッシュだけを保存する
- raw User-Agentはログ、監査details、Issue、テスト成果物へ出力しない
- 不正なIP形式は `<redacted>` とする

これらは不正アクセス調査に必要な相関性を残しつつ、個別端末・利用者の直接識別情報を減らすための方針である。

## 保持期間と閲覧権限

保持期間は監査actionの既存ポリシーに従う。

- 法的保存対象: 5年
- 重要操作: 3年
- 一般操作: 1年
- 認証・MFA・WebAuthn等: 90日

閲覧は監査ログを扱う最小権限の管理者ロールに限定し、Secret Manager、Cloud Logging、Cloud Buildの閲覧権限とは分離する。個人アカウントへの恒久的な広範囲Viewer権限は付与しない。

## 実装・検証

- `sanitize_audit_log_details_for_storage` が保存直前にallowlistを適用する
- unknown action、unknown key、nested raw valueの保存をテストする
- IPのnetwork masking、User-Agent hash、UUIDのpresence化をテストする
- Docker上のpytestとsecurity log static checkをCIで実行する
