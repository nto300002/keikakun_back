"""
Employee制限リクエストサービス層

ビジネスロジック:
- Employeeの作成、リクエストの作成・承認・却下処理
- 承認時の実際のCRUD操作実行
- 実行結果の記録とエラーハンドリング
"""

import logging
from typing import Optional, Dict, Any, List
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status

from app.crud.crud_approval_request import approval_request
from app.models.approval_request import ApprovalRequest
from app.models.enums import ActionType
from app.schemas.employee_action_request import EmployeeActionRequestCreate
from app.services.approval.employee_action_executor import EmployeeActionExecutor
from app.services.approval.employee_action_notice_service import EmployeeActionNoticeService
from app.messages import ja

logger = logging.getLogger(__name__)


def _get_action_type(request: ApprovalRequest) -> ActionType:
    """ApprovalRequestからaction_typeを取得"""
    return ActionType(request.request_data.get("action_type"))


class EmployeeActionService:
    """Employee制限リクエストのビジネスロジックを管理するサービス"""

    def __init__(
        self,
        notice_service: Optional[EmployeeActionNoticeService] = None,
        executor: Optional[EmployeeActionExecutor] = None,
    ):
        self.notice_service = notice_service or EmployeeActionNoticeService()
        self.executor = executor or EmployeeActionExecutor()

    async def create_request(
        self,
        db: AsyncSession,
        *,
        requester_staff_id: UUID,
        office_id: UUID,
        obj_in: EmployeeActionRequestCreate
    ) -> ApprovalRequest:
        """
        Employee制限リクエストを作成（統合型ApprovalRequest）

        Args:
            db: データベースセッション
            requester_staff_id: リクエスト作成者のスタッフID
            office_id: 事業所ID
            obj_in: リクエスト作成スキーマ

        Returns:
            作成されたApprovalRequest
        """
        logger.info(
            "Creating employee action request: resource_type=%s action_type=%s",
            obj_in.resource_type,
            obj_in.action_type,
        )

        # ApprovalRequestを作成（employee_action種別）
        request = await approval_request.create_employee_action_request(
            db=db,
            requester_staff_id=requester_staff_id,
            office_id=office_id,
            resource_type=obj_in.resource_type.value,
            action_type=obj_in.action_type.value,
            resource_id=obj_in.resource_id,
            original_request_data=obj_in.request_data
        )

        # commit()前にIDを保存（commit()後はオブジェクトがexpiredになるため）
        request_id = request.id

        # 通知作成用に一時的にリレーションシップを含めて取得
        result = await db.execute(
            select(ApprovalRequest)
            .where(ApprovalRequest.id == request_id)
            .options(
                selectinload(ApprovalRequest.requester),
                selectinload(ApprovalRequest.office)
            )
        )
        request = result.scalar_one()

        # 通知を作成（承認者に送信）※commitはしない
        await self.notice_service.create_request_notifications(db, request)

        # 最後に1回だけcommit
        await db.commit()

        # commit()後にリレーションシップも含めて再取得（MissingGreenlet対策）
        result = await db.execute(
            select(ApprovalRequest)
            .where(ApprovalRequest.id == request_id)
            .options(
                selectinload(ApprovalRequest.requester),
                selectinload(ApprovalRequest.office)
            )
        )
        request = result.scalar_one()

        return request

    async def approve_request(
        self,
        db: AsyncSession,
        *,
        request_id: UUID,
        reviewer_staff_id: UUID,
        reviewer_notes: Optional[str] = None
    ) -> ApprovalRequest:
        """
        Employee制限リクエストを承認し、実際の作成、編集を実行

        Args:
            db: データベースセッション
            request_id: リクエストID
            reviewer_staff_id: 承認者のスタッフID
            reviewer_notes: 承認コメント（オプション）

        Returns:
            承認されたEmployee制限リクエスト
        """
        # リクエストを取得
        request = await approval_request.get(db, id=request_id)
        if not request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ja.SERVICE_EMPLOYEE_ACTION_REQUEST_NOT_FOUND.format(request_id=request_id)
            )

        logger.info(
            "Approving employee action request: action=%s",
            _get_action_type(request),
        )

        # 承認処理と作成、編集、実行
        execution_result = None
        try:
            # 実際の作成、編集、削除を実行
            execution_result = await self._execute_action(db, request)

            # 承認処理
            approved_request = await approval_request.approve(
                db=db,
                request_id=request_id,
                reviewer_staff_id=reviewer_staff_id,
                reviewer_notes=reviewer_notes
            )

            # 実行結果を設定
            approved_request = await approval_request.set_execution_result(
                db=db,
                request_id=request_id,
                execution_result=execution_result
            )

            logger.info("Employee action executed successfully")

        except Exception as e:
            logger.error(
                "Failed to execute employee action: error_type=%s",
                type(e).__name__,
            )

            # トランザクションがロールバック状態になっているため、明示的にrollbackを実行
            await db.rollback()

            # エラー情報を記録
            execution_result = {
                "success": False,
                "error": "Employee action execution failed",
                "error_type": type(e).__name__
            }

            # エラーがあっても承認処理は実行（エラー情報を記録）
            approved_request = await approval_request.approve(
                db=db,
                request_id=request_id,
                reviewer_staff_id=reviewer_staff_id,
                reviewer_notes=reviewer_notes
            )

            # 実行結果を設定（エラー情報）
            approved_request = await approval_request.set_execution_result(
                db=db,
                request_id=request_id,
                execution_result=execution_result
            )

        # commit()前にIDを保存（commit()後はオブジェクトがexpiredになるため）
        approved_request_id = request_id

        # 通知作成用に一時的にリレーションシップを含めて取得
        result = await db.execute(
            select(ApprovalRequest)
            .where(ApprovalRequest.id == approved_request_id)
            .options(
                selectinload(ApprovalRequest.requester),
                selectinload(ApprovalRequest.reviewer),
                selectinload(ApprovalRequest.office)
            )
        )
        approved_request = result.scalar_one()

        await self.notice_service.create_approved_notifications(db, approved_request)

        # 最後に1回だけcommit
        await db.commit()

        # commit()後にリレーションシップも含めて再取得（MissingGreenlet対策）
        result = await db.execute(
            select(ApprovalRequest)
            .where(ApprovalRequest.id == approved_request_id)
            .options(
                selectinload(ApprovalRequest.requester),
                selectinload(ApprovalRequest.reviewer),
                selectinload(ApprovalRequest.office)
            )
        )
        approved_request = result.scalar_one()

        return approved_request

    async def reject_request(
        self,
        db: AsyncSession,
        *,
        request_id: UUID,
        reviewer_staff_id: UUID,
        reviewer_notes: Optional[str] = None
    ) -> ApprovalRequest:
        """
        Employee制限リクエストを却下

        Args:
            db: データベースセッション
            request_id: リクエストID
            reviewer_staff_id: 却下者のスタッフID
            reviewer_notes: 却下理由（オプション）

        Returns:
            却下されたEmployee制限リクエスト
        """
        logger.info("Rejecting employee action request")

        # リクエストを却下
        rejected_request = await approval_request.reject(
            db=db,
            request_id=request_id,
            reviewer_staff_id=reviewer_staff_id,
            reviewer_notes=reviewer_notes
        )

        # commit()前にIDを保存（commit()後はオブジェクトがexpiredになるため）
        rejected_request_id = request_id

        # 通知作成用に一時的にリレーションシップを含めて取得
        result = await db.execute(
            select(ApprovalRequest)
            .where(ApprovalRequest.id == rejected_request_id)
            .options(
                selectinload(ApprovalRequest.requester),
                selectinload(ApprovalRequest.reviewer),
                selectinload(ApprovalRequest.office)
            )
        )
        rejected_request = result.scalar_one()

        await self.notice_service.create_rejected_notifications(db, rejected_request)

        # 最後に1回だけcommit
        await db.commit()

        # commit()後にリレーションシップも含めて再取得（MissingGreenlet対策）
        result = await db.execute(
            select(ApprovalRequest)
            .where(ApprovalRequest.id == rejected_request_id)
            .options(
                selectinload(ApprovalRequest.requester),
                selectinload(ApprovalRequest.reviewer),
                selectinload(ApprovalRequest.office)
            )
        )
        rejected_request = result.scalar_one()

        return rejected_request

    async def _execute_action(
        self,
        db: AsyncSession,
        request: ApprovalRequest
    ) -> Dict[str, Any]:
        """リクエストに基づく実行処理を専用Executorへ委譲する。"""
        return await self.executor.execute_action(db, request)

    async def _create_request_notification(
        self,
        db: AsyncSession,
        request: ApprovalRequest
    ) -> None:
        await self.notice_service.create_request_notifications(db, request)

    async def _create_approval_notification(
        self,
        db: AsyncSession,
        request: ApprovalRequest
    ) -> None:
        await self.notice_service.create_approved_notifications(db, request)

    async def _create_rejection_notification(
        self,
        db: AsyncSession,
        request: ApprovalRequest
    ) -> None:
        await self.notice_service.create_rejected_notifications(db, request)

    async def _get_approvers(
        self,
        db: AsyncSession,
        office_id: UUID
    ) -> List[UUID]:
        return await self.notice_service.get_approvers(db, office_id)

    def _extract_detail_from_request_data(
        self,
        request: ApprovalRequest
    ) -> str:
        return self.notice_service.extract_detail_from_request_data(request)


# サービスインスタンスをエクスポート
employee_action_service = EmployeeActionService()
