from typing import List, Optional
from uuid import UUID
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select, update

from app.crud.base import CRUDBase
from app.models.role_change_request import RoleChangeRequest
from app.models.enums import StaffRole, RequestStatus
from app.schemas.role_change_request import (
    RoleChangeRequestCreate,
    RoleChangeRequestApprove,
    RoleChangeRequestReject,
)


class CRUDRoleChangeRequest(CRUDBase[RoleChangeRequest, RoleChangeRequestCreate, RoleChangeRequestApprove]):

    async def create(
        self,
        db: AsyncSession,
        *,
        obj_in: RoleChangeRequestCreate,
        requester_staff_id: UUID,
        office_id: UUID,
        from_role: StaffRole
    ) -> RoleChangeRequest:
        """Role変更リクエストを作成"""
        db_obj = RoleChangeRequest(
            requester_staff_id=requester_staff_id,
            office_id=office_id,
            from_role=from_role,
            requested_role=obj_in.requested_role,
            request_notes=obj_in.request_notes,
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
    ) -> List[RoleChangeRequest]:
        """リクエスト作成者IDでリクエスト一覧を取得"""
        result = await db.execute(
            select(self.model)
            .where(self.model.requester_staff_id == requester_staff_id)
            .order_by(self.model.created_at.desc())
            .options(
                selectinload(self.model.requester),
                selectinload(self.model.reviewer),
                selectinload(self.model.office)
            )
        )
        return list(result.scalars().all())

    async def get_pending_for_approver(
        self,
        db: AsyncSession,
        approver_staff_id: UUID,
        approver_role: StaffRole,
        office_id: UUID
    ) -> List[RoleChangeRequest]:
        """
        承認者が承認可能なpendingリクエスト一覧を取得

        承認権限のルール:
        - Manager: employee → manager/owner のリクエストを承認可能
        - Owner: すべてのリクエストを承認可能
        """
        query = select(self.model).where(
            self.model.office_id == office_id,
            self.model.status == RequestStatus.pending
        )

        # Manager権限の場合: employee → manager/owner のみ
        if approver_role == StaffRole.manager:
            query = query.where(self.model.from_role == StaffRole.employee)
        # Owner権限の場合: すべてのリクエスト

        query = query.order_by(self.model.created_at.desc()).options(
            selectinload(self.model.requester),
            selectinload(self.model.office)
        )

        result = await db.execute(query)
        return list(result.scalars().all())

    async def approve(
        self,
        db: AsyncSession,
        request_id: UUID,
        reviewer_staff_id: UUID,
        reviewer_notes: Optional[str] = None
    ) -> RoleChangeRequest:
        """Role変更リクエストを承認"""
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
                reviewed_by_staff_id=reviewer_staff_id,
                reviewed_at=datetime.now(),
                reviewer_notes=reviewer_notes,
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
                selectinload(self.model.reviewer),
                selectinload(self.model.office)
            )
        )
        return result.scalar_one()

    async def reject(
        self,
        db: AsyncSession,
        request_id: UUID,
        reviewer_staff_id: UUID,
        reviewer_notes: Optional[str] = None
    ) -> RoleChangeRequest:
        """Role変更リクエストを却下"""
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
                reviewed_by_staff_id=reviewer_staff_id,
                reviewed_at=datetime.now(),
                reviewer_notes=reviewer_notes,
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
                selectinload(self.model.reviewer),
                selectinload(self.model.office)
            )
        )
        return result.scalar_one()

    async def get_by_status(
        self,
        db: AsyncSession,
        office_id: UUID,
        status: RequestStatus
    ) -> List[RoleChangeRequest]:
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
                selectinload(self.model.reviewer),
                selectinload(self.model.office)
            )
        )
        return list(result.scalars().all())

    async def get_by_office(
        self,
        db: AsyncSession,
        office_id: UUID
    ) -> List[RoleChangeRequest]:
        """事業所IDでリクエスト一覧を取得"""
        result = await db.execute(
            select(self.model)
            .where(self.model.office_id == office_id)
            .order_by(self.model.created_at.desc())
            .options(
                selectinload(self.model.requester),
                selectinload(self.model.reviewer),
                selectinload(self.model.office)
            )
        )
        return list(result.scalars().all())


# インスタンス化
crud_role_change_request = CRUDRoleChangeRequest(RoleChangeRequest)
