from datetime import date, timedelta
from typing import Tuple
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, selectinload

from app.crud.crud_welfare_recipient import crud_welfare_recipient
from app.models.enums import CYCLE_STEPS, SupportPlanStep
from app.models.support_plan_cycle import SupportPlanCycle, SupportPlanStatus
from app.models.welfare_recipient import OfficeWelfareRecipient


class SupportPlanIntegrityService:
    """Support plan integrity checks and repair operations."""

    def check_data_integrity(self, db: Session, welfare_recipient_id: UUID) -> dict:
        result = {
            "is_valid": True,
            "missing_components": [],
            "issues": [],
        }

        try:
            welfare_recipient = crud_welfare_recipient.get(db, welfare_recipient_id)
            if not welfare_recipient:
                result["is_valid"] = False
                result["issues"].append("利用者情報が見つかりません")
                return result

            cycle_stmt = select(SupportPlanCycle).where(
                SupportPlanCycle.welfare_recipient_id == welfare_recipient_id,
                SupportPlanCycle.is_latest_cycle == True,
            )
            latest_cycle = db.execute(cycle_stmt).scalars().first()

            if not latest_cycle:
                result["is_valid"] = False
                result["missing_components"].append("支援計画サイクル")
                return result

            status_stmt = select(SupportPlanStatus).where(
                SupportPlanStatus.plan_cycle_id == latest_cycle.id
            )
            statuses = list(db.execute(status_stmt).scalars().all())
            existing_steps = [status.step_type for status in statuses]
            missing_steps = [step for step in CYCLE_STEPS if step not in existing_steps]

            if missing_steps:
                result["is_valid"] = False
                result["missing_components"].extend(
                    [f"ステップ_{step.value}" for step in missing_steps]
                )

            return result
        except Exception as exc:
            result["is_valid"] = False
            result["issues"].append(f"整合性チェック中にエラーが発生しました: {str(exc)}")
            return result

    def repair_support_plan_data(self, db: Session, welfare_recipient_id: UUID) -> bool:
        try:
            integrity_result = self.check_data_integrity(db, welfare_recipient_id)
            if integrity_result["is_valid"]:
                return True

            if "支援計画サイクル" in integrity_result["missing_components"]:
                self.create_initial_support_plan_sync(db, welfare_recipient_id)
            else:
                self.repair_missing_statuses(db, welfare_recipient_id)

            db.commit()
            return True
        except Exception:
            db.rollback()
            return False

    def create_initial_support_plan_sync(
        self,
        db: Session,
        welfare_recipient_id: UUID,
    ) -> None:
        office_stmt = select(OfficeWelfareRecipient.office_id).where(
            OfficeWelfareRecipient.welfare_recipient_id == welfare_recipient_id
        ).limit(1)
        office_id = db.execute(office_stmt).scalar_one_or_none()
        if not office_id:
            raise Exception("利用者の事業所情報が見つかりません")

        count_stmt = (
            select(func.count())
            .select_from(SupportPlanCycle)
            .where(SupportPlanCycle.welfare_recipient_id == welfare_recipient_id)
        )
        existing_cycles_count = db.execute(count_stmt).scalar_one()
        new_cycle_number = existing_cycles_count + 1

        cycle = SupportPlanCycle(
            welfare_recipient_id=welfare_recipient_id,
            office_id=office_id,
            is_latest_cycle=True,
            cycle_number=new_cycle_number,
            plan_cycle_start_date=date.today(),
            next_renewal_deadline=date.today() + timedelta(days=180),
        )
        db.add(cycle)
        db.flush()

        for i, step in enumerate(CYCLE_STEPS):
            db.add(
                SupportPlanStatus(
                    plan_cycle_id=cycle.id,
                    welfare_recipient_id=welfare_recipient_id,
                    office_id=office_id,
                    step_type=step,
                    completed=False,
                    is_latest_status=(i == 0),
                )
            )

        db.flush()

    def repair_missing_statuses(
        self,
        db: Session,
        welfare_recipient_id: UUID,
    ) -> None:
        cycle_stmt = select(SupportPlanCycle).where(
            SupportPlanCycle.welfare_recipient_id == welfare_recipient_id,
            SupportPlanCycle.is_latest_cycle == True,
        )
        latest_cycle = db.execute(cycle_stmt).scalars().first()
        if not latest_cycle:
            raise Exception("最新の支援計画サイクルが見つかりません")

        status_stmt = select(SupportPlanStatus).where(
            SupportPlanStatus.plan_cycle_id == latest_cycle.id
        )
        existing_statuses = list(db.execute(status_stmt).scalars().all())
        existing_steps = [status.step_type for status in existing_statuses]

        for step in CYCLE_STEPS:
            if step not in existing_steps:
                db.add(
                    SupportPlanStatus(
                        plan_cycle_id=latest_cycle.id,
                        welfare_recipient_id=latest_cycle.welfare_recipient_id,
                        office_id=latest_cycle.office_id,
                        step_type=step,
                        completed=False,
                        completed_at=None,
                    )
                )

    def check_and_repair_plan_data(
        self,
        db: Session,
        welfare_recipient_id: UUID,
    ) -> Tuple[bool, str]:
        try:
            cycle_stmt = select(SupportPlanCycle).where(
                SupportPlanCycle.welfare_recipient_id == welfare_recipient_id,
                SupportPlanCycle.is_latest_cycle == True,
            )
            latest_cycle = db.execute(cycle_stmt).scalars().first()

            if not latest_cycle:
                self.create_initial_support_plan_sync(db, welfare_recipient_id)
                try:
                    db.commit()
                except Exception:
                    db.rollback()
                return True, "初期支援計画サイクルとステータスを作成しました"

            try:
                self.repair_missing_statuses(db, welfare_recipient_id)
                try:
                    db.commit()
                except Exception:
                    db.rollback()
                return True, "不足しているステータスを確認・修復しました"
            except Exception as exc:
                try:
                    db.rollback()
                except Exception:
                    pass
                return False, f"修復中にエラー: {exc}"

        except Exception as exc:
            try:
                db.rollback()
            except Exception:
                pass
            return False, f"チェック実行中にエラー: {exc}"

    async def repair_recipient_support_plan(
        self,
        *,
        db: AsyncSession,
        welfare_recipient_id: UUID,
        performed_by: UUID | None = None,
    ) -> Tuple[bool, str]:
        try:
            office_stmt = select(OfficeWelfareRecipient.office_id).where(
                OfficeWelfareRecipient.welfare_recipient_id == welfare_recipient_id
            ).limit(1)
            office_result = await db.execute(office_stmt)
            office_id = office_result.scalar_one_or_none()

            if not office_id:
                return False, "利用者の事業所情報が見つかりません"

            stmt = (
                select(SupportPlanCycle)
                .where(
                    SupportPlanCycle.welfare_recipient_id == welfare_recipient_id,
                    SupportPlanCycle.is_latest_cycle == True,
                )
                .options(selectinload(SupportPlanCycle.statuses))
            )
            res = await db.execute(stmt)
            latest_cycle = res.scalars().first()

            if not latest_cycle:
                cycle = SupportPlanCycle(
                    welfare_recipient_id=welfare_recipient_id,
                    office_id=office_id,
                    is_latest_cycle=True,
                    plan_cycle_start_date=date.today(),
                    next_renewal_deadline=date.today(),
                )
                db.add(cycle)
                await db.flush()

                for step in self.required_initial_steps:
                    db.add(
                        SupportPlanStatus(
                            plan_cycle_id=cycle.id,
                            welfare_recipient_id=welfare_recipient_id,
                            office_id=office_id,
                            step_type=step,
                            completed=False,
                        )
                    )
                await db.flush()
                await db.commit()
                return True, "初期支援計画サイクルとステータスを作成しました"

            created = await self.repair_missing_statuses_async(
                db=db,
                welfare_recipient_id=welfare_recipient_id,
                latest_cycle=latest_cycle,
            )
            if created > 0:
                await db.commit()
                return True, f"不足していた {created} 件のステータスを作成しました"

            return False, "データは正常です"
        except Exception as exc:
            try:
                await db.rollback()
            except Exception:
                pass
            return False, f"修復中にエラー: {exc}"

    async def repair_missing_statuses_async(
        self,
        *,
        db: AsyncSession,
        welfare_recipient_id: UUID,
        latest_cycle: SupportPlanCycle,
    ) -> int:
        if not latest_cycle:
            raise Exception("最新サイクルが見つかりません")

        existing_steps = [status.step_type for status in latest_cycle.statuses]
        to_create = [
            step for step in self.required_initial_steps if step not in existing_steps
        ]

        for step in to_create:
            db.add(
                SupportPlanStatus(
                    plan_cycle_id=latest_cycle.id,
                    welfare_recipient_id=latest_cycle.welfare_recipient_id,
                    office_id=latest_cycle.office_id,
                    step_type=step,
                    completed=False,
                )
            )

        if to_create:
            await db.flush()

        return len(to_create)

    @property
    def required_initial_steps(self) -> list[SupportPlanStep]:
        return [
            SupportPlanStep.assessment,
            SupportPlanStep.draft_plan,
            SupportPlanStep.staff_meeting,
        ]
