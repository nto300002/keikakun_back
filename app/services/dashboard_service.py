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

    def _get_latest_step(self, cycle: Optional[SupportPlanCycle]) -> Optional[SupportPlanStep]:
        """最新のステップを取得"""
        if not cycle or not hasattr(cycle, 'statuses') or not cycle.statuses:
            return None

        step_order = [
            SupportPlanStep.assessment,
            SupportPlanStep.draft_plan,
            SupportPlanStep.staff_meeting,
            SupportPlanStep.final_plan_signed,
            SupportPlanStep.monitoring,
        ]
        completed_steps = {status.step_type for status in cycle.statuses if status.completed}

        for step in step_order:
            if step not in completed_steps:
                return step
        return SupportPlanStep.monitoring

    def _calculate_monitoring_due_date(self, cycle: Optional[SupportPlanCycle]) -> Optional[date]:
        """モニタリング期限を計算"""
        if not cycle or not hasattr(cycle, 'statuses') or not cycle.statuses:
            return None

        monitoring_status = next((s for s in cycle.statuses if s.step_type == SupportPlanStep.monitoring), None)
        if not monitoring_status or monitoring_status.completed:
            return None

        final_plan_signed_status = next((s for s in cycle.statuses if s.step_type == SupportPlanStep.final_plan_signed and s.completed), None)
        if not final_plan_signed_status or not final_plan_signed_status.completed_at:
            return None

        deadline_days = monitoring_status.monitoring_deadline or 7
        return (final_plan_signed_status.completed_at + timedelta(days=deadline_days)).date()

    def _get_max_user_count(self, billing_status: BillingStatus) -> int:
        """最大利用者数を取得"""
        if billing_status == BillingStatus.free:
            return 5
        elif billing_status == BillingStatus.active:
            return 100
        return 0

    def _create_recipient_summary(self, recipient: WelfareRecipient) -> dict:
        """利用者サマリーを作成"""
        # 最新のサイクルを取得
        latest_cycle = None
        if hasattr(recipient, 'support_plan_cycles') and recipient.support_plan_cycles:
            latest_cycle = max(recipient.support_plan_cycles, key=lambda c: c.cycle_number)

        # 基本情報
        summary = {
            'id': str(recipient.id),
            'full_name': f"{recipient.last_name} {recipient.first_name}",
            'furigana': f"{recipient.last_name_furigana} {recipient.first_name_furigana}",
            'current_cycle_number': latest_cycle.cycle_number if latest_cycle else 0,
            'latest_step': self._get_latest_step(latest_cycle),
            'monitoring_due_date': self._calculate_monitoring_due_date(latest_cycle),
            'next_renewal_deadline': None,
        }

        # 次回更新日の計算（サイクルがある場合）
        if latest_cycle and hasattr(latest_cycle, 'start_date') and latest_cycle.start_date:
            # 一般的に支援計画は6ヶ月または12ヶ月のサイクル
            renewal_months = 12  # デフォルト12ヶ月
            next_renewal = latest_cycle.start_date + timedelta(days=renewal_months * 30)
            summary['next_renewal_deadline'] = next_renewal.date()

        return summary