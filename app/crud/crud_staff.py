from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.security import get_password_hash
from app.models.enums import StaffRole
from app.models.staff import Staff
from app.schemas.staff import StaffCreate


class CRUDStaff:
    async def get_by_email(self, db: AsyncSession, *, email: str) -> Staff | None:
        query = select(Staff).filter(Staff.email == email)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def create_admin(self, db: AsyncSession, *, obj_in: StaffCreate) -> Staff:
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


staff = CRUDStaff()