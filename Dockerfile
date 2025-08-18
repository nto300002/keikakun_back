# Dockerfile

# --- ステージ 1: base ---
# 目的: 本番環境と開発環境で共通の依存関係をインストールする
FROM python:3.12-slim-bullseye AS base

# Pythonのログがバッファリングされず、直接Dockerログに出力されるようにする
ENV PYTHONUNBUFFERED=1

# アプリケーションの作業ディレクトリを設定
WORKDIR /app

# 依存関係をインストール
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# --- ステージ 2: production ---
# 目的: Cloud Runで実行するための、軽量でセキュアな本番イメージを作成する
FROM base AS production

# セキュリティ向上のため、非rootユーザーを作成して切り替える
RUN addgroup --system --gid 1001 pythonuser && \
    adduser --system --uid 1001 pythonuser
USER pythonuser

# アプリケーションのソースコードをコピー
COPY . .

# Cloud Runがデフォルトでリッスンするポート番号 (8080)
EXPOSE 8080

# 本番サーバー(gunicorn)を起動するコマンド
# Cloud Runのベストプラクティスに従い、ポート8080で起動
CMD exec gunicorn -w 1 -k uvicorn.workers.UvicornWorker -b "0.0.0.0:${PORT}" app.main:app

# --- ステージ 3: development ---
# 目的: ローカル開発用のイメージ。ホットリロードなど開発ツールを含む
FROM base AS development

# 開発用の依存関係を追加でインストール
COPY requirements-dev.txt .
RUN pip install --no-cache-dir --upgrade -r requirements-dev.txt

# 開発サーバー(uvicorn)を起動するコマンド
# ホットリロードを有効にし、コンテナ外からアクセスできるよう0.0.0.0でリッスン
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]