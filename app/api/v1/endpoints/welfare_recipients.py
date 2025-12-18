from typing import Any, List
from uuid import UUID
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from psycopg import errors as psycopg_errors
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.crud.crud_welfare_recipient import crud_welfare_recipient
from app.models.staff import Staff
from app.models.enums import ResourceType, ActionType
from app.schemas.welfare_recipient import (
    WelfareRecipientResponse,
    WelfareRecipientCreate,
    WelfareRecipientUpdate,
    WelfareRecipientListResponse,
    UserRegistrationRequest,
    UserRegistrationResponse
)
from app.services.welfare_recipient_service import WelfareRecipientService
from app.core.exceptions import (
    NotFoundException,
    ForbiddenException,
    BadRequestException
)
from app.messages import ja

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/", response_model=UserRegistrationResponse, status_code=status.HTTP_201_CREATED)
async def create_welfare_recipient(
    *,
    db: AsyncSession = Depends(deps.get_db),
    registration_data: UserRegistrationRequest,
    current_staff: Staff = Depends(deps.require_active_billing)
) -> Any:
    """
    包括的なデータで新しい福祉受給者を作成する。
    管理者および所有者のみが受給者を作成できます。
    """


    # Check if disability_details has empty category
    for detail in (registration_data.disability_details or []):
        if not detail.category or detail.category.strip() == "":
            raise BadRequestException(ja.RECIPIENT_CATEGORY_MISSING)

    try:
        logger.info("[ENDPOINT DEBUG] create_welfare_recipient START")

        # Load office associations explicitly to avoid lazy loading issues
        office_associations = getattr(current_staff, 'office_associations', None)

        if not office_associations or len(office_associations) == 0:
            raise ForbiddenException(ja.RECIPIENT_MUST_HAVE_OFFICE)

        office_id = office_associations[0].office_id
        logger.info(f"[ENDPOINT DEBUG] office_id={office_id}")

        # Employee restriction check
        employee_request = await deps.check_employee_restriction(
            db=db,
            current_staff=current_staff,
            resource_type=ResourceType.welfare_recipient,
            action_type=ActionType.create,
            request_data=registration_data.model_dump(mode='json')
        )

        if employee_request:
            # Employee case: return request created response
            return JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content={
                    "success": True,
                    "message": ja.EMPLOYEE_REQUEST_PENDING,
                    "recipient_id": None,
                    "support_plan_created": False,
                    "request_id": str(employee_request.id)
                }
            )

        logger.info("[ENDPOINT DEBUG] Calling WelfareRecipientService.create_recipient_with_details...")
        welfare_recipient_id = await WelfareRecipientService.create_recipient_with_details(
            db=db,
            registration_data=registration_data,
            office_id=office_id
        )
        logger.info(f"[ENDPOINT DEBUG] Service call completed. welfare_recipient_id={welfare_recipient_id}")

        logger.info("[ENDPOINT DEBUG] Calling db.commit()...")
        try:
            await db.commit()
            logger.info("[ENDPOINT DEBUG] db.commit() completed successfully")
        except Exception as commit_error:
            logger.error(f"[ENDPOINT DEBUG] db.commit() FAILED: {type(commit_error).__name__}: {commit_error}")
            import traceback
            logger.error(f"[ENDPOINT DEBUG] Traceback:\n{traceback.format_exc()}")
            raise

        logger.info("[ENDPOINT DEBUG] Creating response...")
        return UserRegistrationResponse(
            success=True,
            message=ja.RECIPIENT_CREATE_SUCCESS,
            recipient_id=welfare_recipient_id,
            support_plan_created=True
        )

    except psycopg_errors.InvalidTextRepresentation as e:
        logger.error(f"[ENDPOINT DEBUG] InvalidTextRepresentation: {e}")
        await db.rollback()

        if "disability_category" in str(e):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ja.RECIPIENT_DISABILITY_CATEGORY_MISSING
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ja.RECIPIENT_INVALID_INPUT
        )

    except ValueError as e:
        logger.error(f"[ENDPOINT DEBUG] ValueError: {e}")
        await db.rollback()
        raise BadRequestException(str(e))
    except HTTPException as e:
        logger.error(f"[ENDPOINT DEBUG] HTTPException: {e.status_code} - {e.detail}")
        await db.rollback()
        raise
    except Exception as e:
        logger.error(f"[ENDPOINT DEBUG] Unexpected Exception: {type(e).__name__}: {e}")
        await db.rollback()

        import traceback
        logger.error(f"[ENDPOINT DEBUG] Full traceback:\n{traceback.format_exc()}")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ja.RECIPIENT_CREATE_FAILED.format(error=str(e))
        )

@router.get("/", response_model=WelfareRecipientListResponse)
async def list_welfare_recipients(
    db: AsyncSession = Depends(deps.get_db),
    current_staff: Staff = Depends(deps.get_current_user),
    skip: int = 0,
    limit: int = 100,
    search: str = None
) -> Any:
    """
    現在の職員の所属部署の福祉受給者を検索する。

    名前（漢字とふりがな両方）による検索をサポート（任意）。
    """
    office_associations = getattr(current_staff, 'office_associations', None)
    if not office_associations:
        raise ForbiddenException(ja.RECIPIENT_MUST_HAVE_OFFICE)

    office_id = office_associations[0].office_id

    if search:
        welfare_recipients = await crud_welfare_recipient.search_by_name(
            db=db,
            office_id=office_id,
            search_term=search.strip(),
            skip=skip,
            limit=limit
        )
    else:
        welfare_recipients = await crud_welfare_recipient.get_by_office(
            db=db,
            office_id=office_id,
            skip=skip,
            limit=limit
        )

    # For pagination, we need the total count
    # Note: In production, you might want to implement this more efficiently
    all_recipients = await crud_welfare_recipient.get_by_office(db=db, office_id=office_id, skip=0, limit=10000)
    total = len(all_recipients)

    return WelfareRecipientListResponse(
        recipients=welfare_recipients,
        total=total,
        page=skip // limit + 1 if limit > 0 else 1,
        per_page=limit,
        pages=(total + limit - 1) // limit if limit > 0 else 1
    )


@router.get("/{recipient_id}", response_model=WelfareRecipientResponse)
async def get_welfare_recipient(
    *,
    db: AsyncSession = Depends(deps.get_db),
    recipient_id: UUID,
    current_staff: Staff = Depends(deps.get_current_user)
) -> Any:
    """
    IDで特定の福祉受給者を特定し、関連する詳細情報をすべて取得する。
    全ての職員が利用者の詳細情報を参照できます。
    """

    welfare_recipient = await crud_welfare_recipient.get_with_details(db=db, recipient_id=recipient_id)
    if not welfare_recipient:
        raise NotFoundException(ja.RECIPIENT_NOT_FOUND)

    # Verify the recipient belongs to the staff's office
    office_associations = getattr(current_staff, 'office_associations', None)
    if not office_associations:
        raise ForbiddenException(ja.RECIPIENT_MUST_HAVE_OFFICE)

    office_id = office_associations[0].office_id

    # Check if the recipient is associated with the staff's office
    recipient_office_ids = [assoc.office_id for assoc in welfare_recipient.office_associations]
    if office_id not in recipient_office_ids:
        raise ForbiddenException(ja.RECIPIENT_ACCESS_DENIED)

    return welfare_recipient


@router.put("/{recipient_id}", response_model=WelfareRecipientResponse)
async def update_welfare_recipient(
    *,
    db: AsyncSession = Depends(deps.get_db),
    recipient_id: UUID,
    registration_data: UserRegistrationRequest,
    current_staff: Staff = Depends(deps.require_active_billing)
) -> Any:
    """
    福祉受給者を包括的なデータで更新する。

    緊急連絡先や障害の詳細を含む関連する全記録を更新します。
    受給者情報の更新はownerおよびmanagerのみが可能です。
    """
    # Get existing recipient
    welfare_recipient = await crud_welfare_recipient.get_with_details(db=db, recipient_id=recipient_id)
    if not welfare_recipient:
        raise NotFoundException(ja.RECIPIENT_NOT_FOUND)

    # Verify the recipient belongs to the staff's office
    office_associations = getattr(current_staff, 'office_associations', None)
    if not office_associations:
        raise ForbiddenException(ja.RECIPIENT_MUST_HAVE_OFFICE)

    office_id = office_associations[0].office_id
    recipient_office_ids = [assoc.office_id for assoc in welfare_recipient.office_associations]
    if office_id not in recipient_office_ids:
        raise ForbiddenException(ja.RECIPIENT_ACCESS_DENIED)

    # Employee restriction check
    employee_request = await deps.check_employee_restriction(
        db=db,
        current_staff=current_staff,
        resource_type=ResourceType.welfare_recipient,
        action_type=ActionType.update,
        resource_id=recipient_id,
        request_data=registration_data.model_dump(mode='json')
    )

    if employee_request:
        # Employee case: return request created response
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "success": True,
                "message": ja.EMPLOYEE_REQUEST_PENDING,
                "recipient_id": str(recipient_id),
                "support_plan_created": False,
                "request_id": str(employee_request.id)
            }
        )

    try:
        updated_recipient = await crud_welfare_recipient.update_comprehensive(
            db=db,
            recipient_id=recipient_id,
            registration_data=registration_data
        )

        if not updated_recipient:
            raise NotFoundException(ja.RECIPIENT_UPDATE_NOT_FOUND)

        return updated_recipient

    except ValueError as e:
        raise BadRequestException(str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ja.RECIPIENT_UPDATE_FAILED.format(error=str(e))
        )


@router.delete("/{recipient_id}")
async def delete_welfare_recipient(
    *,
    db: AsyncSession = Depends(deps.get_db),
    recipient_id: UUID,
    current_staff: Staff = Depends(deps.require_active_billing)
) -> Any:
    """
    Delete welfare recipient and all related data.

    Only managers and owners can delete recipients.
    This will cascade delete all related records.
    """

    # Get existing recipient with only office associations (lightweight query for delete)
    welfare_recipient = await crud_welfare_recipient.get_with_office_associations(db=db, recipient_id=recipient_id)
    if not welfare_recipient:
        raise NotFoundException(ja.RECIPIENT_NOT_FOUND)

    # Verify the recipient belongs to the staff's office
    office_associations = getattr(current_staff, 'office_associations', None)
    if not office_associations:
        raise ForbiddenException(ja.RECIPIENT_MUST_HAVE_OFFICE)

    office_id = office_associations[0].office_id
    recipient_office_ids = [assoc.office_id for assoc in welfare_recipient.office_associations]
    if office_id not in recipient_office_ids:
        raise ForbiddenException(ja.RECIPIENT_ACCESS_DENIED)

    # Employee restriction check
    employee_request = await deps.check_employee_restriction(
        db=db,
        current_staff=current_staff,
        resource_type=ResourceType.welfare_recipient,
        action_type=ActionType.delete,
        resource_id=recipient_id
    )

    if employee_request:
        # Employee case: return request created response
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "message": ja.EMPLOYEE_REQUEST_PENDING,
                "request_id": str(employee_request.id)
            }
        )

    try:
        success = await crud_welfare_recipient.delete_with_cascade(db=db, recipient_id=recipient_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=ja.RECIPIENT_DELETE_FAILED
            )

        return {"message": ja.RECIPIENT_DELETED_SUCCESS}

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ja.RECIPIENT_DELETE_FAILED
        )


@router.post("/{recipient_id}/repair-support-plan")
async def repair_support_plan(
    *,
    db: AsyncSession = Depends(deps.get_db),
    recipient_id: UUID,
    current_staff: Staff = Depends(deps.require_active_billing)
) -> Any:
    """
    Repair/recreate support plan data for a welfare recipient.

    This endpoint addresses the requirement in mini.md for handling cases
    where support plan data is missing or corrupted.
    """
    # Check permissions - only managers and owners can repair data
    if current_staff.role.value not in ["manager", "owner"]:
        raise ForbiddenException(ja.RECIPIENT_REPAIR_PERMISSION_DENIED)

    welfare_recipient = await crud_welfare_recipient.get(db=db, id=recipient_id)
    if not welfare_recipient:
        raise NotFoundException(ja.RECIPIENT_NOT_FOUND)

    # Verify the recipient belongs to the staff's office
    office_associations = getattr(current_staff, 'office_associations', None)
    if not office_associations:
        raise ForbiddenException(ja.RECIPIENT_MUST_HAVE_OFFICE)

    office_id = office_associations[0].office_id
    recipient_office_ids = [assoc.office_id for assoc in welfare_recipient.office_associations]
    if office_id not in recipient_office_ids:
        raise ForbiddenException(ja.RECIPIENT_ACCESS_DENIED)

    try:
        # Recreate support plan data
        await crud_welfare_recipient._create_initial_support_plan(db, recipient_id, office_id)
        await db.commit()

        return {
            "success": True,
            "message": ja.RECIPIENT_REPAIR_SUPPORT_PLAN_SUCCESS,
            "recipient_id": recipient_id
        }

    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ja.RECIPIENT_REPAIR_SUPPORT_PLAN_FAILED
        )