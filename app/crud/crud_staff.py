import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.security import get_password_hash
from app.models.enums import StaffRole
from app.models.staff import Staff
from app.models.office import OfficeStaff # OfficeStaffをインポート
from app.schemas.staff import AdminCreate, StaffCreate


class CRUDStaff:
    async def get(self, db: AsyncSession, *, id: uuid.UUID) -> Staff | None:
        query = select(Staff).filter(Staff.id == id).options(
            # 文字列ではなく、クラス属性を直接指定する
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        )
        result = await db.execute(query)
        staff = result.scalar_one_or_none()
        if staff and staff.office_associations:
            staff.office = staff.office_associations[0].office
        else:
            staff.office = None
        return staff

    async def get_by_email(self, db: AsyncSession, *, email: str) -> Staff | None:
        query = select(Staff).filter(Staff.email == email)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def create_admin(self, db: AsyncSession, *, obj_in: AdminCreate) -> Staff:
        db_obj = Staff(
            email=obj_in.email,
            hashed_password=get_password_hash(obj_in.password),
            name=obj_in.name,
            role=StaffRole.owner,
        )
        db.add(db_obj)
        await db.flush()  # トランザクションはテスト側で管理するためcommitはしない
        await db.refresh(db_obj)
        return db_obj

    async def create_staff(self, db: AsyncSession, *, obj_in: StaffCreate) -> Staff:
        db_obj = Staff(
            email=obj_in.email,
            hashed_password=get_password_hash(obj_in.password),
            name=obj_in.name,
            role=obj_in.role,
        )
        db.add(db_obj)
        await db.flush()  # トランザクションはテスト側で管理するためcommitはしない
        await db.refresh(db_obj)
        return db_obj


staff = CRUDStaff()