"""
ApprovalRequest (統合型承認リクエスト) CRUDのテスト
TDD方式でテストを先に作成
"""
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
import pytest

from app.crud.crud_approval_request import approval_request as crud_approval_request
from app.models.enums import ApprovalResourceType, RequestStatus

pytestmark = pytest.mark.asyncio


class TestApprovalRequestCreate:
    """承認リクエスト作成のテスト"""

    async def test_create_withdrawal_request_staff(
        self,
        db_session: AsyncSession,
        owner_user_factory,
        employee_user_factory,
    ) -> None:
        """
        スタッフ退会リクエスト作成テスト
        """
        owner = await owner_user_factory()
        office = owner.office_associations[0].office
        employee = await employee_user_factory(office=office)

        # スタッフ退会リクエスト作成
        request = await crud_approval_request.create_withdrawal_request(
            db=db_session,
            requester_staff_id=owner.id,
            office_id=office.id,
            withdrawal_type="staff",
            reason="退職のため",
            target_staff_id=employee.id,
            is_test_data=True
        )

        assert request.id is not None
        assert request.requester_staff_id == owner.id
        assert request.office_id == office.id
        assert request.resource_type == ApprovalResourceType.withdrawal
        assert request.status == RequestStatus.pending
        assert request.request_data["withdrawal_type"] == "staff"
        assert request.request_data["target_staff_id"] == str(employee.id)
        assert request.request_data["reason"] == "退職のため"

    async def test_create_withdrawal_request_office(
        self,
        db_session: AsyncSession,
        owner_user_factory,
    ) -> None:
        """
        事務所退会リクエスト作成テスト
        """
        owner = await owner_user_factory()
        office = owner.office_associations[0].office

        # 事務所退会リクエスト作成
        request = await crud_approval_request.create_withdrawal_request(
            db=db_session,
            requester_staff_id=owner.id,
            office_id=office.id,
            withdrawal_type="office",
            reason="事業終了のため",
            affected_staff_ids=[owner.id],
            is_test_data=True
        )

        assert request.id is not None
        assert request.resource_type == ApprovalResourceType.withdrawal
        assert request.request_data["withdrawal_type"] == "office"
        assert request.request_data["reason"] == "事業終了のため"
        assert str(owner.id) in request.request_data["affected_staff_ids"]

    async def test_create_generic_request(
        self,
        db_session: AsyncSession,
        employee_user_factory,
    ) -> None:
        """
        汎用的な承認リクエスト作成テスト（role_change）
        """
        employee = await employee_user_factory()
        office = employee.office_associations[0].office

        # ロール変更リクエスト作成
        request = await crud_approval_request.create_request(
            db=db_session,
            requester_staff_id=employee.id,
            office_id=office.id,
            resource_type=ApprovalResourceType.role_change,
            request_data={
                "from_role": "employee",
                "requested_role": "manager",
                "request_notes": "昇格希望"
            },
            is_test_data=True
        )

        assert request.id is not None
        assert request.resource_type == ApprovalResourceType.role_change
        assert request.status == RequestStatus.pending
        assert request.request_data["from_role"] == "employee"


class TestApprovalRequestQuery:
    """承認リクエスト取得のテスト"""

    async def test_get_pending_requests(
        self,
        db_session: AsyncSession,
        owner_user_factory,
        employee_user_factory,
    ) -> None:
        """
        承認待ちリクエスト一覧取得テスト
        """
        owner = await owner_user_factory()
        office = owner.office_associations[0].office
        employee = await employee_user_factory(office=office)

        # リクエスト作成
        await crud_approval_request.create_withdrawal_request(
            db=db_session,
            requester_staff_id=owner.id,
            office_id=office.id,
            withdrawal_type="staff",
            target_staff_id=employee.id,
            is_test_data=True
        )

        # 承認待ちリクエスト取得
        requests = await crud_approval_request.get_pending_requests(
            db=db_session,
            office_id=office.id,
            include_test_data=True
        )

        assert len(requests) >= 1
        assert all(r.status == RequestStatus.pending for r in requests)
        assert all(r.office_id == office.id for r in requests)

    async def test_get_pending_withdrawal_requests(
        self,
        db_session: AsyncSession,
        owner_user_factory,
    ) -> None:
        """
        承認待ちの退会リクエスト一覧取得テスト（app_admin用）
        """
        owner = await owner_user_factory()
        office = owner.office_associations[0].office

        # 退会リクエスト作成
        await crud_approval_request.create_withdrawal_request(
            db=db_session,
            requester_staff_id=owner.id,
            office_id=office.id,
            withdrawal_type="office",
            is_test_data=True
        )

        # 退会リクエストのみ取得
        requests = await crud_approval_request.get_pending_withdrawal_requests(
            db=db_session,
            include_test_data=True
        )

        assert len(requests) >= 1
        assert all(r.resource_type == ApprovalResourceType.withdrawal for r in requests)

    async def test_get_by_requester(
        self,
        db_session: AsyncSession,
        owner_user_factory,
    ) -> None:
        """
        リクエスト作成者でリクエスト一覧を取得するテスト
        """
        owner = await owner_user_factory()
        office = owner.office_associations[0].office

        # 複数のリクエスト作成
        await crud_approval_request.create_request(
            db=db_session,
            requester_staff_id=owner.id,
            office_id=office.id,
            resource_type=ApprovalResourceType.role_change,
            is_test_data=True
        )

        await crud_approval_request.create_withdrawal_request(
            db=db_session,
            requester_staff_id=owner.id,
            office_id=office.id,
            withdrawal_type="office",
            is_test_data=True
        )

        # 作成者でフィルタ
        requests = await crud_approval_request.get_by_requester(
            db=db_session,
            requester_staff_id=owner.id,
            include_test_data=True
        )

        assert len(requests) >= 2
        assert all(r.requester_staff_id == owner.id for r in requests)

    async def test_get_by_office_with_pagination(
        self,
        db_session: AsyncSession,
        owner_user_factory,
    ) -> None:
        """
        事務所でリクエスト一覧を取得（ページネーション付き）テスト
        """
        owner = await owner_user_factory()
        office = owner.office_associations[0].office

        # 3件のリクエスト作成
        for i in range(3):
            await crud_approval_request.create_request(
                db=db_session,
                requester_staff_id=owner.id,
                office_id=office.id,
                resource_type=ApprovalResourceType.role_change,
                request_data={"index": i},
                is_test_data=True
            )

        # 1ページ目
        requests, total = await crud_approval_request.get_by_office(
            db=db_session,
            office_id=office.id,
            skip=0,
            limit=2,
            include_test_data=True
        )

        assert len(requests) == 2
        assert total >= 3


class TestApprovalRequestApproveReject:
    """承認・却下処理のテスト"""

    async def test_approve_request(
        self,
        db_session: AsyncSession,
        owner_user_factory,
        app_admin_user_factory,
    ) -> None:
        """
        リクエスト承認テスト
        """
        owner = await owner_user_factory()
        office = owner.office_associations[0].office
        app_admin = await app_admin_user_factory()

        # リクエスト作成
        request = await crud_approval_request.create_withdrawal_request(
            db=db_session,
            requester_staff_id=owner.id,
            office_id=office.id,
            withdrawal_type="office",
            is_test_data=True
        )

        assert request.status == RequestStatus.pending

        # 承認
        approved = await crud_approval_request.approve(
            db=db_session,
            request_id=request.id,
            reviewer_staff_id=app_admin.id,
            reviewer_notes="承認します"
        )

        assert approved.status == RequestStatus.approved
        assert approved.reviewed_by_staff_id == app_admin.id
        assert approved.reviewed_at is not None
        assert approved.reviewer_notes == "承認します"

    async def test_reject_request(
        self,
        db_session: AsyncSession,
        owner_user_factory,
        app_admin_user_factory,
    ) -> None:
        """
        リクエスト却下テスト
        """
        owner = await owner_user_factory()
        office = owner.office_associations[0].office
        app_admin = await app_admin_user_factory()

        # リクエスト作成
        request = await crud_approval_request.create_withdrawal_request(
            db=db_session,
            requester_staff_id=owner.id,
            office_id=office.id,
            withdrawal_type="office",
            is_test_data=True
        )

        # 却下
        rejected = await crud_approval_request.reject(
            db=db_session,
            request_id=request.id,
            reviewer_staff_id=app_admin.id,
            reviewer_notes="却下理由"
        )

        assert rejected.status == RequestStatus.rejected
        assert rejected.reviewed_by_staff_id == app_admin.id
        assert rejected.reviewer_notes == "却下理由"

    async def test_cannot_approve_already_processed(
        self,
        db_session: AsyncSession,
        owner_user_factory,
        app_admin_user_factory,
    ) -> None:
        """
        既に処理済みのリクエストは承認できないことを確認するテスト
        """
        owner = await owner_user_factory()
        office = owner.office_associations[0].office
        app_admin = await app_admin_user_factory()

        # リクエスト作成
        request = await crud_approval_request.create_withdrawal_request(
            db=db_session,
            requester_staff_id=owner.id,
            office_id=office.id,
            withdrawal_type="office",
            is_test_data=True
        )

        # 1回目の承認
        await crud_approval_request.approve(
            db=db_session,
            request_id=request.id,
            reviewer_staff_id=app_admin.id
        )

        # 2回目の承認（エラーになるべき）
        with pytest.raises(Exception):
            await crud_approval_request.approve(
                db=db_session,
                request_id=request.id,
                reviewer_staff_id=app_admin.id
            )


class TestApprovalRequestExecution:
    """実行結果設定のテスト"""

    async def test_set_execution_result(
        self,
        db_session: AsyncSession,
        owner_user_factory,
        app_admin_user_factory,
    ) -> None:
        """
        実行結果を設定するテスト
        """
        owner = await owner_user_factory()
        office = owner.office_associations[0].office
        app_admin = await app_admin_user_factory()

        # リクエスト作成
        request = await crud_approval_request.create_withdrawal_request(
            db=db_session,
            requester_staff_id=owner.id,
            office_id=office.id,
            withdrawal_type="office",
            is_test_data=True
        )

        # 承認
        await crud_approval_request.approve(
            db=db_session,
            request_id=request.id,
            reviewer_staff_id=app_admin.id
        )

        # 実行結果を設定
        execution_result = {
            "success": True,
            "withdrawal_type": "office",
            "deleted_staff_count": 3
        }

        updated = await crud_approval_request.set_execution_result(
            db=db_session,
            request_id=request.id,
            execution_result=execution_result
        )

        assert updated.execution_result["success"] is True
        assert updated.execution_result["deleted_staff_count"] == 3


class TestApprovalRequestDuplicateCheck:
    """重複チェックのテスト"""

    async def test_has_pending_withdrawal_staff(
        self,
        db_session: AsyncSession,
        owner_user_factory,
        employee_user_factory,
    ) -> None:
        """
        スタッフ退会リクエストの重複チェックテスト
        """
        owner = await owner_user_factory()
        office = owner.office_associations[0].office
        employee = await employee_user_factory(office=office)

        # 最初は存在しない
        has_pending = await crud_approval_request.has_pending_withdrawal(
            db=db_session,
            office_id=office.id,
            withdrawal_type="staff",
            target_staff_id=employee.id
        )
        assert has_pending is False

        # リクエスト作成
        await crud_approval_request.create_withdrawal_request(
            db=db_session,
            requester_staff_id=owner.id,
            office_id=office.id,
            withdrawal_type="staff",
            target_staff_id=employee.id,
            is_test_data=True
        )

        # 作成後は存在する
        has_pending = await crud_approval_request.has_pending_withdrawal(
            db=db_session,
            office_id=office.id,
            withdrawal_type="staff",
            target_staff_id=employee.id
        )
        assert has_pending is True

    async def test_has_pending_withdrawal_office(
        self,
        db_session: AsyncSession,
        owner_user_factory,
    ) -> None:
        """
        事務所退会リクエストの重複チェックテスト
        """
        owner = await owner_user_factory()
        office = owner.office_associations[0].office

        # 最初は存在しない
        has_pending = await crud_approval_request.has_pending_withdrawal(
            db=db_session,
            office_id=office.id,
            withdrawal_type="office"
        )
        assert has_pending is False

        # リクエスト作成
        await crud_approval_request.create_withdrawal_request(
            db=db_session,
            requester_staff_id=owner.id,
            office_id=office.id,
            withdrawal_type="office",
            is_test_data=True
        )

        # 作成後は存在する
        has_pending = await crud_approval_request.has_pending_withdrawal(
            db=db_session,
            office_id=office.id,
            withdrawal_type="office"
        )
        assert has_pending is True
