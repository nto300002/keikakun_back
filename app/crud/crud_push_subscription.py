"""
Push通知購読のCRUD操作
"""
from typing import List, Optional, Dict
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.push_subscription import PushSubscription
from app.schemas.push_subscription import PushSubscriptionInDB


class CRUDPushSubscription(CRUDBase[PushSubscription, PushSubscriptionInDB, PushSubscriptionInDB]):
    """Push購読のCRUD操作"""

    async def get_by_staff_id(
        self,
        db: AsyncSession,
        staff_id: UUID
    ) -> List[PushSubscription]:
        """
        スタッフIDで購読情報を全件取得

        Args:
            db: データベースセッション
            staff_id: スタッフID

        Returns:
            List[PushSubscription]: スタッフの全デバイスの購読情報
        """
        stmt = select(PushSubscription).where(PushSubscription.staff_id == staff_id)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_staff_ids_batch(
        self,
        db: AsyncSession,
        staff_ids: List[UUID]
    ) -> Dict[UUID, List[PushSubscription]]:
        """
        複数スタッフの購読情報を一括取得（N+1問題解消）

        Args:
            db: データベースセッション
            staff_ids: スタッフIDのリスト

        Returns:
            Dict[UUID, List[PushSubscription]]: {staff_id: [subscription, ...]} の辞書
        """
        if not staff_ids:
            return {}

        # 全スタッフの購読情報を1クエリで取得
        stmt = (
            select(PushSubscription)
            .where(PushSubscription.staff_id.in_(staff_ids))
            .order_by(PushSubscription.staff_id.asc(), PushSubscription.created_at.asc())
        )

        result = await db.execute(stmt)
        subscriptions = result.scalars().all()

        # スタッフIDごとにグループ化
        subscriptions_by_staff: Dict[UUID, List[PushSubscription]] = {
            staff_id: [] for staff_id in staff_ids
        }

        for subscription in subscriptions:
            subscriptions_by_staff[subscription.staff_id].append(subscription)

        return subscriptions_by_staff

    async def get_by_endpoint(
        self,
        db: AsyncSession,
        endpoint: str
    ) -> Optional[PushSubscription]:
        """
        エンドポイントで購読情報を取得

        Args:
            db: データベースセッション
            endpoint: Push Serviceエンドポイント

        Returns:
            Optional[PushSubscription]: 購読情報（存在しない場合はNone）
        """
        stmt = select(PushSubscription).where(PushSubscription.endpoint == endpoint)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def create_or_update(
        self,
        db: AsyncSession,
        *,
        staff_id: UUID,
        endpoint: str,
        p256dh_key: str,
        auth_key: str,
        user_agent: str | None = None
    ) -> PushSubscription:
        """
        購読情報を作成または更新（複数デバイス対応）

        同一エンドポイントが既に存在する場合は更新、存在しない場合は新規作成。
        複数デバイス（PC + スマホ等）からの購読を許可するため、
        新規作成時に既存の購読を削除しない。

        ⚠️ 重要な設計決定（Web Push機能において基本的に変更不可）:
        - 1ユーザーが複数デバイスで通知を受信できるよう、既存購読を保持
        - この削除ロジックを復活させると、新規デバイス登録時に既存デバイスが
          通知を受信できなくなる
        - 例: PCで購読済みのユーザーがスマホで購読 → PCの購読が削除される問題
        - 修正日: 2026-01-19（パフォーマンス・セキュリティレビュー Issue #1）

        Args:
            db: データベースセッション
            staff_id: スタッフID
            endpoint: Push Serviceエンドポイント
            p256dh_key: P-256公開鍵
            auth_key: 認証シークレット
            user_agent: ユーザーエージェント（任意）

        Returns:
            PushSubscription: 作成または更新された購読情報
        """
        existing = await self.get_by_endpoint(db=db, endpoint=endpoint)

        if existing:
            # 既存のエンドポイントの場合は鍵情報を更新
            existing.staff_id = staff_id
            existing.p256dh_key = p256dh_key
            existing.auth_key = auth_key
            if user_agent:
                existing.user_agent = user_agent

            db.add(existing)
            await db.commit()
            await db.refresh(existing)
            return existing
        else:
            # 新規エンドポイントの場合は新規作成
            # ⚠️ 重要: 既存の購読は削除しない（複数デバイス対応のため）
            subscription_data = PushSubscriptionInDB(
                staff_id=staff_id,
                endpoint=endpoint,
                p256dh_key=p256dh_key,
                auth_key=auth_key,
                user_agent=user_agent
            )
            return await self.create(db=db, obj_in=subscription_data, auto_commit=True)

    async def delete_by_endpoint(
        self,
        db: AsyncSession,
        endpoint: str
    ) -> bool:
        """
        エンドポイントで購読情報を削除

        Args:
            db: データベースセッション
            endpoint: Push Serviceエンドポイント

        Returns:
            bool: 削除成功の場合True、対象が存在しない場合False
        """
        subscription = await self.get_by_endpoint(db=db, endpoint=endpoint)
        if subscription:
            await db.delete(subscription)
            await db.commit()
            return True
        return False

    async def delete_by_staff_id(
        self,
        db: AsyncSession,
        staff_id: UUID
    ) -> int:
        """
        スタッフIDで購読情報を全件削除

        Args:
            db: データベースセッション
            staff_id: スタッフID

        Returns:
            int: 削除した購読情報の件数
        """
        subscriptions = await self.get_by_staff_id(db=db, staff_id=staff_id)
        count = len(subscriptions)

        for subscription in subscriptions:
            await db.delete(subscription)

        await db.commit()
        return count


crud_push_subscription = CRUDPushSubscription(PushSubscription)
