from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import crud, models, schemas
from app.api import deps
from app.messages import ja

router = APIRouter()


@router.get("/", response_model=list[schemas.OfficeResponse])
async def read_offices(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.Staff = Depends(deps.get_current_user),
) -> Any:
    """
    すべての事業所の一覧を取得する（employee/managerが選択するため）
    """
    offices = await crud.office.get_multi(db)
    return offices


@router.get("/me", response_model=schemas.OfficeResponse)
async def read_my_office(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.Staff = Depends(deps.get_current_user),
) -> Any:
    """
    現在ログインしているユーザーが所属する事業所の情報を取得する
    """
    # ユーザーの所属情報を eager load する
    stmt = (
        select(models.Staff)
        .options(selectinload(models.Staff.office_associations)
        .selectinload(models.OfficeStaff.office))
        .where(models.Staff.id == current_user.id)
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not user.office_associations:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ja.OFFICE_NOT_FOUND_FOR_USER,
        )

    # ユーザーは複数の事業所に所属できる設計になっているが、
    # 現状は最初の事業所を返す（多くの場合は一つのはず）
    office = user.office_associations[0].office
    if not office:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ja.OFFICE_INFO_NOT_FOUND,
        )

    return office


@router.post("/setup", response_model=schemas.OfficeResponse, status_code=status.HTTP_201_CREATED)
async def setup_office(
    *, 
    db: AsyncSession = Depends(deps.get_db),
    office_in: schemas.OfficeCreate,
    current_user: models.Staff = Depends(deps.get_current_user),
) -> Any:
    """
    事業所を新規作成し、作成したユーザーを事業所に所属させる
    """
    if current_user.role != models.StaffRole.owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ja.PERM_OPERATION_FORBIDDEN,
        )

    # DBから最新のユーザー情報を取得し、関連をロード
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

    # 同じ名前の事業所が既に存在するかチェック
    existing_office = await crud.office.get_by_name(db, name=office_in.name)
    if existing_office:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=ja.OFFICE_NAME_ALREADY_EXISTS,
        )

    try:
        office = await crud.office.create_with_owner(db=db, obj_in=office_in, user=user_in_db)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=ja.OFFICE_NAME_ALREADY_EXISTS,
        )

    return office