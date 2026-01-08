#!/bin/bash
# Test Clock クイックサイクル自動化スクリプト
# 使い方: ./test_clock_quick_cycle.sh

set -e

# 色付き出力
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}==============================================================================${NC}"
echo -e "${BLUE}Test Clock クイックサイクル${NC}"
echo -e "${BLUE}==============================================================================${NC}"

# Price IDを環境変数から取得（デフォルト値あり）
STRIPE_PRICE_ID=${STRIPE_PRICE_ID:-"price_1PqJKwBxyBErCNcARtNT1cXy"}

# 1. Test Clock作成
echo -e "\n${GREEN}[1/6] Test Clock作成中...${NC}"
RESULT=$(docker exec keikakun_app-backend-1 python3 scripts/stripe_test_clock_manager.py create --name "Quick Test $(date +%Y%m%d_%H%M%S)" 2>&1)
TEST_CLOCK_ID=$(echo "$RESULT" | grep "Test Clock ID:" | awk '{print $4}')

if [ -z "$TEST_CLOCK_ID" ]; then
    echo -e "${RED}❌ Test Clock作成失敗${NC}"
    echo "$RESULT"
    exit 1
fi

echo -e "${GREEN}✅ Test Clock作成完了: $TEST_CLOCK_ID${NC}"

# 2. Test Clock付きCustomer作成
echo -e "\n${GREEN}[2/6] Customer作成中...${NC}"
CUSTOMER_ID=$(docker exec keikakun_app-backend-1 python3 -c "
import stripe
from app.core.config import settings
from datetime import datetime

stripe.api_key = settings.STRIPE_SECRET_KEY.get_secret_value()

customer = stripe.Customer.create(
    email=f'test-{datetime.now().strftime(\"%Y%m%d%H%M%S\")}@example.com',
    name='Quick Test Customer',
    test_clock='$TEST_CLOCK_ID',
    metadata={'office_id': 'test-office-quick', 'created_by': 'quick_cycle_script'}
)

print(customer.id)
" 2>/dev/null)

if [ -z "$CUSTOMER_ID" ]; then
    echo -e "${RED}❌ Customer作成失敗${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Customer作成完了: $CUSTOMER_ID${NC}"

# 3. Subscription作成（Trial 7日）
echo -e "\n${GREEN}[3/6] Subscription作成中...${NC}"
SUBSCRIPTION_ID=$(docker exec keikakun_app-backend-1 python3 -c "
import stripe
from app.core.config import settings
from datetime import datetime, timedelta, timezone

stripe.api_key = settings.STRIPE_SECRET_KEY.get_secret_value()

trial_end = int((datetime.now(timezone.utc) + timedelta(days=7)).timestamp())

subscription = stripe.Subscription.create(
    customer='$CUSTOMER_ID',
    items=[{'price': '$STRIPE_PRICE_ID'}],
    trial_end=trial_end
)

print(subscription.id)
" 2>/dev/null)

if [ -z "$SUBSCRIPTION_ID" ]; then
    echo -e "${RED}❌ Subscription作成失敗${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Subscription作成完了: $SUBSCRIPTION_ID${NC}"

# 4. アプリDBにBilling作成
echo -e "\n${GREEN}[4/6] アプリDBにBilling作成中...${NC}"
BILLING_INFO=$(docker exec keikakun_app-backend-1 python3 -c "
import asyncio
from uuid import uuid4
from datetime import datetime, timedelta, timezone
from app.db.session import AsyncSessionLocal
from app.models.office import Office
from app.models.billing import Billing
from app.models.enums import BillingStatus, OfficeType

async def create_test_billing():
    async with AsyncSessionLocal() as db:
        office = Office(
            id=uuid4(),
            name='Quick Test Office $(date +%Y%m%d_%H%M%S)',
            type=OfficeType.VISITING_CARE,
            phone_number='000-0000-9999',
            is_test_data=True
        )
        db.add(office)
        await db.flush()

        billing = Billing(
            id=uuid4(),
            office_id=office.id,
            billing_status=BillingStatus.early_payment,
            trial_start_date=datetime.now(timezone.utc),
            trial_end_date=datetime.now(timezone.utc) + timedelta(days=7),
            current_plan_amount=6000,
            stripe_customer_id='$CUSTOMER_ID',
            stripe_subscription_id='$SUBSCRIPTION_ID'
        )
        db.add(billing)
        await db.commit()

        print(f'{billing.id}|{office.id}')

asyncio.run(create_test_billing())
" 2>/dev/null)

BILLING_ID=$(echo "$BILLING_INFO" | cut -d'|' -f1)
OFFICE_ID=$(echo "$BILLING_INFO" | cut -d'|' -f2)

if [ -z "$BILLING_ID" ]; then
    echo -e "${RED}❌ Billing作成失敗${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Billing作成完了: $BILLING_ID${NC}"

# 5. 情報表示
echo -e "\n${BLUE}==============================================================================${NC}"
echo -e "${BLUE}テスト環境準備完了${NC}"
echo -e "${BLUE}==============================================================================${NC}"
echo ""
echo -e "Test Clock ID:    ${YELLOW}$TEST_CLOCK_ID${NC}"
echo -e "Customer ID:      ${YELLOW}$CUSTOMER_ID${NC}"
echo -e "Subscription ID:  ${YELLOW}$SUBSCRIPTION_ID${NC}"
echo -e "Billing ID:       ${YELLOW}$BILLING_ID${NC}"
echo -e "Office ID:        ${YELLOW}$OFFICE_ID${NC}"
echo ""

# 6. 次のステップを表示
echo -e "${GREEN}[5/6] 次のステップ:${NC}"
echo ""
echo -e "${BLUE}# 時間を進める（7日）${NC}"
echo -e "docker exec keikakun_app-backend-1 python3 scripts/stripe_test_clock_manager.py advance --clock-id $TEST_CLOCK_ID --days 7"
echo ""
echo -e "${BLUE}# Webhookログ確認${NC}"
echo -e "docker logs keikakun_app-backend-1 --tail 100 | grep -i webhook"
echo ""
echo -e "${BLUE}# Billing状態確認${NC}"
echo -e "docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py list | grep -A 6 \"$BILLING_ID\""
echo ""
echo -e "${BLUE}# クリーンアップ（削除）${NC}"
echo -e "docker exec keikakun_app-backend-1 python3 scripts/stripe_test_clock_manager.py delete --clock-id $TEST_CLOCK_ID"
echo ""

# IDをファイルに保存
mkdir -p /tmp/test_clocks
echo "$TEST_CLOCK_ID" > /tmp/test_clocks/last_test_clock_id.txt
echo "$CUSTOMER_ID" > /tmp/test_clocks/last_customer_id.txt
echo "$BILLING_ID" > /tmp/test_clocks/last_billing_id.txt
echo "$OFFICE_ID" > /tmp/test_clocks/last_office_id.txt

echo -e "${GREEN}[6/6] IDを保存しました: /tmp/test_clocks/${NC}"
echo ""
echo -e "${BLUE}==============================================================================${NC}"
echo -e "${GREEN}✅ セットアップ完了！上記のコマンドでテストを続行してください${NC}"
echo -e "${BLUE}==============================================================================${NC}"
