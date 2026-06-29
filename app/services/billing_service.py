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
from datetime import datetime, timedelta, timezone
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

    def _normalize_trial_end_date(self, trial_end_date: Optional[datetime]) -> Optional[datetime]:
        if not trial_end_date:
            return None

        if trial_end_date.tzinfo is not None:
            return trial_end_date

        return trial_end_date.replace(tzinfo=timezone.utc)

    async def correct_expired_free_billing_before_checkout(
        self,
        db: AsyncSession,
        *,
        billing_id: UUID,
        office_id: UUID,
        trial_end_date: Optional[datetime],
        auto_commit: bool = False
    ) -> Optional[datetime]:
        """
        期限切れfreeが残っている場合、Checkout前にtrial_expiredへ補正する。

        Returns:
            timezone-awareなtrial_end_date。trial_end_dateがない場合はNone。
        """
        now = datetime.now(timezone.utc)
        normalized_trial_end_date = self._normalize_trial_end_date(trial_end_date)

        billing = await crud.billing.get(db=db, id=billing_id)
        if (
            billing
            and billing.billing_status == BillingStatus.free
            and normalized_trial_end_date
            and normalized_trial_end_date < now
        ):
            await crud.billing.update_status(
                db=db,
                billing_id=billing_id,
                status=BillingStatus.trial_expired,
                auto_commit=auto_commit
            )
            logger.info(
                "Expired free billing corrected before checkout: "
                f"billing_id={billing_id}, office_id={office_id}"
            )

        return normalized_trial_end_date

    def _build_checkout_subscription_data(
        self,
        *,
        office_id: UUID,
        office_name: str,
        user_id: UUID,
        trial_end_date: Optional[datetime],
        now: datetime
    ) -> Dict[str, Any]:
        subscription_data: Dict[str, Any] = {
            'metadata': {
                'office_id': str(office_id),
                'office_name': office_name,
                'created_by_user_id': str(user_id),
            }
        }

        if trial_end_date and trial_end_date > now:
            subscription_data['trial_end'] = int(trial_end_date.timestamp())

        return subscription_data

    def _log_checkout_error(
        self,
        *,
        error: Exception,
        checkout_route: str,
        billing_id: UUID,
        office_id: UUID,
        billing_status: Optional[BillingStatus],
        trial_end_date: Optional[datetime],
        has_stripe_customer_id: bool
    ) -> None:
        logger.error(
            "Checkout session creation failed: "
            f"stripe_error_type={type(error).__name__}, "
            f"checkout_route={checkout_route}, "
            f"billing_id={billing_id}, "
            f"office_id={office_id}, "
            f"billing_status={billing_status.value if billing_status else None}, "
            f"trial_end_date={trial_end_date.isoformat() if trial_end_date else None}, "
            f"has_stripe_customer_id={has_stripe_customer_id}"
        )

    async def create_checkout_session_for_existing_customer(
        self,
        db: AsyncSession,
        *,
        billing_id: UUID,
        office_id: UUID,
        office_name: str,
        user_id: UUID,
        stripe_customer_id: str,
        trial_end_date: Optional[datetime],
        stripe_secret_key: str,
        stripe_price_id: str,
        frontend_url: str
    ) -> Dict[str, str]:
        """
        既存Stripe CustomerでCheckout Sessionを作成する。
        """
        billing_status: Optional[BillingStatus] = None
        normalized_trial_end_date: Optional[datetime] = None
        try:
            billing = await crud.billing.get(db=db, id=billing_id)
            if billing:
                billing_status = billing.billing_status

            now = datetime.now(timezone.utc)
            normalized_trial_end_date = await self.correct_expired_free_billing_before_checkout(
                db=db,
                billing_id=billing_id,
                office_id=office_id,
                trial_end_date=trial_end_date,
                auto_commit=False
            )

            stripe.api_key = stripe_secret_key
            checkout_session = stripe.checkout.Session.create(
                mode='subscription',
                customer=stripe_customer_id,
                line_items=[{
                    'price': stripe_price_id,
                    'quantity': 1
                }],
                subscription_data=self._build_checkout_subscription_data(
                    office_id=office_id,
                    office_name=office_name,
                    user_id=user_id,
                    trial_end_date=normalized_trial_end_date,
                    now=now
                ),
                automatic_tax={'enabled': True},
                customer_update={'address': 'auto'},
                billing_address_collection='required',
                payment_method_types=['card'],
                success_url=f"{frontend_url}/admin?tab=plan&success=true",
                cancel_url=f"{frontend_url}/admin?tab=plan&canceled=true",
            )

            await db.commit()

            return {
                "session_id": checkout_session.id,
                "url": checkout_session.url
            }

        except stripe.error.StripeError as e:
            await db.rollback()
            self._log_checkout_error(
                error=e,
                checkout_route="existing_customer",
                billing_id=billing_id,
                office_id=office_id,
                billing_status=billing_status,
                trial_end_date=normalized_trial_end_date,
                has_stripe_customer_id=True
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=ja.BILLING_CHECKOUT_SESSION_FAILED
            )
        except Exception as e:
            await db.rollback()
            self._log_checkout_error(
                error=e,
                checkout_route="existing_customer",
                billing_id=billing_id,
                office_id=office_id,
                billing_status=billing_status,
                trial_end_date=normalized_trial_end_date,
                has_stripe_customer_id=True
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=ja.BILLING_CHECKOUT_SESSION_FAILED
            )

    async def create_checkout_session_with_customer(
        self,
        db: AsyncSession,
        *,
        billing_id: UUID,
        office_id: UUID,
        office_name: str,
        user_email: str,
        user_id: UUID,
        trial_end_date: Optional[datetime],
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
        billing_status: Optional[BillingStatus] = None
        normalized_trial_end_date: Optional[datetime] = None
        customer_id: Optional[str] = None
        try:
            billing = await crud.billing.get(db=db, id=billing_id)
            if billing:
                billing_status = billing.billing_status

            now = datetime.now(timezone.utc)
            normalized_trial_end_date = await self.correct_expired_free_billing_before_checkout(
                db=db,
                billing_id=billing_id,
                office_id=office_id,
                trial_end_date=trial_end_date,
                auto_commit=False
            )

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
                subscription_data=self._build_checkout_subscription_data(
                    office_id=office_id,
                    office_name=office_name,
                    user_id=user_id,
                    trial_end_date=normalized_trial_end_date,
                    now=now
                ),
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
            self._log_checkout_error(
                error=e,
                checkout_route="new_customer",
                billing_id=billing_id,
                office_id=office_id,
                billing_status=billing_status,
                trial_end_date=normalized_trial_end_date,
                has_stripe_customer_id=customer_id is not None
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=ja.BILLING_CHECKOUT_SESSION_FAILED
            )
        except Exception as e:
            # その他のエラー時もロールバック
            await db.rollback()
            self._log_checkout_error(
                error=e,
                checkout_route="new_customer",
                billing_id=billing_id,
                office_id=office_id,
                billing_status=billing_status,
                trial_end_date=normalized_trial_end_date,
                has_stripe_customer_id=customer_id is not None
            )
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
                logger.info(f"[Webhook:{event_id}] Billing not found for customer {customer_id} - skipping (possibly test data)")

                await crud.webhook_event.create_event_record(
                    db=db,
                    event_id=event_id,
                    event_type='invoice.payment_succeeded',
                    source='stripe',
                    billing_id=None,
                    office_id=None,
                    payload={"customer_id": customer_id, "note": "Customer not found in database"},
                    status='skipped',
                    auto_commit=True
                )
                return

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
                logger.info(f"[Webhook:{event_id}] Billing not found for customer {customer_id} - skipping (possibly test data)")

                await crud.webhook_event.create_event_record(
                    db=db,
                    event_id=event_id,
                    event_type='invoice.payment_failed',
                    source='stripe',
                    billing_id=None,
                    office_id=None,
                    payload={"customer_id": customer_id, "note": "Customer not found in database"},
                    status='skipped',
                    auto_commit=True
                )
                return

            # 1. ステータス更新（auto_commit=False）
            now = datetime.now(timezone.utc)
            trial_end_date = self._normalize_trial_end_date(billing.trial_end_date)
            is_trial_active = bool(trial_end_date and trial_end_date > now)

            if not is_trial_active:
                await crud.billing.update_status(
                    db=db,
                    billing_id=billing.id,
                    status=BillingStatus.payment_failed,
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

            previous_status = billing.billing_status
            logger.info(
                "[Webhook:%s] Subscription created payload: customer_id=%s, "
                "subscription_id=%s, stripe_status=%s, cancel_at_period_end=%s, "
                "cancel_at=%s, trial_start=%s, trial_end=%s, latest_invoice=%s, "
                "billing_id=%s, office_id=%s, previous_billing_status=%s, "
                "db_trial_end_date=%s, db_stripe_subscription_id=%s",
                event_id,
                customer_id,
                subscription_data.get('id'),
                subscription_data.get('status'),
                subscription_data.get('cancel_at_period_end'),
                subscription_data.get('cancel_at'),
                subscription_data.get('trial_start'),
                subscription_data.get('trial_end'),
                subscription_data.get('latest_invoice'),
                billing.id,
                billing.office_id,
                previous_status.value if previous_status else None,
                billing.trial_end_date.isoformat() if billing.trial_end_date else None,
                billing.stripe_subscription_id,
            )

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
            trial_end_date = self._normalize_trial_end_date(billing.trial_end_date)

            is_trial_active = (
                trial_end_date and
                trial_end_date > now
            )

            new_status = BillingStatus.early_payment if is_trial_active else BillingStatus.active
            logger.info(
                "[Webhook:%s] Subscription created status decision: billing_id=%s, "
                "previous_status=%s, new_status=%s, db_trial_end_date=%s, "
                "normalized_trial_end_date=%s, now=%s, is_trial_active=%s",
                event_id,
                billing.id,
                previous_status.value if previous_status else None,
                new_status.value,
                billing.trial_end_date.isoformat() if billing.trial_end_date else None,
                trial_end_date.isoformat() if trial_end_date else None,
                now.isoformat(),
                is_trial_active,
            )
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
            logger.exception(
                "[Webhook:%s] Subscription creation processing error: "
                "customer_id=%s, subscription_id=%s, stripe_status=%s, "
                "cancel_at_period_end=%s, cancel_at=%s, latest_invoice=%s",
                event_id,
                subscription_data.get('customer'),
                subscription_data.get('id'),
                subscription_data.get('status'),
                subscription_data.get('cancel_at_period_end'),
                subscription_data.get('cancel_at'),
                subscription_data.get('latest_invoice'),
            )
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
            subscription_status = subscription_data.get('status')
            subscription_id = subscription_data.get('id')

            # デバッグログ: イベントの詳細を記録
            logger.info(
                "[Webhook:%s] Subscription updated payload: customer_id=%s, "
                "subscription_id=%s, stripe_status=%s, cancel_at_period_end=%s, "
                "cancel_at=%s, canceled_at=%s, cancellation_reason=%s, "
                "trial_start=%s, trial_end=%s, current_period_end=%s, latest_invoice=%s",
                event_id,
                customer_id,
                subscription_id,
                subscription_status,
                cancel_at_period_end,
                cancel_at,
                subscription_data.get('canceled_at'),
                subscription_data.get('cancellation_details', {}).get('reason')
                if isinstance(subscription_data.get('cancellation_details'), dict)
                else None,
                subscription_data.get('trial_start'),
                subscription_data.get('trial_end'),
                subscription_data.get('current_period_end'),
                subscription_data.get('latest_invoice'),
            )

            billing = await crud.billing.get_by_stripe_customer_id(
                db=db,
                stripe_customer_id=customer_id
            )

            if not billing:
                logger.info(f"[Webhook:{event_id}] Billing not found for customer {customer_id} - skipping (possibly test data)")

                await crud.webhook_event.create_event_record(
                    db=db,
                    event_id=event_id,
                    event_type='customer.subscription.updated',
                    source='stripe',
                    billing_id=None,
                    office_id=None,
                    payload={
                        "customer_id": customer_id,
                        "cancel_at_period_end": cancel_at_period_end,
                        "cancel_at": cancel_at,
                        "note": "Customer not found in database"
                    },
                    status='skipped',
                    auto_commit=True
                )
                return

            previous_status = billing.billing_status
            logger.info(
                "[Webhook:%s] Current billing before subscription update: "
                "billing_id=%s, office_id=%s, billing_status=%s, "
                "db_trial_end_date=%s, db_subscription_start_date=%s, "
                "db_last_payment_date=%s, db_scheduled_cancel_at=%s, "
                "db_stripe_subscription_id=%s",
                event_id,
                billing.id,
                billing.office_id,
                previous_status.value if previous_status else None,
                billing.trial_end_date.isoformat() if billing.trial_end_date else None,
                billing.subscription_start_date.isoformat() if billing.subscription_start_date else None,
                billing.last_payment_date.isoformat() if billing.last_payment_date else None,
                billing.scheduled_cancel_at.isoformat() if billing.scheduled_cancel_at else None,
                billing.stripe_subscription_id,
            )

            now = datetime.now(timezone.utc)
            trial_end_date = self._normalize_trial_end_date(billing.trial_end_date)
            is_stale_unpaid_expired_trial = (
                billing.billing_status in [BillingStatus.free, BillingStatus.canceling]
                and trial_end_date is not None
                and trial_end_date < now
                and billing.last_payment_date is None
                and billing.subscription_start_date is None
            )
            should_cancel_trial_expired_immediately = (
                (billing.billing_status == BillingStatus.trial_expired or is_stale_unpaid_expired_trial)
                and (cancel_at_period_end or cancel_at)
            )
            logger.info(
                "[Webhook:%s] Subscription update status decision flags: billing_id=%s, "
                "previous_status=%s, stripe_status=%s, is_stale_unpaid_expired_trial=%s, "
                "should_cancel_trial_expired_immediately=%s, cancel_at_period_end=%s, "
                "cancel_at=%s, normalized_trial_end_date=%s, now=%s",
                event_id,
                billing.id,
                previous_status.value if previous_status else None,
                subscription_status,
                is_stale_unpaid_expired_trial,
                should_cancel_trial_expired_immediately,
                cancel_at_period_end,
                cancel_at,
                trial_end_date.isoformat() if trial_end_date else None,
                now.isoformat(),
            )

            # スケジュールされたキャンセル日時を保存
            if should_cancel_trial_expired_immediately:
                await crud.billing.update(
                    db=db,
                    db_obj=billing,
                    obj_in={
                        "billing_status": BillingStatus.canceled,
                        "scheduled_cancel_at": None,
                    },
                    auto_commit=False
                )
                logger.info(
                    f"[Webhook:{event_id}] Trial expired subscription canceled immediately "
                    f"for billing_id={billing.id}, previous_status={previous_status.value if previous_status else None}, "
                    f"reason=cancel_signal_on_trial_expired_or_stale_unpaid_expired_trial"
                )
            elif cancel_at:
                cancel_at_datetime = datetime.fromtimestamp(cancel_at, tz=timezone.utc)
                await crud.billing.update(
                    db=db,
                    db_obj=billing,
                    obj_in={"scheduled_cancel_at": cancel_at_datetime},
                    auto_commit=False
                )
                logger.info(f"[Webhook:{event_id}] Scheduled cancellation set for {cancel_at_datetime}")
            elif billing.scheduled_cancel_at is not None:
                await crud.billing.update(
                    db=db,
                    db_obj=billing,
                    obj_in={"scheduled_cancel_at": None},
                    auto_commit=False
                )
                logger.info(f"[Webhook:{event_id}] Scheduled cancellation cleared")

            # cancel_at_period_end=true または cancel_at が設定されている場合、キャンセル予定状態に
            if not should_cancel_trial_expired_immediately and (cancel_at_period_end or cancel_at):
                await crud.billing.update_status(
                    db=db,
                    billing_id=billing.id,
                    status=BillingStatus.canceling,
                    auto_commit=False
                )

                logger.info(f"[Webhook:{event_id}] Subscription set to canceling - cancel_at_period_end={cancel_at_period_end}, cancel_at={cancel_at}")

            # キャンセルが完全にクリアされた場合（cancel_at_period_end=false かつ cancel_at=null）、元のステータスに復元
            elif (
                not should_cancel_trial_expired_immediately
                and not cancel_at_period_end
                and not cancel_at
                and billing.billing_status == BillingStatus.canceling
            ):
                # 元のステータスを判定: trial期間内 or 課金期間中
                now = datetime.now(timezone.utc)
                is_in_trial = now < billing.trial_end_date
                has_subscription = billing.stripe_subscription_id is not None

                # 復元先のステータスを決定
                if is_in_trial and has_subscription:
                    # 無料期間中かつ課金設定済み → early_payment
                    restored_status = BillingStatus.early_payment
                elif is_in_trial and not has_subscription:
                    # 無料期間中かつ課金未設定 → free
                    restored_status = BillingStatus.free
                else:
                    # 課金期間中 → active
                    restored_status = BillingStatus.active

                await crud.billing.update_status(
                    db=db,
                    billing_id=billing.id,
                    status=restored_status,
                    auto_commit=False
                )

                logger.info(f"[Webhook:{event_id}] Subscription cancellation reverted for billing_id={billing.id}, restored to {restored_status}")
            else:
                # どの条件にも当てはまらない場合（通常の更新）
                logger.info(f"[Webhook:{event_id}] Subscription updated but no status change needed - cancel_at_period_end={cancel_at_period_end}, current_status={billing.billing_status}")

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
            logger.info(
                "[Webhook:%s] Subscription update committed: billing_id=%s, "
                "previous_status=%s, cancel_at_period_end=%s, cancel_at=%s, "
                "stripe_status=%s",
                event_id,
                billing.id,
                previous_status.value if previous_status else None,
                cancel_at_period_end,
                cancel_at,
                subscription_status,
            )

        except Exception as e:
            await db.rollback()
            logger.exception(
                "[Webhook:%s] Subscription update processing error: "
                "customer_id=%s, subscription_id=%s, stripe_status=%s, "
                "cancel_at_period_end=%s, cancel_at=%s",
                event_id,
                subscription_data.get('customer'),
                subscription_data.get('id'),
                subscription_data.get('status'),
                subscription_data.get('cancel_at_period_end'),
                subscription_data.get('cancel_at'),
            )
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
                logger.info(f"[Webhook:{event_id}] Billing not found for customer {customer_id} - skipping (possibly test data)")

                await crud.webhook_event.create_event_record(
                    db=db,
                    event_id=event_id,
                    event_type='customer.subscription.deleted',
                    source='stripe',
                    billing_id=None,
                    office_id=None,
                    payload={"customer_id": customer_id, "note": "Customer not found in database"},
                    status='skipped',
                    auto_commit=True
                )
                return

            previous_status = billing.billing_status
            recent_payment_failed_cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
            has_recent_payment_failed = await crud.webhook_event.has_recent_successful_event(
                db=db,
                billing_id=billing.id,
                event_type="invoice.payment_failed",
                since=recent_payment_failed_cutoff
            )
            new_status = (
                BillingStatus.payment_failed
                if has_recent_payment_failed
                else BillingStatus.canceled
            )
            logger.info(
                "[Webhook:%s] Subscription deleted payload: customer_id=%s, "
                "billing_id=%s, office_id=%s, previous_status=%s, "
                "db_stripe_subscription_id=%s, has_recent_payment_failed=%s, "
                "recent_payment_failed_cutoff=%s, new_status=%s",
                event_id,
                customer_id,
                billing.id,
                billing.office_id,
                previous_status.value if previous_status else None,
                billing.stripe_subscription_id,
                has_recent_payment_failed,
                recent_payment_failed_cutoff.isoformat(),
                new_status.value,
            )

            # 1. ステータス更新とスケジュールキャンセルのクリア（auto_commit=False）
            await crud.billing.update(
                db=db,
                db_obj=billing,
                obj_in={
                    "billing_status": new_status,
                    "scheduled_cancel_at": None
                },
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
                action=(
                    "billing.subscription_deleted_after_payment_failed"
                    if has_recent_payment_failed
                    else "billing.subscription_canceled"
                ),
                target_type="billing",
                target_id=billing.id,
                office_id=billing.office_id,
                details={
                    "event_id": event_id,
                    "event_type": "customer.subscription.deleted",
                    "has_recent_payment_failed": has_recent_payment_failed,
                    "source": "stripe_webhook"
                },
                auto_commit=False
            )

            # 4. commit
            await db.commit()

            logger.info(
                "[Webhook:%s] Subscription deleted committed: billing_id=%s, "
                "previous_status=%s, new_status=%s",
                event_id,
                billing.id,
                previous_status.value if previous_status else None,
                new_status.value,
            )

        except Exception as e:
            await db.rollback()
            logger.exception(
                "[Webhook:%s] Subscription deletion processing error: customer_id=%s",
                event_id,
                customer_id,
            )
            raise
