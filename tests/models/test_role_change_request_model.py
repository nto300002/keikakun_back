"""
注意: このテストファイルは非推奨です。

旧テーブル (role_change_requests) は削除され、
統合approval_requestsテーブルに移行されました。

統合テーブルのテストは以下を参照:
- tests/crud/test_crud_approval_request.py
"""
import pytest
import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models.role_change_request import RoleChangeRequest
from app.models.enums import StaffRole, RequestStatus

pytestmark = pytest.mark.skip(reason="旧モデルテーブル(role_change_requests)は削除済み。統合ApprovalRequestを使用")


class TestRoleChangeRequestModel:
    """RoleChangeRequestモデルのテスト"""

    @pytest.mark.asyncio
    async def test_create_role_change_request(
        self,
        db_session: AsyncSession,
        employee_user_factory,
        office_factory
    ):
        """RoleChangeRequest作成の基本テスト"""
        # employeeユーザーを作成
        employee = await employee_user_factory(with_office=False)
        office = await office_factory(creator=employee)

        # role変更リクエストを作成（employee → manager）
        request = RoleChangeRequest(
            requester_staff_id=employee.id,
            office_id=office.id,
            from_role=StaffRole.employee,
            requested_role=StaffRole.manager,
            status=RequestStatus.pending,
            request_notes="マネージャーへの昇格を希望します"
        )
        db_session.add(request)
        await db_session.commit()
        await db_session.refresh(request)

        # 基本属性の確認
        assert request.id is not None
        assert request.requester_staff_id == employee.id
        assert request.office_id == office.id
        assert request.from_role == StaffRole.employee
        assert request.requested_role == StaffRole.manager
        assert request.status == RequestStatus.pending
        assert request.request_notes == "マネージャーへの昇格を希望します"
        assert request.created_at is not None
        assert request.updated_at is not None

    @pytest.mark.asyncio
    async def test_role_change_request_default_status(
        self,
        db_session: AsyncSession,
        employee_user_factory,
        office_factory
    ):
        """RoleChangeRequestのデフォルトステータスがpendingであることを確認"""
        employee = await employee_user_factory(with_office=False)
        office = await office_factory(creator=employee)

        request = RoleChangeRequest(
            requester_staff_id=employee.id,
            office_id=office.id,
            from_role=StaffRole.employee,
            requested_role=StaffRole.manager
        )
        db_session.add(request)
        await db_session.commit()
        await db_session.refresh(request)

        assert request.status == RequestStatus.pending
        assert request.reviewed_by_staff_id is None
        assert request.reviewed_at is None
        assert request.reviewer_notes is None

    @pytest.mark.asyncio
    async def test_role_change_request_approval(
        self,
        db_session: AsyncSession,
        employee_user_factory,
        manager_user_factory,
        office_factory
    ):
        """RoleChangeRequestの承認処理テスト"""
        employee = await employee_user_factory(with_office=False)
        office = await office_factory(creator=employee)
        manager = await manager_user_factory(office=office, with_office=True)

        # リクエスト作成
        request = RoleChangeRequest(
            requester_staff_id=employee.id,
            office_id=office.id,
            from_role=StaffRole.employee,
            requested_role=StaffRole.manager,
            status=RequestStatus.pending
        )
        db_session.add(request)
        await db_session.commit()

        # 承認処理
        request.status = RequestStatus.approved
        request.reviewed_by_staff_id = manager.id
        request.reviewed_at = datetime.now(timezone.utc)
        request.reviewer_notes = "承認しました"
        await db_session.commit()
        await db_session.refresh(request)

        # 承認後の状態確認
        assert request.status == RequestStatus.approved
        assert request.reviewed_by_staff_id == manager.id
        assert request.reviewed_at is not None
        assert request.reviewer_notes == "承認しました"

    @pytest.mark.asyncio
    async def test_role_change_request_rejection(
        self,
        db_session: AsyncSession,
        employee_user_factory,
        manager_user_factory,
        office_factory
    ):
        """RoleChangeRequestの却下処理テスト"""
        employee = await employee_user_factory(with_office=False)
        office = await office_factory(creator=employee)
        manager = await manager_user_factory(office=office, with_office=True)

        request = RoleChangeRequest(
            requester_staff_id=employee.id,
            office_id=office.id,
            from_role=StaffRole.employee,
            requested_role=StaffRole.owner,
            status=RequestStatus.pending
        )
        db_session.add(request)
        await db_session.commit()

        # 却下処理
        request.status = RequestStatus.rejected
        request.reviewed_by_staff_id = manager.id
        request.reviewed_at = datetime.now(timezone.utc)
        request.reviewer_notes = "現時点では承認できません"
        await db_session.commit()
        await db_session.refresh(request)

        assert request.status == RequestStatus.rejected
        assert request.reviewed_by_staff_id == manager.id
        assert request.reviewer_notes == "現時点では承認できません"

    @pytest.mark.asyncio
    async def test_role_change_request_foreign_key_staff(
        self,
        db_session: AsyncSession,
        office_factory,
        employee_user_factory
    ):
        """RoleChangeRequestのstaff外部キー制約テスト"""
        employee = await employee_user_factory(with_office=False)
        office = await office_factory(creator=employee)

        # 存在しないstaff_idを指定
        fake_staff_id = uuid.uuid4()

        request = RoleChangeRequest(
            requester_staff_id=fake_staff_id,
            office_id=office.id,
            from_role=StaffRole.employee,
            requested_role=StaffRole.manager
        )

        db_session.add(request)
        with pytest.raises(IntegrityError):
            await db_session.flush()

    @pytest.mark.asyncio
    async def test_role_change_request_foreign_key_office(
        self,
        db_session: AsyncSession,
        employee_user_factory
    ):
        """RoleChangeRequestのoffice外部キー制約テスト"""
        employee = await employee_user_factory(with_office=False)

        # 存在しないoffice_idを指定
        fake_office_id = uuid.uuid4()

        request = RoleChangeRequest(
            requester_staff_id=employee.id,
            office_id=fake_office_id,
            from_role=StaffRole.employee,
            requested_role=StaffRole.manager
        )

        db_session.add(request)
        with pytest.raises(IntegrityError):
            await db_session.flush()

    @pytest.mark.asyncio
    async def test_role_change_request_relationship_requester(
        self,
        db_session: AsyncSession,
        employee_user_factory,
        office_factory
    ):
        """RoleChangeRequestとRequester（Staff）のリレーションシップテスト"""
        employee = await employee_user_factory(with_office=False)
        office = await office_factory(creator=employee)

        request = RoleChangeRequest(
            requester_staff_id=employee.id,
            office_id=office.id,
            from_role=StaffRole.employee,
            requested_role=StaffRole.manager
        )
        db_session.add(request)
        await db_session.commit()

        # Eagerロードしてrelationshipを確認
        await db_session.refresh(request, ["requester"])

        assert request.requester is not None
        assert request.requester.id == employee.id
        assert request.requester.email == employee.email

    @pytest.mark.asyncio
    async def test_role_change_request_relationship_reviewer(
        self,
        db_session: AsyncSession,
        employee_user_factory,
        manager_user_factory,
        office_factory
    ):
        """RoleChangeRequestとReviewer（Staff）のリレーションシップテスト"""
        employee = await employee_user_factory(with_office=False)
        office = await office_factory(creator=employee)
        manager = await manager_user_factory(office=office, with_office=True)

        request = RoleChangeRequest(
            requester_staff_id=employee.id,
            office_id=office.id,
            from_role=StaffRole.employee,
            requested_role=StaffRole.manager,
            reviewed_by_staff_id=manager.id
        )
        db_session.add(request)
        await db_session.commit()

        # Eagerロードしてrelationshipを確認
        await db_session.refresh(request, ["reviewer"])

        assert request.reviewer is not None
        assert request.reviewer.id == manager.id
        assert request.reviewer.email == manager.email

    @pytest.mark.asyncio
    async def test_role_change_request_relationship_office(
        self,
        db_session: AsyncSession,
        employee_user_factory,
        office_factory
    ):
        """RoleChangeRequestとOfficeのリレーションシップテスト"""
        employee = await employee_user_factory(with_office=False)
        office = await office_factory(creator=employee)

        request = RoleChangeRequest(
            requester_staff_id=employee.id,
            office_id=office.id,
            from_role=StaffRole.employee,
            requested_role=StaffRole.manager
        )
        db_session.add(request)
        await db_session.commit()

        # Eagerロードしてrelationshipを確認
        await db_session.refresh(request, ["office"])

        assert request.office is not None
        assert request.office.id == office.id
        assert request.office.name == office.name

    @pytest.mark.asyncio
    async def test_role_change_request_updated_at_changes(
        self,
        db_session: AsyncSession,
        employee_user_factory,
        office_factory
    ):
        """RoleChangeRequest updated_at更新のテスト"""
        employee = await employee_user_factory(with_office=False)
        office = await office_factory(creator=employee)

        request = RoleChangeRequest(
            requester_staff_id=employee.id,
            office_id=office.id,
            from_role=StaffRole.employee,
            requested_role=StaffRole.manager
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
    async def test_role_change_request_manager_to_owner(
        self,
        db_session: AsyncSession,
        manager_user_factory,
        office_factory
    ):
        """Manager → Ownerへの変更リクエストテスト"""
        manager = await manager_user_factory(with_office=False)
        office = await office_factory(creator=manager)

        request = RoleChangeRequest(
            requester_staff_id=manager.id,
            office_id=office.id,
            from_role=StaffRole.manager,
            requested_role=StaffRole.owner,
            request_notes="オーナーへの昇格を希望します"
        )
        db_session.add(request)
        await db_session.commit()
        await db_session.refresh(request)

        assert request.from_role == StaffRole.manager
        assert request.requested_role == StaffRole.owner
        assert request.status == RequestStatus.pending

    @pytest.mark.asyncio
    async def test_role_change_request_manager_to_employee(
        self,
        db_session: AsyncSession,
        manager_user_factory,
        office_factory
    ):
        """Manager → Employeeへの変更リクエストテスト（降格）"""
        manager = await manager_user_factory(with_office=False)
        office = await office_factory(creator=manager)

        request = RoleChangeRequest(
            requester_staff_id=manager.id,
            office_id=office.id,
            from_role=StaffRole.manager,
            requested_role=StaffRole.employee,
            request_notes="従業員に戻りたいです"
        )
        db_session.add(request)
        await db_session.commit()
        await db_session.refresh(request)

        assert request.from_role == StaffRole.manager
        assert request.requested_role == StaffRole.employee
        assert request.status == RequestStatus.pending
