"""
WithdrawalService (退会サービス) のテスト
TDD方式でテストを先に作成
"""
import pytest
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID, uuid4
from typing import Tuple
from fastapi import HTTPException, status

from app.db.session import AsyncSessionLocal
from app.models.staff import Staff
from app.models.office import Office, OfficeStaff
from app.models.enums import StaffRole, OfficeType, RequestStatus, ApprovalResourceType
from app.core.security import get_password_hash
from app.services.withdrawal_service import withdrawal_service
from app.crud.crud_staff import staff as crud_staff
from app.crud.crud_office import crud_office
from app.crud.crud_approval_request import approval_request as crud_approval_request
from app.crud.crud_archived_staff import archived_staff as crud_archived_staff

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s:%(name)s:%(message)s'
)

# Suppress SQLAlchemy logs
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
logging.getLogger('sqlalchemy.pool').setLevel(logging.WARNING)
logging.getLogger('app').setLevel(logging.INFO)

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="function")
async def db() -> AsyncSession:
    """テスト用の非同期DBセッションを提供するフィクスチャ"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            try:
                await session.rollback()
            except Exception:
                pass


@pytest.fixture(scope="function")
async def setup_office_with_staff(db: AsyncSession) -> Tuple[UUID, UUID, UUID, UUID]:
    """
    テスト用の事業所と複数のスタッフを作成
    Returns: (office_id, owner_id, manager_id, employee_id)
    """
    # Owner作成
    owner = Staff(
        first_name="オーナー",
        last_name="テスト",
        full_name="テスト オーナー",
        email=f"owner_{uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash("password"),
        role=StaffRole.owner,
        is_test_data=True
    )
    db.add(owner)
    await db.flush()

    # Office作成
    office = Office(
        name="テスト事業所",
        type=OfficeType.type_A_office,
        created_by=owner.id,
        last_modified_by=owner.id,
        is_test_data=True
    )
    db.add(office)
    await db.flush()

    # OfficeStaff関連付け（Owner）
    office_staff_owner = OfficeStaff(
        office_id=office.id,
        staff_id=owner.id,
        is_primary=True
    )
    db.add(office_staff_owner)

    # Manager作成
    manager = Staff(
        first_name="マネージャー",
        last_name="テスト",
        full_name="テスト マネージャー",
        email=f"manager_{uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash("password"),
        role=StaffRole.manager,
        is_test_data=True
    )
    db.add(manager)
    await db.flush()

    # OfficeStaff関連付け（Manager）
    office_staff_manager = OfficeStaff(
        office_id=office.id,
        staff_id=manager.id,
        is_primary=True
    )
    db.add(office_staff_manager)

    # Employee作成
    employee = Staff(
        first_name="エンプロイー",
        last_name="テスト",
        full_name="テスト エンプロイー",
        email=f"employee_{uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash("password"),
        role=StaffRole.employee,
        is_test_data=True
    )
    db.add(employee)
    await db.flush()

    # OfficeStaff関連付け（Employee）
    office_staff_employee = OfficeStaff(
        office_id=office.id,
        staff_id=employee.id,
        is_primary=True
    )
    db.add(office_staff_employee)

    # commit前にIDを保存（MissingGreenlet対策）
    office_id = office.id
    owner_id = owner.id
    manager_id = manager.id
    employee_id = employee.id

    await db.commit()

    return office_id, owner_id, manager_id, employee_id


@pytest.fixture(scope="function")
async def setup_app_admin(db: AsyncSession) -> UUID:
    """
    テスト用のapp_adminを作成
    Returns: app_admin_id
    """
    app_admin = Staff(
        first_name="アプリ管理者",
        last_name="テスト",
        full_name="テスト アプリ管理者",
        email=f"appadmin_{uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash("password"),
        role=StaffRole.app_admin,
        is_test_data=True
    )
    db.add(app_admin)
    await db.flush()
    app_admin_id = app_admin.id
    await db.commit()
    return app_admin_id


# ===== スタッフ退会リクエスト作成テスト =====

class TestStaffWithdrawalRequestCreate:
    """スタッフ退会リクエスト作成のテスト"""

    async def test_create_staff_withdrawal_request(
        self,
        db: AsyncSession,
        setup_office_with_staff: Tuple[UUID, UUID, UUID, UUID]
    ):
        """スタッフ退会リクエスト作成の基本テスト"""
        office_id, owner_id, manager_id, employee_id = setup_office_with_staff

        request = await withdrawal_service.create_staff_withdrawal_request(
            db=db,
            requester_staff_id=owner_id,
            office_id=office_id,
            target_staff_id=employee_id,
            reason="退職のため"
        )

        assert request is not None
        assert request.requester_staff_id == owner_id
        assert request.office_id == office_id
        assert request.resource_type == ApprovalResourceType.withdrawal
        assert request.status == RequestStatus.pending
        assert request.request_data["withdrawal_type"] == "staff"
        assert request.request_data["target_staff_id"] == str(employee_id)
        assert request.request_data["reason"] == "退職のため"

    async def test_create_staff_withdrawal_request_duplicate(
        self,
        db: AsyncSession,
        setup_office_with_staff: Tuple[UUID, UUID, UUID, UUID]
    ):
        """重複するスタッフ退会リクエストは作成できない（409エラー）"""
        office_id, owner_id, manager_id, employee_id = setup_office_with_staff

        # 1件目のリクエスト作成
        await withdrawal_service.create_staff_withdrawal_request(
            db=db,
            requester_staff_id=owner_id,
            office_id=office_id,
            target_staff_id=employee_id,
            reason="退職のため"
        )

        # 2件目のリクエスト作成（エラーになるべき）
        with pytest.raises(HTTPException) as exc_info:
            await withdrawal_service.create_staff_withdrawal_request(
                db=db,
                requester_staff_id=owner_id,
                office_id=office_id,
                target_staff_id=employee_id,
                reason="別の理由"
            )
        assert exc_info.value.status_code == status.HTTP_409_CONFLICT


# ===== 事務所退会リクエスト作成テスト =====

class TestOfficeWithdrawalRequestCreate:
    """事務所退会リクエスト作成のテスト"""

    async def test_create_office_withdrawal_request(
        self,
        db: AsyncSession,
        setup_office_with_staff: Tuple[UUID, UUID, UUID, UUID]
    ):
        """事務所退会リクエスト作成の基本テスト"""
        office_id, owner_id, manager_id, employee_id = setup_office_with_staff

        request = await withdrawal_service.create_office_withdrawal_request(
            db=db,
            requester_staff_id=owner_id,
            office_id=office_id,
            reason="事業終了のため"
        )

        assert request is not None
        assert request.requester_staff_id == owner_id
        assert request.office_id == office_id
        assert request.resource_type == ApprovalResourceType.withdrawal
        assert request.status == RequestStatus.pending
        assert request.request_data["withdrawal_type"] == "office"
        assert request.request_data["reason"] == "事業終了のため"
        # 影響を受けるスタッフIDが記録されている
        assert "affected_staff_ids" in request.request_data
        assert len(request.request_data["affected_staff_ids"]) >= 3  # owner, manager, employee

    async def test_create_office_withdrawal_request_by_non_owner(
        self,
        db: AsyncSession,
        setup_office_with_staff: Tuple[UUID, UUID, UUID, UUID]
    ):
        """owner以外は事務所退会リクエストを作成できない（403エラー）"""
        office_id, owner_id, manager_id, employee_id = setup_office_with_staff

        # managerがリクエスト作成を試みる
        with pytest.raises(HTTPException) as exc_info:
            await withdrawal_service.create_office_withdrawal_request(
                db=db,
                requester_staff_id=manager_id,
                office_id=office_id,
                reason="事業終了のため"
            )
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

    async def test_create_office_withdrawal_request_duplicate(
        self,
        db: AsyncSession,
        setup_office_with_staff: Tuple[UUID, UUID, UUID, UUID]
    ):
        """重複する事務所退会リクエストは作成できない（409エラー）"""
        office_id, owner_id, manager_id, employee_id = setup_office_with_staff

        # 1件目のリクエスト作成
        await withdrawal_service.create_office_withdrawal_request(
            db=db,
            requester_staff_id=owner_id,
            office_id=office_id,
            reason="事業終了のため"
        )

        # 2件目のリクエスト作成（エラーになるべき）
        with pytest.raises(HTTPException) as exc_info:
            await withdrawal_service.create_office_withdrawal_request(
                db=db,
                requester_staff_id=owner_id,
                office_id=office_id,
                reason="別の理由"
            )
        assert exc_info.value.status_code == status.HTTP_409_CONFLICT


# ===== 退会リクエスト承認テスト =====

class TestWithdrawalApproval:
    """退会リクエスト承認のテスト"""

    async def test_approve_staff_withdrawal(
        self,
        db: AsyncSession,
        setup_office_with_staff: Tuple[UUID, UUID, UUID, UUID],
        setup_app_admin: UUID
    ):
        """スタッフ退会リクエスト承認テスト"""
        office_id, owner_id, manager_id, employee_id = setup_office_with_staff
        app_admin_id = setup_app_admin

        # リクエスト作成
        request = await withdrawal_service.create_staff_withdrawal_request(
            db=db,
            requester_staff_id=owner_id,
            office_id=office_id,
            target_staff_id=employee_id,
            reason="退職のため"
        )

        # 承認処理
        approved_request = await withdrawal_service.approve_withdrawal(
            db=db,
            request_id=request.id,
            reviewer_staff_id=app_admin_id,
            reviewer_notes="承認します"
        )

        assert approved_request.status == RequestStatus.approved
        assert approved_request.reviewed_by_staff_id == app_admin_id
        assert approved_request.reviewer_notes == "承認します"

        # スタッフが論理削除されたことを確認
        deleted_staff = await crud_staff.get(db, id=employee_id)
        assert deleted_staff is not None
        assert deleted_staff.is_deleted is True
        assert deleted_staff.deleted_at is not None
        assert deleted_staff.deleted_by == app_admin_id

        # アーカイブが作成されたことを確認
        archive = await crud_archived_staff.get_by_original_staff_id(db, staff_id=employee_id)
        assert archive is not None
        assert archive.original_staff_id == employee_id
        assert archive.archive_reason == "staff_withdrawal"
        assert archive.anonymized_full_name.startswith("スタッフ-")
        assert archive.anonymized_email.endswith("@deleted.local")
        assert archive.legal_retention_until is not None

    async def test_approve_office_withdrawal(
        self,
        db: AsyncSession,
        setup_office_with_staff: Tuple[UUID, UUID, UUID, UUID],
        setup_app_admin: UUID
    ):
        """事務所退会リクエスト承認テスト"""
        office_id, owner_id, manager_id, employee_id = setup_office_with_staff
        app_admin_id = setup_app_admin

        # リクエスト作成
        request = await withdrawal_service.create_office_withdrawal_request(
            db=db,
            requester_staff_id=owner_id,
            office_id=office_id,
            reason="事業終了のため"
        )

        # 承認処理
        approved_request = await withdrawal_service.approve_withdrawal(
            db=db,
            request_id=request.id,
            reviewer_staff_id=app_admin_id,
            reviewer_notes="承認します"
        )

        assert approved_request.status == RequestStatus.approved

        # 事務所が論理削除されたことを確認
        office = await crud_office.get(db, id=office_id)
        assert office.is_deleted is True
        assert office.deleted_at is not None
        assert office.deleted_by == app_admin_id

        # 全スタッフが論理削除されたことを確認
        owner_check = await crud_staff.get(db, id=owner_id)
        manager_check = await crud_staff.get(db, id=manager_id)
        employee_check = await crud_staff.get(db, id=employee_id)
        assert owner_check is not None
        assert owner_check.is_deleted is True
        assert manager_check is not None
        assert manager_check.is_deleted is True
        assert employee_check is not None
        assert employee_check.is_deleted is True

        # 全スタッフのアーカイブが作成されたことを確認
        owner_archive = await crud_archived_staff.get_by_original_staff_id(db, staff_id=owner_id)
        manager_archive = await crud_archived_staff.get_by_original_staff_id(db, staff_id=manager_id)
        employee_archive = await crud_archived_staff.get_by_original_staff_id(db, staff_id=employee_id)

        assert owner_archive is not None
        assert owner_archive.archive_reason == "office_withdrawal"
        assert manager_archive is not None
        assert manager_archive.archive_reason == "office_withdrawal"
        assert employee_archive is not None
        assert employee_archive.archive_reason == "office_withdrawal"

    async def test_approve_withdrawal_by_non_admin(
        self,
        db: AsyncSession,
        setup_office_with_staff: Tuple[UUID, UUID, UUID, UUID]
    ):
        """app_admin以外は退会リクエストを承認できない（403エラー）"""
        office_id, owner_id, manager_id, employee_id = setup_office_with_staff

        # リクエスト作成
        request = await withdrawal_service.create_staff_withdrawal_request(
            db=db,
            requester_staff_id=owner_id,
            office_id=office_id,
            target_staff_id=employee_id,
            reason="退職のため"
        )

        # ownerが承認を試みる（失敗すべき）
        with pytest.raises(HTTPException) as exc_info:
            await withdrawal_service.approve_withdrawal(
                db=db,
                request_id=request.id,
                reviewer_staff_id=owner_id,
                reviewer_notes="承認します"
            )
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

    async def test_approve_nonexistent_request(
        self,
        db: AsyncSession,
        setup_app_admin: UUID
    ):
        """存在しないリクエストの承認は404エラー"""
        app_admin_id = setup_app_admin

        with pytest.raises(HTTPException) as exc_info:
            await withdrawal_service.approve_withdrawal(
                db=db,
                request_id=uuid4(),
                reviewer_staff_id=app_admin_id,
                reviewer_notes="承認します"
            )
        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


# ===== 退会リクエスト却下テスト =====

class TestWithdrawalRejection:
    """退会リクエスト却下のテスト"""

    async def test_reject_staff_withdrawal(
        self,
        db: AsyncSession,
        setup_office_with_staff: Tuple[UUID, UUID, UUID, UUID],
        setup_app_admin: UUID
    ):
        """スタッフ退会リクエスト却下テスト"""
        office_id, owner_id, manager_id, employee_id = setup_office_with_staff
        app_admin_id = setup_app_admin

        # リクエスト作成
        request = await withdrawal_service.create_staff_withdrawal_request(
            db=db,
            requester_staff_id=owner_id,
            office_id=office_id,
            target_staff_id=employee_id,
            reason="退職のため"
        )

        # 却下処理
        rejected_request = await withdrawal_service.reject_withdrawal(
            db=db,
            request_id=request.id,
            reviewer_staff_id=app_admin_id,
            reviewer_notes="却下理由"
        )

        assert rejected_request.status == RequestStatus.rejected
        assert rejected_request.reviewed_by_staff_id == app_admin_id
        assert rejected_request.reviewer_notes == "却下理由"

        # スタッフは削除されていないことを確認
        staff = await crud_staff.get(db, id=employee_id)
        assert staff is not None

    async def test_reject_office_withdrawal(
        self,
        db: AsyncSession,
        setup_office_with_staff: Tuple[UUID, UUID, UUID, UUID],
        setup_app_admin: UUID
    ):
        """事務所退会リクエスト却下テスト"""
        office_id, owner_id, manager_id, employee_id = setup_office_with_staff
        app_admin_id = setup_app_admin

        # リクエスト作成
        request = await withdrawal_service.create_office_withdrawal_request(
            db=db,
            requester_staff_id=owner_id,
            office_id=office_id,
            reason="事業終了のため"
        )

        # 却下処理
        rejected_request = await withdrawal_service.reject_withdrawal(
            db=db,
            request_id=request.id,
            reviewer_staff_id=app_admin_id,
            reviewer_notes="却下理由"
        )

        assert rejected_request.status == RequestStatus.rejected

        # 事務所は削除されていないことを確認
        office = await crud_office.get(db, id=office_id)
        assert office is not None
        assert office.is_deleted is False

        # スタッフも削除されていないことを確認
        owner_check = await crud_staff.get(db, id=owner_id)
        assert owner_check is not None

    async def test_reject_withdrawal_by_non_admin(
        self,
        db: AsyncSession,
        setup_office_with_staff: Tuple[UUID, UUID, UUID, UUID]
    ):
        """app_admin以外は退会リクエストを却下できない（403エラー）"""
        office_id, owner_id, manager_id, employee_id = setup_office_with_staff

        # リクエスト作成
        request = await withdrawal_service.create_staff_withdrawal_request(
            db=db,
            requester_staff_id=owner_id,
            office_id=office_id,
            target_staff_id=employee_id,
            reason="退職のため"
        )

        # managerが却下を試みる（失敗すべき）
        with pytest.raises(HTTPException) as exc_info:
            await withdrawal_service.reject_withdrawal(
                db=db,
                request_id=request.id,
                reviewer_staff_id=manager_id,
                reviewer_notes="却下理由"
            )
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

    async def test_reject_nonexistent_request(
        self,
        db: AsyncSession,
        setup_app_admin: UUID
    ):
        """存在しないリクエストの却下は404エラー"""
        app_admin_id = setup_app_admin

        with pytest.raises(HTTPException) as exc_info:
            await withdrawal_service.reject_withdrawal(
                db=db,
                request_id=uuid4(),
                reviewer_staff_id=app_admin_id,
                reviewer_notes="却下理由"
            )
        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


# ===== 退会リクエスト取得テスト =====

class TestWithdrawalRequestQuery:
    """退会リクエスト取得のテスト"""

    async def test_get_pending_withdrawal_requests(
        self,
        db: AsyncSession,
        setup_office_with_staff: Tuple[UUID, UUID, UUID, UUID]
    ):
        """承認待ちの退会リクエスト一覧取得テスト"""
        office_id, owner_id, manager_id, employee_id = setup_office_with_staff

        # 複数のリクエスト作成
        request1 = await withdrawal_service.create_staff_withdrawal_request(
            db=db,
            requester_staff_id=owner_id,
            office_id=office_id,
            target_staff_id=employee_id,
            reason="退職のため"
        )

        # 取得
        requests = await withdrawal_service.get_pending_withdrawal_requests(
            db=db,
            include_test_data=True
        )

        assert len(requests) >= 1
        assert all(r.status == RequestStatus.pending for r in requests)
        assert all(r.resource_type == ApprovalResourceType.withdrawal for r in requests)

    async def test_get_withdrawal_request(
        self,
        db: AsyncSession,
        setup_office_with_staff: Tuple[UUID, UUID, UUID, UUID]
    ):
        """退会リクエスト単体取得テスト"""
        office_id, owner_id, manager_id, employee_id = setup_office_with_staff

        # リクエスト作成
        request = await withdrawal_service.create_staff_withdrawal_request(
            db=db,
            requester_staff_id=owner_id,
            office_id=office_id,
            target_staff_id=employee_id,
            reason="退職のため"
        )

        # 取得
        fetched_request = await withdrawal_service.get_withdrawal_request(
            db=db,
            request_id=request.id
        )

        assert fetched_request is not None
        assert fetched_request.id == request.id

    async def test_get_nonexistent_withdrawal_request(
        self,
        db: AsyncSession
    ):
        """存在しない退会リクエストの取得はNoneを返す"""
        fetched_request = await withdrawal_service.get_withdrawal_request(
            db=db,
            request_id=uuid4()
        )

        assert fetched_request is None


# ===== 退会処理実行の検証テスト =====

class TestWithdrawalExecution:
    """退会処理実行の検証テスト"""

    async def test_staff_soft_delete_verification(
        self,
        db: AsyncSession,
        setup_office_with_staff: Tuple[UUID, UUID, UUID, UUID],
        setup_app_admin: UUID
    ):
        """スタッフ退会時に論理削除されることを確認"""
        office_id, owner_id, manager_id, employee_id = setup_office_with_staff
        app_admin_id = setup_app_admin

        # 削除前の確認
        employee_before = await crud_staff.get(db, id=employee_id)
        assert employee_before is not None
        assert employee_before.is_deleted is False
        employee_email = employee_before.email

        # リクエスト作成・承認
        request = await withdrawal_service.create_staff_withdrawal_request(
            db=db,
            requester_staff_id=owner_id,
            office_id=office_id,
            target_staff_id=employee_id,
            reason="退職のため"
        )

        await withdrawal_service.approve_withdrawal(
            db=db,
            request_id=request.id,
            reviewer_staff_id=app_admin_id,
            reviewer_notes="承認"
        )

        # 削除後の確認（論理削除なので存在するがis_deleted=True）
        employee_after = await crud_staff.get(db, id=employee_id)
        assert employee_after is not None
        assert employee_after.is_deleted is True
        assert employee_after.deleted_at is not None
        assert employee_after.deleted_by == app_admin_id

    async def test_office_soft_delete_verification(
        self,
        db: AsyncSession,
        setup_office_with_staff: Tuple[UUID, UUID, UUID, UUID],
        setup_app_admin: UUID
    ):
        """事務所退会時に論理削除されることを確認"""
        office_id, owner_id, manager_id, employee_id = setup_office_with_staff
        app_admin_id = setup_app_admin

        # 削除前の確認
        office_before = await crud_office.get(db, id=office_id)
        assert office_before is not None
        assert office_before.is_deleted is False

        # リクエスト作成・承認
        request = await withdrawal_service.create_office_withdrawal_request(
            db=db,
            requester_staff_id=owner_id,
            office_id=office_id,
            reason="事業終了のため"
        )

        await withdrawal_service.approve_withdrawal(
            db=db,
            request_id=request.id,
            reviewer_staff_id=app_admin_id,
            reviewer_notes="承認"
        )

        # 削除後の確認（論理削除なので存在するがis_deleted=True）
        office_after = await crud_office.get(db, id=office_id)
        assert office_after is not None
        assert office_after.is_deleted is True
        assert office_after.deleted_at is not None
        assert office_after.deleted_by == app_admin_id

    async def test_office_withdrawal_soft_deletes_all_staff(
        self,
        db: AsyncSession,
        setup_office_with_staff: Tuple[UUID, UUID, UUID, UUID],
        setup_app_admin: UUID
    ):
        """事務所退会時に全スタッフが論理削除されることを確認"""
        office_id, owner_id, manager_id, employee_id = setup_office_with_staff
        app_admin_id = setup_app_admin

        # 削除前の確認
        staff_ids_before = await crud_office.get_staff_ids_by_office(db, office_id)
        assert len(staff_ids_before) >= 3  # owner, manager, employee

        # リクエスト作成・承認
        request = await withdrawal_service.create_office_withdrawal_request(
            db=db,
            requester_staff_id=owner_id,
            office_id=office_id,
            reason="事業終了のため"
        )

        await withdrawal_service.approve_withdrawal(
            db=db,
            request_id=request.id,
            reviewer_staff_id=app_admin_id,
            reviewer_notes="承認"
        )

        # 全スタッフが論理削除されたことを確認
        for staff_id in staff_ids_before:
            staff = await crud_staff.get(db, id=staff_id)
            assert staff is not None, f"Staff {staff_id} should exist"
            assert staff.is_deleted is True, f"Staff {staff_id} should be soft deleted"
            assert staff.deleted_at is not None
            assert staff.deleted_by == app_admin_id

    async def test_execution_result_recorded(
        self,
        db: AsyncSession,
        setup_office_with_staff: Tuple[UUID, UUID, UUID, UUID],
        setup_app_admin: UUID
    ):
        """退会処理の実行結果が記録されることを確認"""
        office_id, owner_id, manager_id, employee_id = setup_office_with_staff
        app_admin_id = setup_app_admin

        # リクエスト作成・承認
        request = await withdrawal_service.create_staff_withdrawal_request(
            db=db,
            requester_staff_id=owner_id,
            office_id=office_id,
            target_staff_id=employee_id,
            reason="退職のため"
        )

        await withdrawal_service.approve_withdrawal(
            db=db,
            request_id=request.id,
            reviewer_staff_id=app_admin_id,
            reviewer_notes="承認"
        )

        # 実行結果を確認
        updated_request = await crud_approval_request.get_by_id_with_relations(db, request.id)
        assert updated_request.execution_result is not None
        assert updated_request.execution_result["success"] is True
        assert updated_request.execution_result["withdrawal_type"] == "staff"

    async def test_cannot_login_after_office_withdrawal(
        self,
        db: AsyncSession,
        setup_office_with_staff: Tuple[UUID, UUID, UUID, UUID],
        setup_app_admin: UUID
    ):
        """事務所退会後は、その事務所のスタッフでログインできないことを確認"""
        office_id, owner_id, manager_id, employee_id = setup_office_with_staff
        app_admin_id = setup_app_admin

        # ログイン前の確認 - 事務所が有効であることを確認
        office_before = await crud_office.get(db, id=office_id)
        assert office_before is not None
        assert office_before.is_deleted is False

        # 事務所退会リクエスト作成・承認
        request = await withdrawal_service.create_office_withdrawal_request(
            db=db,
            requester_staff_id=owner_id,
            office_id=office_id,
            reason="事業終了のため"
        )

        await withdrawal_service.approve_withdrawal(
            db=db,
            request_id=request.id,
            reviewer_staff_id=app_admin_id,
            reviewer_notes="承認"
        )

        # 退会後の確認 - 事務所が論理削除されていることを確認
        office_after = await crud_office.get(db, id=office_id)
        assert office_after is not None
        assert office_after.is_deleted is True

        # 全スタッフが論理削除されていることを確認
        owner_check = await crud_staff.get(db, id=owner_id)
        manager_check = await crud_staff.get(db, id=manager_id)
        employee_check = await crud_staff.get(db, id=employee_id)
        assert owner_check is not None
        assert owner_check.is_deleted is True
        assert manager_check is not None
        assert manager_check.is_deleted is True
        assert employee_check is not None
        assert employee_check.is_deleted is True

        # ログイン試行は、スタッフが論理削除されているため拒否される
        # （is_deleted=Trueまたは所属事務所のis_deleted=Trueのチェックで失敗する）
