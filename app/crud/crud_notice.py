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

    async def update_type_by_link_url(
        self,
        db: AsyncSession,
        link_url: str,
        new_type: str,
        old_type: Optional[str] = None
    ) -> int:
        """
        link_urlで通知を検索してtypeを更新

        Args:
            db: データベースセッション
            link_url: 検索するlink_url
            new_type: 新しいtype値
            old_type: 更新対象の古いtype値（オプション）。指定した場合、このtypeの通知のみ更新

        Returns:
            更新された件数

        Note:
            このメソッドはcommitしない。親メソッドで最後に1回だけcommitする。
        """
        stmt = update(self.model).where(self.model.link_url == link_url)

        # old_typeが指定されている場合は、そのtypeの通知のみ更新
        if old_type is not None:
            stmt = stmt.where(self.model.type == old_type)

        stmt = stmt.values(type=new_type, updated_at=datetime.now())
        result = await db.execute(stmt)
        return result.rowcount

    async def delete_old_notices_over_limit(
        self,
        db: AsyncSession,
        office_id: UUID,
        limit: int = 50
    ) -> int:
        """
        事務所の通知数が制限を超えた場合、古いものから削除

        Args:
            db: データベースセッション
            office_id: 事務所ID
            limit: 保持する最大通知数（デフォルト50件）

        Returns:
            削除された件数

        Note:
            このメソッドはcommitしない。親メソッドで最後に1回だけcommitする。
        """
        # 事務所の全通知を作成日時降順で取得
        result = await db.execute(
            select(self.model)
            .where(self.model.office_id == office_id)
            .order_by(self.model.created_at.desc())
        )
        notices = list(result.scalars().all())

        # 制限を超える通知を削除
        if len(notices) > limit:
            notices_to_delete = notices[limit:]
            delete_count = 0
            for notice in notices_to_delete:
                await db.delete(notice)
                delete_count += 1
            return delete_count

        return 0


# インスタンス化
crud_notice = CRUDNotice(Notice)
