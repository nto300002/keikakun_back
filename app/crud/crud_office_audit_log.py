"""
事務所監査ログのCRUD操作
"""
from typing import List, Dict, Any
from uuid import UUID
import json

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc

from app.models.office import OfficeAuditLog


class CRUDOfficeAuditLog:
    async def create_office_update_log(
        self,
        db: AsyncSession,
        *,
        office_id: UUID,
        staff_id: UUID,
        action_type: str,
        old_values: Dict[str, Any],
        new_values: Dict[str, Any]
    ) -> OfficeAuditLog:
        """
        事務所情報変更の監査ログを作成
        - flush のみ実行（commit は endpoint で実行）
        """
        # 変更内容を JSON 形式で保存
        details = json.dumps({
            "old_values": old_values,
            "new_values": new_values
        }, ensure_ascii=False)

        audit_log = OfficeAuditLog(
            office_id=office_id,
            staff_id=staff_id,
            action_type=action_type,
            details=details
        )

        db.add(audit_log)
        await db.flush()
        await db.refresh(audit_log)

        return audit_log

    async def get_by_office_id(
        self,
        db: AsyncSession,
        *,
        office_id: UUID,
        skip: int = 0,
        limit: int = 100
    ) -> List[OfficeAuditLog]:
        """
        事務所の監査ログを取得（最新順）
        """
        query = (
            select(OfficeAuditLog)
            .where(OfficeAuditLog.office_id == office_id)
            .order_by(desc(OfficeAuditLog.created_at))
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(query)
        return list(result.scalars().all())


crud_office_audit_log = CRUDOfficeAuditLog()
