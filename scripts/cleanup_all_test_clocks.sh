#!/bin/bash
# すべてのTest Clocksを一括削除するスクリプト
# 使い方: ./cleanup_all_test_clocks.sh

set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}==============================================================================${NC}"
echo -e "${BLUE}Test Clocks 一括クリーンアップ${NC}"
echo -e "${BLUE}==============================================================================${NC}"

# 1. StripeのTest Clocksを削除
echo -e "\n${GREEN}[1/2] StripeのTest Clocksを削除中...${NC}"

RESULT=$(docker exec keikakun_app-backend-1 python3 << 'EOF'
import stripe
from app.core.config import settings

stripe.api_key = settings.STRIPE_SECRET_KEY.get_secret_value()

test_clocks = stripe.test_helpers.TestClock.list(limit=100)

if not test_clocks.data:
    print("0")
else:
    count = 0
    for clock in test_clocks.data:
        try:
            print(f"削除中: {clock.id} ({clock.name})", flush=True)
            stripe.test_helpers.TestClock.delete(clock.id)
            count += 1
        except Exception as e:
            print(f"エラー: {clock.id} - {e}", flush=True)
    print(f"{count}")
EOF
)

DELETED_COUNT=$(echo "$RESULT" | tail -1)
echo -e "${GREEN}✅ ${DELETED_COUNT}個のTest Clocksを削除しました${NC}"

# 2. アプリDBのテストデータを削除
echo -e "\n${GREEN}[2/2] アプリDBのテストデータを削除中...${NC}"

docker exec -it keikakun_app-backend-1 psql $DATABASE_URL -c "
DO \$\$
DECLARE
    billing_count INTEGER;
    office_count INTEGER;
BEGIN
    -- Billingsを削除
    DELETE FROM billings WHERE is_test_data = true;
    GET DIAGNOSTICS billing_count = ROW_COUNT;

    -- Officesを削除
    DELETE FROM offices WHERE is_test_data = true;
    GET DIAGNOSTICS office_count = ROW_COUNT;

    RAISE NOTICE 'Billings削除: %件, Offices削除: %件', billing_count, office_count;
END \$\$;
" 2>&1 | grep -i "notice" || true

echo -e "${GREEN}✅ アプリDBのテストデータを削除しました${NC}"

# 3. 一時ファイルを削除
if [ -d "/tmp/test_clocks" ]; then
    rm -rf /tmp/test_clocks
    echo -e "${GREEN}✅ 一時ファイルを削除しました${NC}"
fi

echo -e "\n${BLUE}==============================================================================${NC}"
echo -e "${GREEN}✅ すべてのクリーンアップ完了${NC}"
echo -e "${BLUE}==============================================================================${NC}"
