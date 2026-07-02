"""
app_admin用監査ログAPIエンドポイント
"""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_app_admin
from app.models.staff import Staff
from app.models.office import Office
from app.crud.crud_audit_log import audit_log as crud_audit_log

router = APIRouter()


@router.get("")
async def get_audit_logs(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: Staff = Depends(require_app_admin),
    target_type: Optional[str] = Query(None, description="対象リソースタイプでフィルタ（staff, office, withdrawal_request, terms_agreement）"),
    skip: int = Query(0, ge=0, description="スキップ数"),
    limit: int = Query(50, ge=1, le=50, description="取得数上限（最大50）")
):
    """
    監査ログ一覧を取得（app_admin専用）

    - **target_type**: 対象リソースタイプでフィルタ
    - **skip**: ページネーション用オフセット
    - **limit**: 取得件数（デフォルト50件、最大50件）
    """
    # 監査ログを取得
    logs, total = await crud_audit_log.get_logs(
        db=db,
        target_type=target_type,
        skip=skip,
        limit=limit,
        include_test_data=False
    )

    staff_ids = {log.staff_id for log in logs if log.staff_id is not None}
    office_ids = {log.office_id for log in logs if log.office_id is not None}

    staff_names = {}
    if staff_ids:
        staff_result = await db.execute(
            select(Staff.id, Staff.full_name).where(Staff.id.in_(staff_ids))
        )
        staff_names = {staff_id: full_name for staff_id, full_name in staff_result.all()}

    office_names = {}
    if office_ids:
        office_result = await db.execute(
            select(Office.id, Office.name).where(Office.id.in_(office_ids))
        )
        office_names = {office_id: name for office_id, name in office_result.all()}

    # レスポンスを作成（標準的なページネーション形式）
    items = []
    for log in logs:
        log_dict = {
            "id": log.id,
            "staff_id": log.staff_id,
            "actor_id": log.staff_id,
            "actor_name": staff_names.get(log.staff_id),
            "actor_role": log.actor_role,
            "action": log.action,
            "target_type": log.target_type,
            "target_id": log.target_id,
            "office_id": log.office_id,
            "office_name": office_names.get(log.office_id),
            "ip_address": log.ip_address,
            "user_agent": log.user_agent,
            "details": log.details,
            "timestamp": log.timestamp,
            "created_at": log.timestamp,
            "is_test_data": log.is_test_data
        }
        items.append(log_dict)

    return {
        "logs": items,  # フロントエンドの期待値に合わせて "logs" を使用
        "total": total,
        "skip": skip,
        "limit": limit
    }
