from fastapi import APIRouter, Depends

from app import schemas
from app.api import deps
from app.models.staff import Staff

router = APIRouter()


@router.get("/me", response_model=schemas.staff.StaffRead)
async def read_users_me(
    current_user: Staff = Depends(deps.get_current_user),
) -> Staff:
    """
    認証済みユーザーの情報を取得
    """
    return current_user
