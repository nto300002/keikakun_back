"""
退会リクエストAPIエンドポイント

オーナーが事務所の退会リクエストを作成し、app_adminが承認/却下するためのAPI

CRUD層とサービス層との連携:
- crud_approval_request: リクエストの作成・取得・更新
- crud_audit_log: 監査ログの記録
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select, func
from typing import Optional
from uuid import UUID

from app.api import deps
from app.models.staff import Staff
from app.models.enums import StaffRole, RequestStatus, ApprovalResourceType
from app.models.approval_request import ApprovalRequest
from app.crud.crud_approval_request import approval_request as crud_approval_request
from app.crud.crud_audit_log import audit_log as crud_audit_log
from app.schemas.withdrawal_request import (
    WithdrawalRequestCreate,
    WithdrawalRequestRead,
    WithdrawalRequestApprove,
    WithdrawalRequestReject,
    WithdrawalRequestListResponse
)
from app.messages import ja

router = APIRouter()


def _to_withdrawal_response(request: ApprovalRequest) -> WithdrawalRequestRead:
    """ApprovalRequestからWithdrawalRequestReadに変換"""
    request_data = request.request_data or {}
    return WithdrawalRequestRead(
        id=request.id,
        requester_staff_id=request.requester_staff_id,
        office_id=request.office_id,
        status=request.status,
        title=request_data.get("title", ""),
        reason=request_data.get("reason", ""),
        reviewed_by_staff_id=request.reviewed_by_staff_id,
        reviewed_at=request.reviewed_at,
        reviewer_notes=request.reviewer_notes,
        created_at=request.created_at,
        updated_at=request.updated_at,
        requester_name=request.requester.full_name if request.requester else None,
        office_name=request.office.name if request.office else None
    )


def _get_client_info(request: Request) -> tuple[Optional[str], Optional[str]]:
    """リクエストからクライアント情報を取得"""
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    return ip_address, user_agent


@router.post("", response_model=WithdrawalRequestRead, status_code=status.HTTP_201_CREATED)
async def create_withdrawal_request(
    request: Request,
    *,
    db: AsyncSession = Depends(deps.get_db),
    obj_in: WithdrawalRequestCreate,
    current_user: Staff = Depends(deps.get_current_user)
) -> WithdrawalRequestRead:
    """
    退会リクエストを作成

    - ownerのみ作成可能
    - 403: リクエストを行う権限がありません
    - 422: タイトルまたは申請内容が空
    """
    # 権限チェック: ownerのみ
    if current_user.role != StaffRole.owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ja.WITHDRAWAL_OWNER_ONLY
        )

    # 事業所IDを取得
    if not current_user.office_associations:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ja.WITHDRAWAL_NO_OFFICE
        )

    office_id = current_user.office_associations[0].office_id

    # 既存の承認待ちリクエストがないか確認
    has_pending = await crud_approval_request.has_pending_withdrawal(
        db,
        office_id=office_id,
        withdrawal_type="office"
    )
    if has_pending:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="この事務所に対する退会リクエストは既に承認待ちです"
        )

    # CRUD層を使用してリクエスト作成
    approval_req = await crud_approval_request.create_request(
        db,
        requester_staff_id=current_user.id,
        office_id=office_id,
        resource_type=ApprovalResourceType.withdrawal,
        request_data={
            "title": obj_in.title,
            "reason": obj_in.reason,
            "withdrawal_type": "office"
        },
        is_test_data=getattr(current_user, 'is_test_data', False)
    )

    # commitの前にIDをキャッシュ（MissingGreenletエラー対策）
    request_id = approval_req.id

    # 監査ログを記録
    ip_address, user_agent = _get_client_info(request)
    await crud_audit_log.create_log(
        db,
        actor_id=current_user.id,
        action="withdrawal.requested",
        target_type="withdrawal_request",
        target_id=request_id,
        office_id=office_id,
        actor_role=current_user.role.value,
        ip_address=ip_address,
        user_agent=user_agent,
        details={
            "title": obj_in.title,
            "withdrawal_type": "office"
        },
        is_test_data=getattr(current_user, 'is_test_data', False)
    )

    # commit前にリレーションをロード
    loaded_request = await crud_approval_request.get_by_id_with_relations(db, request_id)

    # commit前にレスポンスデータを生成（MissingGreenletエラー対策）
    response_data = _to_withdrawal_response(loaded_request)

    # commitはレスポンス生成後に実行
    await db.commit()

    return response_data


@router.get("")
async def get_withdrawal_requests(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: Staff = Depends(deps.get_current_user),
    status_filter: Optional[RequestStatus] = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=100)
):
    """
    退会リクエスト一覧を取得

    - app_admin: 全件取得可能
    - owner: 自事務所のリクエストのみ取得可能
    - manager/employee: アクセス不可 (403)
    """
    # 権限チェック
    if current_user.role not in [StaffRole.app_admin, StaffRole.owner]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ja.WITHDRAWAL_LIST_OWNER_OR_ADMIN_ONLY
        )

    # ownerの場合は自事務所のみ
    office_id = None
    if current_user.role == StaffRole.owner:
        if not current_user.office_associations:
            return {
                "requests": [],
                "total": 0,
                "skip": skip,
                "limit": limit
            }
        office_id = current_user.office_associations[0].office_id

    # CRUD層を使用して取得
    if office_id:
        requests, total = await crud_approval_request.get_by_office(
            db,
            office_id=office_id,
            resource_type=ApprovalResourceType.withdrawal,
            status_filter=status_filter,
            skip=skip,
            limit=limit,
            include_test_data=True
        )
    else:
        # app_adminの場合は全件取得
        query = select(ApprovalRequest).where(
            ApprovalRequest.resource_type == ApprovalResourceType.withdrawal
        ).options(
            selectinload(ApprovalRequest.requester),
            selectinload(ApprovalRequest.reviewer),
            selectinload(ApprovalRequest.office)
        )

        if status_filter:
            query = query.where(ApprovalRequest.status == status_filter)

        # 総件数取得
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # ページネーション
        query = query.order_by(ApprovalRequest.created_at.desc())
        query = query.offset(skip).limit(limit)

        result = await db.execute(query)
        requests = list(result.scalars().all())

    items = [_to_withdrawal_response(req) for req in requests]

    # フロントエンドの期待する形式に合わせる
    return {
        "requests": items,  # フロントエンドは "requests" キーを期待
        "total": total,
        "skip": skip,
        "limit": limit
    }


@router.patch("/{request_id}/approve", response_model=WithdrawalRequestRead)
async def approve_withdrawal_request(
    request: Request,
    *,
    db: AsyncSession = Depends(deps.get_db),
    request_id: UUID,
    obj_in: WithdrawalRequestApprove,
    current_user: Staff = Depends(deps.get_current_user)
) -> WithdrawalRequestRead:
    """
    退会リクエストを承認

    - app_adminのみ承認可能
    - 403: リクエストを承認する権限がありません
    - 404: リクエストが見つかりません
    - 400: 既に処理済みのリクエスト
    """
    # 権限チェック: app_adminのみ
    if current_user.role != StaffRole.app_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ja.WITHDRAWAL_APPROVE_APP_ADMIN_ONLY
        )

    # リクエスト取得
    approval_req = await crud_approval_request.get_by_id_with_relations(db, request_id)

    if not approval_req or approval_req.resource_type != ApprovalResourceType.withdrawal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ja.WITHDRAWAL_REQUEST_NOT_FOUND
        )

    # 処理済みチェック
    if approval_req.status != RequestStatus.pending:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ja.WITHDRAWAL_ALREADY_PROCESSED.format(status=approval_req.status.value)
        )

    # CRUD層を使用して承認処理
    approved_request = await crud_approval_request.approve(
        db,
        request_id=request_id,
        reviewer_staff_id=current_user.id,
        reviewer_notes=obj_in.reviewer_notes
    )

    # 監査ログを記録
    ip_address, user_agent = _get_client_info(request)
    await crud_audit_log.create_log(
        db,
        actor_id=current_user.id,
        action="withdrawal.approved",
        target_type="withdrawal_request",
        target_id=request_id,
        office_id=approval_req.office_id,
        actor_role=current_user.role.value,
        ip_address=ip_address,
        user_agent=user_agent,
        details={
            "reviewer_notes": obj_in.reviewer_notes,
            "requester_staff_id": str(approval_req.requester_staff_id)
        },
        is_test_data=getattr(approval_req, 'is_test_data', False)
    )

    # commit前にリレーションをロード
    loaded_request = await crud_approval_request.get_by_id_with_relations(db, request_id)

    # commit前にレスポンスデータを生成（MissingGreenletエラー対策）
    response_data = _to_withdrawal_response(loaded_request)

    # commitはレスポンス生成後に実行
    await db.commit()

    return response_data


@router.patch("/{request_id}/reject", response_model=WithdrawalRequestRead)
async def reject_withdrawal_request(
    request: Request,
    *,
    db: AsyncSession = Depends(deps.get_db),
    request_id: UUID,
    obj_in: WithdrawalRequestReject,
    current_user: Staff = Depends(deps.get_current_user)
) -> WithdrawalRequestRead:
    """
    退会リクエストを却下

    - app_adminのみ却下可能
    - 403: リクエストを却下する権限がありません
    - 404: リクエストが見つかりません
    - 400: 既に処理済みのリクエスト
    """
    # 権限チェック: app_adminのみ
    if current_user.role != StaffRole.app_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ja.WITHDRAWAL_REJECT_APP_ADMIN_ONLY
        )

    # リクエスト取得
    approval_req = await crud_approval_request.get_by_id_with_relations(db, request_id)

    if not approval_req or approval_req.resource_type != ApprovalResourceType.withdrawal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ja.WITHDRAWAL_REQUEST_NOT_FOUND
        )

    # 処理済みチェック
    if approval_req.status != RequestStatus.pending:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ja.WITHDRAWAL_ALREADY_PROCESSED.format(status=approval_req.status.value)
        )

    # CRUD層を使用して却下処理
    rejected_request = await crud_approval_request.reject(
        db,
        request_id=request_id,
        reviewer_staff_id=current_user.id,
        reviewer_notes=obj_in.reviewer_notes
    )

    # 監査ログを記録
    ip_address, user_agent = _get_client_info(request)
    await crud_audit_log.create_log(
        db,
        actor_id=current_user.id,
        action="withdrawal.rejected",
        target_type="withdrawal_request",
        target_id=request_id,
        office_id=approval_req.office_id,
        actor_role=current_user.role.value,
        ip_address=ip_address,
        user_agent=user_agent,
        details={
            "reviewer_notes": obj_in.reviewer_notes,
            "requester_staff_id": str(approval_req.requester_staff_id)
        },
        is_test_data=getattr(approval_req, 'is_test_data', False)
    )

    # commit前にリレーションをロード
    loaded_request = await crud_approval_request.get_by_id_with_relations(db, request_id)

    # commit前にレスポンスデータを生成（MissingGreenletエラー対策）
    response_data = _to_withdrawal_response(loaded_request)

    # commitはレスポンス生成後に実行
    await db.commit()

    return response_data
