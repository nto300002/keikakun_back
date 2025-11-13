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


def _parse_birth_day(birth_day_value: Any) -> Optional[date]:
    """
    birthDay値を安全にdateオブジェクトに変換

    Args:
        birth_day_value: 文字列、dateオブジェクト、またはNone

    Returns:
        dateオブジェクトまたはNone
    """
    if birth_day_value is None:
        return None
    if isinstance(birth_day_value, date):
        return birth_day_value
    if isinstance(birth_day_value, str):
        return date.fromisoformat(birth_day_value)
    return None


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

            # トランザクションがロールバック状態になっているため、明示的にrollbackを実行
            await db.rollback()

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

        # 通知作成用の詳細情報を事前に取得（MissingGreenlet対策）
        detail_info = self._extract_detail_from_request_data(approved_request)
        office_id = approved_request.office_id
        requester_full_name = approved_request.requester.full_name
        requester_staff_id = approved_request.requester_staff_id

        # 承認者のIDリストを取得（_get_approversメソッドを使用）
        approver_staff_ids = await self._get_approvers(db, office_id)

        # 既存の承認待ち通知を削除（承認者向けの通知）※commitはしない
        # typeだけ更新するとtitle/contentと矛盾するため、削除して新しい通知を作成
        link_url = f"/employee-action-requests/{approved_request.id}"
        delete_stmt = select(crud_notice.model).where(
            crud_notice.model.link_url == link_url,
            crud_notice.model.type == NoticeType.employee_action_pending.value
        )
        delete_result = await db.execute(delete_stmt)
        notices_to_delete = delete_result.scalars().all()

        for notice in notices_to_delete:
            await db.delete(notice)

        # 送信者向けの既存通知も削除（employee_action_request_sent）
        delete_sender_stmt = select(crud_notice.model).where(
            crud_notice.model.link_url == link_url,
            crud_notice.model.type == NoticeType.employee_action_request_sent.value
        )
        delete_sender_result = await db.execute(delete_sender_stmt)
        sender_notices_to_delete = delete_sender_result.scalars().all()

        for notice in sender_notices_to_delete:
            await db.delete(notice)

        # 送信者向けの新しい通知を作成（employee_action_approved）
        sender_notice_data = NoticeCreate(
            recipient_staff_id=requester_staff_id,
            office_id=office_id,
            type=NoticeType.employee_action_approved.value,
            title="作成、編集、削除リクエストが承認されました",
            content=f"あなたの{detail_info}リクエストが承認されました。",
            link_url=link_url
        )
        await crud_notice.create(db, obj_in=sender_notice_data)

        # 承認者向けの通知を再作成
        for approver_id in approver_staff_ids:
            approver_notice_data = NoticeCreate(
                recipient_staff_id=approver_id,
                office_id=office_id,
                type=NoticeType.employee_action_approved.value,
                title="作成、編集、削除リクエストが承認されました",
                content=f"{requester_full_name}さんの{detail_info}リクエストを承認しました。",
                link_url=link_url
            )
            await crud_notice.create(db, obj_in=approver_notice_data)

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

        # 通知作成用の詳細情報を事前に取得（MissingGreenlet対策）
        detail_info = self._extract_detail_from_request_data(rejected_request)
        office_id = rejected_request.office_id
        requester_full_name = rejected_request.requester.full_name
        requester_staff_id = rejected_request.requester_staff_id

        # 承認者のIDリストを取得（_get_approversメソッドを使用）
        approver_staff_ids = await self._get_approvers(db, office_id)

        # 既存の承認待ち通知を削除（承認者向けの通知）※commitはしない
        # typeだけ更新するとtitle/contentと矛盾するため、削除して新しい通知を作成
        link_url = f"/employee-action-requests/{rejected_request.id}"
        delete_stmt = select(crud_notice.model).where(
            crud_notice.model.link_url == link_url,
            crud_notice.model.type == NoticeType.employee_action_pending.value
        )
        delete_result = await db.execute(delete_stmt)
        notices_to_delete = delete_result.scalars().all()

        for notice in notices_to_delete:
            await db.delete(notice)

        # 送信者向けの既存通知も削除（employee_action_request_sent）
        delete_sender_stmt = select(crud_notice.model).where(
            crud_notice.model.link_url == link_url,
            crud_notice.model.type == NoticeType.employee_action_request_sent.value
        )
        delete_sender_result = await db.execute(delete_sender_stmt)
        sender_notices_to_delete = delete_sender_result.scalars().all()

        for notice in sender_notices_to_delete:
            await db.delete(notice)

        # 送信者向けの新しい通知を作成（employee_action_rejected）
        sender_notice_data = NoticeCreate(
            recipient_staff_id=requester_staff_id,
            office_id=office_id,
            type=NoticeType.employee_action_rejected.value,
            title="作成、編集、削除リクエストが却下されました",
            content=f"あなたの{detail_info}リクエストが却下されました。",
            link_url=link_url
        )
        await crud_notice.create(db, obj_in=sender_notice_data)

        # 承認者向けの通知を再作成
        for approver_id in approver_staff_ids:
            approver_notice_data = NoticeCreate(
                recipient_staff_id=approver_id,
                office_id=office_id,
                type=NoticeType.employee_action_rejected.value,
                title="作成、編集、削除リクエストが却下されました",
                content=f"{requester_full_name}さんの{detail_info}リクエストを却下しました。",
                link_url=link_url
            )
            await crud_notice.create(db, obj_in=approver_notice_data)

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
            # form_data階層を取得（後方互換性のために3つの形式をサポート）
            # 1. 新形式: request_data.form_data.basicInfo (camelCase)
            # 2. 旧形式: request_data.basic_info (snake_case)
            # 3. 最古形式: request_data に直接フィールド (snake_case)
            form_data = request_data.get("form_data", {})
            basic_info = form_data.get("basicInfo", {})

            # 旧形式の場合、direct_dataから取得
            if not basic_info:
                basic_info = request_data.get("basic_info", {})

            # 最古形式の場合、request_dataから直接取得
            if not basic_info and "first_name" in request_data:
                basic_info = request_data
                form_data = request_data  # 最古形式の場合、form_dataもrequest_dataとして扱う

            # 新規作成
            # フィールド名は camelCase と snake_case の両方をサポート
            gender_value = basic_info.get("gender")
            recipient = WelfareRecipient(
                first_name=basic_info.get("firstName") or basic_info.get("first_name"),
                last_name=basic_info.get("lastName") or basic_info.get("last_name"),
                first_name_furigana=basic_info.get("firstNameFurigana") or basic_info.get("first_name_furigana"),
                last_name_furigana=basic_info.get("lastNameFurigana") or basic_info.get("last_name_furigana"),
                birth_day=_parse_birth_day(basic_info.get("birthDay") or basic_info.get("birth_day")),
                gender=GenderType(gender_value) if gender_value else None
            )
            db.add(recipient)
            await db.flush()

            # IDを保存（flush後はexpiredになる可能性があるため）
            recipient_id = recipient.id

            # 関連データの作成（住所、緊急連絡先、障害情報）
            logger.info("Creating related data for recipient")

            # 住所・連絡先情報
            contact_address = form_data.get("contactAddress", {})
            if not contact_address:
                contact_address = request_data.get("contact_address", {})

            # ServiceRecipientDetail は必須フィールド（address, tel, form_of_residence, means_of_transportation）が
            # 全て存在する場合のみ作成する
            detail_id = None
            if contact_address and contact_address.get("address") and contact_address.get("tel"):
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

            # 緊急連絡先（detail_id が存在する場合のみ作成）
            if detail_id:
                emergency_contacts = form_data.get("emergencyContacts", [])
                if not emergency_contacts:
                    emergency_contacts = request_data.get("emergency_contacts", [])
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
                        first_name=contact_data.get("firstName") or contact_data.get("first_name"),
                        last_name=contact_data.get("lastName") or contact_data.get("last_name"),
                        first_name_furigana=contact_data.get("firstNameFurigana") or contact_data.get("first_name_furigana"),
                        last_name_furigana=contact_data.get("lastNameFurigana") or contact_data.get("last_name_furigana"),
                        relationship=contact_data.get("relationship"),
                        tel=contact_data.get("tel"),
                        address=address,
                        notes=notes,
                        priority=contact_data.get("priority")
                    )
                    db.add(emergency_contact)

            # 障害情報（必須フィールドが存在する場合のみ作成）
            disability_info = form_data.get("disabilityInfo", {})
            if not disability_info:
                disability_info = request_data.get("disability_info", {})

            disability_status_id = None
            if disability_info and disability_info.get("disabilityOrDiseaseName") and disability_info.get("livelihoodProtection"):
                # 空文字列をNoneに変換
                special_remarks = disability_info.get("specialRemarks") or disability_info.get("special_remarks")
                if special_remarks == "":
                    special_remarks = None

                disability_status = DisabilityStatus(
                    welfare_recipient_id=recipient_id,
                    disability_or_disease_name=disability_info.get("disabilityOrDiseaseName") or disability_info.get("disability_or_disease_name"),
                    livelihood_protection=disability_info.get("livelihoodProtection") or disability_info.get("livelihood_protection"),
                    special_remarks=special_remarks
                )
                db.add(disability_status)
                await db.flush()
                disability_status_id = disability_status.id

            # 障害詳細（disability_status_id が存在する場合のみ作成）
            if disability_status_id:
                disability_details = form_data.get("disabilityDetails", [])
                if not disability_details:
                    disability_details = request_data.get("disability_details", [])
                for detail_data in disability_details:
                    # 空文字列をNoneに変換（Enum型フィールド対策）
                    physical_disability_type = detail_data.get("physicalDisabilityType") or detail_data.get("physical_disability_type")
                    if physical_disability_type == "":
                        physical_disability_type = None

                    grade_or_level = detail_data.get("gradeOrLevel") or detail_data.get("grade_or_level")
                    if grade_or_level == "":
                        grade_or_level = None

                    physical_disability_type_other_text = detail_data.get("physicalDisabilityTypeOtherText") or detail_data.get("physical_disability_type_other_text")
                    if physical_disability_type_other_text == "":
                        physical_disability_type_other_text = None

                    disability_detail = DisabilityDetail(
                        disability_status_id=disability_status_id,
                        category=detail_data.get("category"),
                        grade_or_level=grade_or_level,
                        physical_disability_type=physical_disability_type,
                        physical_disability_type_other_text=physical_disability_type_other_text,
                        application_status=detail_data.get("applicationStatus") or detail_data.get("application_status")
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

            # form_data階層を取得（後方互換性のために3つの形式をサポート）
            # 1. 新形式: request_data.form_data.basicInfo (camelCase)
            # 2. 旧形式: request_data.basic_info (snake_case)
            # 3. 最古形式: request_data に直接フィールド (snake_case)
            form_data = request_data.get("form_data", {})
            basic_info = form_data.get("basicInfo", {})

            # 旧形式の場合、direct_dataから取得
            if not basic_info:
                basic_info = request_data.get("basic_info", {})

            # 最古形式の場合、request_dataから直接取得
            if not basic_info and "first_name" in request_data:
                basic_info = request_data

            # 更新するフィールドを適用（camelCase と snake_case の両方をサポート）
            if "firstName" in basic_info or "first_name" in basic_info:
                recipient.first_name = basic_info.get("firstName") or basic_info.get("first_name")
            if "lastName" in basic_info or "last_name" in basic_info:
                recipient.last_name = basic_info.get("lastName") or basic_info.get("last_name")
            if "firstNameFurigana" in basic_info or "first_name_furigana" in basic_info:
                recipient.first_name_furigana = basic_info.get("firstNameFurigana") or basic_info.get("first_name_furigana")
            if "lastNameFurigana" in basic_info or "last_name_furigana" in basic_info:
                recipient.last_name_furigana = basic_info.get("lastNameFurigana") or basic_info.get("last_name_furigana")
            if "birthDay" in basic_info or "birth_day" in basic_info:
                recipient.birth_day = _parse_birth_day(basic_info.get("birthDay") or basic_info.get("birth_day"))
            if "gender" in basic_info:
                gender_value = basic_info["gender"]
                recipient.gender = GenderType(gender_value) if gender_value else None

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
        """SupportPlanStatusに対するアクションを実行"""
        action_type = request.action_type
        request_data = request.request_data or {}

        logger.info(f"Executing support_plan_status action: {action_type}")
        logger.info(f"Request data: {request_data}")

        # deliverable_idを取得
        deliverable_id = request_data.get("deliverable_id")

        if not deliverable_id:
            logger.warning("No deliverable_id found in request_data")
            return {
                "success": False,
                "action": str(action_type),
                "error": "deliverable_id is required"
            }

        # deliverableが存在するか確認
        from app.models.support_plan_cycle import PlanDeliverable
        deliverable_stmt = select(PlanDeliverable).where(PlanDeliverable.id == deliverable_id)
        deliverable_result = await db.execute(deliverable_stmt)
        deliverable = deliverable_result.scalar_one_or_none()

        if not deliverable:
            logger.error(f"Deliverable {deliverable_id} not found")
            return {
                "success": False,
                "action": str(action_type),
                "error": f"Deliverable {deliverable_id} not found"
            }

        logger.info(f"Deliverable {deliverable_id} found. No further action needed (already uploaded).")

        # deliverableは既にアップロード済みなので、特に何もしない
        # 将来的に承認フラグなどを追加する場合はここで更新

        return {
            "success": True,
            "action": str(action_type),
            "deliverable_id": str(deliverable_id),
            "message": "PDF deliverable already uploaded and verified"
        }

    async def _create_request_notification(
        self,
        db: AsyncSession,
        request: EmployeeActionRequest
    ) -> None:
        """
        Employee制限リクエスト作成時の通知を承認者と送信者に送信

        Args:
            db: データベースセッション
            request: Employee制限リクエスト

        Note:
            このメソッドはcommitしない。親メソッドで最後に1回だけcommitする。
        """
        # _get_approvers呼び出し前に必要な値を変数に格納
        # (_get_approvers内のdb.execute()でrequestオブジェクトがexpireされるため)
        office_id = request.office_id
        requester_full_name = request.requester.full_name
        requester_staff_id = request.requester_staff_id
        request_id = request.id

        # request_dataから詳細情報を抽出
        detail_info = self._extract_detail_from_request_data(request)

        # 1. 承認可能なスタッフ（manager/owner）に通知を作成
        approvers = await self._get_approvers(db, office_id)

        # 各承認者に通知を作成
        for approver_id in approvers:
            notice_data = NoticeCreate(
                recipient_staff_id=approver_id,
                office_id=office_id,
                type=NoticeType.employee_action_pending.value,
                title="作成、編集、削除リクエストが作成されました",
                content=f"{requester_full_name}さんが{detail_info}をリクエストしました。",
                link_url=f"/employee-action-requests/{request_id}"
            )
            await crud_notice.create(db, obj_in=notice_data)

        # 2. リクエスト作成者（送信者）にも通知を作成
        requester_notice_data = NoticeCreate(
            recipient_staff_id=requester_staff_id,
            office_id=office_id,
            type=NoticeType.employee_action_request_sent.value,
            title="作成、編集、削除リクエストを送信しました",
            content=f"あなたの{detail_info}リクエストを送信しました。承認をお待ちください。",
            link_url=f"/employee-action-requests/{request_id}"
        )
        await crud_notice.create(db, obj_in=requester_notice_data)

        # 3. 事務所の通知数が50件を超えた場合、古いものから削除
        await crud_notice.delete_old_notices_over_limit(db, office_id=office_id, limit=50)

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
        # リレーションシップの値を事前に変数に保存（MissingGreenlet対策）
        office_id = request.office_id
        requester_staff_id = request.requester_staff_id
        request_id = request.id

        # request_dataから詳細情報を抽出
        detail_info = self._extract_detail_from_request_data(request)

        notice_data = NoticeCreate(
            recipient_staff_id=requester_staff_id,
            office_id=office_id,
            type=NoticeType.employee_action_approved.value,
            title="作成、編集、削除リクエストが承認されました",
            content=f"あなたの{detail_info}リクエストが承認されました。",
            link_url=f"/employee-action-requests/{request_id}"
        )
        await crud_notice.create(db, obj_in=notice_data)

        # 事務所の通知数が50件を超えた場合、古いものから削除
        await crud_notice.delete_old_notices_over_limit(db, office_id=office_id, limit=50)

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
        # リレーションシップの値を事前に変数に保存（MissingGreenlet対策）
        office_id = request.office_id
        requester_staff_id = request.requester_staff_id
        request_id = request.id

        # request_dataから詳細情報を抽出
        detail_info = self._extract_detail_from_request_data(request)

        notice_data = NoticeCreate(
            recipient_staff_id=requester_staff_id,
            office_id=office_id,
            type=NoticeType.employee_action_rejected.value,
            title="作成、編集、削除リクエストが却下されました",
            content=f"あなたの{detail_info}リクエストが却下されました。",
            link_url=f"/employee-action-requests/{request_id}"
        )
        await crud_notice.create(db, obj_in=notice_data)

        # 事務所の通知数が50件を超えた場合、古いものから削除
        await crud_notice.delete_old_notices_over_limit(db, office_id=office_id, limit=50)

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
