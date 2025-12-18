"""
WebhookEvent CRUD操作
"""
from typing import Optional, List
from uuid import UUID
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func

from app.crud.base import CRUDBase
from app.models.webhook_event import WebhookEvent
from app.schemas.webhook_event import WebhookEventCreate, WebhookEventUpdate


class CRUDWebhookEvent(CRUDBase[WebhookEvent, WebhookEventCreate, WebhookEventUpdate]):
    """WebhookEvent CRUD操作クラス"""

    async def get_by_event_id(
        self,
        db: AsyncSession,
        event_id: str
    ) -> Optional[WebhookEvent]:
        """
        Stripe Event IDでWebhookEventを取得

        Args:
            db: データベースセッション
            event_id: Stripe Event ID

        Returns:
            WebhookEvent または None
        """
        result = await db.execute(
            select(self.model)
            .where(self.model.event_id == event_id)
        )
        return result.scalars().first()

    async def is_event_processed(
        self,
        db: AsyncSession,
        event_id: str
    ) -> bool:
        """
        イベントが既に処理済みかどうかを確認

        Args:
            db: データベースセッション
            event_id: Stripe Event ID

        Returns:
            True: 処理済み, False: 未処理
        """
        webhook_event = await self.get_by_event_id(db=db, event_id=event_id)
        return webhook_event is not None

    async def create_event_record(
        self,
        db: AsyncSession,
        *,
        event_id: str,
        event_type: str,
        source: str = "stripe",
        billing_id: Optional[UUID] = None,
        office_id: Optional[UUID] = None,
        payload: Optional[dict] = None,
        status: str = "success",
        error_message: Optional[str] = None,
        auto_commit: bool = True
    ) -> WebhookEvent:
        """
        Webhookイベント処理記録を作成

        Args:
            db: データベースセッション
            event_id: Stripe Event ID
            event_type: イベントタイプ
            source: Webhook送信元（デフォルト: stripe）
            billing_id: 関連するBilling ID
            office_id: 関連するOffice ID
            payload: Webhookペイロード
            status: 処理ステータス（success, failed, skipped）
            error_message: エラーメッセージ
            auto_commit: 自動コミット（デフォルト: True）

        Returns:
            作成されたWebhookEvent

        Note:
            - auto_commit=Falseの場合、トランザクション管理は呼び出し側で行う
        """
        webhook_event_data = WebhookEventCreate(
            event_id=event_id,
            event_type=event_type,
            source=source,
            billing_id=billing_id,
            office_id=office_id,
            payload=payload,
            status=status,
            error_message=error_message
        )
        return await self.create(db=db, obj_in=webhook_event_data, auto_commit=auto_commit)

    async def get_recent_events(
        self,
        db: AsyncSession,
        *,
        event_type: Optional[str] = None,
        billing_id: Optional[UUID] = None,
        office_id: Optional[UUID] = None,
        limit: int = 100
    ) -> List[WebhookEvent]:
        """
        最近のWebhookイベントを取得

        Args:
            db: データベースセッション
            event_type: イベントタイプでフィルタ
            billing_id: Billing IDでフィルタ
            office_id: Office IDでフィルタ
            limit: 取得件数上限

        Returns:
            WebhookEventリスト（新しい順）
        """
        query = select(self.model)

        if event_type:
            query = query.where(self.model.event_type == event_type)
        if billing_id:
            query = query.where(self.model.billing_id == billing_id)
        if office_id:
            query = query.where(self.model.office_id == office_id)

        query = query.order_by(self.model.processed_at.desc()).limit(limit)

        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_failed_events(
        self,
        db: AsyncSession,
        *,
        since: Optional[datetime] = None,
        limit: int = 100
    ) -> List[WebhookEvent]:
        """
        失敗したWebhookイベントを取得

        Args:
            db: データベースセッション
            since: この日時以降のイベントのみ取得
            limit: 取得件数上限

        Returns:
            失敗したWebhookEventリスト（新しい順）
        """
        query = select(self.model).where(self.model.status == "failed")

        if since:
            query = query.where(self.model.processed_at >= since)

        query = query.order_by(self.model.processed_at.desc()).limit(limit)

        result = await db.execute(query)
        return list(result.scalars().all())

    async def cleanup_old_events(
        self,
        db: AsyncSession,
        *,
        retention_days: int = 90,
        batch_size: int = 1000
    ) -> int:
        """
        古いWebhookイベントレコードを削除

        Args:
            db: データベースセッション
            retention_days: 保持期間（日数、デフォルト: 90日）
            batch_size: 一度に削除する最大件数

        Returns:
            削除された件数

        Note:
            - commitはエンドポイント層で行う
            - 定期的に実行することを推奨（cronジョブなど）
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

        # 削除対象のカウント
        count_query = (
            select(func.count())
            .select_from(self.model)
            .where(self.model.processed_at < cutoff_date)
        )
        count_result = await db.execute(count_query)
        total_count = count_result.scalar() or 0

        if total_count == 0:
            return 0

        # バッチ削除
        delete_query = (
            delete(self.model)
            .where(self.model.processed_at < cutoff_date)
        )
        await db.execute(delete_query)

        return min(total_count, batch_size)


# インスタンス化
webhook_event = CRUDWebhookEvent(WebhookEvent)
