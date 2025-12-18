"""
Billing CRUD操作
"""
from typing import Optional
from uuid import UUID
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.crud.base import CRUDBase
from app.models.billing import Billing
from app.models.enums import BillingStatus
from app.schemas.billing import BillingCreate, BillingUpdate


class CRUDBilling(CRUDBase[Billing, BillingCreate, BillingUpdate]):
    """Billing CRUD操作クラス"""

    async def get_by_office_id(
        self,
        db: AsyncSession,
        office_id: UUID
    ) -> Optional[Billing]:
        """事業所IDでBilling情報を取得"""
        result = await db.execute(
            select(self.model)
            .where(self.model.office_id == office_id)
            .options(selectinload(self.model.office))
        )
        return result.scalars().first()

    async def get_by_stripe_customer_id(
        self,
        db: AsyncSession,
        stripe_customer_id: str
    ) -> Optional[Billing]:
        """Stripe Customer IDでBilling情報を取得"""
        result = await db.execute(
            select(self.model)
            .where(self.model.stripe_customer_id == stripe_customer_id)
            .options(selectinload(self.model.office))
        )
        return result.scalars().first()

    async def get_by_stripe_subscription_id(
        self,
        db: AsyncSession,
        stripe_subscription_id: str
    ) -> Optional[Billing]:
        """Stripe Subscription IDでBilling情報を取得"""
        result = await db.execute(
            select(self.model)
            .where(self.model.stripe_subscription_id == stripe_subscription_id)
            .options(selectinload(self.model.office))
        )
        return result.scalars().first()

    async def create_for_office(
        self,
        db: AsyncSession,
        office_id: UUID,
        trial_days: int = 180
    ) -> Billing:
        """
        事業所用のBilling情報を作成（新規登録時用）

        Args:
            db: データベースセッション
            office_id: 事業所ID
            trial_days: 無料期間日数（デフォルト180日）
        """
        now = datetime.now(timezone.utc)
        trial_end = now + timedelta(days=trial_days)

        billing_data = BillingCreate(
            office_id=office_id,
            billing_status=BillingStatus.free,
            trial_start_date=now,
            trial_end_date=trial_end,
            current_plan_amount=6000
        )

        return await self.create(db=db, obj_in=billing_data)

    async def update_status(
        self,
        db: AsyncSession,
        billing_id: UUID,
        status: BillingStatus,
        auto_commit: bool = True
    ) -> Optional[Billing]:
        """課金ステータスを更新"""
        billing = await self.get(db=db, id=billing_id)
        if not billing:
            return None

        update_data = BillingUpdate(billing_status=status)
        return await self.update(db=db, db_obj=billing, obj_in=update_data, auto_commit=auto_commit)

    async def update_stripe_customer(
        self,
        db: AsyncSession,
        billing_id: UUID,
        stripe_customer_id: str,
        auto_commit: bool = True
    ) -> Optional[Billing]:
        """Stripe Customer IDを更新"""
        billing = await self.get(db=db, id=billing_id)
        if not billing:
            return None

        update_data = BillingUpdate(stripe_customer_id=stripe_customer_id)
        return await self.update(db=db, db_obj=billing, obj_in=update_data, auto_commit=auto_commit)

    async def update_stripe_subscription(
        self,
        db: AsyncSession,
        billing_id: UUID,
        stripe_subscription_id: str,
        subscription_start_date: Optional[datetime] = None,
        next_billing_date: Optional[datetime] = None,
        auto_commit: bool = True
    ) -> Optional[Billing]:
        """Stripe Subscription情報を更新"""
        billing = await self.get(db=db, id=billing_id)
        if not billing:
            return None

        update_data = BillingUpdate(
            stripe_subscription_id=stripe_subscription_id,
            subscription_start_date=subscription_start_date or datetime.now(timezone.utc),
            next_billing_date=next_billing_date
        )
        return await self.update(db=db, db_obj=billing, obj_in=update_data, auto_commit=auto_commit)

    async def record_payment(
        self,
        db: AsyncSession,
        billing_id: UUID,
        payment_date: Optional[datetime] = None,
        auto_commit: bool = True
    ) -> Optional[Billing]:
        """支払い記録を更新"""
        billing = await self.get(db=db, id=billing_id)
        if not billing:
            return None

        update_data = BillingUpdate(
            last_payment_date=payment_date or datetime.now(timezone.utc),
            billing_status=BillingStatus.active
        )
        return await self.update(db=db, db_obj=billing, obj_in=update_data, auto_commit=auto_commit)

    # ========================================
    # ステータス判定メソッド
    # ========================================

    def is_active_subscription(self, billing: Billing) -> bool:
        """
        アクティブなサブスクリプションかを判定

        Returns:
            True: active, early_payment, canceling（期間終了まで利用可能）
            False: free, past_due, canceled
        """
        return billing.billing_status in [
            BillingStatus.active,
            BillingStatus.early_payment,
            BillingStatus.canceling
        ]

    def is_pending_cancellation(self, billing: Billing) -> bool:
        """
        キャンセル予定状態かを判定

        Returns:
            True: canceling のみ
            False: その他
        """
        return billing.billing_status == BillingStatus.canceling

    def can_access_paid_features(self, billing: Billing) -> bool:
        """
        有料機能にアクセスできるかを判定

        Returns:
            True: early_payment, active, canceling（期間終了まで利用可能）
            False: free, past_due, canceled
        """
        return billing.billing_status in [
            BillingStatus.early_payment,
            BillingStatus.active,
            BillingStatus.canceling
        ]

    def requires_payment_action(self, billing: Billing) -> bool:
        """
        支払いアクションが必要かを判定

        Returns:
            True: past_due のみ
            False: その他
        """
        return billing.billing_status == BillingStatus.past_due

    # ========================================
    # ステータスメッセージ取得メソッド
    # ========================================

    def get_status_display_message(self, billing: Billing) -> str:
        """
        ステータスの表示メッセージを取得

        Args:
            billing: Billingオブジェクト

        Returns:
            各ステータスに対応する日本語表示メッセージ
        """
        messages = {
            BillingStatus.free: "無料トライアル中",
            BillingStatus.early_payment: "課金設定済み（無料期間中）",
            BillingStatus.active: "課金中",
            BillingStatus.past_due: "支払い遅延",
            BillingStatus.canceling: "キャンセル予定",
            BillingStatus.canceled: "キャンセル済み",
        }
        return messages.get(billing.billing_status, "不明")

    def get_cancellation_message(self, billing: Billing) -> str:
        """
        キャンセル予定の詳細メッセージを取得

        Args:
            billing: Billingオブジェクト

        Returns:
            canceling状態の場合、期間終了日を含む詳細メッセージ
            その他の状態の場合、空文字列
        """
        if billing.billing_status != BillingStatus.canceling:
            return ""

        end_date = billing.trial_end_date.strftime('%Y年%m月%d日')
        return f"{end_date}まで利用できます。それ以降は自動的に終了します。"

    def get_next_action_message(self, billing: Billing) -> str:
        """
        次のアクションメッセージを取得

        Args:
            billing: Billingオブジェクト

        Returns:
            各ステータスに応じた次のアクション案内メッセージ
        """
        messages = {
            BillingStatus.free: "課金設定を行うと、より多くの機能が利用できます。",
            BillingStatus.past_due: "支払い方法を更新してください。",
            BillingStatus.canceling: "キャンセルの取り消しができます。",
            BillingStatus.canceled: "再契約することで、サービスを再開できます。",
        }
        return messages.get(billing.billing_status, "")


# インスタンス化
billing = CRUDBilling(Billing)
