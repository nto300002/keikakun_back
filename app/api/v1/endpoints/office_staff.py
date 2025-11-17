from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import crud, models, schemas
from app.api import deps
from app.messages import ja

router = APIRouter()


@router.post("/associate-office", status_code=status.HTTP_200_OK)
async def associate_staff_to_office(
    *,
    db: AsyncSession = Depends(deps.get_db),
    office_association: schemas.StaffOfficeAssociationCreate,
    current_user: models.Staff = Depends(deps.get_current_user),
) -> Any:
    """
    現在ログインしているスタッフを指定された事業所に関連付ける
    """
    # employee または manager のみが実行可能
    if current_user.role == models.StaffRole.owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ja.OFFICE_OWNER_CANNOT_USE_ENDPOINT,
        )

    # ユーザーが既に事業所に所属していないかチェック
    stmt = select(models.Staff).options(selectinload(models.Staff.office_associations)).where(models.Staff.id == current_user.id)
    result = await db.execute(stmt)
    user_in_db = result.scalar_one_or_none()

    if not user_in_db:
        raise HTTPException(status_code=404, detail=ja.OFFICE_USER_NOT_FOUND)

    if user_in_db.office_associations:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ja.OFFICE_ALREADY_ASSOCIATED,
        )

    # 指定された事業所が存在するかチェック
    office = await crud.office.get(db, id=office_association.office_id)
    if not office:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ja.OFFICE_NOT_FOUND,
        )

    # 関連付けを作成
    office_staff_data = {
        "staff_id": current_user.id,
        "office_id": office_association.office_id,
    }
    
    office_staff = await crud.office_staff.create(db=db, obj_in=office_staff_data)
    
    return {"message": "事業所への所属が完了しました。"}