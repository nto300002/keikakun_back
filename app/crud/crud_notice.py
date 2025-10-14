from typing import List, Optional
from uuid import UUID
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select, update, delete

from app.crud.base import CRUDBase
from app.models.notice import Notice
from app.schemas.notice import NoticeCreate, NoticeUpdate


class CRUDNotice(CRUDBase[Notice, NoticeCreate, NoticeUpdate]):

    async def get_by_staff_id(
        self,
        db: AsyncSession,
        staff_id: UUID
    ) -> List[Notice]:
        """スタッフIDでお知らせ一覧を取得"""
        result = await db.execute(
            select(self.model)
            .where(self.model.recipient_staff_id == staff_id)
            .order_by(self.model.created_at.desc())
            .options(
                selectinload(self.model.recipient_staff),
                selectinload(self.model.office)
            )
        )
        return list(result.scalars().all())

    async def get_unread_by_staff_id(
        self,
        db: AsyncSession,
        staff_id: UUID
    ) -> List[Notice]:
        """スタッフIDで未読のお知らせ一覧を取得"""
        result = await db.execute(
            select(self.model)
            .where(
                self.model.recipient_staff_id == staff_id,
                self.model.is_read == False
            )
            .order_by(self.model.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_office_id(
        self,
        db: AsyncSession,
        office_id: UUID
    ) -> List[Notice]:
        """事業所IDでお知らせ一覧を取得"""
        result = await db.execute(
            select(self.model)
            .where(self.model.office_id == office_id)
            .order_by(self.model.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_type(
        self,
        db: AsyncSession,
        staff_id: UUID,
        notice_type: str
    ) -> List[Notice]:
        """スタッフIDとタイプでお知らせ一覧を取得"""
        result = await db.execute(
            select(self.model)
            .where(
                self.model.recipient_staff_id == staff_id,
                self.model.type == notice_type
            )
            .order_by(self.model.created_at.desc())
        )
        return list(result.scalars().all())

    async def mark_as_read(
        self,
        db: AsyncSession,
        notice_id: UUID
    ) -> Optional[Notice]:
        """お知らせを既読にする"""
        await db.execute(
            update(self.model)
            .where(self.model.id == notice_id)
            .values(is_read=True, updated_at=datetime.now())
        )
        await db.commit()
        return await self.get(db, notice_id)

    async def mark_all_as_read(
        self,
        db: AsyncSession,
        staff_id: UUID
    ) -> int:
        """スタッフの全お知らせを既読にする"""
        result = await db.execute(
            update(self.model)
            .where(
                self.model.recipient_staff_id == staff_id,
                self.model.is_read == False
            )
            .values(is_read=True, updated_at=datetime.now())
        )
        await db.commit()
        return result.rowcount

    async def delete_old_read_notices(
        self,
        db: AsyncSession,
        days_old: int = 30
    ) -> int:
        """古い既読お知らせを削除"""
        cutoff_date = datetime.now() - timedelta(days=days_old)
        result = await db.execute(
            delete(self.model)
            .where(
                self.model.is_read == True,
                self.model.created_at < cutoff_date
            )
        )
        await db.commit()
        return result.rowcount


# インスタンス化
crud_notice = CRUDNotice(Notice)
