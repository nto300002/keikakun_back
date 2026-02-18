#!/bin/bash

###############################################################################
# Cloud Run デプロイスクリプト
#
# 使用方法:
#   ./scripts/deploy-cloudrun.sh [環境] [オプション]
#
# 環境:
#   dev   - 開発環境
#   prod  - 本番環境
#
# オプション:
#   --build-only    - イメージのビルドのみ（デプロイしない）
#   --deploy-only   - デプロイのみ（ビルドしない）
#   --dry-run       - 実行コマンドを表示（実際には実行しない）
#
# 例:
#   ./scripts/deploy-cloudrun.sh dev
#   ./scripts/deploy-cloudrun.sh prod --build-only
###############################################################################

set -e  # エラー時に停止

# =====================================
# 環境変数
# =====================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# 色付き出力
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# =====================================
# 関数定義
# =====================================

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_usage() {
    echo "使用方法: $0 [環境] [オプション]"
    echo ""
    echo "環境:"
    echo "  dev   - 開発環境"
    echo "  prod  - 本番環境"
    echo ""
    echo "オプション:"
    echo "  --build-only    - イメージのビルドのみ"
    echo "  --deploy-only   - デプロイのみ"
    echo "  --dry-run       - 実行コマンドを表示"
    echo ""
    echo "例:"
    echo "  $0 dev"
    echo "  $0 prod --build-only"
}

# =====================================
# 引数パース
# =====================================

ENVIRONMENT=""
BUILD_ONLY=false
DEPLOY_ONLY=false
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case $1 in
        dev|prod)
            ENVIRONMENT="$1"
            shift
            ;;
        --build-only)
            BUILD_ONLY=true
            shift
            ;;
        --deploy-only)
            DEPLOY_ONLY=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h|--help)
            print_usage
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            print_usage
            exit 1
            ;;
    esac
done

# 環境チェック
if [[ -z "$ENVIRONMENT" ]]; then
    log_error "環境を指定してください（dev または prod）"
    print_usage
    exit 1
fi

# =====================================
# 環境別設定
# =====================================

if [[ "$ENVIRONMENT" == "prod" ]]; then
    PROJECT_ID="keikakun-prod"
    SERVICE_NAME="keikakun-backend-prod"
    IMAGE_TAG="latest"
    REGION="asia-northeast1"
    CONFIG_FILE="cloudrun-prod.yaml"
elif [[ "$ENVIRONMENT" == "dev" ]]; then
    PROJECT_ID="keikakun-dev"
    SERVICE_NAME="keikakun-backend-dev"
    IMAGE_TAG="dev"
    REGION="asia-northeast1"
    CONFIG_FILE="cloudrun-dev.yaml"
else
    log_error "無効な環境: $ENVIRONMENT"
    exit 1
fi

IMAGE_URL="gcr.io/${PROJECT_ID}/keikakun-backend:${IMAGE_TAG}"

# =====================================
# 前提条件チェック
# =====================================

log_info "前提条件をチェックしています..."

# gcloudコマンドの確認
if ! command -v gcloud &> /dev/null; then
    log_error "gcloud コマンドが見つかりません"
    log_error "Google Cloud SDK をインストールしてください"
    exit 1
fi

# プロジェクトの設定確認
CURRENT_PROJECT=$(gcloud config get-value project 2>/dev/null)
if [[ "$CURRENT_PROJECT" != "$PROJECT_ID" ]]; then
    log_warning "現在のプロジェクト: $CURRENT_PROJECT"
    log_warning "デプロイ先プロジェクト: $PROJECT_ID"
    read -p "プロジェクトを切り替えますか？ (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        gcloud config set project "$PROJECT_ID"
    else
        log_error "プロジェクトが一致しません"
        exit 1
    fi
fi

# Dockerfileの確認
if [[ ! -f "$PROJECT_ROOT/Dockerfile" ]]; then
    log_error "Dockerfile が見つかりません: $PROJECT_ROOT/Dockerfile"
    exit 1
fi

# 設定ファイルの確認
if [[ ! -f "$PROJECT_ROOT/$CONFIG_FILE" ]] && [[ "$DEPLOY_ONLY" == false ]]; then
    log_error "設定ファイルが見つかりません: $PROJECT_ROOT/$CONFIG_FILE"
    exit 1
fi

log_success "前提条件チェック完了"

# =====================================
# デプロイ確認
# =====================================

if [[ "$DRY_RUN" == false ]]; then
    echo ""
    echo "========================================="
    echo "デプロイ設定"
    echo "========================================="
    echo "環境: $ENVIRONMENT"
    echo "プロジェクト: $PROJECT_ID"
    echo "サービス: $SERVICE_NAME"
    echo "イメージ: $IMAGE_URL"
    echo "リージョン: $REGION"
    echo "設定ファイル: $CONFIG_FILE"
    echo "========================================="
    echo ""

    read -p "この設定でデプロイを実行しますか？ (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "デプロイをキャンセルしました"
        exit 0
    fi
fi

# =====================================
# イメージビルド
# =====================================

if [[ "$DEPLOY_ONLY" == false ]]; then
    log_info "Dockerイメージをビルドしています..."

    BUILD_CMD="gcloud builds submit \
        --tag=$IMAGE_URL \
        --project=$PROJECT_ID \
        $PROJECT_ROOT"

    if [[ "$DRY_RUN" == true ]]; then
        log_info "[DRY-RUN] $BUILD_CMD"
    else
        eval "$BUILD_CMD"
        log_success "イメージビルド完了: $IMAGE_URL"
    fi
fi

if [[ "$BUILD_ONLY" == true ]]; then
    log_success "ビルドのみ完了"
    exit 0
fi

# =====================================
# Cloud Runデプロイ
# =====================================

if [[ "$DEPLOY_ONLY" == false ]] || [[ "$BUILD_ONLY" == false ]]; then
    log_info "Cloud Runにデプロイしています..."

    # 設定ファイルのPROJECT_IDを置換
    TEMP_CONFIG="/tmp/${CONFIG_FILE}.tmp"
    sed "s/PROJECT_ID/${PROJECT_ID}/g" "$PROJECT_ROOT/$CONFIG_FILE" > "$TEMP_CONFIG"

    # イメージURLを更新
    sed -i.bak "s|image:.*|image: ${IMAGE_URL}|g" "$TEMP_CONFIG"

    DEPLOY_CMD="gcloud run services replace $TEMP_CONFIG \
        --platform=managed \
        --region=$REGION \
        --project=$PROJECT_ID"

    if [[ "$DRY_RUN" == true ]]; then
        log_info "[DRY-RUN] $DEPLOY_CMD"
        cat "$TEMP_CONFIG"
    else
        eval "$DEPLOY_CMD"
        rm -f "$TEMP_CONFIG" "${TEMP_CONFIG}.bak"
        log_success "デプロイ完了"
    fi
fi

# =====================================
# デプロイ後の確認
# =====================================

if [[ "$DRY_RUN" == false ]]; then
    log_info "デプロイ後の確認..."

    # サービスURLの取得
    SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" \
        --platform=managed \
        --region="$REGION" \
        --project="$PROJECT_ID" \
        --format="value(status.url)")

    if [[ -n "$SERVICE_URL" ]]; then
        log_success "サービスURL: $SERVICE_URL"

        # ヘルスチェック
        log_info "ヘルスチェックを実行しています..."
        HEALTH_URL="${SERVICE_URL}/api/v1/health"

        if curl -s -f -m 10 "$HEALTH_URL" > /dev/null; then
            log_success "ヘルスチェック: OK"
        else
            log_warning "ヘルスチェック: FAIL"
            log_warning "URL: $HEALTH_URL"
        fi
    fi

    # デプロイ情報の表示
    log_info "デプロイ情報を取得しています..."
    gcloud run services describe "$SERVICE_NAME" \
        --platform=managed \
        --region="$REGION" \
        --project="$PROJECT_ID" \
        --format="table(
            status.conditions[0].type,
            status.conditions[0].status,
            status.latestReadyRevisionName,
            status.traffic[0].percent
        )"
fi

# =====================================
# 完了
# =====================================

echo ""
log_success "========================================="
log_success "デプロイが完了しました！"
log_success "========================================="
echo ""
echo "次のステップ:"
echo "  1. サービスURLにアクセスして動作確認"
echo "  2. Cloud Consoleでログを確認"
echo "  3. モニタリングダッシュボードを確認"
echo ""

if [[ "$ENVIRONMENT" == "prod" ]]; then
    log_warning "本番環境にデプロイしました"
    log_warning "必ず動作確認を行ってください"
fi
