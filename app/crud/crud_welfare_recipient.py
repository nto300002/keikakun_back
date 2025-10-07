from typing import List, Optional
from uuid import uuid4, UUID
import logging
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.crud.base import CRUDBase
from app.models.welfare_recipient import (
    WelfareRecipient,
    ServiceRecipientDetail,
    EmergencyContact,
    DisabilityStatus,
    DisabilityDetail,
    OfficeWelfareRecipient
)
from app.schemas.welfare_recipient import (
    WelfareRecipientCreate,
    WelfareRecipientUpdate,
    UserRegistrationRequest
)


class CRUDWelfareRecipient(CRUDBase[WelfareRecipient, WelfareRecipientCreate, WelfareRecipientUpdate]):

    async def get_with_office_associations(self, db: AsyncSession, recipient_id: UUID) -> Optional[WelfareRecipient]:
        """Get welfare recipient with only office associations (lightweight for delete/permission checks)"""
        stmt = (
            select(WelfareRecipient)
            .where(WelfareRecipient.id == recipient_id)
            .options(
                selectinload(WelfareRecipient.office_associations)
            )
        )
        result = await db.execute(stmt)
        return result.scalars().first()

    async def get_with_details(self, db: AsyncSession, recipient_id: UUID) -> Optional[WelfareRecipient]:
        """Get welfare recipient with all related details"""
        stmt = (
            select(WelfareRecipient)
            .where(WelfareRecipient.id == recipient_id)
            .options(
                selectinload(WelfareRecipient.detail).selectinload(ServiceRecipientDetail.emergency_contacts),
                selectinload(WelfareRecipient.disability_status).selectinload(DisabilityStatus.details),
                selectinload(WelfareRecipient.office_associations)  # 遅延読み込みを防ぐため追加
            )
        )
        result = await db.execute(stmt)
        return result.scalars().first()

    async def get_by_office(self, db: AsyncSession, office_id: UUID, skip: int = 0, limit: int = 100) -> List[WelfareRecipient]:
        """Get all welfare recipients for a specific office"""
        stmt = (
            select(WelfareRecipient)
            .join(OfficeWelfareRecipient)
            .where(OfficeWelfareRecipient.office_id == office_id)
            .options(
                selectinload(WelfareRecipient.detail).selectinload(ServiceRecipientDetail.emergency_contacts),
                selectinload(WelfareRecipient.disability_status).selectinload(DisabilityStatus.details)
            )
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def create_related_data(
        self,
        db: AsyncSession,
        *,
        welfare_recipient: WelfareRecipient,
        registration_data: UserRegistrationRequest,
        office_id: UUID
    ) -> None:
        """Create related data for a welfare recipient."""
        contact_address = registration_data.contact_address
        detail = ServiceRecipientDetail(
            welfare_recipient_id=welfare_recipient.id,
            address=contact_address.address,
            form_of_residence=contact_address.formOfResidence,
            form_of_residence_other_text=contact_address.formOfResidenceOtherText,
            means_of_transportation=contact_address.meansOfTransportation,
            means_of_transportation_other_text=contact_address.meansOfTransportationOtherText,
            tel=contact_address.tel
        )
        db.add(detail)
        await db.flush()

        for contact_data in registration_data.emergency_contacts:
            emergency_contact = EmergencyContact(
                service_recipient_detail_id=detail.id,
                first_name=contact_data.first_name,
                last_name=contact_data.last_name,
                first_name_furigana=contact_data.first_name_furigana,
                last_name_furigana=contact_data.last_name_furigana,
                relationship=contact_data.relationship,
                tel=contact_data.tel,
                address=contact_data.address,
                notes=contact_data.notes,
                priority=contact_data.priority
            )
            db.add(emergency_contact)

        disability_info = registration_data.disability_info
        disability_status = DisabilityStatus(
            welfare_recipient_id=welfare_recipient.id,
            disability_or_disease_name=disability_info.disabilityOrDiseaseName,
            livelihood_protection=disability_info.livelihoodProtection,
            special_remarks=disability_info.specialRemarks
        )
        db.add(disability_status)
        await db.flush()

        for detail_data in registration_data.disability_details:
            disability_detail = DisabilityDetail(
                disability_status_id=disability_status.id,
                category=detail_data.category,
                grade_or_level=detail_data.grade_or_level,
                physical_disability_type=detail_data.physical_disability_type,
                physical_disability_type_other_text=detail_data.physical_disability_type_other_text,
                application_status=detail_data.application_status
            )
            db.add(disability_detail)

        office_association = OfficeWelfareRecipient(
            welfare_recipient_id=welfare_recipient.id,
            office_id=office_id
        )
        db.add(office_association)

    async def search_by_name(self, db: AsyncSession, office_id: UUID, search_term: str, skip: int = 0, limit: int = 100) -> List[WelfareRecipient]:
        """Search welfare recipients by name (supports both kanji and furigana)"""
        search_pattern = f"%{search_term}%"

        stmt = (
            select(WelfareRecipient)
            .join(OfficeWelfareRecipient)
            .where(
                OfficeWelfareRecipient.office_id == office_id,
                (WelfareRecipient.first_name.ilike(search_pattern)) |
                (WelfareRecipient.last_name.ilike(search_pattern)) |
                (WelfareRecipient.first_name_furigana.ilike(search_pattern)) |
                (WelfareRecipient.last_name_furigana.ilike(search_pattern))
            )
            .options(
                selectinload(WelfareRecipient.detail).selectinload(ServiceRecipientDetail.emergency_contacts),
                selectinload(WelfareRecipient.disability_status).selectinload(DisabilityStatus.details)
            )
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def update_comprehensive(
        self,
        db: AsyncSession,
        recipient_id: UUID,
        registration_data: UserRegistrationRequest
    ) -> Optional[WelfareRecipient]:
        """Update welfare recipient with comprehensive data"""
        welfare_recipient = await self.get(db, recipient_id)
        if not welfare_recipient:
            return None

        # Update basic info
        basic_info = registration_data.basic_info
        welfare_recipient.first_name = basic_info.firstName
        welfare_recipient.last_name = basic_info.lastName
        welfare_recipient.first_name_furigana = basic_info.firstNameFurigana
        welfare_recipient.last_name_furigana = basic_info.lastNameFurigana
        welfare_recipient.birth_day = basic_info.birthDay
        welfare_recipient.gender = basic_info.gender

        # Update related data if exists
        # TODO: Implement full update for related data (details, contacts, etc.)
        if welfare_recipient.detail:
            contact_address = registration_data.contact_address
            welfare_recipient.detail.address = contact_address.address
            welfare_recipient.detail.form_of_residence = contact_address.formOfResidence
            welfare_recipient.detail.tel = contact_address.tel
            welfare_recipient.detail.means_of_transportation = contact_address.meansOfTransportation

        await db.commit()
        await db.refresh(welfare_recipient)

        return await self.get_with_details(db, recipient_id)

    async def delete_with_cascade(self, db: AsyncSession, recipient_id: UUID) -> bool:
        """Delete welfare recipient and all related data"""
        from sqlalchemy import delete as sql_delete

        try:
            # Delete related records first to avoid foreign key constraint violations

            # 1. Delete office associations (office_welfare_recipients)
            await db.execute(
                sql_delete(OfficeWelfareRecipient).where(
                    OfficeWelfareRecipient.welfare_recipient_id == recipient_id
                )
            )

            # 2. Delete support plan cycles and their related data
            from app.models.support_plan_cycle import SupportPlanCycle, SupportPlanStatus, PlanDeliverable

            # Get all support plan cycles for this recipient
            cycles_stmt = select(SupportPlanCycle.id).where(
                SupportPlanCycle.welfare_recipient_id == recipient_id
            )
            cycles_result = await db.execute(cycles_stmt)
            cycle_ids = [row[0] for row in cycles_result.fetchall()]

            if cycle_ids:
                # Delete plan deliverables first (foreign key constraint)
                await db.execute(
                    sql_delete(PlanDeliverable).where(
                        PlanDeliverable.plan_cycle_id.in_(cycle_ids)
                    )
                )

                # Delete support plan statuses
                await db.execute(
                    sql_delete(SupportPlanStatus).where(
                        SupportPlanStatus.plan_cycle_id.in_(cycle_ids)
                    )
                )

            # Delete support plan cycles
            await db.execute(
                sql_delete(SupportPlanCycle).where(
                    SupportPlanCycle.welfare_recipient_id == recipient_id
                )
            )

            # 3. Delete emergency contacts (via service_recipient_detail)
            detail_stmt = select(ServiceRecipientDetail.id).where(
                ServiceRecipientDetail.welfare_recipient_id == recipient_id
            )
            detail_result = await db.execute(detail_stmt)
            detail_id_row = detail_result.fetchone()

            if detail_id_row:
                detail_id = detail_id_row[0]
                await db.execute(
                    sql_delete(EmergencyContact).where(
                        EmergencyContact.service_recipient_detail_id == detail_id
                    )
                )

            # 4. Delete service recipient detail
            await db.execute(
                sql_delete(ServiceRecipientDetail).where(
                    ServiceRecipientDetail.welfare_recipient_id == recipient_id
                )
            )

            # 5. Delete disability details (via disability_status)
            disability_status_stmt = select(DisabilityStatus.id).where(
                DisabilityStatus.welfare_recipient_id == recipient_id
            )
            disability_status_result = await db.execute(disability_status_stmt)
            disability_status_id_row = disability_status_result.fetchone()

            if disability_status_id_row:
                disability_status_id = disability_status_id_row[0]
                await db.execute(
                    sql_delete(DisabilityDetail).where(
                        DisabilityDetail.disability_status_id == disability_status_id
                    )
                )

            # 6. Delete disability status
            await db.execute(
                sql_delete(DisabilityStatus).where(
                    DisabilityStatus.welfare_recipient_id == recipient_id
                )
            )

            # 7. Finally, delete the welfare recipient
            stmt = sql_delete(WelfareRecipient).where(WelfareRecipient.id == recipient_id)
            result = await db.execute(stmt)

            await db.commit()

            # 削除された行数が0の場合はFalse
            return result.rowcount > 0

        except Exception as e:
            await db.rollback()
            raise e

    async def _create_initial_support_plan(self, db: AsyncSession, recipient_id: UUID) -> None:
        """Create initial support plan for a welfare recipient"""
        from app.models.support_plan_cycle import SupportPlanCycle, SupportPlanStatus
        from app.models.enums import SupportPlanStep
        from datetime import date, timedelta

        cycle = SupportPlanCycle(
            welfare_recipient_id=recipient_id,
            is_latest_cycle=True,
            plan_cycle_start_date=date.today(),
            next_renewal_deadline=date.today() + timedelta(days=180)
        )
        db.add(cycle)
        await db.flush()  # cycle.id を取得するため

        initial_steps = [
            SupportPlanStep.assessment,
            SupportPlanStep.draft_plan,
            SupportPlanStep.staff_meeting,
            SupportPlanStep.final_plan_signed,
            SupportPlanStep.monitoring
        ]

        for step in initial_steps:
            status = SupportPlanStatus(
                plan_cycle_id=cycle.id,
                step_type=step,
                completed=False
            )
            db.add(status)

        await db.flush()


crud_welfare_recipient = CRUDWelfareRecipient(WelfareRecipient)
