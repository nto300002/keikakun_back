from typing import Optional, List, Dict
from datetime import datetime, timedelta, date
from sqlalchemy import select, func, and_, or_, true
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
import re
from app.crud.base import CRUDBase
from app.models import SupportPlanCycle, SupportPlanStatus, Staff, Office, OfficeStaff, WelfareRecipient, OfficeWelfareRecipient
from app.schemas.dashboard import DashboardSummary
from app.models.enums import SupportPlanStep
import uuid


class CRUDDashboard(CRUDBase[WelfareRecipient, DashboardSummary, DashboardSummary]):

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
        office_ids: List[uuid.UUID],
        sort_by: str,
        sort_order: str,
        filters: dict,
        search_term: Optional[str],
        skip: int,
        limit: int,
    ) -> list:
        # 1. サイクル総数をカウントするサブクエリ
        cycle_count_sq = (
            select(
                SupportPlanCycle.welfare_recipient_id,
                func.count(SupportPlanCycle.id).label("cycle_count"),
            )
            .group_by(SupportPlanCycle.welfare_recipient_id)
            .subquery("cycle_count_sq")
        )

        # 2. 最新サイクルIDを取得するためのサブクエリ
        latest_cycle_id_sq = (
            select(
                SupportPlanCycle.welfare_recipient_id,
                func.max(SupportPlanCycle.id).label("latest_cycle_id"),
            )
            .where(SupportPlanCycle.is_latest_cycle == true())
            .group_by(SupportPlanCycle.welfare_recipient_id)
            .subquery("latest_cycle_id_sq")
        )

        # 3. メインクエリの構築
        stmt = select(
            WelfareRecipient,
            func.coalesce(cycle_count_sq.c.cycle_count, 0).label("cycle_count"),
            SupportPlanCycle,
        ).join(OfficeWelfareRecipient).where(OfficeWelfareRecipient.office_id.in_(office_ids))

        # --- JOINs ---
        stmt = stmt.outerjoin(cycle_count_sq, WelfareRecipient.id == cycle_count_sq.c.welfare_recipient_id)

        if sort_by == "next_renewal_deadline":
            stmt = stmt.join(latest_cycle_id_sq, WelfareRecipient.id == latest_cycle_id_sq.c.welfare_recipient_id)
            stmt = stmt.join(SupportPlanCycle, SupportPlanCycle.id == latest_cycle_id_sq.c.latest_cycle_id)
        else:
            stmt = stmt.outerjoin(latest_cycle_id_sq, WelfareRecipient.id == latest_cycle_id_sq.c.welfare_recipient_id)
            stmt = stmt.outerjoin(SupportPlanCycle, SupportPlanCycle.id == latest_cycle_id_sq.c.latest_cycle_id)

        stmt = stmt.options(
            selectinload(SupportPlanCycle.statuses),
            selectinload(WelfareRecipient.support_plan_cycles).selectinload(SupportPlanCycle.statuses),
            selectinload(SupportPlanCycle.deliverables)
        )

        # --- 検索 ---
        if search_term:
            search_words = re.split(r'[\s　]+', search_term.strip())
            conditions = [or_(
                WelfareRecipient.last_name.ilike(f"%{word}%"),
                WelfareRecipient.first_name.ilike(f"%{word}%"),
                WelfareRecipient.last_name_furigana.ilike(f"%{word}%"),
                WelfareRecipient.first_name_furigana.ilike(f"%{word}%"),
            ) for word in search_words if word]
            if conditions:
                stmt = stmt.where(and_(*conditions))

        # --- フィルター ---
        if filters:
            if filters.get("is_overdue"):
                stmt = stmt.where(SupportPlanCycle.next_renewal_deadline < date.today())
            if filters.get("is_upcoming"):
                stmt = stmt.where(SupportPlanCycle.next_renewal_deadline.between(date.today(), date.today() + timedelta(days=30)))
            if filters.get("cycle_number"):
                stmt = stmt.where(func.coalesce(cycle_count_sq.c.cycle_count, 0) == filters["cycle_number"])
            if filters.get("status"):
                try:
                    status_enum = SupportPlanStep[filters["status"]]
                except KeyError:
                    pass  # 無効なステータスは無視
                else:
                    # is_latest_status が true のレコードから step_type を取得するサブクエリ
                    latest_status_subq = select(
                        SupportPlanStatus.plan_cycle_id,
                        SupportPlanStatus.step_type.label("latest_step")
                    ).where(SupportPlanStatus.is_latest_status == true()).subquery()
                    
                    stmt = stmt.join(latest_status_subq, SupportPlanCycle.id == latest_status_subq.c.plan_cycle_id)
                    stmt = stmt.where(latest_status_subq.c.latest_step == status_enum)

        # --- ソート ---
        order_func = None
        if sort_by == "name_phonetic":
            sort_column = func.concat(WelfareRecipient.last_name_furigana, WelfareRecipient.first_name_furigana)
            order_func = sort_column.desc() if sort_order == "desc" else sort_column.asc()
        elif sort_by == "created_at":
            sort_column = WelfareRecipient.created_at
            order_func = sort_column.desc() if sort_order == "desc" else sort_column.asc()
        elif sort_by == "next_renewal_deadline":
            sort_column = SupportPlanCycle.next_renewal_deadline
            # 昇順の場合も nullslast() を使用して、期限がある利用者を優先表示
            order_func = sort_column.desc().nullslast() if sort_order == "desc" else sort_column.asc().nullslast()
        
        if order_func is not None:
            stmt = stmt.order_by(order_func)
        else:
            default_sort_col = func.concat(WelfareRecipient.last_name_furigana, WelfareRecipient.first_name_furigana)
            stmt = stmt.order_by(default_sort_col.asc())

        # --- ページネーションと実行 ---
        stmt = stmt.offset(skip).limit(limit)
        result = await db.execute(stmt)
        return result.all()

    async def get_summary_counts(
        self,
        db: AsyncSession,
        office_ids: List[uuid.UUID],
    ) -> Dict[str, int]:
        """
        ダッシュボード用のサマリー件数を集計します。
        - 全利用者数
        - 期限切れ (Overdue)
        - 更新間近 (Upcoming)
        - サイクル未作成 (No Cycle)
        """
        today = date.today()
        upcoming_deadline = today + timedelta(days=30)

        # ベースクエリ: 対象事業所の利用者
        base_query = (
            select(WelfareRecipient.id)
            .join(OfficeWelfareRecipient)
            .where(OfficeWelfareRecipient.office_id.in_(office_ids))
        )
        
        total_res = await db.execute(select(func.count()).select_from(base_query.subquery()))
        total_recipients = total_res.scalar_one()

        # 最新サイクルをJOINしたクエリ
        query_with_cycle = (
            base_query
            .outerjoin(SupportPlanCycle, and_(
                WelfareRecipient.id == SupportPlanCycle.welfare_recipient_id,
                SupportPlanCycle.is_latest_cycle == True
            ))
        )

        # 各カウントを集計
        overdue_stmt = select(func.count()).select_from(query_with_cycle.where(SupportPlanCycle.next_renewal_deadline < today).subquery())
        upcoming_stmt = select(func.count()).select_from(query_with_cycle.where(SupportPlanCycle.next_renewal_deadline.between(today, upcoming_deadline)).subquery())
        no_cycle_stmt = select(func.count()).select_from(query_with_cycle.where(SupportPlanCycle.id == None).subquery())

        overdue_res = await db.execute(overdue_stmt)
        upcoming_res = await db.execute(upcoming_stmt)
        no_cycle_res = await db.execute(no_cycle_stmt)

        return {
            "total_recipients": total_recipients,
            "overdue_count": overdue_res.scalar_one(),
            "upcoming_count": upcoming_res.scalar_one(),
            "no_cycle_count": no_cycle_res.scalar_one(),
        }

crud_dashboard = CRUDDashboard(WelfareRecipient)
