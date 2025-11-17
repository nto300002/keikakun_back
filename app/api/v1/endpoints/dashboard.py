from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List

from app import schemas, crud, models
from app.api import deps
from app.services.dashboard_service import DashboardService
from app.messages import ja

router = APIRouter()


@router.get("/", response_model=schemas.dashboard.DashboardData)
async def get_dashboard(
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.Staff = Depends(deps.get_current_user),
    search_term: Optional[str] = None,
    sort_by: str = 'name_phonetic',
    sort_order: str = 'asc',
    is_overdue: Optional[bool] = None,
    is_upcoming: Optional[bool] = None,
    status: Optional[str] = None,
    cycle_number: Optional[int] = None,
    skip: int = 0,
    limit: int = 100,
) -> schemas.dashboard.DashboardData:
    """
    ダッシュボード情報を取得します。
    クエリパラメータを指定することで、利用者リストの検索・フィルタリングが可能です。
    """
    service = DashboardService(db)

    # 1. ログインユーザーの事業所情報を取得
    staff_office_info = await crud.staff.get_staff_with_primary_office(db=db, staff_id=current_user.id)
    if not staff_office_info:
        raise HTTPException(status_code=404, detail=ja.DASHBOARD_OFFICE_NOT_FOUND)
    staff, office = staff_office_info

    # 2. 事業所に所属する全利用者数を取得
    # この処理は重い可能性があるので、将来的には専用のcountメソッドをcrudに作ることを検討
    all_recipients = await crud.office.get_recipients_by_office_id(db=db, office_id=office.id)
    current_user_count = len(all_recipients)

    # 3. クエリパラメータに基づいてフィルター辞書を作成
    filters = {}
    if is_overdue is not None: filters["is_overdue"] = is_overdue
    if is_upcoming is not None: filters["is_upcoming"] = is_upcoming
    if status: filters["status"] = status
    if cycle_number is not None: filters["cycle_number"] = cycle_number
    
    # 4. フィルタリングされた利用者リストの情報を一括取得
    filtered_results = await crud.dashboard.get_filtered_summaries(
        db=db,
        office_ids=[office.id],
        sort_by=sort_by,
        sort_order=sort_order,
        filters=filters,
        search_term=search_term,
        skip=skip,
        limit=limit
    )

    # 5. DashboardSummaryスキーマに変換 (DBアクセスなし)
    recipient_summaries = []
    for recipient, cycle_count, latest_cycle in filtered_results:
        latest_step = service._get_latest_step(latest_cycle) if latest_cycle else None
        monitoring_due_date = service._calculate_monitoring_due_date(latest_cycle) if latest_cycle else None
        monitoring_deadline = latest_cycle.monitoring_deadline if latest_cycle else None

        summary = schemas.dashboard.DashboardSummary(
            id=str(recipient.id),
            full_name=f"{recipient.last_name} {recipient.first_name}",
            furigana=f"{recipient.last_name_furigana} {recipient.first_name_furigana}",
            current_cycle_number=cycle_count or 0,
            latest_step=latest_step,
            next_renewal_deadline=latest_cycle.next_renewal_deadline if latest_cycle else None,
            monitoring_due_date=monitoring_due_date,
            monitoring_deadline=monitoring_deadline
        )
        recipient_summaries.append(summary)

    # 6. 最終的なDashboardDataを構築
    max_user_count = service._get_max_user_count(office.billing_status)
    
    return schemas.dashboard.DashboardData(
        staff_name=staff.full_name,
        staff_role=staff.role,
        office_id=office.id,
        office_name=office.name,
        current_user_count=current_user_count,
        max_user_count=max_user_count,
        billing_status=office.billing_status,
        recipients=recipient_summaries
    )