from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud, schemas
from app.api import deps

# DIするためのヘルパー関数
async def get_staff_crud():
    return crud.staff

router = APIRouter()


@router.post(
    "/register-admin",
    response_model=schemas.staff.Staff,
    status_code=status.HTTP_201_CREATED,
)
async def register_admin(
    *,
    db: AsyncSession = Depends(deps.get_db),
    staff_in: schemas.staff.StaffCreate,
    staff_crud=Depends(get_staff_crud),
):
    """
    サービス責任者ロールを持つ新しいスタッフを作成します。
    """
    user = await staff_crud.get_by_email(db, email=staff_in.email)
    if user:
        raise HTTPException(
            status_code=409,  # Conflict
            detail="The user with this email already exists in the system.",
        )

    user = await staff_crud.create_admin(db=db, obj_in=staff_in)
    return user
