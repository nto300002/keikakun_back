from uuid import UUID
from sqlalchemy import select, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload
from pydantic import BaseModel
from typing import List, Dict, Optional
from datetime import datetime

from app.crud.base import CRUDBase
from app.models.support_plan_cycle import SupportPlanCycle, PlanDeliverable
from app.models.welfare_recipient import WelfareRecipient, OfficeWelfareRecipient
from app.models.staff import Staff
from app.models.enums import DeliverableType


class CRUDSupportPlanCycle(CRUDBase[SupportPlanCycle, BaseModel, BaseModel]):
    async def get_cycles_by_recipient(
        self, db: AsyncSession, *, recipient_id: UUID
    ) -> list[SupportPlanCycle]:
        """
        指定された利用者のすべての支援計画サイクルを、関連ステータスと共に取得します。
        """
        stmt = (
            select(SupportPlanCycle)
            .where(SupportPlanCycle.welfare_recipient_id == recipient_id)
            .options(selectinload(SupportPlanCycle.statuses))
            .order_by(SupportPlanCycle.cycle_number.desc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_multi_deliverables_with_relations(
        self,
        db: AsyncSession,
        *,
        office_id: UUID,
        filters: Dict,
        sort_by: str = "uploaded_at",
        sort_order: str = "desc",
        skip: int = 0,
        limit: int = 20
    ) -> List[PlanDeliverable]:
        """
        リレーションを含むPDF一覧を取得

        N+1問題対策:
        - joinedload: plan_cycle（多対一）
        - selectinload: welfare_recipient, staff（一対多）
        """
        # ベースクエリ
        query = (
            select(PlanDeliverable)
            .join(PlanDeliverable.plan_cycle)
            .join(SupportPlanCycle.welfare_recipient)
            .options(
                # Eager Loading
                joinedload(PlanDeliverable.plan_cycle).selectinload(
                    SupportPlanCycle.welfare_recipient
                ),
                joinedload(PlanDeliverable.uploaded_by_staff)
            )
        )

        # フィルター適用
        query = self._apply_deliverable_filters(query, office_id, filters)

        # ソート適用
        query = self._apply_deliverable_sorting(query, sort_by, sort_order)

        # ページネーション
        query = query.offset(skip).limit(limit)

        result = await db.execute(query)
        return list(result.scalars().unique().all())

    async def count_deliverables_with_filters(
        self,
        db: AsyncSession,
        *,
        office_id: UUID,
        filters: Dict
    ) -> int:
        """フィルター条件での総件数取得"""
        query = (
            select(func.count(PlanDeliverable.id))
            .join(PlanDeliverable.plan_cycle)
            .join(SupportPlanCycle.welfare_recipient)
        )

        # フィルター適用
        query = self._apply_deliverable_filters(query, office_id, filters)

        result = await db.execute(query)
        return result.scalar_one()

    def _apply_deliverable_filters(
        self,
        query,
        office_id: UUID,
        filters: Dict
    ):
        """フィルター条件の適用"""
        # 事業所フィルター（必須）
        # WelfareRecipient -> OfficeWelfareRecipient -> Office
        query = query.join(
            OfficeWelfareRecipient,
            WelfareRecipient.id == OfficeWelfareRecipient.welfare_recipient_id
        ).where(OfficeWelfareRecipient.office_id == office_id)

        # 検索キーワード
        if filters.get("search"):
            search_term = f"%{filters['search']}%"
            query = query.where(
                or_(
                    PlanDeliverable.original_filename.ilike(search_term),
                    func.concat(
                        WelfareRecipient.last_name,
                        WelfareRecipient.first_name
                    ).ilike(search_term)
                )
            )

        # 利用者IDフィルター
        if filters.get("recipient_ids"):
            query = query.where(
                WelfareRecipient.id.in_(filters["recipient_ids"])
            )

        # deliverable_typeフィルター
        if filters.get("deliverable_types"):
            query = query.where(
                PlanDeliverable.deliverable_type.in_(filters["deliverable_types"])
            )

        # 日付範囲フィルター
        if filters.get("date_from"):
            query = query.where(PlanDeliverable.uploaded_at >= filters["date_from"])

        if filters.get("date_to"):
            query = query.where(PlanDeliverable.uploaded_at <= filters["date_to"])

        return query

    def _apply_deliverable_sorting(
        self,
        query,
        sort_by: str,
        sort_order: str
    ):
        """ソート条件の適用"""
        # ソート対象の決定
        if sort_by == "uploaded_at":
            order_column = PlanDeliverable.uploaded_at
        elif sort_by == "recipient_name":
            order_column = func.concat(
                WelfareRecipient.last_name_furigana,
                WelfareRecipient.first_name_furigana
            )
        elif sort_by == "file_name":
            order_column = PlanDeliverable.original_filename
        else:
            order_column = PlanDeliverable.uploaded_at

        # ソート順の適用
        if sort_order == "asc":
            query = query.order_by(order_column.asc())
        else:
            query = query.order_by(order_column.desc())

        return query


crud_support_plan_cycle = CRUDSupportPlanCycle(SupportPlanCycle)
