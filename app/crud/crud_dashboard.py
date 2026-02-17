from typing import Optional, List, Dict
from datetime import datetime, timedelta, date
from sqlalchemy import select, func, and_, or_, true, exists, case
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
import re
from app.crud.base import CRUDBase
from app.models import SupportPlanCycle, SupportPlanStatus, Staff, Office, OfficeStaff, WelfareRecipient, OfficeWelfareRecipient, PlanDeliverable
from app.schemas.dashboard import DashboardSummary
from app.models.enums import SupportPlanStep, DeliverableType
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
        # 1. サイクル情報を統合取得するサブクエリ（サイクル数 + 最新サイクルID）
        cycle_info_sq = (
            select(
                SupportPlanCycle.welfare_recipient_id,
                func.count(SupportPlanCycle.id).label("cycle_count"),
                func.max(
                    case(
                        (SupportPlanCycle.is_latest_cycle == true(), SupportPlanCycle.id),
                        else_=None
                    )
                ).label("latest_cycle_id")
            )
            .group_by(SupportPlanCycle.welfare_recipient_id)
            .subquery("cycle_info_sq")
        )

        # 2. メインクエリの構築
        stmt = select(
            WelfareRecipient,
            func.coalesce(cycle_info_sq.c.cycle_count, 0).label("cycle_count"),
            SupportPlanCycle,
        ).join(OfficeWelfareRecipient).where(OfficeWelfareRecipient.office_id.in_(office_ids))

        # --- JOINs（常にOUTER JOINで統一） ---
        stmt = stmt.outerjoin(
            cycle_info_sq,
            WelfareRecipient.id == cycle_info_sq.c.welfare_recipient_id
        )
        stmt = stmt.outerjoin(
            SupportPlanCycle,
            SupportPlanCycle.id == cycle_info_sq.c.latest_cycle_id
        )

        # --- Relationship loading with filtering (Phase 3.1 optimization) ---
        stmt = stmt.options(
            # 最新ステータスのみをロード（_get_latest_step, _calculate_monitoring_due_date で使用）
            selectinload(
                SupportPlanCycle.statuses.and_(SupportPlanStatus.is_latest_status == true())
            ),
            # 全サイクルをロード（ほとんどの利用者は1-2サイクルのみなので許容）
            # ネストされたステータスは、is_latest_status=true または final_plan_signed のみ
            # （_calculate_next_plan_start_days_remaining で前サイクルの final_plan_signed が必要）
            selectinload(WelfareRecipient.support_plan_cycles).selectinload(
                SupportPlanCycle.statuses.and_(
                    or_(
                        SupportPlanStatus.is_latest_status == true(),
                        SupportPlanStatus.step_type == SupportPlanStep.final_plan_signed
                    )
                )
            ),
            # アセスメントPDFのみをロード（_calculate_next_plan_start_days_remaining で使用）
            selectinload(
                SupportPlanCycle.deliverables.and_(
                    PlanDeliverable.deliverable_type == DeliverableType.assessment_sheet
                )
            )
        )

        # --- 検索 ---
        if search_term:
            search_words = re.split(r'[\s　]+', search_term.strip())
            # セキュリティ: DoS対策として検索ワード数を制限（最大10ワード）
            MAX_SEARCH_WORDS = 10
            if len(search_words) > MAX_SEARCH_WORDS:
                search_words = search_words[:MAX_SEARCH_WORDS]

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
            if filters.get("has_assessment_due"):
                # アセスメント開始期限が設定されている利用者（未完了のみ）
                # 個別支援計画の5ステータス: アセスメント → 原案 → 担当者会議 → 本案 → モニタリング
                assessment_exists_subq = exists(
                    select(1).where(
                        and_(
                            SupportPlanStatus.plan_cycle_id == SupportPlanCycle.id,
                            SupportPlanStatus.step_type == SupportPlanStep.assessment,
                            SupportPlanStatus.completed == False,
                            SupportPlanStatus.due_date.isnot(None)
                        )
                    )
                )
                stmt = stmt.where(assessment_exists_subq)
            if filters.get("cycle_number"):
                stmt = stmt.where(func.coalesce(cycle_info_sq.c.cycle_count, 0) == filters["cycle_number"])
            if filters.get("status"):
                try:
                    status_enum = SupportPlanStep[filters["status"]]
                except KeyError:
                    pass  # 無効なステータスは無視
                else:
                    # EXISTS句でステータスをフィルタリング（Phase 3.2 optimization）
                    # JOIN + サブクエリよりも効率的（マッチした時点で早期終了）
                    stmt = stmt.where(
                        exists(
                            select(1).where(
                                and_(
                                    SupportPlanStatus.plan_cycle_id == SupportPlanCycle.id,
                                    SupportPlanStatus.is_latest_status == true(),
                                    SupportPlanStatus.step_type == status_enum
                                )
                            )
                        )
                    )

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

    async def count_filtered_summaries(
        self,
        db: AsyncSession,
        *,
        office_ids: List[uuid.UUID],
        filters: dict,
        search_term: Optional[str],
    ) -> int:
        """
        フィルタリング後の利用者数を取得します（ページネーション前の件数）。

        Args:
            db: データベースセッション
            office_ids: 対象事業所IDリスト
            filters: フィルター条件辞書
            search_term: 検索ワード

        Returns:
            フィルタリング後の利用者数
        """
        # 1. サイクル情報を統合取得するサブクエリ（count_filtered_summariesと同じロジック）
        cycle_info_sq = (
            select(
                SupportPlanCycle.welfare_recipient_id,
                func.count(SupportPlanCycle.id).label("cycle_count"),
                func.max(
                    case(
                        (SupportPlanCycle.is_latest_cycle == true(), SupportPlanCycle.id),
                        else_=None
                    )
                ).label("latest_cycle_id")
            )
            .group_by(SupportPlanCycle.welfare_recipient_id)
            .subquery("cycle_info_sq")
        )

        # 2. カウント用クエリの構築（DISTINCT WelfareRecipient.id）
        stmt = (
            select(func.count(func.distinct(WelfareRecipient.id)))
            .join(OfficeWelfareRecipient)
            .where(OfficeWelfareRecipient.office_id.in_(office_ids))
        )

        # --- JOINs（get_filtered_summariesと同じロジック） ---
        stmt = stmt.outerjoin(
            cycle_info_sq,
            WelfareRecipient.id == cycle_info_sq.c.welfare_recipient_id
        )
        stmt = stmt.outerjoin(
            SupportPlanCycle,
            SupportPlanCycle.id == cycle_info_sq.c.latest_cycle_id
        )

        # --- 検索条件（get_filtered_summariesと同じロジック） ---
        if search_term:
            search_words = re.split(r'[\s　]+', search_term.strip())
            # セキュリティ: DoS対策として検索ワード数を制限（最大10ワード）
            MAX_SEARCH_WORDS = 10
            if len(search_words) > MAX_SEARCH_WORDS:
                search_words = search_words[:MAX_SEARCH_WORDS]

            conditions = [or_(
                WelfareRecipient.last_name.ilike(f"%{word}%"),
                WelfareRecipient.first_name.ilike(f"%{word}%"),
                WelfareRecipient.last_name_furigana.ilike(f"%{word}%"),
                WelfareRecipient.first_name_furigana.ilike(f"%{word}%"),
            ) for word in search_words if word]
            if conditions:
                stmt = stmt.where(and_(*conditions))

        # --- フィルター条件（get_filtered_summariesと同じロジック） ---
        if filters:
            if filters.get("is_overdue"):
                stmt = stmt.where(SupportPlanCycle.next_renewal_deadline < date.today())
            if filters.get("is_upcoming"):
                stmt = stmt.where(SupportPlanCycle.next_renewal_deadline.between(date.today(), date.today() + timedelta(days=30)))
            if filters.get("has_assessment_due"):
                # アセスメント開始期限が設定されている利用者（未完了のみ）
                # 個別支援計画の5ステータス: アセスメント → 原案 → 担当者会議 → 本案 → モニタリング
                assessment_exists_subq = exists(
                    select(1).where(
                        and_(
                            SupportPlanStatus.plan_cycle_id == SupportPlanCycle.id,
                            SupportPlanStatus.step_type == SupportPlanStep.assessment,
                            SupportPlanStatus.completed == False,
                            SupportPlanStatus.due_date.isnot(None)
                        )
                    )
                )
                stmt = stmt.where(assessment_exists_subq)
            if filters.get("cycle_number"):
                stmt = stmt.where(func.coalesce(cycle_info_sq.c.cycle_count, 0) == filters["cycle_number"])
            if filters.get("status"):
                try:
                    status_enum = SupportPlanStep[filters["status"]]
                except KeyError:
                    pass  # 無効なステータスは無視
                else:
                    # EXISTS句でステータスをフィルタリング
                    stmt = stmt.where(
                        exists(
                            select(1).where(
                                and_(
                                    SupportPlanStatus.plan_cycle_id == SupportPlanCycle.id,
                                    SupportPlanStatus.is_latest_status == true(),
                                    SupportPlanStatus.step_type == status_enum
                                )
                            )
                        )
                    )

        # 実行してカウントを取得
        result = await db.execute(stmt)
        return result.scalar_one()

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
