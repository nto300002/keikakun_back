#!/bin/bash
# 最後に作成したTest Clockの時間を進める
# 使い方: ./test_clock_advance_last.sh [days]

DAYS=${1:-7}

if [ ! -f "/tmp/test_clocks/last_test_clock_id.txt" ]; then
    echo "❌ Test Clock IDが見つかりません"
    echo "先に test_clock_quick_cycle.sh または test_clock_one_liner.sh を実行してください"
    exit 1
fi

TEST_CLOCK_ID=$(cat /tmp/test_clocks/last_test_clock_id.txt)

echo "🕐 Test Clock ID: $TEST_CLOCK_ID"
echo "⏰ 時間を進めます: ${DAYS}日"
echo ""

docker exec keikakun_app-backend-1 python3 scripts/stripe_test_clock_manager.py advance \
  --clock-id "$TEST_CLOCK_ID" \
  --days "$DAYS"

echo ""
echo "✅ 完了"
echo ""
echo "次のステップ:"
echo "  # Webhookログ確認"
echo "  docker logs keikakun_app-backend-1 --tail 100 | grep -i webhook"
echo ""
echo "  # Billing状態確認"
if [ -f "/tmp/test_clocks/last_billing_id.txt" ]; then
    BILLING_ID=$(cat /tmp/test_clocks/last_billing_id.txt)
    echo "  docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py list | grep -A 6 \"$BILLING_ID\""
fi
