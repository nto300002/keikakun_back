from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from pydantic import BaseModel

from app.crud.base import CRUDBase
from app.models.support_plan_cycle import SupportPlanCycle


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


crud_support_plan_cycle = CRUDSupportPlanCycle(SupportPlanCycle)
