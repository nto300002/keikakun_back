import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.security import get_password_hash
from app.models.enums import StaffRole
from app.models.staff import Staff
from app.models.office import Office, OfficeStaff 
from app.schemas.staff import AdminCreate, StaffCreate


class CRUDStaff:
    async def get(self, db: AsyncSession, *, id: uuid.UUID) -> Staff | None:
        query = select(Staff).filter(Staff.id == id).options(
            # 文字列ではなく、クラス属性を直接指定する
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office),
            selectinload(Staff.mfa_backup_codes)
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_by_email(self, db: AsyncSession, *, email: str) -> Staff | None:
        query = select(Staff).filter(Staff.email == email)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def create_admin(self, db: AsyncSession, *, obj_in: AdminCreate) -> Staff:
        db_obj = Staff(
            email=obj_in.email,
            hashed_password=get_password_hash(obj_in.password),
            first_name=obj_in.first_name,
            last_name=obj_in.last_name,
            full_name=f"{obj_in.last_name} {obj_in.first_name}",
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
            first_name=obj_in.first_name,
            last_name=obj_in.last_name,
            full_name=f"{obj_in.last_name} {obj_in.first_name}",
            role=obj_in.role,
        )
        db.add(db_obj)
        await db.flush()  # トランザクションはテスト側で管理するためcommitはしない
        await db.refresh(db_obj)
        return db_obj

    async def get_staff_with_primary_office(self, db: AsyncSession, *, staff_id: uuid.UUID) -> tuple[Staff, Office] | None:
        """
        スタッフIDに基づいて、スタッフとそのプライマリ事業所を取得します。
        """
        query = (
            select(Staff, Office)
            .join(OfficeStaff, Staff.id == OfficeStaff.staff_id)
            .join(Office, OfficeStaff.office_id == Office.id)
            .where(Staff.id == staff_id, OfficeStaff.is_primary == True)
        )
        result = await db.execute(query)
        return result.one_or_none()


staff = CRUDStaff()