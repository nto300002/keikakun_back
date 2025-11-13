import pytest
import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models.employee_action_request import EmployeeActionRequest
from app.models.enums import (
    RequestStatus,
    ActionType,
    ResourceType,
)


class TestEmployeeActionRequestModel:
    """EmployeeActionRequestモデルのテスト"""

    @pytest.mark.asyncio
    async def test_create_employee_action_request_create(
        self,
        db_session: AsyncSession,
        employee_user_factory,
        office_factory
    ):
        """EmployeeActionRequest作成の基本テスト（CREATE）"""
        employee = await employee_user_factory(with_office=False)
        office = await office_factory(creator=employee)

        # CREATE アクションリクエストを作成
        request_data = {
            "last_name": "山田",
            "first_name": "太郎",
            "birth_day": "1990-01-01",
            "gender": "male"
        }

        request = EmployeeActionRequest(
            requester_staff_id=employee.id,
            office_id=office.id,
            resource_type=ResourceType.welfare_recipient,
            action_type=ActionType.create,
            resource_id=None,  # createの場合はNone
            request_data=request_data,
            status=RequestStatus.pending
        )
        db_session.add(request)
        await db_session.commit()
        await db_session.refresh(request)

        # 基本属性の確認
        assert request.id is not None
        assert request.requester_staff_id == employee.id
        assert request.office_id == office.id
        assert request.resource_type == ResourceType.welfare_recipient
        assert request.action_type == ActionType.create
        assert request.resource_id is None
        assert request.request_data == request_data
        assert request.status == RequestStatus.pending
        assert request.created_at is not None
        assert request.updated_at is not None

    @pytest.mark.asyncio
    async def test_create_employee_action_request_update(
        self,
        db_session: AsyncSession,
        employee_user_factory,
        office_factory
    ):
        """EmployeeActionRequest作成の基本テスト（UPDATE）"""
        employee = await employee_user_factory(with_office=False)
        office = await office_factory(creator=employee)

        resource_id = uuid.uuid4()
        request_data = {"last_name": "田中"}

        request = EmployeeActionRequest(
            requester_staff_id=employee.id,
            office_id=office.id,
            resource_type=ResourceType.welfare_recipient,
            action_type=ActionType.update,
            resource_id=resource_id,
            request_data=request_data,
            status=RequestStatus.pending
        )
        db_session.add(request)
        await db_session.commit()
        await db_session.refresh(request)

        assert request.action_type == ActionType.update
        assert request.resource_id == resource_id
        assert request.request_data == request_data

    @pytest.mark.asyncio
    async def test_create_employee_action_request_delete(
        self,
        db_session: AsyncSession,
        employee_user_factory,
        office_factory
    ):
        """EmployeeActionRequest作成の基本テスト（DELETE）"""
        employee = await employee_user_factory(with_office=False)
        office = await office_factory(creator=employee)

        resource_id = uuid.uuid4()

        request = EmployeeActionRequest(
            requester_staff_id=employee.id,
            office_id=office.id,
            resource_type=ResourceType.welfare_recipient,
            action_type=ActionType.delete,
            resource_id=resource_id,
            request_data=None,  # deleteの場合はNone
            status=RequestStatus.pending
        )
        db_session.add(request)
        await db_session.commit()
        await db_session.refresh(request)

        assert request.action_type == ActionType.delete
        assert request.resource_id == resource_id
        assert request.request_data is None

    @pytest.mark.asyncio
    async def test_employee_action_request_default_status(
        self,
        db_session: AsyncSession,
        employee_user_factory,
        office_factory
    ):
        """EmployeeActionRequestのデフォルトステータスがpendingであることを確認"""
        employee = await employee_user_factory(with_office=False)
        office = await office_factory(creator=employee)

        request = EmployeeActionRequest(
            requester_staff_id=employee.id,
            office_id=office.id,
            resource_type=ResourceType.support_plan_cycle,
            action_type=ActionType.create
        )
        db_session.add(request)
        await db_session.commit()
        await db_session.refresh(request)

        assert request.status == RequestStatus.pending
        assert request.approved_by_staff_id is None
        assert request.approved_at is None
        assert request.approver_notes is None
        assert request.execution_result is None

    @pytest.mark.asyncio
    async def test_employee_action_request_approval(
        self,
        db_session: AsyncSession,
        employee_user_factory,
        manager_user_factory,
        office_factory
    ):
        """EmployeeActionRequestの承認処理テスト"""
        employee = await employee_user_factory(with_office=False)
        office = await office_factory(creator=employee)
        manager = await manager_user_factory(office=office, with_office=True)

        # リクエスト作成
        request = EmployeeActionRequest(
            requester_staff_id=employee.id,
            office_id=office.id,
            resource_type=ResourceType.welfare_recipient,
            action_type=ActionType.create,
            request_data={"last_name": "山田", "first_name": "太郎"},
            status=RequestStatus.pending
        )
        db_session.add(request)
        await db_session.commit()

        # 承認処理
        request.status = RequestStatus.approved
        request.approved_by_staff_id = manager.id
        request.approved_at = datetime.now(timezone.utc)
        request.approver_notes = "承認しました"
        request.execution_result = {"success": True, "resource_id": str(uuid.uuid4())}
        await db_session.commit()
        await db_session.refresh(request)

        # 承認後の状態確認
        assert request.status == RequestStatus.approved
        assert request.approved_by_staff_id == manager.id
        assert request.approved_at is not None
        assert request.approver_notes == "承認しました"
        assert request.execution_result["success"] is True

    @pytest.mark.asyncio
    async def test_employee_action_request_rejection(
        self,
        db_session: AsyncSession,
        employee_user_factory,
        manager_user_factory,
        office_factory
    ):
        """EmployeeActionRequestの却下処理テスト"""
        employee = await employee_user_factory(with_office=False)
        office = await office_factory(creator=employee)
        manager = await manager_user_factory(office=office, with_office=True)

        request = EmployeeActionRequest(
            requester_staff_id=employee.id,
            office_id=office.id,
            resource_type=ResourceType.welfare_recipient,
            action_type=ActionType.delete,
            resource_id=uuid.uuid4(),
            status=RequestStatus.pending
        )
        db_session.add(request)
        await db_session.commit()

        # 却下処理
        request.status = RequestStatus.rejected
        request.approved_by_staff_id = manager.id
        request.approved_at = datetime.now(timezone.utc)
        request.approver_notes = "削除は承認できません"
        await db_session.commit()
        await db_session.refresh(request)

        assert request.status == RequestStatus.rejected
        assert request.approved_by_staff_id == manager.id
        assert request.approver_notes == "削除は承認できません"
        assert request.execution_result is None  # 却下時は実行されない

    @pytest.mark.asyncio
    async def test_employee_action_request_support_plan_cycle(
        self,
        db_session: AsyncSession,
        employee_user_factory,
        office_factory
    ):
        """SupportPlanCycleリソースのリクエストテスト"""
        employee = await employee_user_factory(with_office=False)
        office = await office_factory(creator=employee)

        request_data = {
            "welfare_recipient_id": str(uuid.uuid4()),
            "cycle_start_date": "2025-01-01",
            "cycle_end_date": "2025-12-31"
        }

        request = EmployeeActionRequest(
            requester_staff_id=employee.id,
            office_id=office.id,
            resource_type=ResourceType.support_plan_cycle,
            action_type=ActionType.create,
            request_data=request_data
        )
        db_session.add(request)
        await db_session.commit()
        await db_session.refresh(request)

        assert request.resource_type == ResourceType.support_plan_cycle
        assert request.request_data == request_data

    @pytest.mark.asyncio
    async def test_employee_action_request_support_plan_status(
        self,
        db_session: AsyncSession,
        employee_user_factory,
        office_factory
    ):
        """SupportPlanStatusリソースのリクエストテスト"""
        employee = await employee_user_factory(with_office=False)
        office = await office_factory(creator=employee)

        resource_id = uuid.uuid4()
        request_data = {"status": "completed"}

        request = EmployeeActionRequest(
            requester_staff_id=employee.id,
            office_id=office.id,
            resource_type=ResourceType.support_plan_status,
            action_type=ActionType.update,
            resource_id=resource_id,
            request_data=request_data
        )
        db_session.add(request)
        await db_session.commit()
        await db_session.refresh(request)

        assert request.resource_type == ResourceType.support_plan_status
        assert request.action_type == ActionType.update
        assert request.resource_id == resource_id

    @pytest.mark.asyncio
    async def test_employee_action_request_foreign_key_staff(
        self,
        db_session: AsyncSession,
        office_factory,
        employee_user_factory
    ):
        """EmployeeActionRequestのstaff外部キー制約テスト"""
        employee = await employee_user_factory(with_office=False)
        office = await office_factory(creator=employee)

        # 存在しないstaff_idを指定
        fake_staff_id = uuid.uuid4()

        request = EmployeeActionRequest(
            requester_staff_id=fake_staff_id,
            office_id=office.id,
            resource_type=ResourceType.welfare_recipient,
            action_type=ActionType.create
        )

        db_session.add(request)
        with pytest.raises(IntegrityError):
            await db_session.flush()

    @pytest.mark.asyncio
    async def test_employee_action_request_foreign_key_office(
        self,
        db_session: AsyncSession,
        employee_user_factory
    ):
        """EmployeeActionRequestのoffice外部キー制約テスト"""
        employee = await employee_user_factory(with_office=False)

        # 存在しないoffice_idを指定
        fake_office_id = uuid.uuid4()

        request = EmployeeActionRequest(
            requester_staff_id=employee.id,
            office_id=fake_office_id,
            resource_type=ResourceType.welfare_recipient,
            action_type=ActionType.create
        )

        db_session.add(request)
        with pytest.raises(IntegrityError):
            await db_session.flush()

    @pytest.mark.asyncio
    async def test_employee_action_request_relationship_requester(
        self,
        db_session: AsyncSession,
        employee_user_factory,
        office_factory
    ):
        """EmployeeActionRequestとRequester（Staff）のリレーションシップテスト"""
        employee = await employee_user_factory(with_office=False)
        office = await office_factory(creator=employee)

        request = EmployeeActionRequest(
            requester_staff_id=employee.id,
            office_id=office.id,
            resource_type=ResourceType.welfare_recipient,
            action_type=ActionType.create
        )
        db_session.add(request)
        await db_session.commit()

        # Eagerロードしてrelationshipを確認
        await db_session.refresh(request, ["requester"])

        assert request.requester is not None
        assert request.requester.id == employee.id
        assert request.requester.email == employee.email

    @pytest.mark.asyncio
    async def test_employee_action_request_relationship_approver(
        self,
        db_session: AsyncSession,
        employee_user_factory,
        manager_user_factory,
        office_factory
    ):
        """EmployeeActionRequestとApprover（Staff）のリレーションシップテスト"""
        employee = await employee_user_factory(with_office=False)
        office = await office_factory(creator=employee)
        manager = await manager_user_factory(office=office, with_office=True)

        request = EmployeeActionRequest(
            requester_staff_id=employee.id,
            office_id=office.id,
            resource_type=ResourceType.welfare_recipient,
            action_type=ActionType.create,
            approved_by_staff_id=manager.id
        )
        db_session.add(request)
        await db_session.commit()

        # Eagerロードしてrelationshipを確認
        await db_session.refresh(request, ["approver"])

        assert request.approver is not None
        assert request.approver.id == manager.id
        assert request.approver.email == manager.email

    @pytest.mark.asyncio
    async def test_employee_action_request_relationship_office(
        self,
        db_session: AsyncSession,
        employee_user_factory,
        office_factory
    ):
        """EmployeeActionRequestとOfficeのリレーションシップテスト"""
        employee = await employee_user_factory(with_office=False)
        office = await office_factory(creator=employee)

        request = EmployeeActionRequest(
            requester_staff_id=employee.id,
            office_id=office.id,
            resource_type=ResourceType.welfare_recipient,
            action_type=ActionType.create
        )
        db_session.add(request)
        await db_session.commit()

        # Eagerロードしてrelationshipを確認
        await db_session.refresh(request, ["office"])

        assert request.office is not None
        assert request.office.id == office.id
        assert request.office.name == office.name

    @pytest.mark.asyncio
    async def test_employee_action_request_updated_at_changes(
        self,
        db_session: AsyncSession,
        employee_user_factory,
        office_factory
    ):
        """EmployeeActionRequest updated_at更新のテスト"""
        employee = await employee_user_factory(with_office=False)
        office = await office_factory(creator=employee)

        request = EmployeeActionRequest(
            requester_staff_id=employee.id,
            office_id=office.id,
            resource_type=ResourceType.welfare_recipient,
            action_type=ActionType.create
        )
        db_session.add(request)
        await db_session.commit()
        await db_session.refresh(request)

        original_updated_at = request.updated_at

        # 少し待ってから更新
        import asyncio
        await asyncio.sleep(0.01)

        request.status = RequestStatus.approved
        await db_session.commit()
        await db_session.refresh(request)

        # updated_atが更新されていることを確認
        assert request.updated_at >= original_updated_at

    @pytest.mark.asyncio
    async def test_employee_action_request_execution_result_storage(
        self,
        db_session: AsyncSession,
        employee_user_factory,
        office_factory
    ):
        """実行結果のJSON保存テスト"""
        employee = await employee_user_factory(with_office=False)
        office = await office_factory(creator=employee)

        request = EmployeeActionRequest(
            requester_staff_id=employee.id,
            office_id=office.id,
            resource_type=ResourceType.welfare_recipient,
            action_type=ActionType.create,
            status=RequestStatus.approved,
            execution_result={
                "success": True,
                "resource_id": str(uuid.uuid4()),
                "created_at": "2025-01-01T00:00:00Z",
                "message": "正常に作成されました"
            }
        )
        db_session.add(request)
        await db_session.commit()
        await db_session.refresh(request)

        # JSON形式で保存されていることを確認
        assert request.execution_result["success"] is True
        assert "resource_id" in request.execution_result
        assert request.execution_result["message"] == "正常に作成されました"
