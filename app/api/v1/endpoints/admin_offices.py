"""
app_admin用事務所管理エンドポイント
"""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload

from app.api.deps import get_db, require_app_admin
from app.models.staff import Staff
from app.models.office import Office, OfficeStaff
from app.schemas.office import OfficeListItemResponse, OfficeDetailResponse, StaffInOffice

router = APIRouter()


@router.get("", response_model=List[OfficeListItemResponse])
async def get_offices(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: Staff = Depends(require_app_admin),
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 30
) -> List[Office]:
    """
    事務所一覧を取得（app_admin専用）

    - **search**: 事務所名で検索（部分一致）
    - **skip**: ページネーション用オフセット
    - **limit**: 取得件数（デフォルト30件）
    """
    query = select(Office)

    # 名前検索
    if search:
        query = query.where(Office.name.ilike(f"%{search}%"))

    # ページネーション
    query = query.offset(skip).limit(limit).order_by(Office.created_at.desc())

    result = await db.execute(query)
    offices = result.scalars().all()

    return offices


@router.get("/{office_id}", response_model=OfficeDetailResponse)
async def get_office_detail(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: Staff = Depends(require_app_admin),
    office_id: UUID
) -> dict:
    """
    事務所詳細を取得（app_admin専用）

    事務所情報 + スタッフ一覧を返す
    """
    # 事務所を取得（スタッフ情報を含む）
    query = (
        select(Office)
        .where(Office.id == office_id)
        .options(
            selectinload(Office.staff_associations)
            .selectinload(OfficeStaff.staff)
        )
    )

    result = await db.execute(query)
    office = result.scalar_one_or_none()

    if not office:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="事務所が見つかりません"
        )

    # スタッフ情報を整形
    staffs = [
        StaffInOffice(
            id=os.staff.id,
            full_name=os.staff.full_name,
            email=os.staff.email,
            role=os.staff.role.value,
            is_mfa_enabled=os.staff.is_mfa_enabled,
            is_email_verified=os.staff.is_email_verified
        )
        for os in office.staff_associations
        if os.staff and not os.staff.is_deleted  # 削除されていないスタッフのみ
    ]

    # レスポンスを構築
    return OfficeDetailResponse(
        id=office.id,
        name=office.name,
        type=office.type,  # Pydanticが自動的に.valueを取得
        address=office.address,
        phone_number=office.phone_number,
        email=office.email,
        is_deleted=office.is_deleted,
        created_at=office.created_at,
        updated_at=office.updated_at,
        staffs=staffs
    )
