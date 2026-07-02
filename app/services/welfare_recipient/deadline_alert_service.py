import os
from datetime import date, timedelta
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.enums import DeliverableType
from app.models.support_plan_cycle import SupportPlanCycle
from app.models.welfare_recipient import WelfareRecipient
from app.schemas.deadline_alert import DeadlineAlertItem, DeadlineAlertResponse


class DeadlineAlertService:
    """Deadline alert queries and response shaping."""

    async def get_deadline_alerts(
        self,
        *,
        db: AsyncSession,
        office_id: UUID,
        threshold_days: int = 30,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> DeadlineAlertResponse:
        today = date.today()
        threshold_date = today + timedelta(days=threshold_days)
        is_testing = os.getenv("TESTING") == "1"

        alerts: List[DeadlineAlertItem] = []

        renewal_conditions = [
            SupportPlanCycle.office_id == office_id,
            SupportPlanCycle.is_latest_cycle == True,
            SupportPlanCycle.next_renewal_deadline.isnot(None),
            SupportPlanCycle.next_renewal_deadline <= threshold_date,
        ]
        if not is_testing:
            renewal_conditions.append(WelfareRecipient.is_test_data == False)

        renewal_stmt = (
            select(WelfareRecipient, SupportPlanCycle)
            .join(
                SupportPlanCycle,
                SupportPlanCycle.welfare_recipient_id == WelfareRecipient.id,
            )
            .where(*renewal_conditions)
            .order_by(
                SupportPlanCycle.next_renewal_deadline.asc(),
                WelfareRecipient.last_name.asc(),
                WelfareRecipient.first_name.asc(),
            )
        )

        renewal_result = await db.execute(renewal_stmt)
        alerts.extend(
            self._build_renewal_alert_item(
                recipient=recipient,
                cycle=cycle,
                today=today,
            )
            for recipient, cycle in renewal_result.all()
        )

        assessment_conditions = [
            SupportPlanCycle.office_id == office_id,
            SupportPlanCycle.is_latest_cycle == True,
        ]
        if not is_testing:
            assessment_conditions.append(WelfareRecipient.is_test_data == False)

        assessment_stmt = (
            select(WelfareRecipient, SupportPlanCycle)
            .join(
                SupportPlanCycle,
                SupportPlanCycle.welfare_recipient_id == WelfareRecipient.id,
            )
            .options(selectinload(SupportPlanCycle.deliverables))
            .where(*assessment_conditions)
            .order_by(
                WelfareRecipient.last_name.asc(),
                WelfareRecipient.first_name.asc(),
            )
        )

        assessment_result = await db.execute(assessment_stmt)
        for recipient, cycle in assessment_result.all():
            if not self._has_assessment_pdf(cycle):
                alerts.append(
                    self._build_assessment_incomplete_alert_item(
                        recipient=recipient,
                        cycle=cycle,
                    )
                )

        total = len(alerts)
        if limit is not None:
            alerts = alerts[offset:offset + limit]

        return DeadlineAlertResponse(alerts=alerts, total=total)

    async def get_deadline_alerts_batch(
        self,
        *,
        db: AsyncSession,
        office_ids: List[UUID],
        threshold_days: int = 30,
    ) -> Dict[UUID, DeadlineAlertResponse]:
        if not office_ids:
            return {}

        today = date.today()
        threshold_date = today + timedelta(days=threshold_days)
        is_testing = os.getenv("TESTING") == "1"

        renewal_conditions = [
            SupportPlanCycle.office_id.in_(office_ids),
            SupportPlanCycle.is_latest_cycle == True,
            SupportPlanCycle.next_renewal_deadline.isnot(None),
            SupportPlanCycle.next_renewal_deadline <= threshold_date,
        ]
        if not is_testing:
            renewal_conditions.append(WelfareRecipient.is_test_data == False)

        renewal_stmt = (
            select(WelfareRecipient, SupportPlanCycle)
            .join(
                SupportPlanCycle,
                SupportPlanCycle.welfare_recipient_id == WelfareRecipient.id,
            )
            .where(*renewal_conditions)
            .order_by(
                SupportPlanCycle.office_id.asc(),
                SupportPlanCycle.next_renewal_deadline.asc(),
                WelfareRecipient.last_name.asc(),
                WelfareRecipient.first_name.asc(),
            )
        )

        renewal_result = await db.execute(renewal_stmt)

        assessment_conditions = [
            SupportPlanCycle.office_id.in_(office_ids),
            SupportPlanCycle.is_latest_cycle == True,
        ]
        if not is_testing:
            assessment_conditions.append(WelfareRecipient.is_test_data == False)

        assessment_stmt = (
            select(WelfareRecipient, SupportPlanCycle)
            .join(
                SupportPlanCycle,
                SupportPlanCycle.welfare_recipient_id == WelfareRecipient.id,
            )
            .options(selectinload(SupportPlanCycle.deliverables))
            .where(*assessment_conditions)
            .order_by(
                SupportPlanCycle.office_id.asc(),
                WelfareRecipient.last_name.asc(),
                WelfareRecipient.first_name.asc(),
            )
        )

        assessment_result = await db.execute(assessment_stmt)
        alerts_by_office: Dict[UUID, List[DeadlineAlertItem]] = {
            office_id: [] for office_id in office_ids
        }

        for recipient, cycle in renewal_result.all():
            alerts_by_office[cycle.office_id].append(
                self._build_renewal_alert_item(
                    recipient=recipient,
                    cycle=cycle,
                    today=today,
                )
            )

        for recipient, cycle in assessment_result.all():
            if not self._has_assessment_pdf(cycle):
                alerts_by_office[cycle.office_id].append(
                    self._build_assessment_incomplete_alert_item(
                        recipient=recipient,
                        cycle=cycle,
                    )
                )

        return {
            office_id: DeadlineAlertResponse(alerts=alerts, total=len(alerts))
            for office_id, alerts in alerts_by_office.items()
        }

    def _build_renewal_alert_item(
        self,
        *,
        recipient: WelfareRecipient,
        cycle: SupportPlanCycle,
        today: date,
    ) -> DeadlineAlertItem:
        days_remaining = (cycle.next_renewal_deadline - today).days
        full_name = f"{recipient.last_name} {recipient.first_name}"

        if days_remaining <= 0:
            alert_type = "renewal_overdue"
            message = f"!{full_name}の更新期限が過ぎています!"
        else:
            alert_type = "renewal_deadline"
            message = f"{full_name}の更新期限まで残り{days_remaining}日"

        return DeadlineAlertItem(
            id=str(recipient.id),
            full_name=full_name,
            alert_type=alert_type,
            message=message,
            next_renewal_deadline=cycle.next_renewal_deadline,
            days_remaining=days_remaining,
            current_cycle_number=cycle.cycle_number,
        )

    def _build_assessment_incomplete_alert_item(
        self,
        *,
        recipient: WelfareRecipient,
        cycle: SupportPlanCycle,
    ) -> DeadlineAlertItem:
        return DeadlineAlertItem(
            id=str(recipient.id),
            full_name=f"{recipient.last_name} {recipient.first_name}",
            alert_type="assessment_incomplete",
            message=f"{recipient.last_name} {recipient.first_name}のアセスメントが完了していません",
            next_renewal_deadline=None,
            days_remaining=None,
            current_cycle_number=cycle.cycle_number,
        )

    def _has_assessment_pdf(self, cycle: SupportPlanCycle) -> bool:
        if not getattr(cycle, "deliverables", None):
            return False

        return any(
            deliverable.deliverable_type == DeliverableType.assessment_sheet
            for deliverable in cycle.deliverables
        )
