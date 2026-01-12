import uuid
import logging
from datetime import date, timedelta
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.models.enums import BillingStatus, SupportPlanStep, DeliverableType
from app.models.welfare_recipient import WelfareRecipient
from app.models.support_plan_cycle import SupportPlanCycle
from app.schemas.dashboard import DashboardData, DashboardSummary

logger = logging.getLogger(__name__)


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

    def _calculate_next_plan_start_days_remaining(
        self,
        recipient: WelfareRecipient,
        latest_cycle: Optional[SupportPlanCycle]
    ) -> Optional[int]:
        """次回計画開始までの残り日数を計算

        条件:
        - is_latest_cycle=true（latest_cycleが存在）
        - アセスメントPDFがアップロードされていない
        - next_plan_start_dateが設定されている（NULLの場合はデフォルト7日を使用）
        - 1サイクル目: plan_cycle_start_dateが設定されている（NULLの場合はcreated_atをフォールバック）
        - 2サイクル目以降: 前サイクルのfinal_plan_signed完了日がある

        計算式:
        - next_plan_start_days = next_plan_start_date または 7（デフォルト）
        - 1サイクル目: 期限日 = サイクル開始日（またはサイクル作成日） + next_plan_start_days
        - 2サイクル目以降: 期限日 = 前サイクルのfinal_plan_signed完了日 + next_plan_start_days
        - 残り日数 = 期限日 - 現在日付

        戻り値:
        - 残り日数（マイナスの場合は期限切れ）
        - 条件を満たさない場合はNone
        """
        logger.info(f"[NEXT_PLAN_START_DEBUG] recipient: {recipient.last_name} {recipient.first_name}, cycle: {latest_cycle.cycle_number if latest_cycle else 'None'}")

        # 条件1: latest_cycleが存在し、is_latest_cycle=true
        if not latest_cycle or not latest_cycle.is_latest_cycle:
            logger.info(f"[NEXT_PLAN_START_DEBUG] 条件1失敗: latest_cycle={latest_cycle}, is_latest={latest_cycle.is_latest_cycle if latest_cycle else 'N/A'}")
            return None

        logger.info(f"[NEXT_PLAN_START_DEBUG] next_plan_start_date: {latest_cycle.next_plan_start_date}")

        # 条件2: next_plan_start_dateが設定されている（NULLの場合はデフォルト7日を使用）
        next_plan_start_days = latest_cycle.next_plan_start_date if latest_cycle.next_plan_start_date is not None else 7
        if next_plan_start_days <= 0:
            logger.info(f"[NEXT_PLAN_START_DEBUG] 条件2失敗: next_plan_start_date is invalid: {next_plan_start_days}")
            return None

        if latest_cycle.next_plan_start_date is None:
            logger.info(f"[NEXT_PLAN_START_DEBUG] next_plan_start_dateがNULL、デフォルト7日を使用")

        # 条件3: アセスメントPDFがアップロードされていない
        if hasattr(latest_cycle, 'deliverables') and latest_cycle.deliverables:
            has_assessment_pdf = any(
                d.deliverable_type == DeliverableType.assessment_sheet
                for d in latest_cycle.deliverables
            )
            logger.info(f"[NEXT_PLAN_START_DEBUG] deliverables count: {len(latest_cycle.deliverables)}, has_assessment: {has_assessment_pdf}")
            if has_assessment_pdf:
                logger.info(f"[NEXT_PLAN_START_DEBUG] 条件3失敗: アセスメントPDF既にアップロード済み")
                return None

        # 条件4: 基準日を取得
        # 1サイクル目の場合: サイクル開始日を使用（NULLの場合はcreated_atをフォールバック）
        # 2サイクル目以降: 前サイクルのfinal_plan_signed完了日を使用
        if latest_cycle.cycle_number == 1:
            logger.info(f"[NEXT_PLAN_START_DEBUG] サイクル1: plan_cycle_start_date={latest_cycle.plan_cycle_start_date}, created_at={latest_cycle.created_at}")
            # 1サイクル目: サイクル開始日を基準にする
            if latest_cycle.plan_cycle_start_date:
                base_date = latest_cycle.plan_cycle_start_date
                logger.info(f"[NEXT_PLAN_START_DEBUG] 使用base_date (plan_cycle_start_date): {base_date}")
            elif latest_cycle.created_at:
                # フォールバック: plan_cycle_start_dateがNULLの場合、サイクル作成日を使用
                base_date = latest_cycle.created_at.date()
                logger.info(f"[NEXT_PLAN_START_DEBUG] 使用base_date (created_at fallback): {base_date}")
            else:
                logger.info(f"[NEXT_PLAN_START_DEBUG] 条件4失敗: plan_cycle_start_dateもcreated_atもNULL")
                return None
        else:
            # 2サイクル目以降: 前サイクルのfinal_plan_signed完了日を基準にする
            if not hasattr(recipient, 'support_plan_cycles') or not recipient.support_plan_cycles:
                return None

            # 前サイクルを取得（cycle_number = latest_cycle.cycle_number - 1）
            prev_cycle = next(
                (c for c in recipient.support_plan_cycles if c.cycle_number == latest_cycle.cycle_number - 1),
                None
            )

            if not prev_cycle:
                return None

            # 前サイクルのfinal_plan_signedステータスを取得
            if not hasattr(prev_cycle, 'statuses') or not prev_cycle.statuses:
                return None

            final_plan_status = next(
                (s for s in prev_cycle.statuses if s.step_type == SupportPlanStep.final_plan_signed),
                None
            )

            if not final_plan_status or not final_plan_status.completed_at:
                return None

            base_date = final_plan_status.completed_at.date()

        # 期限日を計算
        deadline = base_date + timedelta(days=next_plan_start_days)

        # 残り日数を計算
        days_remaining = (deadline - date.today()).days

        logger.info(f"[NEXT_PLAN_START_DEBUG] 計算結果: base_date={base_date}, next_plan_start_days={next_plan_start_days}日, deadline={deadline}, days_remaining={days_remaining}")

        return days_remaining

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
            'next_plan_start_date': latest_cycle.next_plan_start_date if latest_cycle else None,
            'next_plan_start_days_remaining': None,
            'next_renewal_deadline': None,
        }

        # 次回計画開始までの残り日数を計算
        summary['next_plan_start_days_remaining'] = self._calculate_next_plan_start_days_remaining(
            recipient, latest_cycle
        )

        # 次回更新日の計算（サイクルがある場合）
        if latest_cycle and hasattr(latest_cycle, 'start_date') and latest_cycle.start_date:
            # 一般的に支援計画は6ヶ月または12ヶ月のサイクル
            renewal_months = 12  # デフォルト12ヶ月
            next_renewal = latest_cycle.start_date + timedelta(days=renewal_months * 30)
            summary['next_renewal_deadline'] = next_renewal.date()

        return summary