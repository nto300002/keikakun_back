"""Role変更リクエスト統合テスト（Phase 7 - 中優先度）

Role変更リクエストの作成から承認/却下までのE2Eフローを検証

このテストは以下のシナリオを検証します:
1. EmployeeがManager roleをリクエスト → Managerが承認 → role変更成功
2. ManagerがOwner roleをリクエスト → Ownerが承認 → role変更成功
3. Employeeが同じroleをリクエスト → 400 Bad Request
4. Managerが自分のリクエストを承認しようとする → 権限チェック
5. Role変更時に通知が送信される

実行コマンド:
pytest tests/integration/test_role_change_flow.py -v -s --tb=short
"""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status

from app.models.staff import Staff
from app.models.role_change_request import RoleChangeRequest
from app.models.notice import Notice
from app.models.enums import StaffRole, RequestStatus, NoticeType
from app.schemas.role_change_request import RoleChangeRequestCreate
from app.services.role_change_service import role_change_service
from app.crud.crud_role_change_request import crud_role_change_request
from app.crud.crud_notice import crud_notice


@pytest.mark.asyncio
async def test_employee_request_manager_role_and_get_approved(
    db_session,
    office_factory,
    staff_factory
):
    """
    Scenario 1: Employee が Manager role をリクエスト → Manager が承認 → role 変更成功

    テスト内容:
    1. Employee が Manager role への変更をリクエスト
    2. Manager が承認
    3. Employee の role が Manager に変更される
    4. Employee に承認通知が届く
    """
    # Arrange
    office = await office_factory(session=db_session)
    employee = await staff_factory(
        session=db_session,
        office_id=office.id,
        role=StaffRole.employee,
        first_name="従業員"
    )
    manager = await staff_factory(
        session=db_session,
        office_id=office.id,
        role=StaffRole.manager,
        first_name="マネージャー"
    )

    original_role = employee.role

    # Act 1: Employee が Manager role をリクエスト
    request_create = RoleChangeRequestCreate(
        requested_role=StaffRole.manager,
        request_notes="Manager になりたいです"
    )

    request = await role_change_service.create_request(
        db=db_session,
        requester_staff_id=employee.id,
        office_id=office.id,
        obj_in=request_create
    )
    await db_session.commit()

    # Assert 1: リクエストが正しく作成されたか
    assert request.status == RequestStatus.pending
    assert request.from_role == StaffRole.employee
    assert request.requested_role == StaffRole.manager
    assert request.requester_staff_id == employee.id

    print(f"\n✅ Step 1: Employee が Manager role をリクエスト")
    print(f"   Request ID: {request.id}")
    print(f"   From: {request.from_role} → To: {request.requested_role}")

    # Employee の role がまだ変更されていないことを確認
    await db_session.refresh(employee)
    assert employee.role == original_role

    # Act 2: Manager が承認
    approved_request = await role_change_service.approve_request(
        db=db_session,
        request_id=request.id,
        reviewer_staff_id=manager.id,
        reviewer_notes="承認します"
    )
    await db_session.commit()

    # Assert 2: リクエストが承認され、role が変更されたか
    assert approved_request.status == RequestStatus.approved
    assert approved_request.reviewed_by_staff_id == manager.id

    print(f"\n✅ Step 2: Manager がリクエストを承認")
    print(f"   Reviewer: {manager.id}")

    # Employee の role が Manager に変更されたことを確認
    # Staffを再取得（commit後はexpireするため）
    result = await db_session.execute(
        select(Staff).where(Staff.id == employee.id)
    )
    updated_employee = result.scalar_one()
    assert updated_employee.role == StaffRole.manager

    print(f"\n✅ Step 3: Employee の role が変更された")
    print(f"   Before: {original_role}")
    print(f"   After: {updated_employee.role}")

    # Assert 3: Employee に承認通知が届く
    notices = await crud_notice.get_unread_by_staff_id(db=db_session, staff_id=employee.id)
    assert len(notices) > 0, "承認通知が届いていない"

    latest_notice = notices[0]
    assert latest_notice.notice_type == NoticeType.role_change_approved
    assert latest_notice.recipient_staff_id == employee.id

    print(f"\n✅ Step 4: Employee に承認通知が届いた")
    print(f"   Notice Type: {latest_notice.notice_type}")
    print(f"   Notice Title: {latest_notice.notice_title}")


@pytest.mark.asyncio
async def test_manager_request_owner_role_and_get_approved(
    db_session,
    office_factory,
    staff_factory
):
    """
    Scenario 2: Manager が Owner role をリクエスト → Owner が承認 → role 変更成功

    テスト内容:
    1. Manager が Owner role への変更をリクエスト
    2. Owner が承認
    3. Manager の role が Owner に変更される
    4. Manager に承認通知が届く
    """
    # Arrange
    office = await office_factory(session=db_session)
    manager = await staff_factory(
        session=db_session,
        office_id=office.id,
        role=StaffRole.manager,
        first_name="マネージャー"
    )
    owner = await staff_factory(
        session=db_session,
        office_id=office.id,
        role=StaffRole.owner,
        first_name="オーナー"
    )

    original_role = manager.role

    # Act 1: Manager が Owner role をリクエスト
    request_create = RoleChangeRequestCreate(
        requested_role=StaffRole.owner,
        request_notes="Owner になりたいです"
    )

    request = await role_change_service.create_request(
        db=db_session,
        requester_staff_id=manager.id,
        office_id=office.id,
        obj_in=request_create
    )
    await db_session.commit()

    # Assert 1: リクエストが正しく作成されたか
    assert request.status == RequestStatus.pending
    assert request.from_role == StaffRole.manager
    assert request.requested_role == StaffRole.owner

    print(f"\n✅ Step 1: Manager が Owner role をリクエスト")
    print(f"   From: {request.from_role} → To: {request.requested_role}")

    # Act 2: Owner が承認
    approved_request = await role_change_service.approve_request(
        db=db_session,
        request_id=request.id,
        reviewer_staff_id=owner.id,
        reviewer_notes="承認します"
    )
    await db_session.commit()

    # Assert 2: リクエストが承認され、role が変更されたか
    assert approved_request.status == RequestStatus.approved

    # Manager の role が Owner に変更されたことを確認
    result = await db_session.execute(
        select(Staff).where(Staff.id == manager.id)
    )
    updated_manager = result.scalar_one()
    assert updated_manager.role == StaffRole.owner

    print(f"\n✅ Step 2: Manager の role が Owner に変更された")
    print(f"   Before: {original_role}")
    print(f"   After: {updated_manager.role}")

    # Assert 3: Manager に承認通知が届く
    notices = await crud_notice.get_unread_by_staff_id(db=db_session, staff_id=manager.id)
    assert len(notices) > 0, "承認通知が届いていない"

    latest_notice = notices[0]
    assert latest_notice.notice_type == NoticeType.role_change_approved

    print(f"\n✅ Step 3: Manager に承認通知が届いた")
    print(f"   Notice Type: {latest_notice.notice_type}")


@pytest.mark.asyncio
async def test_employee_request_same_role_returns_error(
    db_session,
    office_factory,
    staff_factory
):
    """
    Scenario 3: Employee が同じ role をリクエスト → エラー

    テスト内容:
    - Employee が自分と同じ Employee role をリクエスト
    - ValueError が発生する
    """
    # Arrange
    office = await office_factory(session=db_session)
    employee = await staff_factory(
        session=db_session,
        office_id=office.id,
        role=StaffRole.employee
    )

    # Act & Assert: 同じ role をリクエストするとエラー
    request_create = RoleChangeRequestCreate(
        requested_role=StaffRole.employee,  # 同じ role
        request_notes="Employee のままでお願いします"
    )

    with pytest.raises(HTTPException) as exc_info:
        await role_change_service.create_request(
            db=db_session,
            requester_staff_id=employee.id,
            office_id=office.id,
            obj_in=request_create
        )

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST

    print(f"\n✅ 同じ role のリクエストはエラー")
    print(f"   Error: {exc_info.value.detail}")


@pytest.mark.asyncio
async def test_employee_cannot_approve_own_request(
    db_session,
    office_factory,
    staff_factory
):
    """
    Scenario 4: Employee が自分のリクエストを承認できない

    テスト内容:
    - Employee が Manager role をリクエスト
    - 別の Employee が承認しようとする
    - 承認権限がないため失敗する
    """
    # Arrange
    office = await office_factory(session=db_session)
    employee1 = await staff_factory(
        session=db_session,
        office_id=office.id,
        role=StaffRole.employee,
        first_name="従業員1"
    )
    employee2 = await staff_factory(
        session=db_session,
        office_id=office.id,
        role=StaffRole.employee,
        first_name="従業員2"
    )

    # Employee1 がリクエスト作成
    request_create = RoleChangeRequestCreate(
        requested_role=StaffRole.manager,
        request_notes="Manager になりたいです"
    )

    request = await role_change_service.create_request(
        db=db_session,
        requester_staff_id=employee1.id,
        office_id=office.id,
        obj_in=request_create
    )
    await db_session.commit()

    # Act & Assert: Employee2 が承認しようとしても権限がない
    has_permission = role_change_service.validate_approval_permission(
        reviewer_role=employee2.role,
        request=request
    )

    assert has_permission is False

    print(f"\n✅ Employee は承認権限がない")
    print(f"   Reviewer Role: {employee2.role}")
    print(f"   Has Permission: {has_permission}")


@pytest.mark.asyncio
async def test_manager_request_rejected_by_owner(
    db_session,
    office_factory,
    staff_factory
):
    """
    Scenario 5: Manager のリクエストが Owner によって却下される

    テスト内容:
    1. Manager が Owner role をリクエスト
    2. Owner が却下
    3. Manager の role は変更されない
    4. Manager に却下通知が届く
    """
    # Arrange
    office = await office_factory(session=db_session)
    manager = await staff_factory(
        session=db_session,
        office_id=office.id,
        role=StaffRole.manager,
        first_name="マネージャー"
    )
    owner = await staff_factory(
        session=db_session,
        office_id=office.id,
        role=StaffRole.owner,
        first_name="オーナー"
    )

    original_role = manager.role

    # Act 1: Manager が Owner role をリクエスト
    request_create = RoleChangeRequestCreate(
        requested_role=StaffRole.owner,
        request_notes="Owner になりたいです"
    )

    request = await role_change_service.create_request(
        db=db_session,
        requester_staff_id=manager.id,
        office_id=office.id,
        obj_in=request_create
    )
    await db_session.commit()

    # Act 2: Owner が却下
    rejected_request = await role_change_service.reject_request(
        db=db_session,
        request_id=request.id,
        reviewer_staff_id=owner.id,
        reviewer_notes="今は時期ではありません"
    )
    await db_session.commit()

    # Assert: リクエストが却下され、role は変更されていないか
    assert rejected_request.status == RequestStatus.rejected
    assert rejected_request.reviewed_by_staff_id == owner.id
    assert rejected_request.reviewer_notes == "今は時期ではありません"

    # Manager の role が変更されていないことを確認
    result = await db_session.execute(
        select(Staff).where(Staff.id == manager.id)
    )
    unchanged_manager = result.scalar_one()
    assert unchanged_manager.role == original_role

    print(f"\n✅ Owner がリクエストを却下")
    print(f"   Manager の role は変更されていない: {unchanged_manager.role}")

    # Assert: Manager に却下通知が届く
    notices = await crud_notice.get_unread_by_staff_id(db=db_session, staff_id=manager.id)
    assert len(notices) > 0, "却下通知が届いていない"

    latest_notice = notices[0]
    assert latest_notice.notice_type == NoticeType.role_change_rejected
    assert latest_notice.recipient_staff_id == manager.id

    print(f"\n✅ Manager に却下通知が届いた")
    print(f"   Notice Type: {latest_notice.notice_type}")
    print(f"   Rejection Reason: {rejected_request.reviewer_notes}")


@pytest.mark.asyncio
async def test_get_pending_requests_for_approver(
    db_session,
    office_factory,
    staff_factory
):
    """
    Scenario 6: 承認者が承認可能なリクエスト一覧を取得できる

    テスト内容:
    - 複数の Employee がリクエストを作成
    - Manager が自分が承認可能なリクエスト一覧を取得
    - 自分の事業所のリクエストのみが取得される
    """
    # Arrange
    office = await office_factory(session=db_session)
    employee1 = await staff_factory(
        session=db_session,
        office_id=office.id,
        role=StaffRole.employee,
        first_name="従業員1"
    )
    employee2 = await staff_factory(
        session=db_session,
        office_id=office.id,
        role=StaffRole.employee,
        first_name="従業員2"
    )
    manager = await staff_factory(
        session=db_session,
        office_id=office.id,
        role=StaffRole.manager,
        first_name="マネージャー"
    )

    # Employee1 と Employee2 がリクエスト作成
    for i, employee in enumerate([employee1, employee2], 1):
        request_create = RoleChangeRequestCreate(
            requested_role=StaffRole.manager,
            request_notes=f"従業員{i}のリクエスト"
        )

        await role_change_service.create_request(
            db=db_session,
            requester_staff_id=employee.id,
            office_id=office.id,
            obj_in=request_create
        )

    await db_session.commit()

    # Act: Manager が承認可能なリクエスト一覧を取得
    pending_requests = await crud_role_change_request.get_pending_for_approver(
        db=db_session,
        approver_staff_id=manager.id,
        approver_role=manager.role,
        office_id=office.id
    )

    # Assert: 2件のリクエストが取得される
    assert len(pending_requests) == 2
    assert all(req.status == RequestStatus.pending for req in pending_requests)
    assert all(req.office_id == office.id for req in pending_requests)

    print(f"\n✅ Manager が承認可能なリクエスト一覧を取得")
    print(f"   Pending Requests: {len(pending_requests)}")
    for req in pending_requests:
        print(f"   - Request ID: {req.id}, From: {req.from_role} → {req.requested_role}")
