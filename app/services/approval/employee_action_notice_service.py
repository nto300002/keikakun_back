from typing import List
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.crud_notice import crud_notice
from app.models.approval_request import ApprovalRequest
from app.models.enums import (
    ActionType,
    NoticeType,
    ResourceType,
    StaffRole,
)
from app.models.office import OfficeStaff
from app.models.staff import Staff
from app.schemas.notice import NoticeCreate


class EmployeeActionNoticeService:
    """Notice operations for employee action approval requests."""

    async def create_request_notifications(
        self,
        db: AsyncSession,
        request: ApprovalRequest,
    ) -> None:
        office_id = request.office_id
        requester_full_name = request.requester.full_name
        requester_staff_id = request.requester_staff_id
        request_id = request.id
        link_url = self.build_link_url(request_id)
        detail_info = self.extract_detail_from_request_data(request)

        for approver_id in await self.get_approvers(db, office_id):
            await crud_notice.create(
                db,
                obj_in=NoticeCreate(
                    recipient_staff_id=approver_id,
                    office_id=office_id,
                    type=NoticeType.employee_action_pending.value,
                    title=f"{requester_full_name}さんが{detail_info}リクエストしました。",
                    content=f"{requester_full_name}さんが{detail_info}リクエストしました。",
                    link_url=link_url,
                ),
                auto_commit=False,
            )

        await crud_notice.create(
            db,
            obj_in=NoticeCreate(
                recipient_staff_id=requester_staff_id,
                office_id=office_id,
                type=NoticeType.employee_action_request_sent.value,
                title="作成、編集、削除リクエストを送信しました",
                content=f"あなたの{detail_info}リクエストを送信しました。承認をお待ちください。",
                link_url=link_url,
            ),
            auto_commit=False,
        )

        await crud_notice.delete_old_notices_over_limit(
            db,
            office_id=office_id,
            limit=50,
        )

    async def create_approved_notifications(
        self,
        db: AsyncSession,
        request: ApprovalRequest,
    ) -> None:
        await self._create_resolution_notifications(
            db=db,
            request=request,
            notice_type=NoticeType.employee_action_approved,
            title="作成、編集、削除リクエストが承認されました",
            requester_content_suffix="承認されました。",
            approver_content_suffix="承認しました。",
        )

    async def create_rejected_notifications(
        self,
        db: AsyncSession,
        request: ApprovalRequest,
    ) -> None:
        await self._create_resolution_notifications(
            db=db,
            request=request,
            notice_type=NoticeType.employee_action_rejected,
            title="作成、編集、削除リクエストが却下されました",
            requester_content_suffix="却下されました。",
            approver_content_suffix="却下しました。",
        )

    async def get_approvers(
        self,
        db: AsyncSession,
        office_id: UUID,
    ) -> List[UUID]:
        result = await db.execute(
            select(Staff.id)
            .join(OfficeStaff, OfficeStaff.staff_id == Staff.id)
            .where(
                OfficeStaff.office_id == office_id,
                Staff.role.in_([StaffRole.manager, StaffRole.owner]),
            )
        )

        return list(result.scalars().all())

    def extract_detail_from_request_data(
        self,
        request: ApprovalRequest,
    ) -> str:
        action_ja = {
            ActionType.create: "作成",
            ActionType.update: "更新",
            ActionType.delete: "削除",
        }
        resource_ja = {
            ResourceType.welfare_recipient: "利用者",
            ResourceType.support_plan_cycle: "サポート計画サイクル",
            ResourceType.support_plan_status: "サポート計画ステータス",
        }
        step_type_ja = {
            "assessment": "アセスメント情報",
            "draft_plan": "計画案",
            "staff_meeting": "職員会議記録",
            "final_plan_signed": "最終計画",
            "monitoring": "モニタリング報告",
        }

        action_type = self._get_action_type(request)
        resource_type = self._get_resource_type(request)
        action_name = action_ja.get(action_type, str(action_type))

        if resource_type == ResourceType.support_plan_status:
            request_data = self._get_detail_request_data(request)
            recipient_name = request_data.get("welfare_recipient_full_name", "")
            step_type = request_data.get("step_type", "")
            step_type_name = step_type_ja.get(step_type, "サポート計画ステータス")

            if recipient_name:
                return f"利用者{recipient_name}さんの{step_type_name}の{action_name}を"

            return f"{step_type_name}の{action_name}を"

        resource_name = resource_ja.get(resource_type, str(resource_type))
        target_name = ""
        request_data = self._get_detail_request_data(request)

        if resource_type == ResourceType.welfare_recipient:
            full_name = request_data.get("full_name")
            if full_name:
                target_name = f"{full_name}さん"
            else:
                first_name = request_data.get("first_name")
                last_name = request_data.get("last_name")
                if first_name and last_name:
                    target_name = f"{last_name} {first_name}さん"

        if target_name:
            return f"{resource_name}{target_name}の{action_name}を"

        return f"{resource_name}の{action_name}を"

    def build_link_url(self, request_id: UUID) -> str:
        return f"/approval-requests/{request_id}"

    async def _create_resolution_notifications(
        self,
        *,
        db: AsyncSession,
        request: ApprovalRequest,
        notice_type: NoticeType,
        title: str,
        requester_content_suffix: str,
        approver_content_suffix: str,
    ) -> None:
        detail_info = self.extract_detail_from_request_data(request)
        office_id = request.office_id
        requester_full_name = request.requester.full_name
        requester_staff_id = request.requester_staff_id
        link_url = self.build_link_url(request.id)

        await self._delete_existing_request_notices(db, link_url)

        await crud_notice.create(
            db,
            obj_in=NoticeCreate(
                recipient_staff_id=requester_staff_id,
                office_id=office_id,
                type=notice_type.value,
                title=title,
                content=f"あなたの{detail_info}リクエストが{requester_content_suffix}",
                link_url=link_url,
            ),
            auto_commit=False,
        )

        for approver_id in await self.get_approvers(db, office_id):
            await crud_notice.create(
                db,
                obj_in=NoticeCreate(
                    recipient_staff_id=approver_id,
                    office_id=office_id,
                    type=notice_type.value,
                    title=title,
                    content=(
                        f"{requester_full_name}さんの{detail_info}リクエストを"
                        f"{approver_content_suffix}"
                    ),
                    link_url=link_url,
                ),
                auto_commit=False,
            )

    async def _delete_existing_request_notices(
        self,
        db: AsyncSession,
        link_url: str,
    ) -> None:
        delete_stmt = select(crud_notice.model).where(
            crud_notice.model.link_url == link_url,
            crud_notice.model.type.in_(
                [
                    NoticeType.employee_action_pending.value,
                    NoticeType.employee_action_request_sent.value,
                ]
            ),
        ).with_for_update()

        delete_result = await db.execute(delete_stmt)
        notices_to_delete = delete_result.scalars().all()

        for notice in notices_to_delete:
            await db.delete(notice)

    def _get_resource_type(self, request: ApprovalRequest) -> ResourceType:
        return ResourceType(request.request_data.get("resource_type"))

    def _get_action_type(self, request: ApprovalRequest) -> ActionType:
        return ActionType(request.request_data.get("action_type"))

    def _get_detail_request_data(self, request: ApprovalRequest) -> dict:
        request_data = request.request_data or {}
        return request_data.get("original_request_data") or request_data
