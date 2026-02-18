from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List, Annotated
import logging

from app import schemas, crud, models
from app.api import deps
from app.services.dashboard_service import DashboardService
from app.messages import ja
from app.core.limiter import limiter
from app.core.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

# セキュリティ: 入力バリデーション定数
MAX_SEARCH_TERM_LENGTH = 100
MAX_LIMIT = 1000
MIN_LIMIT = 1


@router.get("/", response_model=schemas.dashboard.DashboardData)
@limiter.limit(settings.RATE_LIMIT_DASHBOARD)  # レート制限: 設定ファイルから読み込み（DoS対策）
async def get_dashboard(
    request: Request,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.Staff = Depends(deps.get_current_user),
    search_term: Annotated[
        Optional[str],
        Query(max_length=MAX_SEARCH_TERM_LENGTH, description="検索ワード（100文字以内）")
    ] = None,
    sort_by: str = 'next_renewal_deadline',
    sort_order: str = 'asc',
    is_overdue: Optional[bool] = None,
    is_upcoming: Optional[bool] = None,
    has_assessment_due: Annotated[
        Optional[bool],
        Query(description="アセスメント開始期限が設定されている利用者のみ（5ステータス: アセスメント → 原案 → 担当者会議 → 本案 → モニタリング）")
    ] = None,
    status: Optional[str] = None,
    cycle_number: Optional[int] = None,
    skip: Annotated[int, Query(ge=0, description="スキップ件数")] = 0,
    limit: Annotated[
        int,
        Query(ge=MIN_LIMIT, le=MAX_LIMIT, description=f"取得件数（{MIN_LIMIT}～{MAX_LIMIT}）")
    ] = 100,
) -> schemas.dashboard.DashboardData:
    """
    ダッシュボード情報を取得します。
    クエリパラメータを指定することで、利用者リストの検索・フィルタリングが可能です。

    レート制限: 60リクエスト/分（DoS対策）
    """
    service = DashboardService(db)

    # 1. ログインユーザーの事業所情報を取得
    staff_office_info = await crud.staff.get_staff_with_primary_office(db=db, staff_id=current_user.id)
    if not staff_office_info:
        raise HTTPException(status_code=404, detail=ja.DASHBOARD_OFFICE_NOT_FOUND)
    staff, office = staff_office_info

    # 2. 事業所に所属する全利用者数を取得（COUNT(*)クエリで効率的に）
    current_user_count = await crud.dashboard.count_office_recipients(
        db=db,
        office_id=office.id
    )

    # 3. クエリパラメータに基づいてフィルター辞書を作成
    filters = {}
    if is_overdue is not None: filters["is_overdue"] = is_overdue
    if is_upcoming is not None: filters["is_upcoming"] = is_upcoming
    if has_assessment_due is not None: filters["has_assessment_due"] = has_assessment_due
    if status: filters["status"] = status
    if cycle_number is not None: filters["cycle_number"] = cycle_number

    # 4. フィルタリング後の件数を取得（ページネーション前）
    filtered_count = await crud.dashboard.count_filtered_summaries(
        db=db,
        office_ids=[office.id],
        filters=filters,
        search_term=search_term
    )

    # 5. フィルタリングされた利用者リストの情報を一括取得（ページネーション適用）
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

    # 6. DashboardSummaryスキーマに変換 (DBアクセスなし)
    recipient_summaries = []
    for recipient, cycle_count, latest_cycle in filtered_results:
        latest_step = service._get_latest_step(latest_cycle) if latest_cycle else None
        monitoring_due_date = service._calculate_monitoring_due_date(latest_cycle) if latest_cycle else None
        next_plan_start_date = latest_cycle.next_plan_start_date if latest_cycle else None

        # 次回計画開始までの残り日数を計算
        next_plan_start_days_remaining = service._calculate_next_plan_start_days_remaining(
            recipient, latest_cycle
        )

        summary = schemas.dashboard.DashboardSummary(
            id=str(recipient.id),
            full_name=f"{recipient.last_name} {recipient.first_name}",
            last_name=recipient.last_name,
            first_name=recipient.first_name,
            furigana=f"{recipient.last_name_furigana} {recipient.first_name_furigana}",
            current_cycle_number=cycle_count or 0,
            latest_step=latest_step,
            next_renewal_deadline=latest_cycle.next_renewal_deadline if latest_cycle else None,
            monitoring_due_date=monitoring_due_date,
            next_plan_start_date=next_plan_start_date,
            next_plan_start_days_remaining=next_plan_start_days_remaining
        )
        recipient_summaries.append(summary)

    # 7. Billing情報を取得
    billing = await crud.billing.get_by_office_id(db=db, office_id=office.id)

    # Billing情報が存在しない場合、自動的に作成（既存Officeの救済措置）
    if not billing:
        logger.warning(f"Billing not found for office {office.id}, auto-creating with 180-day trial")
        billing = await crud.billing.create_for_office(
            db=db,
            office_id=office.id,
            trial_days=180
        )
        logger.info(f"Auto-created billing record: id={billing.id}, office_id={office.id}")

    # 8. 最終的なDashboardDataを構築
    max_user_count = service._get_max_user_count(billing.billing_status)

    return schemas.dashboard.DashboardData(
        staff_name=staff.full_name,
        staff_role=staff.role,
        office_id=office.id,
        office_name=office.name,
        current_user_count=current_user_count,  # 総利用者数（フィルタリング無視）
        filtered_count=filtered_count,          # フィルタリング後の件数（ページネーション前）
        max_user_count=max_user_count,
        billing_status=billing.billing_status,
        recipients=recipient_summaries
    )