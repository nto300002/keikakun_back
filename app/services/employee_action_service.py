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
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.crud.crud_employee_action_request import crud_employee_action_request
from app.crud.crud_welfare_recipient import crud_welfare_recipient
from app.crud.crud_notice import crud_notice
from app.models.employee_action_request import EmployeeActionRequest
from app.models.welfare_recipient import (
    WelfareRecipient,
    OfficeWelfareRecipient,
    ServiceRecipientDetail,
    EmergencyContact,
    DisabilityStatus,
    DisabilityDetail
)
from app.models.enums import RequestStatus, ActionType, ResourceType, GenderType, NoticeType, StaffRole
from app.schemas.employee_action_request import EmployeeActionRequestCreate
from app.schemas.notice import NoticeCreate

logger = logging.getLogger(__name__)


class EmployeeActionService:
    """Employee制限リクエストのビジネスロジックを管理するサービス"""

    async def create_request(
        self,
        db: AsyncSession,
        *,
        requester_staff_id: UUID,
        office_id: UUID,
        obj_in: EmployeeActionRequestCreate
    ) -> EmployeeActionRequest:
        """
        Employee制限リクエストを作成

        Args:
            db: データベースセッション
            requester_staff_id: リクエスト作成者のスタッフID
            office_id: 事業所ID
            obj_in: リクエスト作成データ

        Returns:
            作成されたEmployee制限リクエスト
        """
        logger.info(
            f"Creating employee action request: staff={requester_staff_id}, "
            f"resource_type={obj_in.resource_type}, action_type={obj_in.action_type}"
        )

        # リクエスト作成
        request = await crud_employee_action_request.create(
            db=db,
            obj_in=obj_in,
            requester_staff_id=requester_staff_id,
            office_id=office_id
        )

        # commit()前にIDを保存（commit()後はオブジェクトがexpiredになるため）
        request_id = request.id

        # 通知作成用に一時的にリレーションシップを含めて取得
        result = await db.execute(
            select(EmployeeActionRequest)
            .where(EmployeeActionRequest.id == request_id)
            .options(
                selectinload(EmployeeActionRequest.requester),
                selectinload(EmployeeActionRequest.office)
            )
        )
        request = result.scalar_one()

        # 通知を作成（承認者に送信）※commitはしない
        await self._create_request_notification(db, request)

        # 最後に1回だけcommit
        await db.commit()

        # commit()後にリレーションシップも含めて再取得（MissingGreenlet対策）
        result = await db.execute(
            select(EmployeeActionRequest)
            .where(EmployeeActionRequest.id == request_id)
            .options(
                selectinload(EmployeeActionRequest.requester),
                selectinload(EmployeeActionRequest.office)
            )
        )
        request = result.scalar_one()

        return request

    async def approve_request(
        self,
        db: AsyncSession,
        *,
        request_id: UUID,
        approver_staff_id: UUID,
        approver_notes: Optional[str] = None
    ) -> EmployeeActionRequest:
        """
        Employee制限リクエストを承認し、実際の作成、編集を実行

        Args:
            db: データベースセッション
            request_id: リクエストID
            approver_staff_id: 承認者のスタッフID
            approver_notes: 承認コメント（オプション）

        Returns:
            承認されたEmployee制限リクエスト
        """
        # リクエストを取得
        request = await crud_employee_action_request.get(db, id=request_id)
        if not request:
            raise ValueError(f"Request {request_id} not found")

        logger.info(
            f"Approving employee action request: request_id={request_id}, "
            f"approver={approver_staff_id}, action={request.action_type}"
        )

        # 承認処理と作成、編集、実行
        execution_result = None
        try:
            # 実際の作成、編集、削除を実行
            execution_result = await self._execute_action(db, request)

            # 承認処理
            approved_request = await crud_employee_action_request.approve(
                db=db,
                request_id=request_id,
                approver_staff_id=approver_staff_id,
                approver_notes=approver_notes,
                execution_result=execution_result
            )

            logger.info(
                f"Employee action executed successfully: "
                f"request_id={request_id}, result={execution_result}"
            )

        except Exception as e:
            logger.error(
                f"Failed to execute employee action: "
                f"request_id={request_id}, error={str(e)}"
            )

            # エラー情報を記録
            execution_result = {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__
            }

            # エラーがあっても承認処理は実行（エラー情報を記録）
            approved_request = await crud_employee_action_request.approve(
                db=db,
                request_id=request_id,
                approver_staff_id=approver_staff_id,
                approver_notes=approver_notes,
                execution_result=execution_result
            )

        # commit()前にIDを保存（commit()後はオブジェクトがexpiredになるため）
        approved_request_id = request_id

        # 通知作成用に一時的にリレーションシップを含めて取得
        result = await db.execute(
            select(EmployeeActionRequest)
            .where(EmployeeActionRequest.id == approved_request_id)
            .options(
                selectinload(EmployeeActionRequest.requester),
                selectinload(EmployeeActionRequest.approver),
                selectinload(EmployeeActionRequest.office)
            )
        )
        approved_request = result.scalar_one()

        # 既存の承認待ち通知のtypeを更新（承認済みに変更）※commitはしない
        link_url = f"/employee-action-requests/{approved_request.id}"
        await crud_notice.update_type_by_link_url(
            db=db,
            link_url=link_url,
            new_type=NoticeType.employee_action_approved.value
        )

        # 通知を作成（リクエスト作成者に送信）※commitはしない
        await self._create_approval_notification(db, approved_request)

        # 最後に1回だけcommit
        await db.commit()

        # commit()後にリレーションシップも含めて再取得（MissingGreenlet対策）
        result = await db.execute(
            select(EmployeeActionRequest)
            .where(EmployeeActionRequest.id == approved_request_id)
            .options(
                selectinload(EmployeeActionRequest.requester),
                selectinload(EmployeeActionRequest.approver),
                selectinload(EmployeeActionRequest.office)
            )
        )
        approved_request = result.scalar_one()

        return approved_request

    async def reject_request(
        self,
        db: AsyncSession,
        *,
        request_id: UUID,
        approver_staff_id: UUID,
        approver_notes: Optional[str] = None
    ) -> EmployeeActionRequest:
        """
        Employee制限リクエストを却下

        Args:
            db: データベースセッション
            request_id: リクエストID
            approver_staff_id: 却下者のスタッフID
            approver_notes: 却下理由（オプション）

        Returns:
            却下されたEmployee制限リクエスト
        """
        logger.info(
            f"Rejecting employee action request: request_id={request_id}, "
            f"approver={approver_staff_id}"
        )

        # リクエストを却下
        rejected_request = await crud_employee_action_request.reject(
            db=db,
            request_id=request_id,
            approver_staff_id=approver_staff_id,
            approver_notes=approver_notes
        )

        # commit()前にIDを保存（commit()後はオブジェクトがexpiredになるため）
        rejected_request_id = request_id

        # 通知作成用に一時的にリレーションシップを含めて取得
        result = await db.execute(
            select(EmployeeActionRequest)
            .where(EmployeeActionRequest.id == rejected_request_id)
            .options(
                selectinload(EmployeeActionRequest.requester),
                selectinload(EmployeeActionRequest.approver),
                selectinload(EmployeeActionRequest.office)
            )
        )
        rejected_request = result.scalar_one()

        # 既存の承認待ち通知のtypeを更新（却下済みに変更）※commitはしない
        link_url = f"/employee-action-requests/{rejected_request.id}"
        await crud_notice.update_type_by_link_url(
            db=db,
            link_url=link_url,
            new_type=NoticeType.employee_action_rejected.value
        )

        # 通知を作成（リクエスト作成者に送信）※commitはしない
        await self._create_rejection_notification(db, rejected_request)

        # 最後に1回だけcommit
        await db.commit()

        # commit()後にリレーションシップも含めて再取得（MissingGreenlet対策）
        result = await db.execute(
            select(EmployeeActionRequest)
            .where(EmployeeActionRequest.id == rejected_request_id)
            .options(
                selectinload(EmployeeActionRequest.requester),
                selectinload(EmployeeActionRequest.approver),
                selectinload(EmployeeActionRequest.office)
            )
        )
        rejected_request = result.scalar_one()

        return rejected_request

    async def _execute_action(
        self,
        db: AsyncSession,
        request: EmployeeActionRequest
    ) -> Dict[str, Any]:
        """
        リクエストに基づいて実際のCRUD操作を実行

        Args:
            db: データベースセッション
            request: Employee制限リクエスト

        Returns:
            実行結果（成功/失敗、作成されたリソースID等）

        Raises:
            ValueError: サポートされていないリソースタイプやアクションタイプの場合
        """
        resource_type = request.resource_type
        action_type = request.action_type

        logger.info(
            f"Executing action: resource_type={resource_type}, "
            f"action_type={action_type}, resource_id={request.resource_id}"
        )

        # リソースタイプとアクションタイプに応じて処理を分岐
        if resource_type == ResourceType.welfare_recipient:
            return await self._execute_welfare_recipient_action(db, request)
        elif resource_type == ResourceType.support_plan_cycle:
            return await self._execute_support_plan_cycle_action(db, request)
        elif resource_type == ResourceType.support_plan_status:
            return await self._execute_support_plan_status_action(db, request)
        else:
            raise ValueError(f"Unsupported resource type: {resource_type}")

    async def _execute_welfare_recipient_action(
        self,
        db: AsyncSession,
        request: EmployeeActionRequest
    ) -> Dict[str, Any]:
        """WelfareRecipientに対するアクションを実行"""
        action_type = request.action_type
        request_data = request.request_data or {}

        if action_type == ActionType.create:
            # form_dataから基本情報を取得
            form_data = request_data.get("form_data", {})
            basic_info = form_data.get("basicInfo", {})

            # 新規作成
            recipient = WelfareRecipient(
                first_name=basic_info.get("firstName"),
                last_name=basic_info.get("lastName"),
                first_name_furigana=basic_info.get("firstNameFurigana"),
                last_name_furigana=basic_info.get("lastNameFurigana"),
                birth_day=date.fromisoformat(basic_info.get("birthDay")),
                gender=GenderType(basic_info.get("gender"))
            )
            db.add(recipient)
            await db.flush()

            # IDを保存（flush後はexpiredになる可能性があるため）
            recipient_id = recipient.id

            # 関連データの作成（住所、緊急連絡先、障害情報）
            logger.info("Creating related data for recipient")

            # 住所・連絡先情報
            contact_address = form_data.get("contactAddress", {})

            # 空文字列をNoneに変換
            form_of_residence_other_text = contact_address.get("formOfResidenceOtherText")
            if form_of_residence_other_text == "":
                form_of_residence_other_text = None

            means_of_transportation_other_text = contact_address.get("meansOfTransportationOtherText")
            if means_of_transportation_other_text == "":
                means_of_transportation_other_text = None

            detail = ServiceRecipientDetail(
                welfare_recipient_id=recipient_id,
                address=contact_address.get("address"),
                form_of_residence=contact_address.get("formOfResidence"),
                form_of_residence_other_text=form_of_residence_other_text,
                means_of_transportation=contact_address.get("meansOfTransportation"),
                means_of_transportation_other_text=means_of_transportation_other_text,
                tel=contact_address.get("tel")
            )
            db.add(detail)
            await db.flush()
            detail_id = detail.id

            # 緊急連絡先
            emergency_contacts = form_data.get("emergencyContacts", [])
            for contact_data in emergency_contacts:
                # 空文字列をNoneに変換
                address = contact_data.get("address")
                if address == "":
                    address = None

                notes = contact_data.get("notes")
                if notes == "":
                    notes = None

                emergency_contact = EmergencyContact(
                    service_recipient_detail_id=detail_id,
                    first_name=contact_data.get("firstName"),
                    last_name=contact_data.get("lastName"),
                    first_name_furigana=contact_data.get("firstNameFurigana"),
                    last_name_furigana=contact_data.get("lastNameFurigana"),
                    relationship=contact_data.get("relationship"),
                    tel=contact_data.get("tel"),
                    address=address,
                    notes=notes,
                    priority=contact_data.get("priority")
                )
                db.add(emergency_contact)

            # 障害情報
            disability_info = form_data.get("disabilityInfo", {})

            # 空文字列をNoneに変換
            special_remarks = disability_info.get("specialRemarks")
            if special_remarks == "":
                special_remarks = None

            disability_status = DisabilityStatus(
                welfare_recipient_id=recipient_id,
                disability_or_disease_name=disability_info.get("disabilityOrDiseaseName"),
                livelihood_protection=disability_info.get("livelihoodProtection"),
                special_remarks=special_remarks
            )
            db.add(disability_status)
            await db.flush()
            disability_status_id = disability_status.id

            # 障害詳細
            disability_details = form_data.get("disabilityDetails", [])
            for detail_data in disability_details:
                # 空文字列をNoneに変換（Enum型フィールド対策）
                physical_disability_type = detail_data.get("physicalDisabilityType")
                if physical_disability_type == "":
                    physical_disability_type = None

                grade_or_level = detail_data.get("gradeOrLevel")
                if grade_or_level == "":
                    grade_or_level = None

                physical_disability_type_other_text = detail_data.get("physicalDisabilityTypeOtherText")
                if physical_disability_type_other_text == "":
                    physical_disability_type_other_text = None

                disability_detail = DisabilityDetail(
                    disability_status_id=disability_status_id,
                    category=detail_data.get("category"),
                    grade_or_level=grade_or_level,
                    physical_disability_type=physical_disability_type,
                    physical_disability_type_other_text=physical_disability_type_other_text,
                    application_status=detail_data.get("applicationStatus")
                )
                db.add(disability_detail)

            # 事業所との関連付け
            association = OfficeWelfareRecipient(
                office_id=request.office_id,
                welfare_recipient_id=recipient_id
            )
            db.add(association)
            await db.flush()

            # 初期支援計画（サイクル + ステータス）を作成
            logger.info(f"Creating initial support plan for recipient {recipient_id}")
            from app.services.welfare_recipient_service import WelfareRecipientService
            await WelfareRecipientService._create_initial_support_plan(
                db=db,
                welfare_recipient_id=recipient_id,
                office_id=request.office_id
            )
            logger.info("Initial support plan created successfully")

            return {
                "success": True,
                "action": "create",
                "resource_id": str(recipient_id)
            }

        elif action_type == ActionType.update:
            # 更新
            # resource_idを取得
            recipient_id = request.resource_id

            if not recipient_id:
                raise ValueError("resource_id is required for update action")

            recipient = await crud_welfare_recipient.get(db, id=recipient_id)
            if not recipient:
                raise ValueError(f"WelfareRecipient {recipient_id} not found")

            # form_dataから基本情報を取得
            form_data = request_data.get("form_data", {})
            basic_info = form_data.get("basicInfo", {})

            # 更新するフィールドを適用
            if "firstName" in basic_info:
                recipient.first_name = basic_info["firstName"]
            if "lastName" in basic_info:
                recipient.last_name = basic_info["lastName"]
            if "firstNameFurigana" in basic_info:
                recipient.first_name_furigana = basic_info["firstNameFurigana"]
            if "lastNameFurigana" in basic_info:
                recipient.last_name_furigana = basic_info["lastNameFurigana"]
            if "birthDay" in basic_info:
                recipient.birth_day = date.fromisoformat(basic_info["birthDay"])
            if "gender" in basic_info:
                recipient.gender = GenderType(basic_info["gender"])

            await db.flush()

            return {
                "success": True,
                "action": "update",
                "resource_id": str(recipient.id)
            }

        elif action_type == ActionType.delete:
            # 削除
            # resource_idまたはrequest_dataからwelfare_recipient_idを取得
            recipient_id = request.resource_id
            if not recipient_id and "welfare_recipient_id" in request_data:
                recipient_id = UUID(request_data["welfare_recipient_id"])

            if not recipient_id:
                raise ValueError("resource_id or welfare_recipient_id is required for delete action")

            recipient = await crud_welfare_recipient.get(db, id=recipient_id)
            if not recipient:
                raise ValueError(f"WelfareRecipient {recipient_id} not found")

            await db.delete(recipient)
            await db.flush()

            return {
                "success": True,
                "action": "delete",
                "resource_id": str(recipient_id)
            }

        else:
            raise ValueError(f"Unsupported action type: {action_type}")

    async def _execute_support_plan_cycle_action(
        self,
        db: AsyncSession,
        request: EmployeeActionRequest
    ) -> Dict[str, Any]:
        """SupportPlanCycleに対するアクションを実行（TODO: 実装予定）"""
        # TODO: Phase 7で実装
        return {
            "success": True,
            "action": str(request.action_type),
            "message": "SupportPlanCycle actions not yet implemented"
        }

    async def _execute_support_plan_status_action(
        self,
        db: AsyncSession,
        request: EmployeeActionRequest
    ) -> Dict[str, Any]:
        """SupportPlanStatusに対するアクションを実行（TODO: 実装予定）"""
        # TODO: Phase 7で実装
        return {
            "success": True,
            "action": str(request.action_type),
            "message": "SupportPlanStatus actions not yet implemented"
        }

    async def _create_request_notification(
        self,
        db: AsyncSession,
        request: EmployeeActionRequest
    ) -> None:
        """
        Employee制限リクエスト作成時の通知を承認者に送信

        Args:
            db: データベースセッション
            request: Employee制限リクエスト

        Note:
            このメソッドはcommitしない。親メソッドで最後に1回だけcommitする。
        """
        # 承認可能なスタッフ（manager/owner）を取得
        approvers = await self._get_approvers(db, request.office_id)

        # request_dataから詳細情報を抽出
        detail_info = self._extract_detail_from_request_data(request)

        # 各承認者に通知を作成
        for approver_id in approvers:
            notice_data = NoticeCreate(
                recipient_staff_id=approver_id,
                office_id=request.office_id,
                type=NoticeType.employee_action_pending.value,
                title="作成、編集、削除リクエストが作成されました",
                content=f"{request.requester.full_name}さんが{detail_info}をリクエストしました。",
                link_url=f"/employee-action-requests/{request.id}"
            )
            await crud_notice.create(db, obj_in=notice_data)

        # commitしない（親メソッドで最後に1回だけcommitする）

    async def _create_approval_notification(
        self,
        db: AsyncSession,
        request: EmployeeActionRequest
    ) -> None:
        """
        Employee制限リクエスト承認時の通知をリクエスト作成者に送信

        Args:
            db: データベースセッション
            request: Employee制限リクエスト

        Note:
            このメソッドはcommitしない。親メソッドで最後に1回だけcommitする。
        """
        # request_dataから詳細情報を抽出
        detail_info = self._extract_detail_from_request_data(request)

        notice_data = NoticeCreate(
            recipient_staff_id=request.requester_staff_id,
            office_id=request.office_id,
            type=NoticeType.employee_action_approved.value,
            title="作成、編集、削除リクエストが承認されました",
            content=f"あなたの{detail_info}リクエストが承認されました。",
            link_url=f"/employee-action-requests/{request.id}"
        )
        await crud_notice.create(db, obj_in=notice_data)
        # commitしない（親メソッドで最後に1回だけcommitする）

    async def _create_rejection_notification(
        self,
        db: AsyncSession,
        request: EmployeeActionRequest
    ) -> None:
        """
        Employee制限リクエスト却下時の通知をリクエスト作成者に送信

        Args:
            db: データベースセッション
            request: Employee制限リクエスト

        Note:
            このメソッドはcommitしない。親メソッドで最後に1回だけcommitする。
        """
        # request_dataから詳細情報を抽出
        detail_info = self._extract_detail_from_request_data(request)

        notice_data = NoticeCreate(
            recipient_staff_id=request.requester_staff_id,
            office_id=request.office_id,
            type=NoticeType.employee_action_rejected.value,
            title="作成、編集、削除リクエストが却下されました",
            content=f"あなたの{detail_info}リクエストが却下されました。",
            link_url=f"/employee-action-requests/{request.id}"
        )
        await crud_notice.create(db, obj_in=notice_data)
        # commitしない（親メソッドで最後に1回だけcommitする）

    async def _get_approvers(
        self,
        db: AsyncSession,
        office_id: UUID
    ) -> List[UUID]:
        """
        リクエストを承認可能なスタッフIDのリストを取得（manager/owner）

        Args:
            db: データベースセッション
            office_id: 事業所ID

        Returns:
            承認可能なスタッフIDのリスト
        """
        from app.models.staff import Staff
        from app.models.office import OfficeStaff

        # manager/ownerを取得
        result = await db.execute(
            select(Staff.id)
            .join(OfficeStaff, OfficeStaff.staff_id == Staff.id)
            .where(
                OfficeStaff.office_id == office_id,
                Staff.role.in_([StaffRole.manager, StaffRole.owner])
            )
        )

        return list(result.scalars().all())

    def _extract_detail_from_request_data(
        self,
        request: EmployeeActionRequest
    ) -> str:
        """
        request_dataから詳細情報を抽出して日本語文を生成

        Args:
            request: Employee制限リクエスト

        Returns:
            詳細情報を含む日本語文字列
            例: 「利用者(山田 太郎さん)の作成」
            例: 「山田 太郎さんのアセスメント情報の作成」
        """
        # アクションタイプの日本語表示
        action_ja = {
            ActionType.create: "作成",
            ActionType.update: "更新",
            ActionType.delete: "削除"
        }

        # リソースタイプの日本語表示
        resource_ja = {
            ResourceType.welfare_recipient: "利用者",
            ResourceType.support_plan_cycle: "サポート計画サイクル",
            ResourceType.support_plan_status: "サポート計画ステータス"
        }

        # ステップタイプの日本語表示（SupportPlanStatus用）
        step_type_ja = {
            "assessment": "アセスメント情報",
            "draft_plan": "計画案",
            "staff_meeting": "職員会議記録",
            "final_plan_signed": "最終計画",
            "monitoring": "モニタリング報告"
        }

        action_name = action_ja.get(request.action_type, str(request.action_type))

        # SupportPlanStatusの場合は特別な処理
        if request.resource_type == ResourceType.support_plan_status:
            if request.request_data:
                # 利用者名を取得
                recipient_name = request.request_data.get("welfare_recipient_full_name", "")

                # ステップタイプを日本語化
                step_type = request.request_data.get("step_type", "")
                step_type_name = step_type_ja.get(step_type, "サポート計画ステータス")

                if recipient_name:
                    return f"{recipient_name}さんの{step_type_name}の{action_name}"
                else:
                    return f"{step_type_name}の{action_name}"
            else:
                return f"サポート計画ステータスの{action_name}"

        # WelfareRecipientやその他のリソースタイプの処理
        resource_name = resource_ja.get(request.resource_type, str(request.resource_type))

        # request_dataから対象名を取得
        target_name = ""
        if request.request_data:
            if request.resource_type == ResourceType.welfare_recipient:
                # 利用者の場合、full_nameを取得
                full_name = request.request_data.get("full_name")
                if full_name:
                    target_name = f"({full_name}さん)"
                else:
                    # full_nameが無い場合、first_nameとlast_nameから生成を試みる
                    first_name = request.request_data.get("first_name")
                    last_name = request.request_data.get("last_name")
                    if first_name and last_name:
                        target_name = f"({last_name} {first_name}さん)"
            # 他のリソースタイプも必要に応じて追加可能

        return f"{resource_name}{target_name}の{action_name}"


# サービスインスタンスをエクスポート
employee_action_service = EmployeeActionService()
