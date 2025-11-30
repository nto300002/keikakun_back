"""
Role変更リクエストサービス層

ビジネスロジック:
- リクエストの作成・承認・却下処理
- スタッフのrole変更処理
- 権限チェックとバリデーション
"""

import logging
from typing import Optional, List
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status

from app.crud.crud_approval_request import approval_request
from app.crud.crud_staff import staff as crud_staff
from app.crud.crud_notice import crud_notice
from app.models.approval_request import ApprovalRequest
from app.models.enums import StaffRole, RequestStatus, NoticeType, ApprovalResourceType
from app.schemas.role_change_request import RoleChangeRequestCreate
from app.schemas.notice import NoticeCreate
from app.messages import ja

logger = logging.getLogger(__name__)


def _get_from_role(request: ApprovalRequest) -> StaffRole:
    """request_dataからfrom_roleを取得"""
    if request.request_data and "from_role" in request.request_data:
        role_str = request.request_data["from_role"]
        return StaffRole(role_str) if isinstance(role_str, str) else role_str
    raise ValueError(f"from_role not found in request_data for request {request.id}")


def _get_requested_role(request: ApprovalRequest) -> StaffRole:
    """request_dataからrequested_roleを取得"""
    if request.request_data and "requested_role" in request.request_data:
        role_str = request.request_data["requested_role"]
        return StaffRole(role_str) if isinstance(role_str, str) else role_str
    raise ValueError(f"requested_role not found in request_data for request {request.id}")


def _get_request_notes(request: ApprovalRequest) -> str | None:
    """request_dataからrequest_notesを取得"""
    if request.request_data and "request_notes" in request.request_data:
        return request.request_data["request_notes"]
    return None


class RoleChangeService:
    """Role変更リクエストのビジネスロジックを管理するサービス"""

    async def create_request(
        self,
        db: AsyncSession,
        *,
        requester_staff_id: UUID,
        office_id: UUID,
        obj_in: RoleChangeRequestCreate
    ) -> ApprovalRequest:
        """
        Role変更リクエストを作成

        Args:
            db: データベースセッション
            requester_staff_id: リクエスト作成者のスタッフID
            office_id: 事業所ID
            obj_in: リクエスト作成データ

        Returns:
            作成されたRole変更リクエスト

        Raises:
            ValueError: スタッフが見つからない場合
        """
        # リクエスト作成者の現在のroleを取得
        requester = await crud_staff.get(db, id=requester_staff_id)
        if not requester:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ja.SERVICE_STAFF_NOT_FOUND.format(staff_id=requester_staff_id)
            )

        from_role = requester.role

        # 同じroleへの変更はエラー
        if from_role == obj_in.requested_role:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ja.SERVICE_ROLE_ALREADY_ASSIGNED
            )

        logger.info(
            f"Creating role change request: staff={requester_staff_id}, "
            f"from_role={from_role}, requested_role={obj_in.requested_role}"
        )

        # リクエスト作成
        request = await approval_request.create_role_change_request(
            db=db,
            requester_staff_id=requester_staff_id,
            office_id=office_id,
            from_role=from_role,
            requested_role=obj_in.requested_role,
            request_notes=obj_in.request_notes if hasattr(obj_in, 'request_notes') else None
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
        await self._create_request_notification(db, request)

        # 最後に1回だけcommit
        await db.commit()

        # commit()後にリレーションシップも含めて再取得（MissingGreenlet対策）
        # refresh()ではリレーションシップは再ロードされないため、selectinloadで明示的に再取得
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
        Role変更リクエストを承認し、実際にroleを変更

        Args:
            db: データベースセッション
            request_id: リクエストID
            reviewer_staff_id: 承認者のスタッフID
            reviewer_notes: 承認コメント（オプション）

        Returns:
            承認されたRole変更リクエスト

        Raises:
            ValueError: リクエストが見つからない、または権限がない場合
        """
        # リクエストを取得
        request = await approval_request.get(db, id=request_id)
        if not request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ja.SERVICE_REQUEST_NOT_FOUND.format(request_id=request_id)
            )

        # 承認者の情報を取得
        reviewer = await crud_staff.get(db, id=reviewer_staff_id)
        if not reviewer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ja.SERVICE_REVIEWER_NOT_FOUND.format(reviewer_id=reviewer_staff_id)
            )

        # 権限チェック
        if not self.validate_approval_permission(reviewer.role, request):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ja.SERVICE_NO_APPROVAL_PERMISSION
            )

        logger.info(
            f"Approving role change request: request_id={request_id}, "
            f"reviewer={reviewer_staff_id}, target_role={_get_requested_role(request)}"
        )

        # 1. リクエストを承認
        approved_request = await approval_request.approve(
            db=db,
            request_id=request_id,
            reviewer_staff_id=reviewer_staff_id,
            reviewer_notes=reviewer_notes
        )

        # 2. スタッフのroleを変更
        requester = await crud_staff.get(db, id=request.requester_staff_id)
        if requester:
            requester.role = _get_requested_role(request)
            await db.flush()

            logger.info(
                f"Staff role changed: staff_id={requester.id}, "
                f"new_role={_get_requested_role(request)}"
            )

        # 3. commit()前にIDを保存（commit()後はオブジェクトがexpiredになるため）
        approved_request_id = request_id

        # 4. 通知作成用に一時的にリレーションシップを含めて取得
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

        # 既存の承認待ち通知のtypeを更新（承認済みに変更）※commitはしない
        link_url = f"/role-change-requests/{approved_request.id}"
        await crud_notice.update_type_by_link_url(
            db=db,
            link_url=link_url,
            new_type=NoticeType.role_change_approved.value
        )

        # 通知を作成（リクエスト作成者に送信）※commitはしない
        await self._create_approval_notification(db, approved_request)

        # 5. 最後に1回だけcommit
        await db.commit()

        # 6. commit()後にリレーションシップも含めて再取得（MissingGreenlet対策）
        # refresh()ではリレーションシップは再ロードされないため、selectinloadで明示的に再取得
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
        Role変更リクエストを却下

        Args:
            db: データベースセッション
            request_id: リクエストID
            reviewer_staff_id: 却下者のスタッフID
            reviewer_notes: 却下理由（オプション）

        Returns:
            却下されたRole変更リクエスト

        Raises:
            ValueError: リクエストが見つからない場合
        """
        logger.info(
            f"Rejecting role change request: request_id={request_id}, "
            f"reviewer={reviewer_staff_id}"
        )

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

        # 既存の承認待ち通知のtypeを更新（却下済みに変更）※commitはしない
        link_url = f"/role-change-requests/{rejected_request.id}"
        await crud_notice.update_type_by_link_url(
            db=db,
            link_url=link_url,
            new_type=NoticeType.role_change_rejected.value
        )

        # 通知を作成（リクエスト作成者に送信）※commitはしない
        await self._create_rejection_notification(db, rejected_request)

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

    @staticmethod
    def validate_approval_permission(
        reviewer_role: StaffRole,
        request: ApprovalRequest
    ) -> bool:
        """
        承認権限があるかをチェック

        承認権限のルール:
        - Owner: すべてのリクエストを承認可能
        - Manager: employee → manager/owner のリクエストのみ承認可能
        - Employee: 承認不可

        Args:
            reviewer_role: 承認者のrole
            request: 承認対象のリクエスト

        Returns:
            承認権限がある場合True
        """
        # Ownerはすべてのリクエストを承認可能
        if reviewer_role == StaffRole.owner:
            return True

        # Managerはemployeeからのリクエストのみ承認可能
        if reviewer_role == StaffRole.manager:
            return _get_from_role(request) == StaffRole.employee

        # Employeeは承認不可
        return False

    async def _create_request_notification(
        self,
        db: AsyncSession,
        request: ApprovalRequest
    ) -> None:
        """
        Role変更リクエスト作成時の通知を承認者と送信者に送信

        Args:
            db: データベースセッション
            request: Role変更リクエスト

        Note:
            このメソッドはcommitしない。親メソッドで最後に1回だけcommitする。
        """
        # _get_approvers呼び出し前に必要な値を変数に格納
        # (_get_approvers内のdb.execute()でrequestオブジェクトがexpireされるため)
        office_id = request.office_id
        from_role = _get_from_role(request)
        requested_role = _get_requested_role(request)
        requester_full_name = request.requester.full_name
        requester_staff_id = request.requester_staff_id
        request_id = request.id
        request_notes = _get_request_notes(request)

        # 1. 承認可能なスタッフ（manager/owner）に通知を作成
        approvers = await self._get_approvers(db, office_id, from_role)

        # 各承認者に通知を作成
        for approver_id in approvers:
            # 基本メッセージ
            base_content = f"{requester_full_name}さんが{from_role.value}から{requested_role.value}への変更をリクエストしました。"

            # request_notesがあれば追加
            if request_notes:
                content = f"{base_content}\n\n【リクエスト理由】\n{request_notes}"
            else:
                content = base_content

            notice_data = NoticeCreate(
                recipient_staff_id=approver_id,
                office_id=office_id,
                type=NoticeType.role_change_pending.value,
                title="役割、権限変更リクエストが作成されました",
                content=content,
                link_url=f"/role-change-requests/{request_id}"
            )
            await crud_notice.create(db, obj_in=notice_data)

        # 2. リクエスト作成者（送信者）にも通知を作成
        requester_notice_data = NoticeCreate(
            recipient_staff_id=requester_staff_id,
            office_id=office_id,
            type=NoticeType.role_change_request_sent.value,
            title="役割、権限変更リクエストを送信しました",
            content=f"あなたの{from_role.value}から{requested_role.value}への変更リクエストを送信しました。承認をお待ちください。",
            link_url=f"/role-change-requests/{request_id}"
        )
        await crud_notice.create(db, obj_in=requester_notice_data)

        # 3. 事務所の通知数が50件を超えた場合、古いものから削除
        await crud_notice.delete_old_notices_over_limit(db, office_id=office_id, limit=50)

        # commitしない（親メソッドで最後に1回だけcommitする）

    async def _create_approval_notification(
        self,
        db: AsyncSession,
        request: ApprovalRequest
    ) -> None:
        """
        Role変更リクエスト承認時の通知をリクエスト作成者に送信

        Args:
            db: データベースセッション
            request: Role変更リクエスト

        Note:
            このメソッドはcommitしない。親メソッドで最後に1回だけcommitする。
        """
        # リレーションシップの値を事前に変数に保存（MissingGreenlet対策）
        office_id = request.office_id
        requester_staff_id = request.requester_staff_id
        request_id = request.id
        from_role = _get_from_role(request)
        requested_role = _get_requested_role(request)

        notice_data = NoticeCreate(
            recipient_staff_id=requester_staff_id,
            office_id=office_id,
            type=NoticeType.role_change_approved.value,
            title="役割、権限変更リクエストが承認されました",
            content=f"あなたの{from_role.value}から{requested_role.value}への変更リクエストが承認されました。",
            link_url=f"/role-change-requests/{request_id}"
        )
        await crud_notice.create(db, obj_in=notice_data)

        # 事務所の通知数が50件を超えた場合、古いものから削除
        await crud_notice.delete_old_notices_over_limit(db, office_id=office_id, limit=50)

        # commitしない（親メソッドで最後に1回だけcommitする）

    async def _create_rejection_notification(
        self,
        db: AsyncSession,
        request: ApprovalRequest
    ) -> None:
        """
        Role変更リクエスト却下時の通知をリクエスト作成者に送信

        Args:
            db: データベースセッション
            request: Role変更リクエスト

        Note:
            このメソッドはcommitしない。親メソッドで最後に1回だけcommitする。
        """
        # リレーションシップの値を事前に変数に保存（MissingGreenlet対策）
        office_id = request.office_id
        requester_staff_id = request.requester_staff_id
        request_id = request.id
        from_role = _get_from_role(request)
        requested_role = _get_requested_role(request)

        notice_data = NoticeCreate(
            recipient_staff_id=requester_staff_id,
            office_id=office_id,
            type=NoticeType.role_change_rejected.value,
            title="役割、権限変更リクエストが却下されました",
            content=f"あなたの{from_role.value}から{requested_role.value}への変更リクエストが却下されました。",
            link_url=f"/role-change-requests/{request_id}"
        )
        await crud_notice.create(db, obj_in=notice_data)

        # 事務所の通知数が50件を超えた場合、古いものから削除
        await crud_notice.delete_old_notices_over_limit(db, office_id=office_id, limit=50)

        # commitしない（親メソッドで最後に1回だけcommitする）

    async def _get_approvers(
        self,
        db: AsyncSession,
        office_id: UUID,
        from_role: StaffRole
    ) -> List[UUID]:
        """
        リクエストを承認可能なスタッフIDのリストを取得

        Args:
            db: データベースセッション
            office_id: 事業所ID
            from_role: リクエスト作成者の現在のrole

        Returns:
            承認可能なスタッフIDのリスト
        """
        from app.models.staff import Staff
        from app.models.office import OfficeStaff

        # employeeからのリクエストの場合、manager/ownerが承認可能
        # managerからのリクエストの場合、ownerのみが承認可能
        if from_role == StaffRole.employee:
            # manager/ownerを取得
            result = await db.execute(
                select(Staff.id)
                .join(OfficeStaff, OfficeStaff.staff_id == Staff.id)
                .where(
                    OfficeStaff.office_id == office_id,
                    Staff.role.in_([StaffRole.manager, StaffRole.owner])
                )
            )
        else:
            # ownerのみを取得
            result = await db.execute(
                select(Staff.id)
                .join(OfficeStaff, OfficeStaff.staff_id == Staff.id)
                .where(
                    OfficeStaff.office_id == office_id,
                    Staff.role == StaffRole.owner
                )
            )

        return list(result.scalars().all())


# サービスインスタンスをエクスポート
role_change_service = RoleChangeService()
