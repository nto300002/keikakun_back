"""
Billing Service層

課金関連のビジネスロジックとトランザクション管理を担当。

責務:
- Stripe Checkout Session作成処理
- Webhook処理のトランザクション管理
- 複数のCRUD操作を1つのトランザクションでまとめる
- データ整合性の保証
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from uuid import UUID

import stripe
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app import crud
from app.models.enums import BillingStatus
from app.messages import ja

logger = logging.getLogger(__name__)


class BillingService:
    """
    課金サービス層

    複数のCRUD操作を1つのトランザクションで管理し、
    データ整合性を保証します。
    """

    async def create_checkout_session_with_customer(
        self,
        db: AsyncSession,
        *,
        billing_id: UUID,
        office_id: UUID,
        office_name: str,
        user_email: str,
        user_id: UUID,
        trial_end_date: datetime,
        stripe_secret_key: str,
        stripe_price_id: str,
        frontend_url: str
    ) -> Dict[str, str]:
        """
        Stripe Checkout Sessionを作成（Customer作成を含む）

        全ての操作を1つのトランザクションで実行し、MissingGreenletエラーを回避。

        Args:
            db: データベースセッション
            billing_id: Billing ID
            office_id: 事務所ID
            office_name: 事務所名
            user_email: ユーザーメールアドレス
            user_id: ユーザーID
            trial_end_date: トライアル終了日
            stripe_secret_key: Stripe Secret Key
            stripe_price_id: Stripe Price ID
            frontend_url: フロントエンドURL

        Returns:
            {"session_id": "...", "url": "..."}

        Raises:
            HTTPException: Stripe API呼び出しエラー
        """
        try:
            # 1. Stripe APIでCustomerを作成（DB操作の前に実行）
            stripe.api_key = stripe_secret_key
            customer = stripe.Customer.create(
                email=user_email,
                name=office_name,
                metadata={
                    "office_id": str(office_id),
                    "staff_id": str(user_id)
                }
            )
            customer_id = customer.id

            logger.info(f"Stripe Customer created: {customer_id}")

            # 2. DB更新（auto_commit=Falseで遅延commit）
            await crud.billing.update_stripe_customer(
                db=db,
                billing_id=billing_id,
                stripe_customer_id=customer_id,
                auto_commit=False  # ← 重要: commitを遅延
            )

            # 3. Checkout Sessionを作成（Stripe API）
            checkout_session = stripe.checkout.Session.create(
                mode='subscription',
                customer=customer_id,
                line_items=[{
                    'price': stripe_price_id,
                    'quantity': 1
                }],
                subscription_data={
                    'trial_end': int(trial_end_date.timestamp()),
                    'metadata': {
                        'office_id': str(office_id),
                        'office_name': office_name,
                        'created_by_user_id': str(user_id),
                    }
                },
                automatic_tax={'enabled': True},
                customer_update={'address': 'auto'},
                billing_address_collection='required',
                payment_method_types=['card'],
                success_url=f"{frontend_url}/admin?tab=plan&success=true",
                cancel_url=f"{frontend_url}/admin?tab=plan&canceled=true",
            )

            logger.info(f"Stripe Checkout Session created: {checkout_session.id}")

            # 4. 全ての操作が成功した後、1回だけcommit
            await db.commit()

            return {
                "session_id": checkout_session.id,
                "url": checkout_session.url
            }

        except stripe.error.StripeError as e:
            # Stripeエラー時はロールバック
            await db.rollback()
            logger.error(f"Stripe API error: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=ja.BILLING_CHECKOUT_SESSION_FAILED
            )
        except Exception as e:
            # その他のエラー時もロールバック
            await db.rollback()
            logger.error(f"Checkout session creation error: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=ja.BILLING_CHECKOUT_SESSION_FAILED
            )

    async def process_payment_succeeded(
        self,
        db: AsyncSession,
        *,
        event_id: str,
        customer_id: str
    ) -> None:
        """
        支払い成功Webhookを処理

        全ての操作を1つのトランザクションで実行し、データ整合性を保証。

        Args:
            db: データベースセッション
            event_id: Stripe Event ID
            customer_id: Stripe Customer ID

        Raises:
            ValueError: Billing情報が見つからない場合
            Exception: その他のエラー
        """
        try:
            # Session内のオブジェクトを期限切れにして最新データを取得
            db.expire_all()

            # Billing情報を取得
            billing = await crud.billing.get_by_stripe_customer_id(
                db=db,
                stripe_customer_id=customer_id
            )

            if not billing:
                raise ValueError(f"Billing not found for customer {customer_id}")

            # 1. 支払い記録を更新（auto_commit=False）
            await crud.billing.record_payment(
                db=db,
                billing_id=billing.id,
                auto_commit=False
            )

            # 2. Webhookイベント記録（auto_commit=False）
            await crud.webhook_event.create_event_record(
                db=db,
                event_id=event_id,
                event_type='invoice.payment_succeeded',
                source='stripe',
                billing_id=billing.id,
                office_id=billing.office_id,
                payload={"customer_id": customer_id},
                status='success',
                auto_commit=False
            )

            # 3. 監査ログ記録（auto_commit=False）
            await crud.audit_log.create_log(
                db=db,
                actor_id=None,
                actor_role="system",
                action="billing.payment_succeeded",
                target_type="billing",
                target_id=billing.id,
                office_id=billing.office_id,
                details={
                    "event_id": event_id,
                    "event_type": "invoice.payment_succeeded",
                    "source": "stripe_webhook"
                },
                auto_commit=False
            )

            # 4. 全ての操作が成功した後、1回だけcommit
            await db.commit()

            logger.info(f"[Webhook:{event_id}] Payment succeeded for billing_id={billing.id}")

        except Exception as e:
            # エラー時は全てロールバック
            await db.rollback()
            logger.error(f"[Webhook:{event_id}] Payment processing error: {e}")
            raise

    async def process_payment_failed(
        self,
        db: AsyncSession,
        *,
        event_id: str,
        customer_id: str
    ) -> None:
        """
        支払い失敗Webhookを処理

        Args:
            db: データベースセッション
            event_id: Stripe Event ID
            customer_id: Stripe Customer ID
        """
        try:
            # Session内のオブジェクトを期限切れにして最新データを取得
            db.expire_all()

            billing = await crud.billing.get_by_stripe_customer_id(
                db=db,
                stripe_customer_id=customer_id
            )

            if not billing:
                raise ValueError(f"Billing not found for customer {customer_id}")

            # 1. ステータス更新（auto_commit=False）
            await crud.billing.update_status(
                db=db,
                billing_id=billing.id,
                status=BillingStatus.past_due,
                auto_commit=False
            )

            # 2. Webhookイベント記録（auto_commit=False）
            await crud.webhook_event.create_event_record(
                db=db,
                event_id=event_id,
                event_type='invoice.payment_failed',
                source='stripe',
                billing_id=billing.id,
                office_id=billing.office_id,
                payload={"customer_id": customer_id},
                status='success',
                auto_commit=False
            )

            # 3. 監査ログ記録（auto_commit=False）
            await crud.audit_log.create_log(
                db=db,
                actor_id=None,
                actor_role="system",
                action="billing.payment_failed",
                target_type="billing",
                target_id=billing.id,
                office_id=billing.office_id,
                details={
                    "event_id": event_id,
                    "event_type": "invoice.payment_failed",
                    "source": "stripe_webhook"
                },
                auto_commit=False
            )

            # 4. commit
            await db.commit()

            logger.warning(f"[Webhook:{event_id}] Payment failed for billing_id={billing.id}")

        except Exception as e:
            await db.rollback()
            logger.error(f"[Webhook:{event_id}] Payment failed processing error: {e}")
            raise

    async def process_subscription_created(
        self,
        db: AsyncSession,
        *,
        event_id: str,
        subscription_data: Dict[str, Any]
    ) -> None:
        """
        サブスクリプション作成Webhookを処理

        Args:
            db: データベースセッション
            event_id: Stripe Event ID
            subscription_data: Subscription データ
        """
        try:
            # customer_idを取得（必須）
            customer_id = subscription_data.get('customer')
            if not customer_id:
                logger.error(f"[Webhook:{event_id}] No customer_id in subscription data")
                return

            # 1. 最新のBilling情報を取得
            # Session内のオブジェクトを期限切れにして最新データを取得
            db.expire_all()
            billing = await crud.billing.get_by_stripe_customer_id(
                db=db,
                stripe_customer_id=customer_id
            )

            if not billing:
                raise ValueError(f"Billing not found for customer {customer_id}")

            # 2. Subscription情報を更新（auto_commit=False）
            billing = await crud.billing.update_stripe_subscription(
                db=db,
                billing_id=billing.id,
                stripe_subscription_id=subscription_data['id'],
                subscription_start_date=datetime.now(timezone.utc),
                auto_commit=False
            )

            # 3. ステータス判定: 無料期間中 → early_payment、期限切れ → active
            now = datetime.now(timezone.utc)

            is_trial_active = (
                billing.billing_status == BillingStatus.free and
                billing.trial_end_date and
                billing.trial_end_date > now
            )

            new_status = BillingStatus.early_payment if is_trial_active else BillingStatus.active
            await crud.billing.update_status(
                db=db,
                billing_id=billing.id,
                status=new_status,
                auto_commit=False
            )

            # 4. Webhookイベント記録（auto_commit=False）
            await crud.webhook_event.create_event_record(
                db=db,
                event_id=event_id,
                event_type='customer.subscription.created',
                source='stripe',
                billing_id=billing.id,
                office_id=billing.office_id,
                payload=subscription_data,
                status='success',
                auto_commit=False
            )

            # 5. 監査ログ記録（auto_commit=False）
            await crud.audit_log.create_log(
                db=db,
                actor_id=None,
                actor_role="system",
                action="billing.subscription_created",
                target_type="billing",
                target_id=billing.id,
                office_id=billing.office_id,
                details={
                    "event_id": event_id,
                    "event_type": "customer.subscription.created",
                    "source": "stripe_webhook"
                },
                auto_commit=False
            )

            # 6. commit
            await db.commit()

            logger.info(
                f"[Webhook:{event_id}] Subscription created for customer {customer_id}, "
                f"office_id={billing.office_id}, status={new_status.value}, trial_active={is_trial_active}"
            )

        except Exception as e:
            await db.rollback()
            logger.error(f"[Webhook:{event_id}] Subscription creation processing error: {e}")
            raise

    async def process_subscription_updated(
        self,
        db: AsyncSession,
        *,
        event_id: str,
        subscription_data: Dict[str, Any]
    ) -> None:
        """
        サブスクリプション更新Webhookを処理

        主な用途:
        - cancel_at_period_end=trueの場合、billing_status → canceling
        - キャンセル予定日を記録

        Args:
            db: データベースセッション
            event_id: Stripe Event ID
            subscription_data: Subscription object from Stripe
        """
        try:
            # Session内のオブジェクトを期限切れにして最新データを取得
            db.expire_all()

            customer_id = subscription_data.get('customer')
            cancel_at_period_end = subscription_data.get('cancel_at_period_end', False)
            cancel_at = subscription_data.get('cancel_at')

            billing = await crud.billing.get_by_stripe_customer_id(
                db=db,
                stripe_customer_id=customer_id
            )

            if not billing:
                logger.warning(f"[Webhook:{event_id}] Billing not found for customer {customer_id}")
                return

            # cancel_at_period_end=trueの場合、キャンセル予定状態に
            if cancel_at_period_end:
                await crud.billing.update_status(
                    db=db,
                    billing_id=billing.id,
                    status=BillingStatus.canceling,
                    auto_commit=False
                )

                logger.info(f"[Webhook:{event_id}] Subscription set to cancel at period end for billing_id={billing.id}")

            # cancel_at_period_end=falseでcanceling状態の場合、キャンセル取り消し
            elif not cancel_at_period_end and billing.billing_status == BillingStatus.canceling:
                await crud.billing.update_status(
                    db=db,
                    billing_id=billing.id,
                    status=BillingStatus.active,
                    auto_commit=False
                )

                logger.info(f"[Webhook:{event_id}] Subscription cancellation reverted for billing_id={billing.id}")

            # Webhookイベント記録
            await crud.webhook_event.create_event_record(
                db=db,
                event_id=event_id,
                event_type='customer.subscription.updated',
                source='stripe',
                billing_id=billing.id,
                office_id=billing.office_id,
                payload={
                    "customer_id": customer_id,
                    "cancel_at_period_end": cancel_at_period_end,
                    "cancel_at": cancel_at
                },
                status='success',
                auto_commit=False
            )

            # 監査ログ記録
            await crud.audit_log.create_log(
                db=db,
                actor_id=None,
                actor_role="system",
                action="billing.subscription_updated",
                target_type="billing",
                target_id=billing.id,
                office_id=billing.office_id,
                details={
                    "event_id": event_id,
                    "event_type": "customer.subscription.updated",
                    "cancel_at_period_end": cancel_at_period_end,
                    "source": "stripe_webhook"
                },
                auto_commit=False
            )

            # commit
            await db.commit()

        except Exception as e:
            await db.rollback()
            logger.error(f"[Webhook:{event_id}] Subscription update processing error: {e}")
            raise

    async def process_subscription_deleted(
        self,
        db: AsyncSession,
        *,
        event_id: str,
        customer_id: str
    ) -> None:
        """
        サブスクリプション削除（キャンセル）Webhookを処理

        Args:
            db: データベースセッション
            event_id: Stripe Event ID
            customer_id: Stripe Customer ID
        """
        try:
            # Session内のオブジェクトを期限切れにして最新データを取得
            db.expire_all()

            billing = await crud.billing.get_by_stripe_customer_id(
                db=db,
                stripe_customer_id=customer_id
            )

            if not billing:
                raise ValueError(f"Billing not found for customer {customer_id}")

            # 1. ステータス更新（auto_commit=False）
            await crud.billing.update_status(
                db=db,
                billing_id=billing.id,
                status=BillingStatus.canceled,
                auto_commit=False
            )

            # 2. Webhookイベント記録（auto_commit=False）
            await crud.webhook_event.create_event_record(
                db=db,
                event_id=event_id,
                event_type='customer.subscription.deleted',
                source='stripe',
                billing_id=billing.id,
                office_id=billing.office_id,
                payload={"customer_id": customer_id},
                status='success',
                auto_commit=False
            )

            # 3. 監査ログ記録（auto_commit=False）
            await crud.audit_log.create_log(
                db=db,
                actor_id=None,
                actor_role="system",
                action="billing.subscription_canceled",
                target_type="billing",
                target_id=billing.id,
                office_id=billing.office_id,
                details={
                    "event_id": event_id,
                    "event_type": "customer.subscription.deleted",
                    "source": "stripe_webhook"
                },
                auto_commit=False
            )

            # 4. commit
            await db.commit()

            logger.info(f"[Webhook:{event_id}] Subscription canceled for billing_id={billing.id}")

        except Exception as e:
            await db.rollback()
            logger.error(f"[Webhook:{event_id}] Subscription deletion processing error: {e}")
            raise
