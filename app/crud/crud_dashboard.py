from datetime import date, timedelta
import uuid
from typing import List, Optional
import re
from sqlalchemy import select, or_, and_, func, asc, desc, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload
# import logging

from app.crud.base import CRUDBase
from app.models import WelfareRecipient, OfficeWelfareRecipient, SupportPlanCycle, SupportPlanStatus, Staff, Office, OfficeStaff
from app.schemas.dashboard import DashboardSummary
from app.models.enums import SupportPlanStep


class CRUDDashboard(CRUDBase[WelfareRecipient, DashboardSummary, DashboardSummary]):
    async def get_cycle_count_for_recipient(self, db: AsyncSession, *, welfare_recipient_id: uuid.UUID) -> int:
        """
        特定の利用者の支援計画サイクルの総数を取得します。
        """
        query = (
            select(func.count())
            .select_from(SupportPlanCycle)
            .where(SupportPlanCycle.welfare_recipient_id == welfare_recipient_id)
        )
        result = await db.execute(query)
        return result.scalar_one()

    async def get_latest_cycle(self, db: AsyncSession, *, welfare_recipient_id: uuid.UUID) -> Optional[SupportPlanCycle]:
        """
        特定の利用者の最新の支援計画サイクル（関連ステータスも含む）を取得します。
        """
        query = (
            select(SupportPlanCycle)
            .where(
                SupportPlanCycle.welfare_recipient_id == welfare_recipient_id,
                SupportPlanCycle.is_latest_cycle == True
            )
            .options(selectinload(SupportPlanCycle.statuses))
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_staff_office(self, db: AsyncSession, *, staff_id: uuid.UUID) -> Optional[tuple[Staff, Office]]:
        """
        スタッフとその所属事業所を取得します。
        """
        query = (
            select(Staff, Office)
            .join(OfficeStaff, Staff.id == OfficeStaff.staff_id)
            .join(Office, OfficeStaff.office_id == Office.id)
            .where(
                Staff.id == staff_id,
                OfficeStaff.is_primary == True
            )
        )
        result = await db.execute(query)
        row = result.first()
        return (row[0], row[1]) if row else None

    async def get_office_recipients(self, db: AsyncSession, *, office_id: uuid.UUID) -> List[WelfareRecipient]:
        """
        指定された事業所の利用者一覧を取得します。
        """
        query = (
            select(WelfareRecipient)
            .join(OfficeWelfareRecipient)
            .where(OfficeWelfareRecipient.office_id == office_id)
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    async def count_office_recipients(self, db: AsyncSession, *, office_id: uuid.UUID) -> int:
        """
        指定された事業所の利用者数を取得します。
        """
        query = (
            select(func.count())
            .select_from(WelfareRecipient)
            .join(OfficeWelfareRecipient)
            .where(OfficeWelfareRecipient.office_id == office_id)
        )
        result = await db.execute(query)
        return result.scalar_one()

    async def get_filtered_summaries(
        self,
        db: AsyncSession,
        *,
        office_ids: List[str],
        sort_by: str,
        sort_order: str,
        filters: dict,
        search_term: Optional[str],
        skip: int,
        limit: int,
    ) -> List[WelfareRecipient]:
        print(
            "get_filtered_summaries called: office_ids=%s sort_by=%s sort_order=%s filters=%s search_term=%s skip=%s limit=%s",
            office_ids, sort_by, sort_order, filters, search_term, skip, limit
        )
        stmt = (
            select(WelfareRecipient)
            .join(OfficeWelfareRecipient)
            .where(OfficeWelfareRecipient.office_id.in_(office_ids))
        )

        # --- 検索 ---
        if search_term:
            search_words = re.split(r'[\s　]+', search_term.strip())
            conditions = []
            for word in search_words:
                if not word:
                    continue
                name_conditions = or_(
                    WelfareRecipient.last_name.ilike(f"%{word}%"),
                    WelfareRecipient.first_name.ilike(f"%{word}%"),
                    WelfareRecipient.last_name_furigana.ilike(f"%{word}%"),
                    WelfareRecipient.first_name_furigana.ilike(f"%{word}%"),
                )
                conditions.append(name_conditions)
            if conditions:
                stmt = stmt.where(and_(*conditions))

        # --- JOINの決定と実行 ---
        needs_cycle_outer_join = any(k in filters for k in ["is_overdue", "is_upcoming", "status", "cycle_number"])
        needs_cycle_inner_join = sort_by == "next_renewal_deadline"

        if needs_cycle_inner_join:
            stmt = stmt.join(
                SupportPlanCycle,
                and_(
                    WelfareRecipient.id == SupportPlanCycle.welfare_recipient_id,
                    SupportPlanCycle.is_latest_cycle == true(),
                ),
            )
        elif needs_cycle_outer_join:
            stmt = stmt.outerjoin(
                SupportPlanCycle,
                and_(
                    WelfareRecipient.id == SupportPlanCycle.welfare_recipient_id,
                    SupportPlanCycle.is_latest_cycle == True,
                ),
            )

        # --- フィルター ---
        if filters:
            if filters.get("is_overdue"):
                stmt = stmt.where(SupportPlanCycle.next_renewal_deadline < date.today())
            if filters.get("is_upcoming"):
                stmt = stmt.where(
                    SupportPlanCycle.next_renewal_deadline.between(
                        date.today(), date.today() + timedelta(days=30)
                    )
                )
            if filters.get("status"):
                latest_status_subq = (
                    select(
                        SupportPlanStatus.plan_cycle_id,
                        SupportPlanStatus.step_type,
                        func.row_number().over(
                            partition_by=SupportPlanStatus.plan_cycle_id,
                            order_by=SupportPlanStatus.created_at.desc()
                        ).label("rn")
                    )
                    .join(SupportPlanCycle, SupportPlanStatus.plan_cycle_id == SupportPlanCycle.id)
                    .where(SupportPlanCycle.is_latest_cycle == True)
                    .subquery("latest_status_subq")
                )
                # The join to SupportPlanCycle is already done above, so we join the subquery
                stmt = stmt.join(
                    latest_status_subq,
                    latest_status_subq.c.plan_cycle_id == SupportPlanCycle.id
                ).where(
                    and_(
                        latest_status_subq.c.rn == 1,
                        latest_status_subq.c.step_type == filters["status"]
                    )
                )
            if filters.get("cycle_number"):
                stmt = stmt.where(SupportPlanCycle.cycle_number == filters["cycle_number"])

        # --- ソート ---
        if sort_by == "name_phonetic":
            sort_column = func.concat(WelfareRecipient.last_name_furigana, WelfareRecipient.first_name_furigana)
            order_func = sort_column.desc().nullslast() if sort_order == "desc" else sort_column.asc().nullsfirst()
            stmt = stmt.order_by(order_func)
        elif sort_by == "created_at":
            sort_column = WelfareRecipient.created_at
            order_func = sort_column.desc().nullslast() if sort_order == "desc" else sort_column.asc().nullsfirst()
            stmt = stmt.order_by(order_func)
        elif sort_by == "next_renewal_deadline":
            sort_column = SupportPlanCycle.next_renewal_deadline
            order_func = sort_column.desc().nullslast() if sort_order == "desc" else sort_column.asc().nullsfirst()
            stmt = stmt.order_by(order_func)
        else: # Default sort
            default_sort_col = func.concat(WelfareRecipient.last_name_furigana, WelfareRecipient.first_name_furigana)
            stmt = stmt.order_by(default_sort_col.asc().nullsfirst())

        # --- イージアローディング、ページネーション、および実行 ---
        stmt = stmt.options(
            selectinload(WelfareRecipient.support_plan_cycles).selectinload(
                SupportPlanCycle.statuses
            )
        ).offset(skip).limit(limit)

        try:
            print("Compiled stmt: %s", str(stmt))
        except Exception:
            print("Could not stringify stmt")

        result = await db.execute(stmt)
        rows = list(result.scalars().all())
        print("get_filtered_summaries result count: %d", len(rows))
        return rows

crud_dashboard = CRUDDashboard(WelfareRecipient)
