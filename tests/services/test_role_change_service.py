import pytest
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID, uuid4
from typing import Tuple
from fastapi import HTTPException, status

from app.db.session import AsyncSessionLocal
from app.models.staff import Staff
from app.models.office import Office, OfficeStaff
from app.models.enums import StaffRole, OfficeType, RequestStatus
from app.core.security import get_password_hash
from app.schemas.role_change_request import RoleChangeRequestCreate
from app.services.role_change_service import role_change_service

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
                # サービス層がcommit()を行うため、ここではrollbackしない
                # 代わりに、セッションをクローズするだけ
                await session.close()
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
    )
    db.add(owner)
    await db.flush()

    # Office作成
    office = Office(
        name="テスト事業所",
        type=OfficeType.type_A_office,
        created_by=owner.id,
        last_modified_by=owner.id,
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


# ===== リクエスト作成テスト =====

async def test_employee_request_to_manager(
    db: AsyncSession,
    setup_office_with_staff: Tuple[UUID, UUID, UUID, UUID]
):
    """employeeがmanagerへの変更をリクエスト"""
    office_id, owner_id, manager_id, employee_id = setup_office_with_staff

    # リクエスト作成
    request_data = RoleChangeRequestCreate(
        requested_role=StaffRole.manager,
        request_notes="マネージャーへの昇格を希望します"
    )

    request = await role_change_service.create_request(
        db=db,
        requester_staff_id=employee_id,
        office_id=office_id,
        obj_in=request_data
    )

    assert request is not None
    assert request.requester_staff_id == employee_id
    assert request.from_role == StaffRole.employee
    assert request.requested_role == StaffRole.manager
    assert request.status == RequestStatus.pending
    assert request.request_notes == "マネージャーへの昇格を希望します"


async def test_manager_request_to_owner(
    db: AsyncSession,
    setup_office_with_staff: Tuple[UUID, UUID, UUID, UUID]
):
    """managerがownerへの変更をリクエスト"""
    office_id, owner_id, manager_id, employee_id = setup_office_with_staff

    request_data = RoleChangeRequestCreate(
        requested_role=StaffRole.owner,
        request_notes="オーナーへの昇格を希望します"
    )

    request = await role_change_service.create_request(
        db=db,
        requester_staff_id=manager_id,
        office_id=office_id,
        obj_in=request_data
    )

    assert request is not None
    assert request.from_role == StaffRole.manager
    assert request.requested_role == StaffRole.owner
    assert request.status == RequestStatus.pending


# ===== 承認・却下テスト =====

async def test_manager_approve_employee_to_manager(
    db: AsyncSession,
    setup_office_with_staff: Tuple[UUID, UUID, UUID, UUID]
):
    """managerがemployee→managerを承認"""
    office_id, owner_id, manager_id, employee_id = setup_office_with_staff

    # リクエスト作成
    request_data = RoleChangeRequestCreate(
        requested_role=StaffRole.manager,
        request_notes="マネージャーへの昇格を希望します"
    )

    request = await role_change_service.create_request(
        db=db,
        requester_staff_id=employee_id,
        office_id=office_id,
        obj_in=request_data
    )

    # リクエストIDを保存（commit後にオブジェクトがexpireされる可能性があるため）
    request_id = request.id

    # 承認処理
    approved_request = await role_change_service.approve_request(
        db=db,
        request_id=request_id,
        reviewer_staff_id=manager_id,
        reviewer_notes="承認します"
    )

    assert approved_request.status == RequestStatus.approved
    assert approved_request.reviewed_by_staff_id == manager_id
    assert approved_request.reviewer_notes == "承認します"

    # スタッフのroleが変更されているか確認
    from app.crud.crud_staff import staff as crud_staff
    updated_staff = await crud_staff.get(db, id=employee_id)
    assert updated_staff.role == StaffRole.manager


async def test_owner_approve_manager_to_owner(
    db: AsyncSession,
    setup_office_with_staff: Tuple[UUID, UUID, UUID, UUID]
):
    """ownerがmanager→ownerを承認"""
    office_id, owner_id, manager_id, employee_id = setup_office_with_staff

    # リクエスト作成
    request_data = RoleChangeRequestCreate(
        requested_role=StaffRole.owner,
        request_notes="オーナーへの昇格を希望します"
    )

    request = await role_change_service.create_request(
        db=db,
        requester_staff_id=manager_id,
        office_id=office_id,
        obj_in=request_data
    )

    # 承認処理
    approved_request = await role_change_service.approve_request(
        db=db,
        request_id=request.id,
        reviewer_staff_id=owner_id,
        reviewer_notes="承認します"
    )

    assert approved_request.status == RequestStatus.approved


async def test_reject_request(
    db: AsyncSession,
    setup_office_with_staff: Tuple[UUID, UUID, UUID, UUID]
):
    """リクエストの却下処理"""
    office_id, owner_id, manager_id, employee_id = setup_office_with_staff

    # リクエスト作成
    request_data = RoleChangeRequestCreate(
        requested_role=StaffRole.manager,
        request_notes="マネージャーへの昇格を希望します"
    )

    request = await role_change_service.create_request(
        db=db,
        requester_staff_id=employee_id,
        office_id=office_id,
        obj_in=request_data
    )

    # 却下処理
    rejected_request = await role_change_service.reject_request(
        db=db,
        request_id=request.id,
        reviewer_staff_id=manager_id,
        reviewer_notes="まだ早いです"
    )

    assert rejected_request.status == RequestStatus.rejected
    assert rejected_request.reviewed_by_staff_id == manager_id
    assert rejected_request.reviewer_notes == "まだ早いです"

    # スタッフのroleは変更されていないか確認
    from app.crud.crud_staff import staff as crud_staff
    unchanged_staff = await crud_staff.get(db, id=employee_id)
    assert unchanged_staff.role == StaffRole.employee


# ===== 権限チェックテスト =====

async def test_validate_approval_permission_manager_can_approve_employee_request(
    db: AsyncSession,
    setup_office_with_staff: Tuple[UUID, UUID, UUID, UUID]
):
    """managerはemployee→manager/ownerのリクエストを承認可能"""
    office_id, owner_id, manager_id, employee_id = setup_office_with_staff

    # employee → manager リクエスト
    request_data = RoleChangeRequestCreate(
        requested_role=StaffRole.manager,
    )
    request = await role_change_service.create_request(
        db=db,
        requester_staff_id=employee_id,
        office_id=office_id,
        obj_in=request_data
    )

    # managerが承認できるか検証
    from app.crud.crud_staff import staff as crud_staff
    reviewer = await crud_staff.get(db, id=manager_id)

    can_approve = role_change_service.validate_approval_permission(
        reviewer_role=reviewer.role,
        request=request
    )
    assert can_approve is True


async def test_validate_approval_permission_manager_cannot_approve_manager_request(
    db: AsyncSession,
    setup_office_with_staff: Tuple[UUID, UUID, UUID, UUID]
):
    """managerはmanager→ownerのリクエストを承認できない"""
    office_id, owner_id, manager_id, employee_id = setup_office_with_staff

    # manager → owner リクエスト
    request_data = RoleChangeRequestCreate(
        requested_role=StaffRole.owner,
    )
    request = await role_change_service.create_request(
        db=db,
        requester_staff_id=manager_id,
        office_id=office_id,
        obj_in=request_data
    )

    # managerが承認できないか検証
    from app.crud.crud_staff import staff as crud_staff
    reviewer = await crud_staff.get(db, id=manager_id)

    can_approve = role_change_service.validate_approval_permission(
        reviewer_role=reviewer.role,
        request=request
    )
    assert can_approve is False


async def test_validate_approval_permission_owner_can_approve_all(
    db: AsyncSession,
    setup_office_with_staff: Tuple[UUID, UUID, UUID, UUID]
):
    """ownerはすべてのリクエストを承認可能"""
    office_id, owner_id, manager_id, employee_id = setup_office_with_staff

    # manager → owner リクエスト
    request_data = RoleChangeRequestCreate(
        requested_role=StaffRole.owner,
    )
    request = await role_change_service.create_request(
        db=db,
        requester_staff_id=manager_id,
        office_id=office_id,
        obj_in=request_data
    )

    # ownerが承認できるか検証
    from app.crud.crud_staff import staff as crud_staff
    reviewer = await crud_staff.get(db, id=owner_id)

    can_approve = role_change_service.validate_approval_permission(
        reviewer_role=reviewer.role,
        request=request
    )
    assert can_approve is True


# ===== エラーケーステスト =====

async def test_cannot_approve_twice(
    db: AsyncSession,
    setup_office_with_staff: Tuple[UUID, UUID, UUID, UUID]
):
    """既に処理済みのリクエストは承認不可"""
    office_id, owner_id, manager_id, employee_id = setup_office_with_staff

    # リクエスト作成
    request_data = RoleChangeRequestCreate(
        requested_role=StaffRole.manager,
    )
    request = await role_change_service.create_request(
        db=db,
        requester_staff_id=employee_id,
        office_id=office_id,
        obj_in=request_data
    )

    # 1回目の承認
    await role_change_service.approve_request(
        db=db,
        request_id=request.id,
        reviewer_staff_id=manager_id,
    )

    # 2回目の承認（エラーになるはず）
    with pytest.raises(HTTPException) as exc_info:
        await role_change_service.approve_request(
            db=db,
            request_id=request.id,
            reviewer_staff_id=manager_id,
        )
    assert exc_info.value.status_code == status.HTTP_409_CONFLICT


# ===== MissingGreenlet対策テスト =====

async def test_no_missing_greenlet_after_approve(
    db: AsyncSession,
    setup_office_with_staff: Tuple[UUID, UUID, UUID, UUID]
):
    """
    承認後にオブジェクトの属性にアクセスしてもMissingGreenletエラーが発生しない
    （コミット・リフレッシュ処理が正しく行われているか確認）
    """
    office_id, owner_id, manager_id, employee_id = setup_office_with_staff

    # リクエスト作成
    request_data = RoleChangeRequestCreate(
        requested_role=StaffRole.manager,
        request_notes="昇格希望"
    )
    request = await role_change_service.create_request(
        db=db,
        requester_staff_id=employee_id,
        office_id=office_id,
        obj_in=request_data
    )

    # 承認処理
    approved_request = await role_change_service.approve_request(
        db=db,
        request_id=request.id,
        reviewer_staff_id=manager_id,
        reviewer_notes="承認します"
    )

    # コミット後にリレーションシップにアクセスしてもエラーが発生しないことを確認
    assert approved_request.requester is not None
    assert approved_request.requester.id == employee_id
    assert approved_request.reviewer is not None
    assert approved_request.reviewer.id == manager_id
    assert approved_request.office is not None
    assert approved_request.office.id == office_id

    # スタッフのroleが変更されているか確認
    assert approved_request.requester.role == StaffRole.manager


async def test_no_missing_greenlet_after_reject(
    db: AsyncSession,
    setup_office_with_staff: Tuple[UUID, UUID, UUID, UUID]
):
    """
    却下後にオブジェクトの属性にアクセスしてもMissingGreenletエラーが発生しない
    """
    office_id, owner_id, manager_id, employee_id = setup_office_with_staff

    # リクエスト作成
    request_data = RoleChangeRequestCreate(
        requested_role=StaffRole.manager,
        request_notes="昇格希望"
    )
    request = await role_change_service.create_request(
        db=db,
        requester_staff_id=employee_id,
        office_id=office_id,
        obj_in=request_data
    )

    # 却下処理
    rejected_request = await role_change_service.reject_request(
        db=db,
        request_id=request.id,
        reviewer_staff_id=manager_id,
        reviewer_notes="まだ早い"
    )

    # コミット後にリレーションシップにアクセスしてもエラーが発生しないことを確認
    assert rejected_request.requester is not None
    assert rejected_request.requester.id == employee_id
    assert rejected_request.reviewer is not None
    assert rejected_request.reviewer.id == manager_id
    assert rejected_request.office is not None
    assert rejected_request.office.id == office_id


# ===== 通知機能テスト =====

async def test_create_request_creates_notification(
    db: AsyncSession,
    setup_office_with_staff: Tuple[UUID, UUID, UUID, UUID]
):
    """
    Role変更リクエスト作成時に承認者（manager/owner）への通知が作成される
    """
    office_id, owner_id, manager_id, employee_id = setup_office_with_staff

    # リクエスト作成
    request_data = RoleChangeRequestCreate(
        requested_role=StaffRole.manager,
        request_notes="昇格希望"
    )
    request = await role_change_service.create_request(
        db=db,
        requester_staff_id=employee_id,
        office_id=office_id,
        obj_in=request_data
    )

    # 通知が作成されているか確認
    from app.crud.crud_notice import crud_notice
    from app.models.enums import NoticeType

    # Manager宛の通知を確認
    manager_notices = await crud_notice.get_unread_by_staff_id(db, staff_id=manager_id)
    assert len(manager_notices) > 0

    # 通知の内容を確認
    notice = manager_notices[0]
    assert notice.type == NoticeType.role_change_pending.value
    assert notice.recipient_staff_id == manager_id
    assert notice.office_id == office_id
    assert notice.is_read is False
    assert "変更" in notice.content and "リクエスト" in notice.content


async def test_approve_request_creates_notification(
    db: AsyncSession,
    setup_office_with_staff: Tuple[UUID, UUID, UUID, UUID]
):
    """
    Role変更リクエスト承認時にリクエスト作成者への通知が作成される
    """
    office_id, owner_id, manager_id, employee_id = setup_office_with_staff

    # リクエスト作成
    request_data = RoleChangeRequestCreate(
        requested_role=StaffRole.manager,
        request_notes="昇格希望"
    )
    request = await role_change_service.create_request(
        db=db,
        requester_staff_id=employee_id,
        office_id=office_id,
        obj_in=request_data
    )

    # 承認処理
    await role_change_service.approve_request(
        db=db,
        request_id=request.id,
        reviewer_staff_id=manager_id,
        reviewer_notes="承認します"
    )

    # 通知が作成されているか確認
    from app.crud.crud_notice import crud_notice
    from app.models.enums import NoticeType

    # Employee（リクエスト作成者）宛の通知を確認
    employee_notices = await crud_notice.get_unread_by_staff_id(db, staff_id=employee_id)

    # 承認通知を探す
    approval_notices = [n for n in employee_notices if n.type == NoticeType.role_change_approved.value]
    assert len(approval_notices) > 0

    # 通知の内容を確認
    notice = approval_notices[0]
    assert notice.recipient_staff_id == employee_id
    assert notice.office_id == office_id
    assert notice.is_read is False
    assert "承認" in notice.content or "approved" in notice.content.lower()


async def test_reject_request_creates_notification(
    db: AsyncSession,
    setup_office_with_staff: Tuple[UUID, UUID, UUID, UUID]
):
    """
    Role変更リクエスト却下時にリクエスト作成者への通知が作成される
    """
    office_id, owner_id, manager_id, employee_id = setup_office_with_staff

    # リクエスト作成
    request_data = RoleChangeRequestCreate(
        requested_role=StaffRole.manager,
        request_notes="昇格希望"
    )
    request = await role_change_service.create_request(
        db=db,
        requester_staff_id=employee_id,
        office_id=office_id,
        obj_in=request_data
    )

    # 却下処理
    await role_change_service.reject_request(
        db=db,
        request_id=request.id,
        reviewer_staff_id=manager_id,
        reviewer_notes="まだ早い"
    )

    # 通知が作成されているか確認
    from app.crud.crud_notice import crud_notice
    from app.models.enums import NoticeType

    # Employee（リクエスト作成者）宛の通知を確認
    employee_notices = await crud_notice.get_unread_by_staff_id(db, staff_id=employee_id)

    # 却下通知を探す
    rejection_notices = [n for n in employee_notices if n.type == NoticeType.role_change_rejected.value]
    assert len(rejection_notices) > 0

    # 通知の内容を確認
    notice = rejection_notices[0]
    assert notice.recipient_staff_id == employee_id
    assert notice.office_id == office_id
    assert notice.is_read is False
    assert "却下" in notice.content or "rejected" in notice.content.lower()


# ===== 送信者向け通知テスト（新機能） =====

async def test_create_request_sends_notification_to_requester(
    db: AsyncSession,
    setup_office_with_staff: Tuple[UUID, UUID, UUID, UUID]
):
    """
    TDD: リクエスト作成時に送信者にも通知が作成される
    送信者向け通知は role_change_request_sent タイプで作成される
    """
    office_id, owner_id, manager_id, employee_id = setup_office_with_staff

    # リクエスト作成
    request_data = RoleChangeRequestCreate(
        requested_role=StaffRole.manager,
        request_notes="昇格希望"
    )
    request = await role_change_service.create_request(
        db=db,
        requester_staff_id=employee_id,
        office_id=office_id,
        obj_in=request_data
    )

    # 通知が作成されているか確認
    from app.crud.crud_notice import crud_notice
    from app.models.enums import NoticeType

    # 送信者（Employee）宛の通知を確認
    employee_notices = await crud_notice.get_unread_by_staff_id(db, staff_id=employee_id)

    # role_change_request_sent 通知を探す
    sent_notices = [n for n in employee_notices if n.type == NoticeType.role_change_request_sent.value]
    assert len(sent_notices) == 1, "送信者にrole_change_request_sent通知が1件作成されるべき"

    # 通知の内容を確認
    notice = sent_notices[0]
    assert notice.recipient_staff_id == employee_id
    assert notice.office_id == office_id
    assert notice.is_read is False
    assert "送信" in notice.title or "sent" in notice.title.lower()
    assert "承認をお待ちください" in notice.content or "待ち" in notice.content
    assert f"/role-change-requests/{request.id}" in notice.link_url


async def test_create_request_sends_notifications_to_both_requester_and_approvers(
    db: AsyncSession,
    setup_office_with_staff: Tuple[UUID, UUID, UUID, UUID]
):
    """
    TDD: リクエスト作成時に送信者と承認者の両方に通知が作成される
    - 送信者: role_change_request_sent
    - 承認者: role_change_pending
    """
    office_id, owner_id, manager_id, employee_id = setup_office_with_staff

    # リクエスト作成
    request_data = RoleChangeRequestCreate(
        requested_role=StaffRole.manager,
        request_notes="昇格希望"
    )
    request = await role_change_service.create_request(
        db=db,
        requester_staff_id=employee_id,
        office_id=office_id,
        obj_in=request_data
    )

    from app.crud.crud_notice import crud_notice
    from app.models.enums import NoticeType

    # 1. 送信者への通知を確認
    employee_notices = await crud_notice.get_unread_by_staff_id(db, staff_id=employee_id)
    sent_notices = [n for n in employee_notices if n.type == NoticeType.role_change_request_sent.value]
    assert len(sent_notices) == 1, "送信者にrole_change_request_sent通知が作成されるべき"
    assert sent_notices[0].recipient_staff_id == employee_id

    # 2. 承認者（Manager）への通知を確認
    manager_notices = await crud_notice.get_unread_by_staff_id(db, staff_id=manager_id)
    pending_notices = [n for n in manager_notices if n.type == NoticeType.role_change_pending.value]
    assert len(pending_notices) >= 1, "承認者にrole_change_pending通知が作成されるべき"

    manager_pending = [n for n in pending_notices if n.recipient_staff_id == manager_id]
    assert len(manager_pending) >= 1

    # 3. Ownerへの通知も確認
    owner_notices = await crud_notice.get_unread_by_staff_id(db, staff_id=owner_id)
    owner_pending_notices = [n for n in owner_notices if n.type == NoticeType.role_change_pending.value]
    assert len(owner_pending_notices) >= 1, "Ownerにもrole_change_pending通知が作成されるべき"


async def test_approve_request_updates_requester_notification_type(
    db: AsyncSession,
    setup_office_with_staff: Tuple[UUID, UUID, UUID, UUID]
):
    """
    TDD: 承認時に送信者の role_change_request_sent 通知が role_change_approved に更新される
    """
    office_id, owner_id, manager_id, employee_id = setup_office_with_staff

    # リクエスト作成
    request_data = RoleChangeRequestCreate(
        requested_role=StaffRole.manager,
        request_notes="昇格希望"
    )
    request = await role_change_service.create_request(
        db=db,
        requester_staff_id=employee_id,
        office_id=office_id,
        obj_in=request_data
    )

    from app.crud.crud_notice import crud_notice
    from app.models.enums import NoticeType

    # 承認前: role_change_request_sent が存在することを確認
    employee_notices_before = await crud_notice.get_unread_by_staff_id(db, staff_id=employee_id)
    sent_notices = [n for n in employee_notices_before if n.type == NoticeType.role_change_request_sent.value]
    assert len(sent_notices) == 1, "承認前に送信者通知が存在するべき"

    # 承認処理
    await role_change_service.approve_request(
        db=db,
        request_id=request.id,
        reviewer_staff_id=manager_id,
        reviewer_notes="承認します"
    )

    # 承認後: role_change_request_sent が role_change_approved に更新されていることを確認
    employee_notices_after = await crud_notice.get_unread_by_staff_id(db, staff_id=employee_id)

    # もう role_change_request_sent は存在しないはず
    sent_notices_after = [n for n in employee_notices_after if n.type == NoticeType.role_change_request_sent.value]
    assert len(sent_notices_after) == 0, "承認後はrole_change_request_sent通知は存在しないべき"

    # role_change_approved が存在するはず
    approved_notices = [n for n in employee_notices_after if n.type == NoticeType.role_change_approved.value]
    assert len(approved_notices) >= 1, "承認後はrole_change_approved通知が存在するべき"


async def test_reject_request_updates_requester_notification_type(
    db: AsyncSession,
    setup_office_with_staff: Tuple[UUID, UUID, UUID, UUID]
):
    """
    TDD: 却下時に送信者の role_change_request_sent 通知が role_change_rejected に更新される
    """
    office_id, owner_id, manager_id, employee_id = setup_office_with_staff

    # リクエスト作成
    request_data = RoleChangeRequestCreate(
        requested_role=StaffRole.manager,
        request_notes="昇格希望"
    )
    request = await role_change_service.create_request(
        db=db,
        requester_staff_id=employee_id,
        office_id=office_id,
        obj_in=request_data
    )

    from app.crud.crud_notice import crud_notice
    from app.models.enums import NoticeType

    # 却下前: role_change_request_sent が存在することを確認
    employee_notices_before = await crud_notice.get_unread_by_staff_id(db, staff_id=employee_id)
    sent_notices = [n for n in employee_notices_before if n.type == NoticeType.role_change_request_sent.value]
    assert len(sent_notices) == 1, "却下前に送信者通知が存在するべき"

    # 却下処理
    await role_change_service.reject_request(
        db=db,
        request_id=request.id,
        reviewer_staff_id=manager_id,
        reviewer_notes="まだ早い"
    )

    # 却下後: role_change_request_sent が role_change_rejected に更新されていることを確認
    employee_notices_after = await crud_notice.get_unread_by_staff_id(db, staff_id=employee_id)

    # もう role_change_request_sent は存在しないはず
    sent_notices_after = [n for n in employee_notices_after if n.type == NoticeType.role_change_request_sent.value]
    assert len(sent_notices_after) == 0, "却下後はrole_change_request_sent通知は存在しないべき"

    # role_change_rejected が存在するはず
    rejected_notices = [n for n in employee_notices_after if n.type == NoticeType.role_change_rejected.value]
    assert len(rejected_notices) >= 1, "却下後はrole_change_rejected通知が存在するべき"
