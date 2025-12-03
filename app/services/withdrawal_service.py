"""
退会サービス層

ビジネスロジック:
- 退会リクエストの作成・承認・却下処理
- スタッフ/事務所の退会処理
- 監査ログの記録
"""

import logging
from typing import Optional, List, Dict, Any
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status

from app.crud.crud_approval_request import approval_request as crud_approval_request
from app.crud.crud_archived_staff import crud_archived_staff
from app.crud.crud_audit_log import audit_log as crud_audit_log
from app.crud.crud_office import crud_office
from app.crud.crud_staff import staff as crud_staff
from app.models.approval_request import ApprovalRequest
from app.models.office import Office, OfficeStaff
from app.models.staff import Staff
from app.models.enums import StaffRole, RequestStatus, ApprovalResourceType
from app.messages import ja

logger = logging.getLogger(__name__)


class WithdrawalService:
    """退会処理のビジネスロジックを管理するサービス"""

    # =====================================================
    # 退会リクエスト作成
    # =====================================================

    async def create_staff_withdrawal_request(
        self,
        db: AsyncSession,
        *,
        requester_staff_id: UUID,
        office_id: UUID,
        target_staff_id: UUID,
        reason: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> ApprovalRequest:
        """
        スタッフ退会リクエストを作成

        Args:
            db: データベースセッション
            requester_staff_id: リクエスト作成者のスタッフID
            office_id: 事務所ID
            target_staff_id: 退会対象のスタッフID
            reason: 退会理由
            ip_address: 操作元IPアドレス
            user_agent: 操作元User-Agent

        Returns:
            作成された退会リクエスト

        Raises:
            HTTPException: 既存の承認待ちリクエストがある場合
        """
        # 既存の承認待ちリクエストがないか確認
        has_pending = await crud_approval_request.has_pending_withdrawal(
            db,
            office_id=office_id,
            withdrawal_type="staff",
            target_staff_id=target_staff_id
        )
        if has_pending:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="このスタッフに対する退会リクエストは既に承認待ちです"
            )

        # リクエスト作成
        request = await crud_approval_request.create_withdrawal_request(
            db,
            requester_staff_id=requester_staff_id,
            office_id=office_id,
            withdrawal_type="staff",
            reason=reason,
            target_staff_id=target_staff_id
        )

        # 監査ログ記録
        await crud_audit_log.create_log(
            db,
            actor_id=requester_staff_id,
            action="withdrawal.requested",
            target_type="withdrawal_request",
            target_id=request.id,
            office_id=office_id,
            ip_address=ip_address,
            user_agent=user_agent,
            details={
                "withdrawal_type": "staff",
                "target_staff_id": str(target_staff_id),
                "reason": reason
            }
        )

        logger.info(
            f"Staff withdrawal request created: request_id={request.id}, "
            f"target_staff={target_staff_id}, requester={requester_staff_id}"
        )

        return request

    async def create_office_withdrawal_request(
        self,
        db: AsyncSession,
        *,
        requester_staff_id: UUID,
        office_id: UUID,
        reason: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> ApprovalRequest:
        """
        事務所退会リクエストを作成

        Args:
            db: データベースセッション
            requester_staff_id: リクエスト作成者のスタッフID
            office_id: 退会対象の事務所ID
            reason: 退会理由
            ip_address: 操作元IPアドレス
            user_agent: 操作元User-Agent

        Returns:
            作成された退会リクエスト

        Raises:
            HTTPException: 既存の承認待ちリクエストがある場合、権限がない場合
        """
        # リクエスト作成者がownerか確認
        requester = await crud_staff.get(db, id=requester_staff_id)
        if not requester or requester.role != StaffRole.owner:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="事務所の退会リクエストはオーナーのみが作成できます"
            )

        # 既存の承認待ちリクエストがないか確認
        has_pending = await crud_approval_request.has_pending_withdrawal(
            db,
            office_id=office_id,
            withdrawal_type="office"
        )
        if has_pending:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="この事務所に対する退会リクエストは既に承認待ちです"
            )

        # 影響を受けるスタッフIDを取得
        affected_staff_ids = await crud_office.get_staff_ids_by_office(db, office_id)

        # リクエスト作成
        request = await crud_approval_request.create_withdrawal_request(
            db,
            requester_staff_id=requester_staff_id,
            office_id=office_id,
            withdrawal_type="office",
            reason=reason,
            affected_staff_ids=affected_staff_ids
        )

        # 監査ログ記録
        await crud_audit_log.create_log(
            db,
            actor_id=requester_staff_id,
            action="withdrawal.requested",
            target_type="withdrawal_request",
            target_id=request.id,
            office_id=office_id,
            ip_address=ip_address,
            user_agent=user_agent,
            details={
                "withdrawal_type": "office",
                "affected_staff_count": len(affected_staff_ids),
                "reason": reason
            }
        )

        logger.info(
            f"Office withdrawal request created: request_id={request.id}, "
            f"office={office_id}, affected_staff_count={len(affected_staff_ids)}"
        )

        return request

    # =====================================================
    # 退会リクエスト承認・却下
    # =====================================================

    async def approve_withdrawal(
        self,
        db: AsyncSession,
        *,
        request_id: UUID,
        reviewer_staff_id: UUID,
        reviewer_notes: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> ApprovalRequest:
        """
        退会リクエストを承認し、実際に退会処理を実行

        Args:
            db: データベースセッション
            request_id: リクエストID
            reviewer_staff_id: 承認者のスタッフID（app_admin）
            reviewer_notes: 承認コメント
            ip_address: 操作元IPアドレス
            user_agent: 操作元User-Agent

        Returns:
            承認された退会リクエスト

        Raises:
            HTTPException: リクエストが見つからない、権限がない場合
        """
        # 承認者がapp_adminか確認
        reviewer = await crud_staff.get(db, id=reviewer_staff_id)
        if not reviewer or reviewer.role != StaffRole.app_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="退会リクエストの承認はアプリ管理者のみが行えます"
            )

        # リクエスト取得
        request = await crud_approval_request.get_by_id_with_relations(db, request_id)
        if not request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ja.SERVICE_REQUEST_NOT_FOUND.format(request_id=request_id)
            )

        if request.resource_type != ApprovalResourceType.withdrawal:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="このリクエストは退会リクエストではありません"
            )

        # 承認処理
        approved_request = await crud_approval_request.approve(
            db,
            request_id=request_id,
            reviewer_staff_id=reviewer_staff_id,
            reviewer_notes=reviewer_notes
        )

        # 退会処理を実行
        withdrawal_type = request.request_data.get("withdrawal_type")
        execution_result = await self._execute_withdrawal(
            db,
            request=request,
            executor_id=reviewer_staff_id,
            ip_address=ip_address,
            user_agent=user_agent
        )

        # 実行結果を記録
        await crud_approval_request.set_execution_result(
            db,
            request_id=request_id,
            execution_result=execution_result
        )

        # 監査ログ記録
        await crud_audit_log.create_log(
            db,
            actor_id=reviewer_staff_id,
            action="withdrawal.approved",
            target_type="withdrawal_request",
            target_id=request_id,
            office_id=request.office_id,
            ip_address=ip_address,
            user_agent=user_agent,
            details={
                "withdrawal_type": withdrawal_type,
                "execution_result": execution_result
            }
        )

        logger.info(
            f"Withdrawal approved and executed: request_id={request_id}, "
            f"type={withdrawal_type}, reviewer={reviewer_staff_id}"
        )

        return approved_request

    async def reject_withdrawal(
        self,
        db: AsyncSession,
        *,
        request_id: UUID,
        reviewer_staff_id: UUID,
        reviewer_notes: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> ApprovalRequest:
        """
        退会リクエストを却下

        Args:
            db: データベースセッション
            request_id: リクエストID
            reviewer_staff_id: 却下者のスタッフID（app_admin）
            reviewer_notes: 却下理由
            ip_address: 操作元IPアドレス
            user_agent: 操作元User-Agent

        Returns:
            却下された退会リクエスト

        Raises:
            HTTPException: リクエストが見つからない、権限がない場合
        """
        # 却下者がapp_adminか確認
        reviewer = await crud_staff.get(db, id=reviewer_staff_id)
        if not reviewer or reviewer.role != StaffRole.app_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="退会リクエストの却下はアプリ管理者のみが行えます"
            )

        # リクエスト取得
        request = await crud_approval_request.get_by_id_with_relations(db, request_id)
        if not request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ja.SERVICE_REQUEST_NOT_FOUND.format(request_id=request_id)
            )

        if request.resource_type != ApprovalResourceType.withdrawal:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="このリクエストは退会リクエストではありません"
            )

        # 却下処理
        rejected_request = await crud_approval_request.reject(
            db,
            request_id=request_id,
            reviewer_staff_id=reviewer_staff_id,
            reviewer_notes=reviewer_notes
        )

        # 監査ログ記録
        withdrawal_type = request.request_data.get("withdrawal_type") if request.request_data else None
        await crud_audit_log.create_log(
            db,
            actor_id=reviewer_staff_id,
            action="withdrawal.rejected",
            target_type="withdrawal_request",
            target_id=request_id,
            office_id=request.office_id,
            ip_address=ip_address,
            user_agent=user_agent,
            details={
                "withdrawal_type": withdrawal_type,
                "reason": reviewer_notes
            }
        )

        logger.info(
            f"Withdrawal rejected: request_id={request_id}, "
            f"type={withdrawal_type}, reviewer={reviewer_staff_id}"
        )

        return rejected_request

    # =====================================================
    # 退会処理の実行
    # =====================================================

    async def _execute_withdrawal(
        self,
        db: AsyncSession,
        *,
        request: ApprovalRequest,
        executor_id: UUID,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        退会処理を実行

        Args:
            db: データベースセッション
            request: 承認済みの退会リクエスト
            executor_id: 実行者のスタッフID
            ip_address: 操作元IPアドレス
            user_agent: 操作元User-Agent

        Returns:
            実行結果（成功/失敗、詳細情報）
        """
        withdrawal_type = request.request_data.get("withdrawal_type")

        try:
            if withdrawal_type == "staff":
                return await self._execute_staff_withdrawal(
                    db,
                    request=request,
                    executor_id=executor_id,
                    ip_address=ip_address,
                    user_agent=user_agent
                )
            elif withdrawal_type == "office":
                return await self._execute_office_withdrawal(
                    db,
                    request=request,
                    executor_id=executor_id,
                    ip_address=ip_address,
                    user_agent=user_agent
                )
            else:
                return {
                    "success": False,
                    "error": f"Unknown withdrawal type: {withdrawal_type}"
                }
        except Exception as e:
            logger.error(f"Withdrawal execution failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def _execute_staff_withdrawal(
        self,
        db: AsyncSession,
        *,
        request: ApprovalRequest,
        executor_id: UUID,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        スタッフ退会処理を実行

        スタッフを論理削除（30日後に物理削除される予定）

        Args:
            db: データベースセッション
            request: 承認済みの退会リクエスト
            executor_id: 実行者のスタッフID
            ip_address: 操作元IPアドレス
            user_agent: 操作元User-Agent

        Returns:
            実行結果
        """
        target_staff_id = UUID(request.request_data.get("target_staff_id"))

        # 対象スタッフを取得（リレーションシップをロード）
        target_staff = await crud_staff.get(db, id=target_staff_id)
        if not target_staff:
            return {
                "success": False,
                "error": "Target staff not found"
            }

        # 削除前にスタッフ情報を保存（監査ログ用）
        staff_info = {
            "id": str(target_staff.id),
            "email": target_staff.email,
            "full_name": target_staff.full_name,
            "role": target_staff.role.value
        }

        # 1. アーカイブ作成（法定保存義務対応）
        archive = await crud_archived_staff.create_from_staff(
            db,
            staff=target_staff,
            reason="staff_withdrawal",
            deleted_by=executor_id
        )
        await db.flush()

        logger.info(
            f"Archive created for staff withdrawal: staff_id={target_staff_id}, "
            f"archive_id={archive.id}, retention_until={archive.legal_retention_until}"
        )

        # 2. 監査ログ記録（削除前に記録）
        await crud_audit_log.create_log(
            db,
            actor_id=executor_id,
            action="staff.soft_deleted",
            target_type="staff",
            target_id=target_staff_id,
            office_id=request.office_id,
            ip_address=ip_address,
            user_agent=user_agent,
            details={
                "deleted_staff": staff_info,
                "archive_id": str(archive.id),
                "withdrawal_request_id": str(request.id),
                "deletion_type": "soft_delete",
                "note": "30日後に物理削除される予定、法定保存データは5年間保持"
            }
        )

        # 3. スタッフを論理削除
        await crud_staff.soft_delete(
            db,
            staff_id=target_staff_id,
            deleted_by=executor_id
        )
        await db.flush()

        logger.info(
            f"Staff withdrawn (soft deleted): staff_id={target_staff_id}, "
            f"email={staff_info['email']}, will be hard deleted after 30 days"
        )

        return {
            "success": True,
            "withdrawal_type": "staff",
            "deleted_staff": staff_info,
            "deletion_type": "soft_delete",
            "archive_id": str(archive.id),
            "archive_retention_until": archive.legal_retention_until.isoformat()
        }

    async def _execute_office_withdrawal(
        self,
        db: AsyncSession,
        *,
        request: ApprovalRequest,
        executor_id: UUID,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        事務所退会処理を実行

        事務所を論理削除し、所属スタッフを全員削除

        Args:
            db: データベースセッション
            request: 承認済みの退会リクエスト
            executor_id: 実行者のスタッフID
            ip_address: 操作元IPアドレス
            user_agent: 操作元User-Agent

        Returns:
            実行結果
        """
        office_id = request.office_id

        # 事務所を取得
        office = await crud_office.get(db, id=office_id)
        if not office:
            return {
                "success": False,
                "error": "Office not found"
            }

        # 削除前に事務所情報を保存（監査ログ用）
        office_info = {
            "id": str(office.id),
            "name": office.name,
            "type": office.type.value if office.type else None
        }

        # 所属スタッフIDを取得
        staff_ids = await crud_office.get_staff_ids_by_office(db, office_id)

        # 所属スタッフの情報を取得（監査ログ用）
        deleted_staff_info = []
        for staff_id in staff_ids:
            staff = await crud_staff.get(db, id=staff_id)
            if staff:
                deleted_staff_info.append({
                    "id": str(staff.id),
                    "email": staff.email,
                    "full_name": staff.full_name,
                    "role": staff.role.value
                })

        # 監査ログ記録（削除前に記録）
        await crud_audit_log.create_log(
            db,
            actor_id=executor_id,
            action="office.deleted",
            target_type="office",
            target_id=office_id,
            office_id=office_id,
            ip_address=ip_address,
            user_agent=user_agent,
            details={
                "deleted_office": office_info,
                "deleted_staff_count": len(staff_ids),
                "deleted_staff": deleted_staff_info,
                "withdrawal_request_id": str(request.id)
            }
        )

        # 所属スタッフを全員論理削除（30日後に物理削除される予定）
        archived_staff_ids = []
        for staff_id in staff_ids:
            # スタッフを取得（リレーションシップをロード）
            staff = await crud_staff.get(db, id=staff_id)
            if not staff:
                logger.warning(f"Staff not found during office withdrawal: staff_id={staff_id}")
                continue

            # 1. アーカイブ作成（法定保存義務対応）
            archive = await crud_archived_staff.create_from_staff(
                db,
                staff=staff,
                reason="office_withdrawal",
                deleted_by=executor_id
            )
            await db.flush()
            archived_staff_ids.append(str(archive.id))

            logger.info(
                f"Archive created for office withdrawal: staff_id={staff_id}, "
                f"archive_id={archive.id}, retention_until={archive.legal_retention_until}"
            )

            # 2. 各スタッフの削除ログを記録
            await crud_audit_log.create_log(
                db,
                actor_id=executor_id,
                action="staff.soft_deleted",
                target_type="staff",
                target_id=staff_id,
                office_id=office_id,
                ip_address=ip_address,
                user_agent=user_agent,
                details={
                    "reason": "office_withdrawal",
                    "office_id": str(office_id),
                    "archive_id": str(archive.id),
                    "withdrawal_request_id": str(request.id),
                    "deletion_type": "soft_delete",
                    "note": "30日後に物理削除される予定、法定保存データは5年間保持"
                }
            )

            # 3. スタッフを論理削除
            await crud_staff.soft_delete(
                db,
                staff_id=staff_id,
                deleted_by=executor_id
            )

        # 事務所を論理削除
        await crud_office.soft_delete(
            db,
            office_id=office_id,
            deleted_by=executor_id
        )

        await db.flush()

        logger.info(
            f"Office withdrawn (soft deleted): office_id={office_id}, "
            f"name={office_info['name']}, soft_deleted_staff_count={len(staff_ids)}, "
            f"staff will be hard deleted after 30 days"
        )

        return {
            "success": True,
            "withdrawal_type": "office",
            "deleted_office": office_info,
            "deleted_staff_count": len(staff_ids),
            "staff_deletion_type": "soft_delete",
            "archived_staff_ids": archived_staff_ids,
            "archived_staff_count": len(archived_staff_ids)
        }

    # =====================================================
    # 取得系メソッド
    # =====================================================

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
        return await crud_approval_request.get_pending_withdrawal_requests(
            db,
            include_test_data=include_test_data
        )

    async def get_withdrawal_request(
        self,
        db: AsyncSession,
        request_id: UUID
    ) -> Optional[ApprovalRequest]:
        """
        退会リクエストを取得

        Args:
            db: データベースセッション
            request_id: リクエストID

        Returns:
            退会リクエスト（見つからない場合はNone）
        """
        return await crud_approval_request.get_by_id_with_relations(db, request_id)


# サービスインスタンスをエクスポート
withdrawal_service = WithdrawalService()
