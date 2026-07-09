# けいかくん Backend

FastAPI で実装された、けいかくんのバックエンド API です。認証、MFA、事業所、スタッフ、利用者、支援計画、PDF成果物、通知、課金、外部連携を扱います。

## 技術スタック

- Python 3.12
- FastAPI
- SQLAlchemy 2.x async ORM
- Alembic
- Pydantic v2
- PostgreSQL / Neon
- Stripe
- AWS S3
- Web Push
- Google Calendar API
- Google Cloud Run / Cloud Build

## アプリケーション構成

```text
app/
├── api/v1/endpoints/       # HTTP, auth, request validation, response shaping
├── services/               # business use cases and transaction boundaries
│   ├── approval/
│   ├── billing/
│   ├── calendar/
│   └── welfare_recipient/
├── crud/                   # focused data access
├── models/                 # SQLAlchemy models and enums
├── schemas/                # Pydantic schemas
├── core/                   # settings, auth, security, integrations
├── messages/               # centralized Japanese messages
├── scheduler/              # scheduled jobs
├── tasks/                  # batch task entry points
└── templates/email/        # email templates
```

## ロール

現行ロールは次の4種類です。

- `owner`: 事業所管理者。事業所設定、スタッフ管理、課金、主要データ操作を行います。
- `manager`: 利用者や支援計画の通常管理を行います。
- `employee`: 参照と一部操作申請を行います。制限対象操作は承認フローに回します。
- `app_admin`: アプリ運営者向けロールです。事業所横断の管理、退会申請、お知らせ、監査ログなどを扱います。

## 開発コマンド

バックエンドコマンドは親リポジトリから Docker Compose の `backend` サービス内で実行します。

```bash
docker compose up -d backend
docker compose exec backend alembic upgrade head
docker compose exec backend pytest
```

個別テストの例です。

```bash
docker compose exec backend pytest tests/api/v1/test_csrf_protection.py
docker compose exec backend pytest tests/api/v1/test_csrf_protection.py -m "not performance"
```

よく使う確認コマンドです。

```bash
docker compose exec backend sh -lc 'rg "await db.commit\\(|await db.flush\\(" app/api/v1/endpoints'
docker compose exec backend sh -lc 'rg "print\\(" app --type py'
docker compose exec backend sh -lc 'rg "HTTPException.*detail=\"[A-Za-z]" app/api --type py'
docker compose exec backend sh -lc 'alembic heads && alembic current'
```

## マイグレーション

DB 定義変更は Alembic migration を `migrations/versions/` に追加します。

```bash
docker compose exec backend alembic revision --autogenerate -m "describe_change"
docker compose exec backend alembic upgrade head
```

enum、制約、カラム、インデックス、データ移行を含む変更では、PR に検証手順や件数確認を記載します。通常の開発や CI で `alembic stamp` は使いません。

## 環境変数

代表的な値です。実際の必須値は `app/core/config.py`、GitHub Actions、`cloudbuild.yml` を確認してください。

- `DATABASE_URL`
- `TEST_DATABASE_URL`
- `SECRET_KEY`
- `ENCRYPTION_KEY`
- `CALENDAR_ENCRYPTION_KEY`
- `BACKEND_CORS_ORIGINS`
- `COOKIE_DOMAIN`, `COOKIE_SECURE`, `COOKIE_SAMESITE`
- `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_ID`
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `S3_BUCKET_NAME`
- `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_FROM`
- `VAPID_PRIVATE_KEY`, `VAPID_PUBLIC_KEY`, `VAPID_SUBJECT`
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`

Stripe の現行サブスクリプション価格は月額6,000円です。価格変更は Stripe 側の Price と `STRIPE_PRICE_ID` の整合性を確認して行います。

## 実装ルール

- API 層は HTTP、認証認可、入力検証、レスポンス整形に集中します。
- 複数モデルや複数 CRUD をまたぐ業務処理は service 層に置きます。
- API 層に新しい `await db.commit()` / `await db.flush()` を追加しません。
- CRUD は単一モデルまたは狭い集約のデータアクセスに留めます。
- ユーザー向けエラーメッセージは日本語にし、可能な限り `app/messages/ja.py` に寄せます。
- 本番コードで `print()` を使いません。
- トークン、Cookie、個人情報、Stripe secret、Google credential、MFA secret、PDF ファイル名などをログに出しません。

## CI/CD

Backend は parent repository の GitHub Actions からテストを実行し、Cloud Build 経由で Cloud Run にデプロイします。Cloud Build の本番環境変数は `cloudbuild.yml` の `--update-env-vars` を更新します。
