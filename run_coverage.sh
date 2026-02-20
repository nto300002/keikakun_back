#!/bin/bash

# カバレッジ測定スクリプト
# Usage: ./run_coverage.sh [test_path]

set -e

# 色付き出力
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  テストカバレッジ測定${NC}"
echo -e "${GREEN}========================================${NC}"

# テストパスが指定されていない場合はダッシュボード関連のみ
TEST_PATH="${1:-tests/crud/test_crud_dashboard*.py tests/api/v1/endpoints/test_dashboard.py}"

echo -e "${YELLOW}対象テスト:${NC} ${TEST_PATH}"
echo ""

# カバレッジ測定実行
echo -e "${GREEN}[1/3] カバレッジ測定実行中...${NC}"
pytest ${TEST_PATH} \
    --cov=app.crud.crud_dashboard \
    --cov=app.api.v1.endpoints.dashboard \
    --cov=app.services.dashboard_service \
    --cov-report=html \
    --cov-report=term-missing \
    --cov-report=xml \
    -v

# カバレッジレートを取得
COVERAGE_RATE=$(coverage report | grep "TOTAL" | awk '{print $NF}' | sed 's/%//')

echo ""
echo -e "${GREEN}[2/3] カバレッジレポート生成完了${NC}"
echo -e "  HTML: ${YELLOW}htmlcov/index.html${NC}"
echo -e "  XML:  ${YELLOW}coverage.xml${NC}"

# カバレッジ目標判定
echo ""
echo -e "${GREEN}[3/3] カバレッジ判定${NC}"
if (( $(echo "$COVERAGE_RATE >= 80" | bc -l) )); then
    echo -e "${GREEN}✅ カバレッジ目標達成: ${COVERAGE_RATE}% (目標: 80%以上)${NC}"
    exit 0
else
    echo -e "${RED}❌ カバレッジ目標未達: ${COVERAGE_RATE}% (目標: 80%以上)${NC}"
    exit 1
fi
