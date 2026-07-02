"""Employee action execution boundary."""

import logging
from datetime import date
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.crud_welfare_recipient import crud_welfare_recipient
from app.messages import ja
from app.models.approval_request import ApprovalRequest
from app.models.enums import ActionType, GenderType, ResourceType
from app.models.welfare_recipient import (
    DisabilityDetail,
    DisabilityStatus,
    EmergencyContact,
    OfficeWelfareRecipient,
    ServiceRecipientDetail,
    WelfareRecipient,
)

logger = logging.getLogger(__name__)


def _get_resource_type(request: ApprovalRequest) -> ResourceType:
    resource_type = request.request_data.get("resource_type")
    try:
        return ResourceType(resource_type)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ja.SERVICE_UNSUPPORTED_RESOURCE_TYPE.format(resource_type=resource_type),
        ) from exc


def _get_action_type(request: ApprovalRequest) -> ActionType:
    return ActionType(request.request_data.get("action_type"))


def _get_resource_id(request: ApprovalRequest) -> Optional[UUID]:
    resource_id_str = request.request_data.get("resource_id")
    return UUID(resource_id_str) if resource_id_str else None


def _get_original_request_data(request: ApprovalRequest) -> dict:
    return request.request_data.get("original_request_data", {})


def _parse_birth_day(birth_day_value: Any) -> Optional[date]:
    if birth_day_value is None:
        return None
    if isinstance(birth_day_value, date):
        return birth_day_value
    if isinstance(birth_day_value, str):
        return date.fromisoformat(birth_day_value)
    return None


class EmployeeActionExecutor:
    """Executes approved employee action requests."""

    async def execute_action(
        self,
        db: AsyncSession,
        request: ApprovalRequest,
    ) -> Dict[str, Any]:
        resource_type = _get_resource_type(request)
        action_type = _get_action_type(request)

        logger.info(
            "Executing action: resource_type=%s action_type=%s",
            resource_type,
            action_type,
        )

        if resource_type == ResourceType.welfare_recipient:
            return await self.execute_welfare_recipient_action(db, request)
        if resource_type == ResourceType.support_plan_cycle:
            return await self.execute_support_plan_cycle_action(db, request)
        if resource_type == ResourceType.support_plan_status:
            return await self.execute_support_plan_status_action(db, request)

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ja.SERVICE_UNSUPPORTED_RESOURCE_TYPE.format(resource_type=resource_type),
        )

    async def execute_welfare_recipient_action(
        self,
        db: AsyncSession,
        request: ApprovalRequest,
    ) -> Dict[str, Any]:
        action_type = _get_action_type(request)
        request_data = _get_original_request_data(request)

        if action_type == ActionType.create:
            return await self._create_welfare_recipient(db, request, request_data)
        if action_type == ActionType.update:
            return await self._update_welfare_recipient(db, request, request_data)
        if action_type == ActionType.delete:
            return await self._delete_welfare_recipient(db, request, request_data)

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ja.SERVICE_UNSUPPORTED_ACTION_TYPE.format(action_type=action_type),
        )

    async def _create_welfare_recipient(
        self,
        db: AsyncSession,
        request: ApprovalRequest,
        request_data: dict,
    ) -> Dict[str, Any]:
        form_data = request_data.get("form_data", {})
        basic_info = form_data.get("basicInfo", {})

        if not basic_info:
            basic_info = request_data.get("basic_info", {})

        if not basic_info and "first_name" in request_data:
            basic_info = request_data
            form_data = request_data
        elif not basic_info and "full_name" in request_data:
            name_parts = str(request_data["full_name"]).split()
            if len(name_parts) >= 2:
                basic_info = {
                    "last_name": name_parts[0],
                    "first_name": " ".join(name_parts[1:]),
                    "gender": request_data.get("gender"),
                }
                form_data = request_data

        gender_value = basic_info.get("gender")
        recipient = WelfareRecipient(
            first_name=basic_info.get("firstName") or basic_info.get("first_name"),
            last_name=basic_info.get("lastName") or basic_info.get("last_name"),
            first_name_furigana=basic_info.get("firstNameFurigana") or basic_info.get("first_name_furigana"),
            last_name_furigana=basic_info.get("lastNameFurigana") or basic_info.get("last_name_furigana"),
            birth_day=_parse_birth_day(basic_info.get("birthDay") or basic_info.get("birth_day")),
            gender=GenderType(gender_value) if gender_value else None,
        )
        db.add(recipient)
        await db.flush()

        recipient_id = recipient.id
        await self._create_welfare_recipient_related_data(
            db=db,
            recipient_id=recipient_id,
            request=request,
            request_data=request_data,
            form_data=form_data,
        )

        association = OfficeWelfareRecipient(
            office_id=request.office_id,
            welfare_recipient_id=recipient_id,
        )
        db.add(association)
        await db.flush()

        logger.info("Creating initial support plan for recipient")
        from app.services.welfare_recipient_service import WelfareRecipientService

        await WelfareRecipientService._create_initial_support_plan(
            db=db,
            welfare_recipient_id=recipient_id,
            office_id=request.office_id,
        )
        logger.info("Initial support plan created successfully")

        return {
            "success": True,
            "action": "create",
            "resource_id": str(recipient_id),
        }

    async def _create_welfare_recipient_related_data(
        self,
        *,
        db: AsyncSession,
        recipient_id: UUID,
        request: ApprovalRequest,
        request_data: dict,
        form_data: dict,
    ) -> None:
        logger.info("Creating related data for recipient")

        contact_address = form_data.get("contactAddress", {})
        if not contact_address:
            contact_address = request_data.get("contact_address", {})

        detail_id = None
        if contact_address and contact_address.get("address") and contact_address.get("tel"):
            form_of_residence_other_text = contact_address.get("formOfResidenceOtherText")
            if form_of_residence_other_text == "":
                form_of_residence_other_text = None

            means_of_transportation_other_text = contact_address.get("meansOfTransportationOtherText")
            if means_of_transportation_other_text == "":
                means_of_transportation_other_text = None

            detail = ServiceRecipientDetail(
                welfare_recipient_id=recipient_id,
                address=contact_address.get("address"),
                form_of_residence=contact_address.get("formOfResidence"),
                form_of_residence_other_text=form_of_residence_other_text,
                means_of_transportation=contact_address.get("meansOfTransportation"),
                means_of_transportation_other_text=means_of_transportation_other_text,
                tel=contact_address.get("tel"),
            )
            db.add(detail)
            await db.flush()
            detail_id = detail.id

        if detail_id:
            emergency_contacts = form_data.get("emergencyContacts", [])
            if not emergency_contacts:
                emergency_contacts = request_data.get("emergency_contacts", [])
            for contact_data in emergency_contacts:
                address = contact_data.get("address")
                if address == "":
                    address = None

                notes = contact_data.get("notes")
                if notes == "":
                    notes = None

                db.add(
                    EmergencyContact(
                        service_recipient_detail_id=detail_id,
                        first_name=contact_data.get("firstName") or contact_data.get("first_name"),
                        last_name=contact_data.get("lastName") or contact_data.get("last_name"),
                        first_name_furigana=(
                            contact_data.get("firstNameFurigana") or contact_data.get("first_name_furigana")
                        ),
                        last_name_furigana=(
                            contact_data.get("lastNameFurigana") or contact_data.get("last_name_furigana")
                        ),
                        relationship=contact_data.get("relationship"),
                        tel=contact_data.get("tel"),
                        address=address,
                        notes=notes,
                        priority=contact_data.get("priority"),
                    )
                )

        disability_info = form_data.get("disabilityInfo", {})
        if not disability_info:
            disability_info = request_data.get("disability_info", {})

        disability_status_id = None
        if (
            disability_info
            and disability_info.get("disabilityOrDiseaseName")
            and disability_info.get("livelihoodProtection")
        ):
            special_remarks = disability_info.get("specialRemarks") or disability_info.get("special_remarks")
            if special_remarks == "":
                special_remarks = None

            disability_status = DisabilityStatus(
                welfare_recipient_id=recipient_id,
                disability_or_disease_name=(
                    disability_info.get("disabilityOrDiseaseName")
                    or disability_info.get("disability_or_disease_name")
                ),
                livelihood_protection=(
                    disability_info.get("livelihoodProtection") or disability_info.get("livelihood_protection")
                ),
                special_remarks=special_remarks,
            )
            db.add(disability_status)
            await db.flush()
            disability_status_id = disability_status.id

        if disability_status_id:
            disability_details = form_data.get("disabilityDetails", [])
            if not disability_details:
                disability_details = request_data.get("disability_details", [])
            for detail_data in disability_details:
                physical_disability_type = (
                    detail_data.get("physicalDisabilityType") or detail_data.get("physical_disability_type")
                )
                if physical_disability_type == "":
                    physical_disability_type = None

                grade_or_level = detail_data.get("gradeOrLevel") or detail_data.get("grade_or_level")
                if grade_or_level == "":
                    grade_or_level = None

                physical_disability_type_other_text = (
                    detail_data.get("physicalDisabilityTypeOtherText")
                    or detail_data.get("physical_disability_type_other_text")
                )
                if physical_disability_type_other_text == "":
                    physical_disability_type_other_text = None

                db.add(
                    DisabilityDetail(
                        disability_status_id=disability_status_id,
                        category=detail_data.get("category"),
                        grade_or_level=grade_or_level,
                        physical_disability_type=physical_disability_type,
                        physical_disability_type_other_text=physical_disability_type_other_text,
                        application_status=(
                            detail_data.get("applicationStatus") or detail_data.get("application_status")
                        ),
                    )
                )

    async def _update_welfare_recipient(
        self,
        db: AsyncSession,
        request: ApprovalRequest,
        request_data: dict,
    ) -> Dict[str, Any]:
        recipient_id = _get_resource_id(request)

        if not recipient_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ja.SERVICE_RESOURCE_ID_REQUIRED_FOR_UPDATE,
            )

        recipient = await crud_welfare_recipient.get(db, id=recipient_id)
        if not recipient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ja.SERVICE_RECIPIENT_NOT_FOUND.format(recipient_id=recipient_id),
            )

        form_data = request_data.get("form_data", {})
        basic_info = form_data.get("basicInfo", {})
        if not basic_info:
            basic_info = request_data.get("basic_info", {})
        if not basic_info and "first_name" in request_data:
            basic_info = request_data

        if "firstName" in basic_info or "first_name" in basic_info:
            recipient.first_name = basic_info.get("firstName") or basic_info.get("first_name")
        if "lastName" in basic_info or "last_name" in basic_info:
            recipient.last_name = basic_info.get("lastName") or basic_info.get("last_name")
        if "firstNameFurigana" in basic_info or "first_name_furigana" in basic_info:
            recipient.first_name_furigana = (
                basic_info.get("firstNameFurigana") or basic_info.get("first_name_furigana")
            )
        if "lastNameFurigana" in basic_info or "last_name_furigana" in basic_info:
            recipient.last_name_furigana = (
                basic_info.get("lastNameFurigana") or basic_info.get("last_name_furigana")
            )
        if "birthDay" in basic_info or "birth_day" in basic_info:
            recipient.birth_day = _parse_birth_day(basic_info.get("birthDay") or basic_info.get("birth_day"))
        if "gender" in basic_info:
            gender_value = basic_info["gender"]
            recipient.gender = GenderType(gender_value) if gender_value else None

        await db.flush()

        return {
            "success": True,
            "action": "update",
            "resource_id": str(recipient.id),
        }

    async def _delete_welfare_recipient(
        self,
        db: AsyncSession,
        request: ApprovalRequest,
        request_data: dict,
    ) -> Dict[str, Any]:
        recipient_id = _get_resource_id(request)
        if not recipient_id and "welfare_recipient_id" in request_data:
            recipient_id = UUID(request_data["welfare_recipient_id"])

        if not recipient_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ja.SERVICE_RESOURCE_ID_REQUIRED_FOR_DELETE,
            )

        recipient = await crud_welfare_recipient.get(db, id=recipient_id)
        if not recipient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ja.SERVICE_RECIPIENT_NOT_FOUND.format(recipient_id=recipient_id),
            )

        await db.delete(recipient)
        await db.flush()

        return {
            "success": True,
            "action": "delete",
            "resource_id": str(recipient_id),
        }

    async def execute_support_plan_cycle_action(
        self,
        db: AsyncSession,
        request: ApprovalRequest,
    ) -> Dict[str, Any]:
        return {
            "success": True,
            "action": str(_get_action_type(request)),
            "message": "SupportPlanCycle actions not yet implemented",
        }

    async def execute_support_plan_status_action(
        self,
        db: AsyncSession,
        request: ApprovalRequest,
    ) -> Dict[str, Any]:
        action_type = _get_action_type(request)
        request_data = request.request_data or {}

        logger.info("Executing support_plan_status action: %s", action_type)

        deliverable_id = request_data.get("deliverable_id")

        if not deliverable_id:
            logger.warning("No deliverable_id found in request_data")
            return {
                "success": False,
                "action": str(action_type),
                "error": "deliverable_id is required",
            }

        from app.models.support_plan_cycle import PlanDeliverable

        deliverable_stmt = select(PlanDeliverable).where(PlanDeliverable.id == deliverable_id)
        deliverable_result = await db.execute(deliverable_stmt)
        deliverable = deliverable_result.scalar_one_or_none()

        if not deliverable:
            logger.error("Deliverable not found")
            return {
                "success": False,
                "action": str(action_type),
                "error": f"Deliverable {deliverable_id} not found",
            }

        logger.info("Deliverable found. No further action needed")

        return {
            "success": True,
            "action": str(action_type),
            "deliverable_id": str(deliverable_id),
            "message": "PDF deliverable already uploaded and verified",
        }
