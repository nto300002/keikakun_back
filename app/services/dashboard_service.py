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
        """最新のステップを取得

        is_latest_status == True の status を基準に現在のステップを決定する。
        フォールバック: is_latest_status が存在しない場合は assessment を返す。
        """
        if not cycle or not hasattr(cycle, 'statuses') or not cycle.statuses:
            return None

        # is_latest_status == True のステータスを優先
        latest_status = next((s for s in cycle.statuses if s.is_latest_status), None)
        if latest_status:
            return latest_status.step_type

        # フォールバック: is_latest_status が存在しない場合は assessment
        return SupportPlanStep.assessment

    def _calculate_monitoring_due_date(self, cycle: Optional[SupportPlanCycle]) -> Optional[date]:
        """モニタリング期限を取得

        is_latest_status == True かつ step_type == monitoring のステータスから due_date を取得する。
        due_date が設定されていない場合は None を返す。
        """
        if not cycle or not hasattr(cycle, 'statuses') or not cycle.statuses:
            return None

        # is_latest_status == True かつ step_type == monitoring のステータスを探す
        latest_monitoring_status = next(
            (s for s in cycle.statuses if s.is_latest_status and s.step_type == SupportPlanStep.monitoring),
            None
        )

        if not latest_monitoring_status:
            return None

        # due_date が設定されていればそれを返す
        return latest_monitoring_status.due_date

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
            'monitoring_deadline': latest_cycle.monitoring_deadline if latest_cycle else None,
            'next_renewal_deadline': None,
        }

        # 次回更新日の計算（サイクルがある場合）
        if latest_cycle and hasattr(latest_cycle, 'start_date') and latest_cycle.start_date:
            # 一般的に支援計画は6ヶ月または12ヶ月のサイクル
            renewal_months = 12  # デフォルト12ヶ月
            next_renewal = latest_cycle.start_date + timedelta(days=renewal_months * 30)
            summary['next_renewal_deadline'] = next_renewal.date()

        return summary