"""
RoleChangeRequest (Role変更リクエスト) CRUDのテスト
TDD方式でテストを先に作成
"""
from sqlalchemy.ext.asyncio import AsyncSession
import pytest
from datetime import datetime, timezone

from app import crud
from app.models.enums import StaffRole, RequestStatus
from app.schemas.role_change_request import RoleChangeRequestCreate

pytestmark = pytest.mark.asyncio


async def test_create_role_change_request(
    db_session: AsyncSession,
    employee_user_factory,
    office_factory
) -> None:
    """
    Role変更リクエスト作成テスト
    """
    employee = await employee_user_factory()
    office = employee.office_associations[0].office

    # リクエストデータ（employee → manager）
    request_data = RoleChangeRequestCreate(
        requested_role=StaffRole.manager,
        request_notes="マネージャーへの昇格を希望します"
    )

    # リクエスト作成（from_roleとoffice_idは手動で追加）
    created_request = await crud.role_change_request.create(
        db=db_session,
        obj_in=request_data,
        requester_staff_id=employee.id,
        office_id=office.id,
        from_role=employee.role
    )

    assert created_request.id is not None
    assert created_request.requester_staff_id == employee.id
    assert created_request.office_id == office.id
    assert created_request.from_role == StaffRole.employee
    assert created_request.requested_role == StaffRole.manager
    assert created_request.status == RequestStatus.pending
    assert created_request.request_notes == "マネージャーへの昇格を希望します"


async def test_get_role_change_request_by_id(
    db_session: AsyncSession,
    employee_user_factory
) -> None:
    """
    IDでRole変更リクエストを取得するテスト
    """
    employee = await employee_user_factory()
    office = employee.office_associations[0].office

    request_data = RoleChangeRequestCreate(
        requested_role=StaffRole.owner,
        request_notes="オーナーへの昇格を希望します"
    )

    created_request = await crud.role_change_request.create(
        db=db_session,
        obj_in=request_data,
        requester_staff_id=employee.id,
        office_id=office.id,
        from_role=employee.role
    )

    # 取得
    retrieved_request = await crud.role_change_request.get(
        db=db_session,
        id=created_request.id
    )

    assert retrieved_request is not None
    assert retrieved_request.id == created_request.id
    assert retrieved_request.requested_role == StaffRole.owner


async def test_get_requests_by_requester(
    db_session: AsyncSession,
    employee_user_factory
) -> None:
    """
    リクエスト作成者IDでリクエスト一覧を取得するテスト
    """
    employee = await employee_user_factory()
    office = employee.office_associations[0].office

    # 複数のリクエストを作成
    for role in [StaffRole.manager, StaffRole.owner]:
        request_data = RoleChangeRequestCreate(
            requested_role=role,
            request_notes=f"{role}への変更を希望します"
        )
        await crud.role_change_request.create(
            db=db_session,
            obj_in=request_data,
            requester_staff_id=employee.id,
            office_id=office.id,
            from_role=employee.role
        )

    # リクエスト作成者でリクエスト一覧を取得
    requests = await crud.role_change_request.get_by_requester(
        db=db_session,
        requester_staff_id=employee.id
    )

    assert len(requests) == 2
    assert all(req.requester_staff_id == employee.id for req in requests)


async def test_get_pending_requests_for_approver_manager(
    db_session: AsyncSession,
    employee_user_factory,
    manager_user_factory
) -> None:
    """
    Manager権限で承認可能なpendingリクエスト一覧を取得するテスト
    （employee → manager/owner）
    """
    employee = await employee_user_factory()
    office = employee.office_associations[0].office
    manager = await manager_user_factory(office=office)

    # employee → managerのリクエスト作成（managerが承認可能）
    request_data = RoleChangeRequestCreate(
        requested_role=StaffRole.manager,
        request_notes="マネージャーへの昇格を希望します"
    )
    await crud.role_change_request.create(
        db=db_session,
        obj_in=request_data,
        requester_staff_id=employee.id,
        office_id=office.id,
        from_role=StaffRole.employee
    )

    # managerが承認可能なpendingリクエストを取得
    pending_requests = await crud.role_change_request.get_pending_for_approver(
        db=db_session,
        approver_staff_id=manager.id,
        approver_role=StaffRole.manager,
        office_id=office.id
    )

    assert len(pending_requests) >= 1
    assert all(req.status == RequestStatus.pending for req in pending_requests)
    assert all(req.from_role == StaffRole.employee for req in pending_requests)


async def test_get_pending_requests_for_approver_owner(
    db_session: AsyncSession,
    manager_user_factory,
    employee_user_factory
) -> None:
    """
    Owner権限で承認可能なpendingリクエスト一覧を取得するテスト
    （manager → owner）
    """
    # 最初のマネージャーを作成（このマネージャーはowner権限を持つとする）
    owner = await manager_user_factory()
    office = owner.office_associations[0].office

    # 別のマネージャーを作成
    manager = await manager_user_factory(office=office)

    # manager → ownerのリクエスト作成（ownerのみが承認可能）
    request_data = RoleChangeRequestCreate(
        requested_role=StaffRole.owner,
        request_notes="オーナーへの昇格を希望します"
    )
    await crud.role_change_request.create(
        db=db_session,
        obj_in=request_data,
        requester_staff_id=manager.id,
        office_id=office.id,
        from_role=StaffRole.manager
    )

    # ownerが承認可能なpendingリクエストを取得
    pending_requests = await crud.role_change_request.get_pending_for_approver(
        db=db_session,
        approver_staff_id=owner.id,
        approver_role=StaffRole.owner,
        office_id=office.id
    )

    assert len(pending_requests) >= 1
    assert all(req.status == RequestStatus.pending for req in pending_requests)


async def test_approve_role_change_request(
    db_session: AsyncSession,
    employee_user_factory,
    manager_user_factory
) -> None:
    """
    Role変更リクエスト承認テスト
    """
    employee = await employee_user_factory()
    office = employee.office_associations[0].office
    manager = await manager_user_factory(office=office)

    # リクエスト作成
    request_data = RoleChangeRequestCreate(
        requested_role=StaffRole.manager,
        request_notes="マネージャーへの昇格を希望します"
    )
    created_request = await crud.role_change_request.create(
        db=db_session,
        obj_in=request_data,
        requester_staff_id=employee.id,
        office_id=office.id,
        from_role=StaffRole.employee
    )

    assert created_request.status == RequestStatus.pending

    # 承認処理
    approved_request = await crud.role_change_request.approve(
        db=db_session,
        request_id=created_request.id,
        reviewer_staff_id=manager.id,
        reviewer_notes="承認しました"
    )

    assert approved_request.status == RequestStatus.approved
    assert approved_request.reviewed_by_staff_id == manager.id
    assert approved_request.reviewed_at is not None
    assert approved_request.reviewer_notes == "承認しました"


async def test_reject_role_change_request(
    db_session: AsyncSession,
    employee_user_factory,
    manager_user_factory
) -> None:
    """
    Role変更リクエスト却下テスト
    """
    employee = await employee_user_factory()
    office = employee.office_associations[0].office
    manager = await manager_user_factory(office=office)

    # リクエスト作成
    request_data = RoleChangeRequestCreate(
        requested_role=StaffRole.owner,
        request_notes="オーナーへの昇格を希望します"
    )
    created_request = await crud.role_change_request.create(
        db=db_session,
        obj_in=request_data,
        requester_staff_id=employee.id,
        office_id=office.id,
        from_role=StaffRole.employee
    )

    assert created_request.status == RequestStatus.pending

    # 却下処理
    rejected_request = await crud.role_change_request.reject(
        db=db_session,
        request_id=created_request.id,
        reviewer_staff_id=manager.id,
        reviewer_notes="現時点では承認できません"
    )

    assert rejected_request.status == RequestStatus.rejected
    assert rejected_request.reviewed_by_staff_id == manager.id
    assert rejected_request.reviewed_at is not None
    assert rejected_request.reviewer_notes == "現時点では承認できません"


async def test_get_requests_by_status(
    db_session: AsyncSession,
    employee_user_factory,
    manager_user_factory
) -> None:
    """
    ステータスでフィルタリングしてリクエストを取得するテスト
    """
    employee = await employee_user_factory()
    office = employee.office_associations[0].office
    manager = await manager_user_factory(office=office)

    # pending リクエスト作成
    pending_request_data = RoleChangeRequestCreate(
        requested_role=StaffRole.manager,
        request_notes="pending リクエスト"
    )
    pending_request = await crud.role_change_request.create(
        db=db_session,
        obj_in=pending_request_data,
        requester_staff_id=employee.id,
        office_id=office.id,
        from_role=StaffRole.employee
    )

    # approved リクエスト作成と承認
    approved_request_data = RoleChangeRequestCreate(
        requested_role=StaffRole.manager,
        request_notes="approved リクエスト"
    )
    approved_request = await crud.role_change_request.create(
        db=db_session,
        obj_in=approved_request_data,
        requester_staff_id=employee.id,
        office_id=office.id,
        from_role=StaffRole.employee
    )
    await crud.role_change_request.approve(
        db=db_session,
        request_id=approved_request.id,
        reviewer_staff_id=manager.id,
        reviewer_notes="承認"
    )

    # pending ステータスのリクエストのみ取得
    pending_requests = await crud.role_change_request.get_by_status(
        db=db_session,
        office_id=office.id,
        status=RequestStatus.pending
    )

    assert len(pending_requests) >= 1
    assert all(req.status == RequestStatus.pending for req in pending_requests)


async def test_get_requests_by_office(
    db_session: AsyncSession,
    employee_user_factory
) -> None:
    """
    事業所IDでリクエスト一覧を取得するテスト
    """
    employee1 = await employee_user_factory()
    office1 = employee1.office_associations[0].office

    employee2 = await employee_user_factory()
    office2 = employee2.office_associations[0].office

    # office1のリクエスト作成
    request_data_office1 = RoleChangeRequestCreate(
        requested_role=StaffRole.manager,
        request_notes="office1のリクエスト"
    )
    await crud.role_change_request.create(
        db=db_session,
        obj_in=request_data_office1,
        requester_staff_id=employee1.id,
        office_id=office1.id,
        from_role=StaffRole.employee
    )

    # office2のリクエスト作成
    request_data_office2 = RoleChangeRequestCreate(
        requested_role=StaffRole.manager,
        request_notes="office2のリクエスト"
    )
    await crud.role_change_request.create(
        db=db_session,
        obj_in=request_data_office2,
        requester_staff_id=employee2.id,
        office_id=office2.id,
        from_role=StaffRole.employee
    )

    # office1のリクエストのみ取得
    office1_requests = await crud.role_change_request.get_by_office(
        db=db_session,
        office_id=office1.id
    )

    assert len(office1_requests) >= 1
    assert all(req.office_id == office1.id for req in office1_requests)


async def test_delete_role_change_request(
    db_session: AsyncSession,
    employee_user_factory
) -> None:
    """
    Role変更リクエスト削除テスト（pending状態のみ削除可能）
    """
    employee = await employee_user_factory()
    office = employee.office_associations[0].office

    request_data = RoleChangeRequestCreate(
        requested_role=StaffRole.manager,
        request_notes="削除テスト"
    )
    created_request = await crud.role_change_request.create(
        db=db_session,
        obj_in=request_data,
        requester_staff_id=employee.id,
        office_id=office.id,
        from_role=StaffRole.employee
    )

    request_id = created_request.id

    # 削除
    removed_request = await crud.role_change_request.remove(
        db=db_session,
        id=request_id
    )

    assert removed_request is not None
    assert removed_request.id == request_id

    # 削除後に取得できないことを確認
    deleted_request = await crud.role_change_request.get(
        db=db_session,
        id=request_id
    )
    assert deleted_request is None


async def test_cannot_approve_already_processed_request(
    db_session: AsyncSession,
    employee_user_factory,
    manager_user_factory
) -> None:
    """
    既に処理済みのリクエストは承認できないことを確認するテスト
    """
    employee = await employee_user_factory()
    office = employee.office_associations[0].office
    manager = await manager_user_factory(office=office)

    # リクエスト作成
    request_data = RoleChangeRequestCreate(
        requested_role=StaffRole.manager,
        request_notes="二重承認テスト"
    )
    created_request = await crud.role_change_request.create(
        db=db_session,
        obj_in=request_data,
        requester_staff_id=employee.id,
        office_id=office.id,
        from_role=StaffRole.employee
    )

    # 1回目の承認
    await crud.role_change_request.approve(
        db=db_session,
        request_id=created_request.id,
        reviewer_staff_id=manager.id,
        reviewer_notes="1回目の承認"
    )

    # 2回目の承認（エラーになるべき）
    with pytest.raises(Exception):  # 適切な例外型に置き換える
        await crud.role_change_request.approve(
            db=db_session,
            request_id=created_request.id,
            reviewer_staff_id=manager.id,
            reviewer_notes="2回目の承認"
        )
