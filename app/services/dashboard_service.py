import uuid
from datetime import date, timedelta
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.models.enums import BillingStatus, SupportPlanStep
from app.models.welfare_recipient import WelfareRecipient
from app.models.support_plan_cycle import SupportPlanCycle
from app.schemas.dashboard import DashboardData, DashboardSummary


class DashboardService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.crud = crud

    async def get_dashboard_data(self, staff_id: uuid.UUID) -> Optional[DashboardData]:
        """ダッシュボード情報を取得"""
        staff_office_result = await self.crud.staff.get_staff_with_primary_office(db=self.db, staff_id=staff_id)
        if not staff_office_result:
            return None

        staff, office = staff_office_result

        recipients = await self.crud.office.get_recipients_by_office_id(db=self.db, office_id=office.id)
        current_user_count = len(recipients)
        max_user_count = self._get_max_user_count(office.billing_status)

        recipient_summaries = []
        for recipient in recipients:
            summary = await self._create_recipient_summary(recipient)
            recipient_summaries.append(summary)

        return DashboardData(
            staff_name=staff.name,
            staff_role=staff.role,
            office_id=office.id,
            office_name=office.name,
            current_user_count=current_user_count,
            max_user_count=max_user_count,
            billing_status=office.billing_status,
            recipients=recipient_summaries
        )

    async def _create_recipient_summary(self, recipient: WelfareRecipient) -> DashboardSummary:
        """ダッシュボード:利用者情報"""
        full_name = f"{recipient.last_name} {recipient.first_name}"
        cycle_number = await self._get_cycle_number(recipient.id)
        latest_cycle = await self.crud.dashboard.get_latest_cycle(db=self.db, welfare_recipient_id=recipient.id)
        
        latest_step = None
        next_renewal_deadline = None
        monitoring_due_date = None

        if latest_cycle:
            latest_step = self._get_latest_step(latest_cycle)
            next_renewal_deadline = latest_cycle.next_renewal_deadline
            monitoring_due_date = self._calculate_monitoring_due_date(latest_cycle)

        full_furigana = f"{recipient.last_name_furigana} {recipient.first_name_furigana}"

        return DashboardSummary(
            id=str(recipient.id),
            full_name=full_name,
            furigana=full_furigana,
            current_cycle_number=cycle_number,
            latest_step=latest_step,
            next_renewal_deadline=next_renewal_deadline,
            monitoring_due_date=monitoring_due_date
        )

    async def _get_cycle_number(self, welfare_recipient_id: uuid.UUID) -> int:
        """利用者の支援計画サイクルの数を取得"""
        return await self.crud.dashboard.get_cycle_count_for_recipient(db=self.db, welfare_recipient_id=welfare_recipient_id)

    def _get_latest_step(self, cycle: SupportPlanCycle) -> Optional[SupportPlanStep]:
        """最新のステップを取得"""
        if not hasattr(cycle, 'statuses') or not cycle.statuses:
            return SupportPlanStep.assessment

        step_order = [SupportPlanStep.assessment, SupportPlanStep.draft_plan, SupportPlanStep.staff_meeting, SupportPlanStep.final_plan_signed, SupportPlanStep.monitoring]
        completed_steps = {status.step_type for status in cycle.statuses if status.completed}

        for step in step_order:
            if step not in completed_steps:
                return step
        return SupportPlanStep.monitoring

    def _calculate_monitoring_due_date(self, cycle: SupportPlanCycle) -> Optional[date]:
        """モニタリング期限を計算"""
        if not hasattr(cycle, 'statuses') or not cycle.statuses:
            return None

        monitoring_status = next((s for s in cycle.statuses if s.step_type == SupportPlanStep.monitoring), None)
        if not monitoring_status or monitoring_status.completed:
            return None

        deadline_days = monitoring_status.monitoring_deadline or 7
        previous_step_completion = next((s.completed_at for s in cycle.statuses if s.step_type == SupportPlanStep.final_plan_signed and s.completed and s.completed_at), None)

        if previous_step_completion:
            return (previous_step_completion + timedelta(days=deadline_days)).date()
        return None

    def _get_max_user_count(self, billing_status: BillingStatus) -> int:
        """最大利用者数を取得"""
        if billing_status == BillingStatus.free:
            return 5
        elif billing_status == BillingStatus.active:
            return 100
        return 0