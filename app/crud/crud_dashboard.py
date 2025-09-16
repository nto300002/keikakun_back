import uuid
from typing import List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload

from app.models.staff import Staff
from app.models.office import Office, OfficeStaff
from app.models.welfare_recipient import WelfareRecipient, OfficeWelfareRecipient
from app.models.support_plan_cycle import SupportPlanCycle


class CRUDDashboard:
    async def _ensure_db_open(self, db: Optional[AsyncSession] = None) -> None:
        """
        Ensure the provided DB session (or self.db) is available and not closed.
        Raise a clear Exception if missing/closed so callers/tests observe failures.
        """
        check_db = db if db is not None else getattr(self, "db", None)
        if check_db is None:
            raise Exception("Database session is required")
        # Only treat explicit boolean `closed == True` as closed.
        # Some test fixtures provide MagicMock objects whose `.closed` is not a bool,
        # so avoid treating non-bool values as "closed".
        closed_val = getattr(check_db, "closed", False)
        if isinstance(closed_val, bool) and closed_val:
            raise Exception("Database session is closed")

    async def get_staff_office(self, db: Optional[AsyncSession] = None, staff_id: Optional[uuid.UUID] = None):
        """
        スタッフのプライマリ事業所を取得。
        テストや呼び出し側が db をキーワード引数で渡すことを想定。
        """
        await self._ensure_db_open(db)
        query = (
            select(Staff, Office)
            .join(OfficeStaff, Staff.id == OfficeStaff.staff_id)
            .join(Office, Office.id == OfficeStaff.office_id)
            .where(
                and_(
                    Staff.id == staff_id,
                    OfficeStaff.is_primary == True
                )
            )
        )
        result = await db.execute(query)
        return result.one_or_none()

    async def get_office_recipients(self, db: AsyncSession, *, office_id: uuid.UUID) -> List[WelfareRecipient]:
        """オフィスに所属する利用者の情報を取得"""
        query = (
            select(WelfareRecipient)
            .join(OfficeWelfareRecipient, WelfareRecipient.id == OfficeWelfareRecipient.welfare_recipient_id)
            .where(OfficeWelfareRecipient.office_id == office_id)
            .options(
                selectinload(WelfareRecipient.support_plan_cycles).selectinload(SupportPlanCycle.statuses)
            )
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_latest_cycle(self, db: AsyncSession, *, welfare_recipient_id: uuid.UUID) -> Optional[SupportPlanCycle]:
        """最新の支援計画サイクルを取得"""
        query = (
            select(SupportPlanCycle)
            .where(
                and_(
                    SupportPlanCycle.welfare_recipient_id == welfare_recipient_id,
                    SupportPlanCycle.is_latest_cycle == True
                )
            )
            .options(selectinload(SupportPlanCycle.statuses))
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def count_office_recipients(self, db: AsyncSession, *, office_id: uuid.UUID) -> int:
        """オフィスに所属する利用者の数をカウント"""
        query = (
            select(func.count())
            .select_from(OfficeWelfareRecipient)
            .where(OfficeWelfareRecipient.office_id == office_id)
        )
        result = await db.execute(query)
        return result.scalar() or 0

    async def get_cycle_count_for_recipient(self, db: AsyncSession, *, welfare_recipient_id: uuid.UUID) -> int:
        """利用者の支援計画サイクルの数を取得"""
        query = (
            select(func.count())
            .select_from(SupportPlanCycle)
            .where(SupportPlanCycle.welfare_recipient_id == welfare_recipient_id)
        )
        result = await db.execute(query)
        return result.scalar() or 0

dashboard_crud = CRUDDashboard()
