"""
スタッフ監査ログ CRUD操作
"""
import uuid
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.staff_audit_log import StaffAuditLog


class CRUDStaffAuditLog(CRUDBase[StaffAuditLog, Dict[str, Any], Dict[str, Any]]):
    """
    スタッフ監査ログのCRUD操作
    """

    async def create_audit_log(
        self,
        db: AsyncSession,
        *,
        staff_id: uuid.UUID,
        action: str,
        performed_by: uuid.UUID,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        details: Optional[dict] = None
    ) -> StaffAuditLog:
        """
        監査ログを作成

        Args:
            db: データベースセッション
            staff_id: 対象スタッフID
            action: 操作種別（"deleted", "created", "updated" など）
            performed_by: 操作実行者のスタッフID
            ip_address: 操作元のIPアドレス
            user_agent: 操作元のUser-Agent
            details: 操作の詳細情報（JSON形式）

        Returns:
            作成された監査ログ

        Note:
            - commitはエンドポイント層で行う
            - トランザクション管理は呼び出し側で行う
        """
        audit_log = StaffAuditLog(
            staff_id=staff_id,
            action=action,
            performed_by=performed_by,
            ip_address=ip_address,
            user_agent=user_agent,
            details=details
        )

        db.add(audit_log)
        await db.flush()

        return audit_log


# インスタンス化
staff_audit_log = CRUDStaffAuditLog(StaffAuditLog)
