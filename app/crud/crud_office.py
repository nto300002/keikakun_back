from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.crud.base import CRUDBase
from app.models.office import Office, OfficeStaff
from app.models.staff import Staff
from app.schemas.office import OfficeCreate, OfficeUpdate


class CRUDOffice(CRUDBase[Office, OfficeCreate, OfficeUpdate]):
    async def create_with_owner(
        self, db: AsyncSession, *, obj_in: OfficeCreate, user: Staff
    ) -> Office:
        """
        Officeを作成し、作成者をOfficeStaffとして関連付けます。
        """
        db_office = Office(
            name=obj_in.name,
            type=obj_in.office_type,  # スキーマのoffice_typeをモデルのtypeにマッピング
            created_by=user.id,
            last_modified_by=user.id,
        )
        db.add(db_office)
        await db.flush()  # OfficeをDBにINSERTし、IDを確定させる

        office_staff = OfficeStaff(
            staff_id=user.id,
            office_id=db_office.id,
            is_primary=True,
        )
        db.add(office_staff)
        
        await db.commit()
        await db.refresh(db_office)
        return db_office

    async def get_by_name(self, db: AsyncSession, *, name: str) -> Optional[Office]:
        result = await db.execute(select(Office).filter(Office.name == name))
        return result.scalars().first()


crud_office = CRUDOffice(Office)
