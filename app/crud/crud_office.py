from typing import List, Optional, Dict, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from fastapi import HTTPException

from app.crud.base import CRUDBase
from app.models.office import Office, OfficeStaff
from app.models.staff import Staff
from app.models.welfare_recipient import WelfareRecipient, OfficeWelfareRecipient
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

    async def get_recipients_by_office_id(self, db: AsyncSession, *, office_id: UUID) -> List[WelfareRecipient]:
        """
        事業所IDに基づいて、その事業所に所属するすべての利用者を取得します。
        """
        query = (
            select(WelfareRecipient)
            .join(OfficeWelfareRecipient, WelfareRecipient.id == OfficeWelfareRecipient.welfare_recipient_id)
            .where(OfficeWelfareRecipient.office_id == office_id)
        )
        result = await db.execute(query)
        return result.scalars().all()

    async def update_office_info(
        self,
        db: AsyncSession,
        *,
        office_id: UUID,
        update_data: Dict[str, Any]
    ) -> Office:
        """
        事務所情報を更新
        - flush のみ実行（commit は endpoint で実行）
        - 存在しない場合は例外を発生
        """
        # 既存の事務所を取得
        office = await db.get(Office, office_id)
        if not office:
            raise HTTPException(status_code=404, detail="Office not found")

        # 更新データを適用
        for key, value in update_data.items():
            if hasattr(office, key):
                setattr(office, key, value)

        # flush のみ（commit はエンドポイントで）
        await db.flush()
        await db.refresh(office)

        return office


crud_office = CRUDOffice(Office)
