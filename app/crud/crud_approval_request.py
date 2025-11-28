"""
統合型承認リクエスト CRUD操作

役割変更、Employee操作、退会の各種承認リクエストを統合管理
"""
import uuid
import datetime
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select, update, and_, func
from fastapi import HTTPException, status

from app.crud.base import CRUDBase
from app.models.approval_request import ApprovalRequest
from app.models.enums import RequestStatus, ApprovalResourceType, StaffRole
from app.messages import ja


class CRUDApprovalRequest(CRUDBase[ApprovalRequest, Dict[str, Any], Dict[str, Any]]):
    """
    統合型承認リクエストのCRUD操作

    提供機能:
    - create_request: 承認リクエスト作成
    - get_pending_requests: 承認待ちリクエスト取得
    - approve: 承認処理
    - reject: 却下処理
    - execute: 承認後の実行処理（execution_result更新）
    """

    async def create_request(
        self,
        db: AsyncSession,
        *,
        requester_staff_id: uuid.UUID,
        office_id: uuid.UUID,
        resource_type: ApprovalResourceType,
        request_data: Optional[dict] = None,
        is_test_data: bool = False
    ) -> ApprovalRequest:
        """
        承認リクエストを作成

        Args:
            db: データベースセッション
            requester_staff_id: リクエスト作成者のスタッフID
            office_id: 対象事務所ID
            resource_type: リクエスト種別
            request_data: リクエスト固有のデータ
            is_test_data: テストデータフラグ

        Returns:
            作成された承認リクエスト
        """
        db_obj = ApprovalRequest(
            requester_staff_id=requester_staff_id,
            office_id=office_id,
            resource_type=resource_type,
            status=RequestStatus.pending,
            request_data=request_data,
            is_test_data=is_test_data
        )
        db.add(db_obj)
        await db.flush()
        await db.refresh(db_obj)
        return db_obj

    async def create_employee_action_request(
        self,
        db: AsyncSession,
        *,
        requester_staff_id: uuid.UUID,
        office_id: uuid.UUID,
        resource_type: str,  # ResourceType値（welfare_recipient, support_plan_cycle, etc.）
        action_type: str,  # ActionType値（create, update, delete）
        resource_id: Optional[uuid.UUID] = None,
        original_request_data: Optional[dict] = None,
        is_test_data: bool = False
    ) -> ApprovalRequest:
        """
        Employee操作リクエストを作成

        Args:
            db: データベースセッション
            requester_staff_id: リクエスト作成者のスタッフID
            office_id: 対象事務所ID
            resource_type: リソースタイプ（welfare_recipient, support_plan_cycle, etc.）
            action_type: アクションタイプ（create, update, delete）
            resource_id: リソースID（updateまたはdeleteの場合）
            original_request_data: 元のリクエストデータ（createまたはupdateの場合）
            is_test_data: テストデータフラグ

        Returns:
            作成された承認リクエスト
        """
        request_data = {
            "resource_type": resource_type,
            "action_type": action_type,
        }
        if resource_id:
            request_data["resource_id"] = str(resource_id)
        if original_request_data:
            request_data["original_request_data"] = original_request_data

        return await self.create_request(
            db,
            requester_staff_id=requester_staff_id,
            office_id=office_id,
            resource_type=ApprovalResourceType.employee_action,
            request_data=request_data,
            is_test_data=is_test_data
        )

    async def create_role_change_request(
        self,
        db: AsyncSession,
        *,
        requester_staff_id: uuid.UUID,
        office_id: uuid.UUID,
        from_role: str,
        requested_role: str,
        request_notes: Optional[str] = None,
        is_test_data: bool = False
    ) -> ApprovalRequest:
        """
        役割変更リクエストを作成

        Args:
            db: データベースセッション
            requester_staff_id: リクエスト作成者のスタッフID
            office_id: 対象事務所ID
            from_role: 現在のロール
            requested_role: 要求するロール
            request_notes: リクエストメモ
            is_test_data: テストデータフラグ

        Returns:
            作成された承認リクエスト
        """
        request_data = {
            "from_role": from_role,
            "requested_role": requested_role,
        }
        if request_notes:
            request_data["request_notes"] = request_notes

        return await self.create_request(
            db,
            requester_staff_id=requester_staff_id,
            office_id=office_id,
            resource_type=ApprovalResourceType.role_change,
            request_data=request_data,
            is_test_data=is_test_data
        )

    async def create_withdrawal_request(
        self,
        db: AsyncSession,
        *,
        requester_staff_id: uuid.UUID,
        office_id: uuid.UUID,
        withdrawal_type: str,  # "staff" or "office"
        reason: Optional[str] = None,
        target_staff_id: Optional[uuid.UUID] = None,
        affected_staff_ids: Optional[List[uuid.UUID]] = None,
        is_test_data: bool = False
    ) -> ApprovalRequest:
        """
        退会リクエストを作成

        Args:
            db: データベースセッション
            requester_staff_id: リクエスト作成者のスタッフID
            office_id: 対象事務所ID
            withdrawal_type: 退会タイプ（"staff" or "office"）
            reason: 退会理由
            target_staff_id: 対象スタッフID（スタッフ退会の場合）
            affected_staff_ids: 影響を受けるスタッフID一覧（事務所退会の場合）
            is_test_data: テストデータフラグ

        Returns:
            作成された退会リクエスト
        """
        request_data = {
            "withdrawal_type": withdrawal_type,
            "reason": reason,
        }
        if target_staff_id:
            request_data["target_staff_id"] = str(target_staff_id)
        if affected_staff_ids:
            request_data["affected_staff_ids"] = [str(sid) for sid in affected_staff_ids]

        return await self.create_request(
            db,
            requester_staff_id=requester_staff_id,
            office_id=office_id,
            resource_type=ApprovalResourceType.withdrawal,
            request_data=request_data,
            is_test_data=is_test_data
        )

    async def get_by_id_with_relations(
        self,
        db: AsyncSession,
        request_id: uuid.UUID
    ) -> Optional[ApprovalRequest]:
        """
        IDでリクエストを取得（関連データ含む）
        """
        result = await db.execute(
            select(self.model)
            .where(self.model.id == request_id)
            .options(
                selectinload(self.model.requester),
                selectinload(self.model.reviewer),
                selectinload(self.model.office)
            )
        )
        return result.scalar_one_or_none()

    async def get_pending_requests(
        self,
        db: AsyncSession,
        *,
        office_id: Optional[uuid.UUID] = None,
        resource_type: Optional[ApprovalResourceType] = None,
        include_test_data: bool = False
    ) -> List[ApprovalRequest]:
        """
        承認待ちリクエスト一覧を取得

        Args:
            db: データベースセッション
            office_id: 事務所IDでフィルタ（Noneの場合は全事務所）
            resource_type: リクエスト種別でフィルタ
            include_test_data: テストデータを含めるか

        Returns:
            承認待ちリクエストリスト
        """
        conditions = [self.model.status == RequestStatus.pending]

        if not include_test_data:
            conditions.append(self.model.is_test_data == False)  # noqa: E712

        if office_id:
            conditions.append(self.model.office_id == office_id)

        if resource_type:
            conditions.append(self.model.resource_type == resource_type)

        query = (
            select(self.model)
            .where(and_(*conditions))
            .order_by(self.model.created_at.desc())
            .options(
                selectinload(self.model.requester),
                selectinload(self.model.office)
            )
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_pending_withdrawal_requests(
        self,
        db: AsyncSession,
        *,
        include_test_data: bool = False
    ) -> List[ApprovalRequest]:
        """
        承認待ちの退会リクエスト一覧を取得（app_admin用）

        Args:
            db: データベースセッション
            include_test_data: テストデータを含めるか

        Returns:
            退会リクエストリスト
        """
        return await self.get_pending_requests(
            db,
            resource_type=ApprovalResourceType.withdrawal,
            include_test_data=include_test_data
        )

    async def get_by_requester(
        self,
        db: AsyncSession,
        requester_staff_id: uuid.UUID,
        *,
        resource_type: Optional[ApprovalResourceType] = None,
        include_test_data: bool = False
    ) -> List[ApprovalRequest]:
        """
        リクエスト作成者でリクエスト一覧を取得
        """
        conditions = [self.model.requester_staff_id == requester_staff_id]

        if not include_test_data:
            conditions.append(self.model.is_test_data == False)  # noqa: E712

        if resource_type:
            conditions.append(self.model.resource_type == resource_type)

        query = (
            select(self.model)
            .where(and_(*conditions))
            .order_by(self.model.created_at.desc())
            .options(
                selectinload(self.model.requester),
                selectinload(self.model.reviewer),
                selectinload(self.model.office)
            )
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_by_office(
        self,
        db: AsyncSession,
        office_id: uuid.UUID,
        *,
        resource_type: Optional[ApprovalResourceType] = None,
        status_filter: Optional[RequestStatus] = None,
        skip: int = 0,
        limit: int = 50,
        include_test_data: bool = False
    ) -> Tuple[List[ApprovalRequest], int]:
        """
        事務所でリクエスト一覧を取得（ページネーション付き）
        """
        conditions = [self.model.office_id == office_id]

        if not include_test_data:
            conditions.append(self.model.is_test_data == False)  # noqa: E712

        if resource_type:
            conditions.append(self.model.resource_type == resource_type)

        if status_filter:
            conditions.append(self.model.status == status_filter)

        where_clause = and_(*conditions)

        # カウント
        count_query = select(func.count()).select_from(self.model).where(where_clause)
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # データ取得
        query = (
            select(self.model)
            .where(where_clause)
            .order_by(self.model.created_at.desc())
            .offset(skip)
            .limit(limit)
            .options(
                selectinload(self.model.requester),
                selectinload(self.model.reviewer),
                selectinload(self.model.office)
            )
        )
        result = await db.execute(query)
        requests = list(result.scalars().all())

        return requests, total

    async def approve(
        self,
        db: AsyncSession,
        request_id: uuid.UUID,
        reviewer_staff_id: uuid.UUID,
        reviewer_notes: Optional[str] = None
    ) -> ApprovalRequest:
        """
        リクエストを承認

        Args:
            db: データベースセッション
            request_id: リクエストID
            reviewer_staff_id: 承認者のスタッフID
            reviewer_notes: 承認者のメモ

        Returns:
            更新された承認リクエスト

        Raises:
            HTTPException: リクエストが見つからない場合、既に処理済みの場合
        """
        request = await self.get(db, id=request_id)
        if not request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ja.SERVICE_REQUEST_NOT_FOUND.format(request_id=request_id)
            )

        if request.status != RequestStatus.pending:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=ja.REQUEST_ALREADY_PROCESSED.format(status=request.status.value)
            )

        now = datetime.datetime.now(datetime.timezone.utc)
        await db.execute(
            update(self.model)
            .where(self.model.id == request_id)
            .values(
                status=RequestStatus.approved,
                reviewed_by_staff_id=reviewer_staff_id,
                reviewed_at=now,
                reviewer_notes=reviewer_notes,
                updated_at=now
            )
        )
        await db.flush()

        return await self.get_by_id_with_relations(db, request_id)

    async def reject(
        self,
        db: AsyncSession,
        request_id: uuid.UUID,
        reviewer_staff_id: uuid.UUID,
        reviewer_notes: Optional[str] = None
    ) -> ApprovalRequest:
        """
        リクエストを却下

        Args:
            db: データベースセッション
            request_id: リクエストID
            reviewer_staff_id: 却下者のスタッフID
            reviewer_notes: 却下理由

        Returns:
            更新された承認リクエスト

        Raises:
            HTTPException: リクエストが見つからない場合、既に処理済みの場合
        """
        request = await self.get(db, id=request_id)
        if not request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ja.SERVICE_REQUEST_NOT_FOUND.format(request_id=request_id)
            )

        if request.status != RequestStatus.pending:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=ja.REQUEST_ALREADY_PROCESSED.format(status=request.status.value)
            )

        now = datetime.datetime.now(datetime.timezone.utc)
        await db.execute(
            update(self.model)
            .where(self.model.id == request_id)
            .values(
                status=RequestStatus.rejected,
                reviewed_by_staff_id=reviewer_staff_id,
                reviewed_at=now,
                reviewer_notes=reviewer_notes,
                updated_at=now
            )
        )
        await db.flush()

        return await self.get_by_id_with_relations(db, request_id)

    async def set_execution_result(
        self,
        db: AsyncSession,
        request_id: uuid.UUID,
        execution_result: dict
    ) -> ApprovalRequest:
        """
        実行結果を設定

        承認後の実行処理の結果を記録

        Args:
            db: データベースセッション
            request_id: リクエストID
            execution_result: 実行結果（成功/失敗、エラーメッセージなど）

        Returns:
            更新された承認リクエスト
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        await db.execute(
            update(self.model)
            .where(self.model.id == request_id)
            .values(
                execution_result=execution_result,
                updated_at=now
            )
        )
        await db.flush()

        return await self.get_by_id_with_relations(db, request_id)

    async def has_pending_withdrawal(
        self,
        db: AsyncSession,
        office_id: uuid.UUID,
        withdrawal_type: str,
        target_staff_id: Optional[uuid.UUID] = None
    ) -> bool:
        """
        同一対象の承認待ち退会リクエストが存在するか確認

        Args:
            db: データベースセッション
            office_id: 事務所ID
            withdrawal_type: 退会タイプ（"staff" or "office"）
            target_staff_id: 対象スタッフID（スタッフ退会の場合）

        Returns:
            存在する場合True
        """
        conditions = [
            self.model.office_id == office_id,
            self.model.resource_type == ApprovalResourceType.withdrawal,
            self.model.status == RequestStatus.pending,
        ]

        query = select(func.count()).select_from(self.model).where(and_(*conditions))
        result = await db.execute(query)
        count = result.scalar() or 0

        if count == 0:
            return False

        # withdrawal_typeとtarget_staff_idでさらにフィルタ
        # request_dataはJSONBなので、詳細なフィルタはアプリケーション側で行う
        requests_query = (
            select(self.model)
            .where(and_(*conditions))
        )
        requests_result = await db.execute(requests_query)
        requests = list(requests_result.scalars().all())

        for req in requests:
            if req.request_data and req.request_data.get("withdrawal_type") == withdrawal_type:
                if withdrawal_type == "office":
                    return True
                elif withdrawal_type == "staff":
                    req_target = req.request_data.get("target_staff_id")
                    if target_staff_id and req_target == str(target_staff_id):
                        return True

        return False


# インスタンス化
approval_request = CRUDApprovalRequest(ApprovalRequest)
