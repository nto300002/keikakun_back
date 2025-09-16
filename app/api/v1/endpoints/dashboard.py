from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.api import deps
from app.models.staff import Staff
from app.services.dashboard_service import DashboardService

router = APIRouter()


@router.get("/", response_model=schemas.dashboard.DashboardData)
async def get_dashboard(
    current_user: Staff = Depends(deps.get_current_user),
    db: AsyncSession = Depends(deps.get_db),
) -> schemas.dashboard.DashboardData:
    """
    ダッシュボード情報を取得
    ログインユーザーが所属する事業所の情報と利用者一覧を取得します。
    """
    service = DashboardService(db)
    dashboard_data = await service.get_dashboard_data(current_user.id)
    
    if not dashboard_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="事業所情報が見つかりません"
        )
    
    return dashboard_data