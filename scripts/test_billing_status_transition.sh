#!/bin/bash
# Billing Status遷移テストスクリプト
# 既存のbillingレコードの状態を読み取り、適切な遷移をテストする
#
# 使い方: ./test_billing_status_transition.sh <billing_id>
# 例: ./test_billing_status_transition.sh daae3740-ee95-4967-a34d-9eca0d487dc9

set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# 引数チェック
if [ $# -ne 1 ]; then
    echo -e "${RED}使い方: $0 <billing_id>${NC}"
    echo -e "例: $0 daae3740-ee95-4967-a34d-9eca0d487dc9"
    exit 1
fi

BILLING_ID=$1
STRIPE_PRICE_ID=${STRIPE_PRICE_ID:-"price_1PqJKwBxyBErCNcARtNT1cXy"}

echo -e "${BLUE}==============================================================================${NC}"
echo -e "${BLUE}Billing Status遷移テスト${NC}"
echo -e "${BLUE}==============================================================================${NC}"

# 1. 既存のbillingレコードを取得
echo -e "\n${GREEN}[1/8] Billingレコード取得中...${NC}"
BILLING_INFO=$(docker exec -i keikakun_app-backend-1 python3 << EOF
import asyncio
from uuid import UUID
from app.db.session import AsyncSessionLocal
from app import crud

async def get_billing():
    async with AsyncSessionLocal() as db:
        billing = await crud.billing.get(db=db, id=UUID('$BILLING_ID'))
        if not billing:
            print("ERROR:Billing not found")
            return

        print(f"{billing.id}|{billing.office_id}|{billing.billing_status.value}|{billing.trial_end_date}|{billing.scheduled_cancel_at}|{billing.stripe_customer_id}|{billing.stripe_subscription_id}")

asyncio.run(get_billing())
EOF
)

if [[ $BILLING_INFO == ERROR:* ]]; then
    echo -e "${RED}❌ Billing ID: $BILLING_ID が見つかりません${NC}"
    exit 1
fi

# パース
BILLING_ID=$(echo "$BILLING_INFO" | cut -d'|' -f1)
OFFICE_ID=$(echo "$BILLING_INFO" | cut -d'|' -f2)
CURRENT_STATUS=$(echo "$BILLING_INFO" | cut -d'|' -f3)
TRIAL_END_DATE=$(echo "$BILLING_INFO" | cut -d'|' -f4)
SCHEDULED_CANCEL_AT=$(echo "$BILLING_INFO" | cut -d'|' -f5)

echo -e "${GREEN}✅ Billing取得完了${NC}"
echo -e "   Billing ID: ${YELLOW}$BILLING_ID${NC}"
echo -e "   Office ID: ${YELLOW}$OFFICE_ID${NC}"
echo -e "   Current Status: ${YELLOW}$CURRENT_STATUS${NC}"
echo -e "   Trial End: ${YELLOW}$TRIAL_END_DATE${NC}"
echo -e "   Scheduled Cancel: ${YELLOW}$SCHEDULED_CANCEL_AT${NC}"

# 状態確認（free_to_early_paymentは特別なステータス）
if [[ ! "$CURRENT_STATUS" =~ ^(early_payment|free|free_to_early_payment|canceling)$ ]]; then
    echo -e "${RED}❌ サポートされていないbilling_status: $CURRENT_STATUS${NC}"
    echo -e "   サポート対象: early_payment, free, free_to_early_payment, canceling"
    exit 1
fi

# 遷移パターンを表示
echo -e "\n${BLUE}テスト対象の遷移:${NC}"
case $CURRENT_STATUS in
    early_payment)
        echo -e "   ${YELLOW}early_payment → active${NC}"
        echo -e "   説明: Trial期間終了時に課金済み → アクティブ化"
        EXPECTED_STATUS="active"
        ;;
    free)
        echo -e "   ${YELLOW}free → past_due${NC}"
        echo -e "   説明: Trial期間終了時に未課金 → 延滞"
        EXPECTED_STATUS="past_due"
        ;;
    free_to_early_payment)
        echo -e "   ${YELLOW}free → early_payment${NC}"
        echo -e "   説明: Trial期間中にサブスク登録 → 早期支払い"
        EXPECTED_STATUS="early_payment"
        ;;
    canceling)
        echo -e "   ${YELLOW}canceling → canceled${NC}"
        echo -e "   説明: scheduled_cancel_at到達 → キャンセル完了"
        EXPECTED_STATUS="canceled"
        ;;
esac

# 2. 既存のTest Clocksを削除
echo -e "\n${GREEN}[2/8] 既存のTest Clocksをクリーンアップ中...${NC}"
docker exec -i keikakun_app-backend-1 python3 << 'EOF' > /dev/null 2>&1
import stripe
from app.core.config import settings

stripe.api_key = settings.STRIPE_SECRET_KEY.get_secret_value()

test_clocks = stripe.test_helpers.TestClock.list(limit=100)
for clock in test_clocks.data:
    try:
        stripe.test_helpers.TestClock.delete(clock.id)
    except:
        pass
EOF
echo -e "${GREEN}✅ クリーンアップ完了${NC}"

# 3. 新しいTest Clock作成
echo -e "\n${GREEN}[3/8] Test Clock作成中...${NC}"
TEST_CLOCK_ID=$(docker exec keikakun_app-backend-1 python3 scripts/stripe_test_clock_manager.py create --name "Status Test $(date +%Y%m%d_%H%M%S)" 2>&1 | grep "Test Clock ID:" | awk '{print $4}')

if [ -z "$TEST_CLOCK_ID" ]; then
    echo -e "${RED}❌ Test Clock作成失敗${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Test Clock作成完了: $TEST_CLOCK_ID${NC}"

# 4. Test Clock付きCustomer作成
echo -e "\n${GREEN}[4/8] Customer作成中...${NC}"
CUSTOMER_ID=$(docker exec keikakun_app-backend-1 python3 -c "
import stripe
from app.core.config import settings
from datetime import datetime

stripe.api_key = settings.STRIPE_SECRET_KEY.get_secret_value()

customer = stripe.Customer.create(
    email=f'test-{datetime.now().strftime(\"%Y%m%d%H%M%S\")}@example.com',
    name='Status Transition Test',
    test_clock='$TEST_CLOCK_ID',
    metadata={'office_id': '$OFFICE_ID', 'billing_id': '$BILLING_ID'}
)

print(customer.id)
")

echo -e "${GREEN}✅ Customer作成完了: $CUSTOMER_ID${NC}"

# 4.5. early_payment、free_to_early_payment、cancelingの場合は支払い方法を追加
if [ "$CURRENT_STATUS" == "early_payment" ] || [ "$CURRENT_STATUS" == "free_to_early_payment" ] || [ "$CURRENT_STATUS" == "canceling" ]; then
    echo -e "\n${GREEN}[4.5/8] 支払い方法設定中（テスト用カード）...${NC}"
    PAYMENT_METHOD_ID=$(docker exec keikakun_app-backend-1 python3 -c "
import stripe
from app.core.config import settings

stripe.api_key = settings.STRIPE_SECRET_KEY.get_secret_value()

# テスト用カードでPaymentMethodを作成
payment_method = stripe.PaymentMethod.create(
    type='card',
    card={
        'token': 'tok_visa'  # Stripeのテスト用トークン（常に成功する）
    }
)

# CustomerにPaymentMethodを関連付け
stripe.PaymentMethod.attach(
    payment_method.id,
    customer='$CUSTOMER_ID'
)

# デフォルトの支払い方法として設定
stripe.Customer.modify(
    '$CUSTOMER_ID',
    invoice_settings={'default_payment_method': payment_method.id}
)

print(payment_method.id)
")
    echo -e "${GREEN}✅ 支払い方法設定完了: $PAYMENT_METHOD_ID${NC}"
fi

# 5. billing_statusに応じてSubscription作成
echo -e "\n${GREEN}[5/8] Subscription作成中（$CURRENT_STATUS用）...${NC}"

if [ "$CURRENT_STATUS" == "early_payment" ]; then
    # Subscription作成（Trial期間を非常に短く設定: 1分後）
    SUBSCRIPTION_ID=$(docker exec keikakun_app-backend-1 python3 -c "
import stripe
from app.core.config import settings
from datetime import datetime, timedelta, timezone

stripe.api_key = settings.STRIPE_SECRET_KEY.get_secret_value()

trial_end = int((datetime.now(timezone.utc) + timedelta(minutes=1)).timestamp())

subscription = stripe.Subscription.create(
    customer='$CUSTOMER_ID',
    items=[{'price': '$STRIPE_PRICE_ID'}],
    trial_end=trial_end
)

print(subscription.id)
")
    echo -e "${GREEN}✅ Subscription作成完了: $SUBSCRIPTION_ID (Trial期間: 1分後)${NC}"

elif [ "$CURRENT_STATUS" == "free_to_early_payment" ]; then
    # Subscription作成（Trial期間を未来に設定: 7日後）
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
")
    echo -e "${GREEN}✅ Subscription作成完了: $SUBSCRIPTION_ID (Trial期間: 7日後)${NC}"

elif [ "$CURRENT_STATUS" == "canceling" ]; then
    # Subscription作成（Trial 7日）
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
")
    echo -e "${GREEN}✅ Subscription作成完了: $SUBSCRIPTION_ID${NC}"

    # cancelingの場合はキャンセル設定
    if [ "$CURRENT_STATUS" == "canceling" ]; then
        echo -e "\n${GREEN}   Subscriptionキャンセル設定中...${NC}"
        docker exec keikakun_app-backend-1 python3 -c "
import stripe
from app.core.config import settings

stripe.api_key = settings.STRIPE_SECRET_KEY.get_secret_value()

stripe.Subscription.modify(
    '$SUBSCRIPTION_ID',
    cancel_at_period_end=True
)
"
        echo -e "${GREEN}   ✅ キャンセル設定完了${NC}"
    fi
else
    # freeの場合はSubscriptionなし
    SUBSCRIPTION_ID=""
    echo -e "${GREEN}✅ Subscription作成スキップ（freeステータス）${NC}"
fi

# 6. Billingレコードを更新
echo -e "\n${GREEN}[6/8] Billingレコード更新中...${NC}"
docker exec -i keikakun_app-backend-1 python3 << EOF
import asyncio
from uuid import UUID
from datetime import datetime, timedelta, timezone
from app.db.session import AsyncSessionLocal
from app import crud
from app.models.enums import BillingStatus

async def update_billing():
    async with AsyncSessionLocal() as db:
        billing = await crud.billing.get(db=db, id=UUID('$BILLING_ID'))

        # 共通更新
        billing.stripe_customer_id = '$CUSTOMER_ID'
        billing.updated_at = datetime.now(timezone.utc)

        # billing_statusに応じた設定
        if '$CURRENT_STATUS' == 'early_payment':
            billing.stripe_subscription_id = '$SUBSCRIPTION_ID'
            billing.billing_status = BillingStatus.early_payment
            billing.trial_end_date = datetime.now(timezone.utc) - timedelta(days=1)
            billing.last_payment_date = datetime.now(timezone.utc) - timedelta(days=7)

        elif '$CURRENT_STATUS' == 'free':
            billing.stripe_subscription_id = None
            billing.billing_status = BillingStatus.free
            billing.trial_end_date = datetime.now(timezone.utc) - timedelta(days=1)
            billing.last_payment_date = None

        elif '$CURRENT_STATUS' == 'free_to_early_payment':
            billing.stripe_subscription_id = None
            billing.billing_status = BillingStatus.free
            billing.trial_end_date = datetime.now(timezone.utc) + timedelta(days=7)
            billing.last_payment_date = None

        elif '$CURRENT_STATUS' == 'canceling':
            billing.stripe_subscription_id = '$SUBSCRIPTION_ID'
            billing.billing_status = BillingStatus.canceling
            billing.scheduled_cancel_at = datetime.now(timezone.utc) - timedelta(days=1)
            billing.trial_end_date = datetime.now(timezone.utc) - timedelta(days=7)

        await db.commit()
        await db.refresh(billing)

        print(f'✅ Billing更新完了')
        print(f'   billing_status: {billing.billing_status.value}')
        print(f'   stripe_customer_id: {billing.stripe_customer_id}')
        print(f'   stripe_subscription_id: {billing.stripe_subscription_id or "None"}')
        if '$CURRENT_STATUS' == 'canceling':
            print(f'   scheduled_cancel_at: {billing.scheduled_cancel_at}')
        else:
            print(f'   trial_end_date: {billing.trial_end_date}')

asyncio.run(update_billing())
EOF

# 7. 時間を進める
if [ "$CURRENT_STATUS" == "early_payment" ]; then
    echo -e "\n${GREEN}[7/8] Test Clockの時間を進めています（1日）...${NC}"
    echo -e "   Trial期間: 1分後 → 1日進めればTrial期間終了"
    docker exec keikakun_app-backend-1 python3 scripts/stripe_test_clock_manager.py advance \
      --clock-id "$TEST_CLOCK_ID" \
      --days 1 > /dev/null 2>&1
    echo -e "${GREEN}✅ 時間を進めました（Trial期間終了）${NC}"
elif [ "$CURRENT_STATUS" == "free_to_early_payment" ]; then
    echo -e "\n${GREEN}[7/8] Test Clockの時間を進める必要なし（Subscription作成直後にWebhook処理）${NC}"
else
    echo -e "\n${GREEN}[7/8] Test Clockの時間を進めています（7日）...${NC}"
    docker exec keikakun_app-backend-1 python3 scripts/stripe_test_clock_manager.py advance \
      --clock-id "$TEST_CLOCK_ID" \
      --days 7 > /dev/null 2>&1
    echo -e "${GREEN}✅ 時間を進めました${NC}"
fi

# 8. Test Clockイベントを手動処理（Webhookサービス層を通す）
if [ "$CURRENT_STATUS" == "early_payment" ]; then
    echo -e "\n${GREEN}[8/9] Webhookイベント処理中（サービス層経由）...${NC}"
    echo -e "   Stripe側の処理完了を待機中（5秒）..."
    sleep 5
    docker exec -i keikakun_app-backend-1 python3 << EOF
import stripe
import asyncio
from uuid import UUID
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app import crud
from app.services.billing_service import BillingService

stripe.api_key = settings.STRIPE_SECRET_KEY.get_secret_value()
billing_service = BillingService()

async def process_webhook_via_service():
    # Stripeから最新のイベントを取得（Trial期間終了時の支払い成功イベント）
    print('   Stripeイベント取得中...')

    # まず、Subscriptionから Customer IDを取得
    subscription = stripe.Subscription.retrieve('$SUBSCRIPTION_ID')
    customer_id = subscription.customer
    print(f'   Customer ID: {customer_id}')

    # Customer IDで invoice.payment_succeeded イベントを検索
    events = stripe.Event.list(limit=50, type='invoice.payment_succeeded')

    target_event = None
    for event in events.data:
        if hasattr(event.data, 'object') and hasattr(event.data.object, 'customer'):
            if event.data.object.customer == customer_id:
                # Subscriptionに関連するInvoiceの最新のイベントを取得
                target_event = event
                print(f'   ✅ イベント発見: {event.type} (ID: {event.id})')
                break

    if not target_event:
        print('   ⚠️  該当イベントが見つかりません')
        return

    # 冪等性チェック回避: 既存のイベントレコードを削除
    async with AsyncSessionLocal() as db:
        from sqlalchemy import text
        result = await db.execute(
            text('DELETE FROM webhook_events WHERE event_id = :event_id'),
            {'event_id': target_event.id}
        )
        await db.commit()
        if result.rowcount > 0:
            print(f'   削除: 既存のwebhook_event ({result.rowcount}件)')

    # Webhookサービス層を通して処理
    async with AsyncSessionLocal() as db:
        # 処理前のステータス確認
        billing_before = await crud.billing.get(db=db, id=UUID('$BILLING_ID'))
        print(f'   処理前: billing_status = {billing_before.billing_status.value}')

        # Webhookサービス層で処理（本番と同じロジック）
        try:
            customer_id = target_event.data.object.customer
            await billing_service.process_payment_succeeded(
                db=db,
                event_id=target_event.id,
                customer_id=customer_id
            )
            print(f'   ✅ Webhookサービス層での処理完了 (invoice.payment_succeeded)')
        except Exception as e:
            print(f'   ❌ エラー: {e}')
            import traceback
            traceback.print_exc()
            raise

    # 処理後のステータス確認（別セッション）
    async with AsyncSessionLocal() as db:
        billing_after = await crud.billing.get(db=db, id=UUID('$BILLING_ID'))
        print(f'   処理後: billing_status = {billing_after.billing_status.value}')
        print(f'   ✅ 遷移結果: {billing_before.billing_status.value} → {billing_after.billing_status.value}')

asyncio.run(process_webhook_via_service())
EOF

    echo -e "${GREEN}✅ Webhookイベント処理完了${NC}"
elif [ "$CURRENT_STATUS" == "free_to_early_payment" ]; then
    echo -e "\n${GREEN}[8/9] Webhookイベント処理中（サービス層経由）...${NC}"
    echo -e "   Stripe側の処理完了を待機中（3秒）..."
    sleep 3
    docker exec -i keikakun_app-backend-1 python3 << EOF
import stripe
import asyncio
from uuid import UUID
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app import crud
from app.services.billing_service import BillingService

stripe.api_key = settings.STRIPE_SECRET_KEY.get_secret_value()
billing_service = BillingService()

async def process_webhook_via_service():
    # Stripeから customer.subscription.created イベントを取得
    print('   Stripeイベント取得中...')

    # Subscriptionから Customer IDを取得
    subscription = stripe.Subscription.retrieve('$SUBSCRIPTION_ID')
    customer_id = subscription.customer
    print(f'   Customer ID: {customer_id}')

    # Customer IDで customer.subscription.created イベントを検索
    events = stripe.Event.list(limit=50, type='customer.subscription.created')

    target_event = None
    for event in events.data:
        if hasattr(event.data, 'object') and hasattr(event.data.object, 'customer'):
            if event.data.object.customer == customer_id:
                target_event = event
                print(f'   ✅ イベント発見: {event.type} (ID: {event.id})')
                break

    if not target_event:
        print('   ⚠️  該当イベントが見つかりません')
        return

    # 冪等性チェック回避: 既存のイベントレコードを削除
    async with AsyncSessionLocal() as db:
        from sqlalchemy import text
        result = await db.execute(
            text('DELETE FROM webhook_events WHERE event_id = :event_id'),
            {'event_id': target_event.id}
        )
        await db.commit()
        if result.rowcount > 0:
            print(f'   削除: 既存のwebhook_event ({result.rowcount}件)')

    # Webhookサービス層を通して処理
    async with AsyncSessionLocal() as db:
        # 処理前のステータス確認
        billing_before = await crud.billing.get(db=db, id=UUID('$BILLING_ID'))
        print(f'   処理前: billing_status = {billing_before.billing_status.value}')

        # Webhookサービス層で処理（本番と同じロジック）
        try:
            customer_id = target_event.data.object.customer
            subscription_id = target_event.data.object.id
            await billing_service.process_subscription_created(
                db=db,
                event_id=target_event.id,
                customer_id=customer_id,
                subscription_id=subscription_id
            )
            print(f'   ✅ Webhookサービス層での処理完了 (customer.subscription.created)')
        except Exception as e:
            print(f'   ❌ エラー: {e}')
            import traceback
            traceback.print_exc()
            raise

    # 処理後のステータス確認（別セッション）
    async with AsyncSessionLocal() as db:
        billing_after = await crud.billing.get(db=db, id=UUID('$BILLING_ID'))
        print(f'   処理後: billing_status = {billing_after.billing_status.value}')
        print(f'   ✅ 遷移結果: {billing_before.billing_status.value} → {billing_after.billing_status.value}')

asyncio.run(process_webhook_via_service())
EOF

    echo -e "${GREEN}✅ Webhookイベント処理完了${NC}"
elif [ "$CURRENT_STATUS" == "free" ]; then
    echo -e "\n${GREEN}[8/9] バッチ処理実行中（free → past_due）...${NC}"
    docker exec -i keikakun_app-backend-1 python3 << EOF
import asyncio
from uuid import UUID
from app.db.session import AsyncSessionLocal
from app import crud
from app.tasks.billing_check import check_trial_expiration

async def run_batch_check():
    async with AsyncSessionLocal() as db:
        # 処理前のステータス確認
        billing_before = await crud.billing.get(db=db, id=UUID('$BILLING_ID'))
        print(f'   処理前: billing_status = {billing_before.billing_status.value}')
        print(f'   trial_end_date = {billing_before.trial_end_date}')

        # バッチ処理実行（free → past_due）
        updated_count = await check_trial_expiration(db=db, dry_run=False)
        print(f'   ✅ バッチ処理完了: {updated_count}件更新')

    # 処理後のステータス確認（別セッション）
    async with AsyncSessionLocal() as db:
        billing_after = await crud.billing.get(db=db, id=UUID('$BILLING_ID'))
        print(f'   処理後: billing_status = {billing_after.billing_status.value}')
        print(f'   ✅ 遷移結果: {billing_before.billing_status.value} → {billing_after.billing_status.value}')

asyncio.run(run_batch_check())
EOF
    echo -e "${GREEN}✅ バッチ処理完了${NC}"
elif [ "$CURRENT_STATUS" == "canceling" ]; then
    echo -e "\n${GREEN}[8/9] バッチ処理実行中（canceling → canceled）...${NC}"
    docker exec -i keikakun_app-backend-1 python3 << EOF
import asyncio
from uuid import UUID
from app.db.session import AsyncSessionLocal
from app import crud
from app.tasks.billing_check import check_scheduled_cancellation

async def run_batch_check():
    async with AsyncSessionLocal() as db:
        # 処理前のステータス確認
        billing_before = await crud.billing.get(db=db, id=UUID('$BILLING_ID'))
        print(f'   処理前: billing_status = {billing_before.billing_status.value}')
        print(f'   scheduled_cancel_at = {billing_before.scheduled_cancel_at}')

        # バッチ処理実行（canceling → canceled）
        updated_count = await check_scheduled_cancellation(db=db, dry_run=False)
        print(f'   ✅ バッチ処理完了: {updated_count}件更新')

    # 処理後のステータス確認（別セッション）
    async with AsyncSessionLocal() as db:
        billing_after = await crud.billing.get(db=db, id=UUID('$BILLING_ID'))
        print(f'   処理後: billing_status = {billing_after.billing_status.value}')
        print(f'   ✅ 遷移結果: {billing_before.billing_status.value} → {billing_after.billing_status.value}')

asyncio.run(run_batch_check())
EOF
    echo -e "${GREEN}✅ バッチ処理完了${NC}"
fi

# 9. 結果表示
echo -e "\n${BLUE}==============================================================================${NC}"
echo -e "${BLUE}テスト完了${NC}"
echo -e "${BLUE}==============================================================================${NC}"
echo ""
echo -e "${YELLOW}実行された遷移:${NC}"
echo -e "   $CURRENT_STATUS → $EXPECTED_STATUS"
echo ""
echo -e "${GREEN}次のステップ:${NC}"
echo ""
echo -e "${BLUE}1. Webhookログを確認:${NC}"
echo -e "   docker logs keikakun_app-backend-1 --tail 200 | grep -i webhook"
echo ""
echo -e "${BLUE}2. Billing状態を確認:${NC}"
echo -e "   docker exec keikakun_app-backend-1 python3 scripts/batch_trigger_setup.py list | grep -A 6 \"$BILLING_ID\""
echo ""
echo -e "   または、SQLで直接確認:"
echo -e "   docker exec -it keikakun_app-backend-1 psql \$DATABASE_URL -c \"SELECT id, billing_status, trial_end_date, scheduled_cancel_at FROM billings WHERE id = '$BILLING_ID';\""
echo ""
echo -e "${BLUE}3. アプリ上で確認:${NC}"
echo -e "   フロントエンドの管理画面でbilling_statusが ${YELLOW}$EXPECTED_STATUS${NC} に変わっているか確認"
echo ""
echo -e "${BLUE}4. クリーンアップ（テスト完了後）:${NC}"
echo -e "   ./k_back/scripts/cleanup_all_test_clocks.sh"
echo ""
echo -e "${BLUE}==============================================================================${NC}"
echo -e "${GREEN}✅ セットアップ完了！Webhookの発火を待ってください（数秒〜数分）${NC}"
echo -e "${BLUE}==============================================================================${NC}"

# IDを保存
mkdir -p /tmp/test_clocks
echo "$TEST_CLOCK_ID" > /tmp/test_clocks/last_test_clock_id.txt
echo "$CUSTOMER_ID" > /tmp/test_clocks/last_customer_id.txt
echo "$BILLING_ID" > /tmp/test_clocks/last_billing_id.txt
