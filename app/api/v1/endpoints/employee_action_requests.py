"""
Employee制限リクエストAPIエンドポイント

Employeeが重要データを変更する際に、Manager/Ownerの承認を必須化するためのAPI
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from uuid import UUID

from app.api import deps
from app.models.staff import Staff
from app.models.enums import StaffRole, RequestStatus
from app.schemas.employee_action_request import (
    EmployeeActionRequestCreate,
    EmployeeActionRequestRead,
    EmployeeActionRequestApprove,
    EmployeeActionRequestReject
)
from app.services.employee_action_service import employee_action_service
from app.crud.crud_employee_action_request import crud_employee_action_request
from app.messages import ja

router = APIRouter()


@router.post("", response_model=EmployeeActionRequestRead, status_code=status.HTTP_201_CREATED)
async def create_employee_action_request(
    *,
    db: AsyncSession = Depends(deps.get_db),
    obj_in: EmployeeActionRequestCreate,
    current_user: Staff = Depends(deps.get_current_user)
) -> EmployeeActionRequestRead:
    """
    Employee制限リクエストを作成

    - Employee: CREATE/UPDATE/DELETEをリクエスト
    - Manager/Owner: 直接実行可能（リクエスト不要）
    """
    # 事業所IDを取得
    if not current_user.office_associations:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ja.ROLE_NO_OFFICE
        )

    office_id = current_user.office_associations[0].office_id

    try:
        request = await employee_action_service.create_request(
            db=db,
            requester_staff_id=current_user.id,
            office_id=office_id,
            obj_in=obj_in
        )
        return request
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("", response_model=List[EmployeeActionRequestRead])
async def get_employee_action_requests(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: Staff = Depends(deps.get_current_user),
    status_filter: Optional[RequestStatus] = Query(None, alias="status")
) -> List[EmployeeActionRequestRead]:
    """
    Employee制限リクエスト一覧を取得

    - 自分が作成したリクエスト
    - 自分が承認可能なリクエスト（manager/owner）
    """
    print(f"\n[DEBUG EMPLOYEE_ACTION_REQUEST] GET /employee-action-requests called")
    print(f"[DEBUG EMPLOYEE_ACTION_REQUEST] Current user: {current_user.id}, Role: {current_user.role}")
    print(f"[DEBUG EMPLOYEE_ACTION_REQUEST] Status filter: {status_filter}")

    # 自分が作成したリクエストを取得
    my_requests = await crud_employee_action_request.get_by_requester(
        db=db,
        requester_staff_id=current_user.id
    )
    print(f"[DEBUG EMPLOYEE_ACTION_REQUEST] My requests count: {len(my_requests)}")
    for req in my_requests:
        print(f"[DEBUG EMPLOYEE_ACTION_REQUEST]   - Request {req.id}: {req.resource_type}.{req.action_type}, status={req.status}")

    # 自分が承認可能なリクエストを取得（manager/owner のみ）
    approvable_requests = []
    if current_user.role in [StaffRole.manager, StaffRole.owner]:
        if current_user.office_associations:
            office_id = current_user.office_associations[0].office_id
            approvable_requests = await crud_employee_action_request.get_pending_for_approver(
                db=db,
                office_id=office_id
            )
            print(f"[DEBUG EMPLOYEE_ACTION_REQUEST] Approvable requests count: {len(approvable_requests)}")

    # 重複を除いてマージ
    all_requests = {req.id: req for req in my_requests + approvable_requests}.values()
    print(f"[DEBUG EMPLOYEE_ACTION_REQUEST] Total unique requests: {len(all_requests)}")

    # ステータスフィルタリング
    if status_filter:
        all_requests = [req for req in all_requests if req.status == status_filter]
        print(f"[DEBUG EMPLOYEE_ACTION_REQUEST] After filtering: {len(all_requests)}")

    result = list(all_requests)
    print(f"[DEBUG EMPLOYEE_ACTION_REQUEST] Returning {len(result)} requests\n")
    return result


@router.patch("/{request_id}/approve", response_model=EmployeeActionRequestRead)
async def approve_employee_action_request(
    *,
    db: AsyncSession = Depends(deps.get_db),
    request_id: UUID,
    obj_in: EmployeeActionRequestApprove,
    current_user: Staff = Depends(deps.get_current_user)
) -> EmployeeActionRequestRead:
    """
    Employee制限リクエストを承認し、実際のアクションを実行

    - Manager/Owner: 承認可能
    - Employee: 承認不可
    """
    # Manager/Owner権限チェック
    if current_user.role not in [StaffRole.manager, StaffRole.owner]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ja.PERM_MANAGER_OR_OWNER_APPROVE
        )

    # リクエストを取得
    request = await crud_employee_action_request.get(db=db, id=request_id)
    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ja.REQUEST_NOT_FOUND
        )

    # 既に処理済みかチェック
    if request.status != RequestStatus.pending:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ja.REQUEST_ALREADY_PROCESSED.format(status=request.status.value)
        )

    # 同じ事業所のリクエストかチェック
    if current_user.office_associations:
        office_id = current_user.office_associations[0].office_id
        if request.office_id != office_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ja.REQUEST_OFFICE_MISMATCH
            )

    try:
        approved_request = await employee_action_service.approve_request(
            db=db,
            request_id=request_id,
            approver_staff_id=current_user.id,
            approver_notes=obj_in.approver_notes
        )
        return approved_request
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.patch("/{request_id}/reject", response_model=EmployeeActionRequestRead)
async def reject_employee_action_request(
    *,
    db: AsyncSession = Depends(deps.get_db),
    request_id: UUID,
    obj_in: EmployeeActionRequestReject,
    current_user: Staff = Depends(deps.get_current_user)
) -> EmployeeActionRequestRead:
    """
    Employee制限リクエストを却下

    - Manager/Owner: 却下可能
    """
    # Manager/Owner権限チェック
    if current_user.role not in [StaffRole.manager, StaffRole.owner]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ja.PERM_MANAGER_OR_OWNER_REJECT
        )

    # リクエストを取得
    request = await crud_employee_action_request.get(db=db, id=request_id)
    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ja.REQUEST_NOT_FOUND
        )

    # 既に処理済みかチェック
    if request.status != RequestStatus.pending:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ja.REQUEST_ALREADY_PROCESSED.format(status=request.status.value)
        )

    # 同じ事業所のリクエストかチェック
    if current_user.office_associations:
        office_id = current_user.office_associations[0].office_id
        if request.office_id != office_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ja.REQUEST_OFFICE_MISMATCH
            )

    try:
        rejected_request = await employee_action_service.reject_request(
            db=db,
            request_id=request_id,
            approver_staff_id=current_user.id,
            approver_notes=obj_in.approver_notes
        )
        return rejected_request
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_employee_action_request(
    *,
    db: AsyncSession = Depends(deps.get_db),
    request_id: UUID,
    current_user: Staff = Depends(deps.get_current_user)
):
    """
    Employee制限リクエストを削除

    - pending状態のリクエストのみ削除可能
    - 作成者のみ削除可能
    """
    # リクエストを取得
    request = await crud_employee_action_request.get(db=db, id=request_id)
    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ja.REQUEST_NOT_FOUND
        )

    # 作成者チェック
    if request.requester_staff_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ja.REQUEST_DELETE_OWN_ONLY
        )

    # pending状態のみ削除可能
    if request.status != RequestStatus.pending:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ja.REQUEST_CANNOT_DELETE_PROCESSED.format(status=request.status.value)
        )

    await crud_employee_action_request.remove(db=db, id=request_id)
    await db.commit()
