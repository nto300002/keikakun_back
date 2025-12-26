#!/bin/bash
# Test Clock作成からSubscription作成までをワンライナーで実行
# 使い方: ./test_clock_one_liner.sh

STRIPE_PRICE_ID=${STRIPE_PRICE_ID:-"price_1PqJKwBxyBErCNcARtNT1cXy"}

docker exec keikakun_app-backend-1 python3 << EOF
import stripe
from app.core.config import settings
from datetime import datetime, timedelta, timezone

stripe.api_key = settings.STRIPE_SECRET_KEY.get_secret_value()

# Test Clock作成
clock = stripe.test_helpers.TestClock.create(
    frozen_time=int(datetime.now(timezone.utc).timestamp()),
    name=f"Quick {datetime.now().strftime('%Y%m%d_%H%M%S')}"
)
print(f"✅ Test Clock: {clock.id}")

# Customer作成
customer = stripe.Customer.create(
    email=f'test-{datetime.now().strftime("%Y%m%d%H%M%S")}@example.com',
    name='Quick Customer',
    test_clock=clock.id,
    metadata={'created_by': 'one_liner'}
)
print(f"✅ Customer: {customer.id}")

# Subscription作成
sub = stripe.Subscription.create(
    customer=customer.id,
    items=[{'price': '$STRIPE_PRICE_ID'}],
    trial_end=int((datetime.now(timezone.utc) + timedelta(days=7)).timestamp())
)
print(f"✅ Subscription: {sub.id}")

print(f"\n{'='*80}")
print("次のコマンド:")
print(f"{'='*80}")
print(f"\n# 時間を進める（7日）")
print(f"docker exec keikakun_app-backend-1 python3 scripts/stripe_test_clock_manager.py advance --clock-id {clock.id} --days 7")
print(f"\n# Webhookログ確認")
print(f"docker logs keikakun_app-backend-1 --tail 100 | grep -i webhook")
print(f"\n# 削除")
print(f"docker exec keikakun_app-backend-1 python3 scripts/stripe_test_clock_manager.py delete --clock-id {clock.id}")
print(f"\n{'='*80}")

# IDをファイルに保存
import os
os.makedirs('/tmp/test_clocks', exist_ok=True)
with open('/tmp/test_clocks/last_test_clock_id.txt', 'w') as f:
    f.write(clock.id)
with open('/tmp/test_clocks/last_customer_id.txt', 'w') as f:
    f.write(customer.id)

print(f"\n✅ IDを /tmp/test_clocks/ に保存しました")
EOF
