"""
Role変更リクエストAPIエンドポイント（統合テーブル版）

従業員が自身のroleを変更するリクエストを作成・管理するためのAPI

注意: このエンドポイントは統合approval_requestsテーブルを使用しています。
旧role_change_requestsテーブルは削除されました。
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from uuid import UUID

from app import schemas
from app.api import deps
from app.models.staff import Staff
from app.models.enums import StaffRole, RequestStatus, ApprovalResourceType
from app.schemas.role_change_request import (
    RoleChangeRequestCreate,
    RoleChangeRequestRead,
    RoleChangeRequestApprove,
    RoleChangeRequestReject
)
from app.services.role_change_service import role_change_service
from app.crud import approval_request
from app.messages import ja

router = APIRouter()


@router.post("", response_model=RoleChangeRequestRead, status_code=status.HTTP_201_CREATED)
async def create_role_change_request(
    *,
    db: AsyncSession = Depends(deps.get_db),
    obj_in: RoleChangeRequestCreate,
    current_user: Staff = Depends(deps.get_current_user)
) -> RoleChangeRequestRead:
    """
    Role変更リクエストを作成

    - employeeはmanagerまたはownerへの変更をリクエスト可能
    - managerはemployeeまたはownerへの変更をリクエスト可能
    - ownerは権限譲渡のみ可能（別のAPIエンドポイント）
    """
    # 自分と同じroleへのリクエストは不可
    if current_user.role == obj_in.requested_role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ja.ROLE_ALREADY_ASSIGNED.format(role=current_user.role.value)
        )

    # 事業所IDを取得（プライマリ事業所を使用）
    if not current_user.office_associations:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ja.ROLE_NO_OFFICE
        )

    office_id = current_user.office_associations[0].office_id

    try:
        request = await role_change_service.create_request(
            db=db,
            requester_staff_id=current_user.id,
            office_id=office_id,
            obj_in=obj_in
        )
        await db.commit()
        await db.refresh(request)
        return request
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("", response_model=List[RoleChangeRequestRead])
async def get_role_change_requests(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: Staff = Depends(deps.get_current_user),
    status_filter: Optional[RequestStatus] = Query(None, alias="status")
) -> List[RoleChangeRequestRead]:
    """
    Role変更リクエスト一覧を取得（統合テーブル版）

    - 自分が作成したリクエスト
    - 自分が承認可能なリクエスト（manager/owner）
    """
    print(f"\n[DEBUG ROLE_CHANGE_REQUEST] GET /role-change-requests called")
    print(f"[DEBUG ROLE_CHANGE_REQUEST] Current user: {current_user.id}, Role: {current_user.role}")
    print(f"[DEBUG ROLE_CHANGE_REQUEST] Status filter: {status_filter}")

    # 自分が作成したリクエストを取得（role_changeタイプのみ）
    my_requests = await approval_request.get_by_requester(
        db=db,
        requester_staff_id=current_user.id,
        resource_type=ApprovalResourceType.role_change
    )
    print(f"[DEBUG ROLE_CHANGE_REQUEST] My requests count: {len(my_requests)}")
    for req in my_requests:
        req_data = req.request_data or {}
        print(f"[DEBUG ROLE_CHANGE_REQUEST]   - Request {req.id}: {req_data.get('from_role')} → {req_data.get('requested_role')}, status={req.status}")

    # 自分が承認可能なリクエストを取得（manager/owner のみ）
    approvable_requests = []
    if current_user.role in [StaffRole.manager, StaffRole.owner]:
        if current_user.office_associations:
            office_id = current_user.office_associations[0].office_id
            # Pendingかつrole_changeタイプのリクエストを取得
            pending_requests = await approval_request.get_pending_requests(
                db=db,
                office_id=office_id,
                resource_type=ApprovalResourceType.role_change
            )
            # リクエスト作成者を除外
            approvable_requests = [req for req in pending_requests if req.requester_staff_id != current_user.id]
            print(f"[DEBUG ROLE_CHANGE_REQUEST] Approvable requests count: {len(approvable_requests)}")

    # 重複を除いてマージ
    all_requests = {req.id: req for req in my_requests + approvable_requests}.values()
    print(f"[DEBUG ROLE_CHANGE_REQUEST] Total unique requests: {len(all_requests)}")

    # ステータスフィルタリング
    if status_filter:
        all_requests = [req for req in all_requests if req.status == status_filter]
        print(f"[DEBUG ROLE_CHANGE_REQUEST] After filtering: {len(all_requests)}")

    result = list(all_requests)
    print(f"[DEBUG ROLE_CHANGE_REQUEST] Returning {len(result)} requests\n")
    return result


@router.patch("/{request_id}/approve", response_model=RoleChangeRequestRead)
async def approve_role_change_request(
    *,
    db: AsyncSession = Depends(deps.get_db),
    request_id: UUID,
    obj_in: RoleChangeRequestApprove,
    current_user: Staff = Depends(deps.get_current_user)
) -> RoleChangeRequestRead:
    """
    Role変更リクエストを承認（統合テーブル版）

    - Manager: employee → manager/owner のリクエストのみ承認可能
    - Owner: すべてのリクエストを承認可能
    - Employee: 承認不可
    """
    # リクエストを取得（統合テーブルから）
    request = await approval_request.get(db=db, id=request_id)
    if not request or request.resource_type != ApprovalResourceType.role_change:
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

    # 承認権限チェック（サービス層を使用）
    if not role_change_service.validate_approval_permission(current_user.role, request):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ja.ROLE_NO_PERMISSION_TO_APPROVE
        )

    try:
        approved_request = await role_change_service.approve_request(
            db=db,
            request_id=request_id,
            reviewer_staff_id=current_user.id,
            reviewer_notes=obj_in.reviewer_notes
        )
        await db.commit()
        await db.refresh(approved_request)
        return approved_request
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.patch("/{request_id}/reject", response_model=RoleChangeRequestRead)
async def reject_role_change_request(
    *,
    db: AsyncSession = Depends(deps.get_db),
    request_id: UUID,
    obj_in: RoleChangeRequestReject,
    current_user: Staff = Depends(deps.get_current_user)
) -> RoleChangeRequestRead:
    """
    Role変更リクエストを却下（統合テーブル版）

    - Manager/Owner: 承認可能なリクエストを却下可能
    """
    # リクエストを取得（統合テーブルから）
    request = await approval_request.get(db=db, id=request_id)
    if not request or request.resource_type != ApprovalResourceType.role_change:
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

    # 却下権限チェック（承認権限と同じ）
    if not role_change_service.validate_approval_permission(current_user.role, request):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ja.ROLE_NO_PERMISSION_TO_REJECT
        )

    try:
        rejected_request = await role_change_service.reject_request(
            db=db,
            request_id=request_id,
            reviewer_staff_id=current_user.id,
            reviewer_notes=obj_in.reviewer_notes
        )
        await db.commit()
        await db.refresh(rejected_request)
        return rejected_request
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role_change_request(
    *,
    db: AsyncSession = Depends(deps.get_db),
    request_id: UUID,
    current_user: Staff = Depends(deps.get_current_user)
):
    """
    Role変更リクエストを削除（統合テーブル版）

    - pending状態のリクエストのみ削除可能
    - 作成者のみ削除可能
    """
    # リクエストを取得（統合テーブルから）
    request = await approval_request.get(db=db, id=request_id)
    if not request or request.resource_type != ApprovalResourceType.role_change:
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

    await approval_request.remove(db=db, id=request_id)
    await db.commit()
