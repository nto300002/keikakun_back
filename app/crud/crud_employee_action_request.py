from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select, update

from app.crud.base import CRUDBase
from app.models.employee_action_request import EmployeeActionRequest
from app.models.enums import RequestStatus, ActionType, ResourceType
from app.schemas.employee_action_request import (
    EmployeeActionRequestCreate,
    EmployeeActionRequestApprove,
    EmployeeActionRequestReject,
)


class CRUDEmployeeActionRequest(CRUDBase[EmployeeActionRequest, EmployeeActionRequestCreate, EmployeeActionRequestApprove]):

    async def create(
        self,
        db: AsyncSession,
        *,
        obj_in: EmployeeActionRequestCreate,
        requester_staff_id: UUID,
        office_id: UUID
    ) -> EmployeeActionRequest:
        """Employee制限リクエストを作成"""
        db_obj = EmployeeActionRequest(
            requester_staff_id=requester_staff_id,
            office_id=office_id,
            resource_type=obj_in.resource_type,
            action_type=obj_in.action_type,
            resource_id=obj_in.resource_id,
            request_data=obj_in.request_data,
            status=RequestStatus.pending
        )
        db.add(db_obj)
        await db.flush()
        await db.refresh(db_obj)
        return db_obj

    async def get_by_requester(
        self,
        db: AsyncSession,
        requester_staff_id: UUID
    ) -> List[EmployeeActionRequest]:
        """リクエスト作成者IDでリクエスト一覧を取得"""
        result = await db.execute(
            select(self.model)
            .where(self.model.requester_staff_id == requester_staff_id)
            .order_by(self.model.created_at.desc())
            .options(
                selectinload(self.model.requester),
                selectinload(self.model.approver),
                selectinload(self.model.office)
            )
        )
        return list(result.scalars().all())

    async def get_pending_for_approver(
        self,
        db: AsyncSession,
        office_id: UUID
    ) -> List[EmployeeActionRequest]:
        """
        承認者が承認可能なpendingリクエスト一覧を取得
        （manager/ownerが承認可能）
        """
        result = await db.execute(
            select(self.model)
            .where(
                self.model.office_id == office_id,
                self.model.status == RequestStatus.pending
            )
            .order_by(self.model.created_at.desc())
            .options(
                selectinload(self.model.requester),
                selectinload(self.model.office)
            )
        )
        return list(result.scalars().all())

    async def approve(
        self,
        db: AsyncSession,
        request_id: UUID,
        approver_staff_id: UUID,
        approver_notes: Optional[str] = None,
        execution_result: Optional[Dict[str, Any]] = None
    ) -> EmployeeActionRequest:
        """
        Employee制限リクエストを承認
        execution_result: 実際のアクション実行結果
        """
        # リクエストを取得
        request = await self.get(db, id=request_id)
        if not request:
            raise ValueError(f"Request {request_id} not found")

        # 既に処理済みの場合はエラー
        if request.status != RequestStatus.pending:
            raise ValueError(f"Request {request_id} is already processed with status {request.status}")

        # 承認処理
        await db.execute(
            update(self.model)
            .where(self.model.id == request_id)
            .values(
                status=RequestStatus.approved,
                approved_by_staff_id=approver_staff_id,
                approved_at=datetime.now(),
                approver_notes=approver_notes,
                execution_result=execution_result,
                updated_at=datetime.now()
            )
        )
        await db.flush()

        # 更新されたリクエストを返す（Eager loadingで関連データも取得）
        result = await db.execute(
            select(self.model)
            .where(self.model.id == request_id)
            .options(
                selectinload(self.model.requester),
                selectinload(self.model.approver),
                selectinload(self.model.office)
            )
        )
        return result.scalar_one()

    async def reject(
        self,
        db: AsyncSession,
        request_id: UUID,
        approver_staff_id: UUID,
        approver_notes: Optional[str] = None
    ) -> EmployeeActionRequest:
        """Employee制限リクエストを却下"""
        # リクエストを取得
        request = await self.get(db, id=request_id)
        if not request:
            raise ValueError(f"Request {request_id} not found")

        # 既に処理済みの場合はエラー
        if request.status != RequestStatus.pending:
            raise ValueError(f"Request {request_id} is already processed with status {request.status}")

        # 却下処理
        await db.execute(
            update(self.model)
            .where(self.model.id == request_id)
            .values(
                status=RequestStatus.rejected,
                approved_by_staff_id=approver_staff_id,
                approved_at=datetime.now(),
                approver_notes=approver_notes,
                updated_at=datetime.now()
            )
        )
        await db.flush()

        # 更新されたリクエストを返す（Eager loadingで関連データも取得）
        result = await db.execute(
            select(self.model)
            .where(self.model.id == request_id)
            .options(
                selectinload(self.model.requester),
                selectinload(self.model.approver),
                selectinload(self.model.office)
            )
        )
        return result.scalar_one()

    async def get_by_resource_type(
        self,
        db: AsyncSession,
        office_id: UUID,
        resource_type: ResourceType
    ) -> List[EmployeeActionRequest]:
        """リソースタイプでフィルタリングしてリクエストを取得"""
        result = await db.execute(
            select(self.model)
            .where(
                self.model.office_id == office_id,
                self.model.resource_type == resource_type
            )
            .order_by(self.model.created_at.desc())
            .options(
                selectinload(self.model.requester),
                selectinload(self.model.approver),
                selectinload(self.model.office)
            )
        )
        return list(result.scalars().all())

    async def get_by_action_type(
        self,
        db: AsyncSession,
        office_id: UUID,
        action_type: ActionType
    ) -> List[EmployeeActionRequest]:
        """アクションタイプでフィルタリングしてリクエストを取得"""
        result = await db.execute(
            select(self.model)
            .where(
                self.model.office_id == office_id,
                self.model.action_type == action_type
            )
            .order_by(self.model.created_at.desc())
            .options(
                selectinload(self.model.requester),
                selectinload(self.model.approver),
                selectinload(self.model.office)
            )
        )
        return list(result.scalars().all())

    async def get_by_status(
        self,
        db: AsyncSession,
        office_id: UUID,
        status: RequestStatus
    ) -> List[EmployeeActionRequest]:
        """ステータスでフィルタリングしてリクエストを取得"""
        result = await db.execute(
            select(self.model)
            .where(
                self.model.office_id == office_id,
                self.model.status == status
            )
            .order_by(self.model.created_at.desc())
            .options(
                selectinload(self.model.requester),
                selectinload(self.model.approver),
                selectinload(self.model.office)
            )
        )
        return list(result.scalars().all())


# インスタンス化
crud_employee_action_request = CRUDEmployeeActionRequest(EmployeeActionRequest)
