import pytest
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID, uuid4
from datetime import date
from typing import Tuple

from app.db.session import AsyncSessionLocal
from app.models.staff import Staff
from app.models.office import Office, OfficeStaff
from app.models.welfare_recipient import WelfareRecipient, OfficeWelfareRecipient
from app.models.enums import (
    StaffRole, OfficeType, RequestStatus,
    ActionType, ResourceType, GenderType
)
from app.core.security import get_password_hash
from app.schemas.employee_action_request import EmployeeActionRequestCreate
from app.services.employee_action_service import employee_action_service

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
async def setup_office_with_staff(db: AsyncSession) -> Tuple[UUID, UUID, UUID]:
    """
    テスト用の事業所とスタッフを作成
    Returns: (office_id, manager_id, employee_id)
    """
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

    # Office作成
    office = Office(
        name="テスト事業所",
        type=OfficeType.type_A_office,
        created_by=manager.id,
        last_modified_by=manager.id,
    )
    db.add(office)
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
    manager_id = manager.id
    employee_id = employee.id

    await db.commit()

    return office_id, manager_id, employee_id


@pytest.fixture(scope="function")
async def setup_welfare_recipient(
    db: AsyncSession,
    setup_office_with_staff: Tuple[UUID, UUID, UUID]
) -> UUID:
    """テスト用の利用者を作成"""
    office_id, manager_id, employee_id = setup_office_with_staff

    recipient = WelfareRecipient(
        first_name="テスト",
        last_name="太郎",
        first_name_furigana="テスト",
        last_name_furigana="タロウ",
        birth_day=date(1990, 1, 1),
        gender=GenderType.male,
    )
    db.add(recipient)
    await db.flush()

    # commit前にIDを保存（MissingGreenlet対策）
    recipient_id = recipient.id

    # 事業所との関連付け
    association = OfficeWelfareRecipient(
        office_id=office_id,
        welfare_recipient_id=recipient_id
    )
    db.add(association)
    await db.commit()

    return recipient_id


# ===== リクエスト作成テスト =====

async def test_employee_create_welfare_recipient_request(
    db: AsyncSession,
    setup_office_with_staff: Tuple[UUID, UUID, UUID]
):
    """employeeがWelfareRecipient作成リクエスト"""
    office_id, manager_id, employee_id = setup_office_with_staff

    # リクエストデータ
    request_data = EmployeeActionRequestCreate(
        resource_type=ResourceType.welfare_recipient,
        action_type=ActionType.create,
        request_data={
            "first_name": "新規",
            "last_name": "利用者",
            "first_name_furigana": "シンキ",
            "last_name_furigana": "リヨウシャ",
            "birth_day": "2000-01-01",
            "gender": "male"
        }
    )

    # リクエスト作成
    request = await employee_action_service.create_request(
        db=db,
        requester_staff_id=employee_id,
        office_id=office_id,
        obj_in=request_data
    )

    assert request is not None
    assert request.requester_staff_id == employee_id
    assert request.resource_type == ResourceType.welfare_recipient
    assert request.action_type == ActionType.create
    assert request.status == RequestStatus.pending
    assert request.request_data is not None


async def test_employee_update_welfare_recipient_request(
    db: AsyncSession,
    setup_office_with_staff: Tuple[UUID, UUID, UUID],
    setup_welfare_recipient: UUID
):
    """employeeがWelfareRecipient更新リクエスト"""
    office_id, manager_id, employee_id = setup_office_with_staff
    recipient_id = setup_welfare_recipient

    request_data = EmployeeActionRequestCreate(
        resource_type=ResourceType.welfare_recipient,
        action_type=ActionType.update,
        resource_id=recipient_id,
        request_data={
            "first_name": "更新後",
            "last_name": "太郎"
        }
    )

    request = await employee_action_service.create_request(
        db=db,
        requester_staff_id=employee_id,
        office_id=office_id,
        obj_in=request_data
    )

    assert request.resource_id == recipient_id
    assert request.action_type == ActionType.update


async def test_employee_delete_welfare_recipient_request(
    db: AsyncSession,
    setup_office_with_staff: Tuple[UUID, UUID, UUID],
    setup_welfare_recipient: UUID
):
    """employeeがWelfareRecipient削除リクエスト"""
    office_id, manager_id, employee_id = setup_office_with_staff
    recipient_id = setup_welfare_recipient

    request_data = EmployeeActionRequestCreate(
        resource_type=ResourceType.welfare_recipient,
        action_type=ActionType.delete,
        resource_id=recipient_id
    )

    request = await employee_action_service.create_request(
        db=db,
        requester_staff_id=employee_id,
        office_id=office_id,
        obj_in=request_data
    )

    assert request.action_type == ActionType.delete
    assert request.resource_id == recipient_id


# ===== 承認・アクション実行テスト =====

async def test_approve_create_request_executes_action(
    db: AsyncSession,
    setup_office_with_staff: Tuple[UUID, UUID, UUID]
):
    """作成リクエストの承認で実際に作成される"""
    office_id, manager_id, employee_id = setup_office_with_staff

    # リクエスト作成
    request_data = EmployeeActionRequestCreate(
        resource_type=ResourceType.welfare_recipient,
        action_type=ActionType.create,
        request_data={
            "first_name": "新規",
            "last_name": "利用者",
            "first_name_furigana": "シンキ",
            "last_name_furigana": "リヨウシャ",
            "birth_day": "2000-01-01",
            "gender": "male"
        }
    )

    request = await employee_action_service.create_request(
        db=db,
        requester_staff_id=employee_id,
        office_id=office_id,
        obj_in=request_data
    )

    # 承認処理
    approved_request = await employee_action_service.approve_request(
        db=db,
        request_id=request.id,
        approver_staff_id=manager_id,
        approver_notes="承認します"
    )

    assert approved_request.status == RequestStatus.approved
    assert approved_request.execution_result is not None
    assert approved_request.execution_result.get("success") is True

    # 実際にWelfareRecipientが作成されているか確認
    created_id = approved_request.execution_result.get("resource_id")
    assert created_id is not None

    from app.crud.crud_welfare_recipient import crud_welfare_recipient
    created_recipient = await crud_welfare_recipient.get(db, id=created_id)
    assert created_recipient is not None
    assert created_recipient.first_name == "新規"
    assert created_recipient.last_name == "利用者"


async def test_approve_update_request_executes_action(
    db: AsyncSession,
    setup_office_with_staff: Tuple[UUID, UUID, UUID],
    setup_welfare_recipient: UUID
):
    """更新リクエストの承認で実際に更新される"""
    office_id, manager_id, employee_id = setup_office_with_staff
    recipient_id = setup_welfare_recipient

    # リクエスト作成
    request_data = EmployeeActionRequestCreate(
        resource_type=ResourceType.welfare_recipient,
        action_type=ActionType.update,
        resource_id=recipient_id,
        request_data={
            "first_name": "更新後"
        }
    )

    request = await employee_action_service.create_request(
        db=db,
        requester_staff_id=employee_id,
        office_id=office_id,
        obj_in=request_data
    )

    # 承認処理
    approved_request = await employee_action_service.approve_request(
        db=db,
        request_id=request.id,
        approver_staff_id=manager_id
    )

    assert approved_request.status == RequestStatus.approved
    assert approved_request.execution_result.get("success") is True

    # 実際に更新されているか確認
    from app.crud.crud_welfare_recipient import crud_welfare_recipient
    updated_recipient = await crud_welfare_recipient.get(db, id=recipient_id)
    assert updated_recipient.first_name == "更新後"


async def test_approve_delete_request_executes_action(
    db: AsyncSession,
    setup_office_with_staff: Tuple[UUID, UUID, UUID],
    setup_welfare_recipient: UUID
):
    """削除リクエストの承認で実際に削除される"""
    office_id, manager_id, employee_id = setup_office_with_staff
    recipient_id = setup_welfare_recipient

    # リクエスト作成
    request_data = EmployeeActionRequestCreate(
        resource_type=ResourceType.welfare_recipient,
        action_type=ActionType.delete,
        resource_id=recipient_id
    )

    request = await employee_action_service.create_request(
        db=db,
        requester_staff_id=employee_id,
        office_id=office_id,
        obj_in=request_data
    )

    # 承認処理
    approved_request = await employee_action_service.approve_request(
        db=db,
        request_id=request.id,
        approver_staff_id=manager_id
    )

    assert approved_request.status == RequestStatus.approved
    assert approved_request.execution_result.get("success") is True

    # 実際に削除されているか確認
    from app.crud.crud_welfare_recipient import crud_welfare_recipient
    deleted_recipient = await crud_welfare_recipient.get(db, id=recipient_id)
    assert deleted_recipient is None


# ===== 却下テスト =====

async def test_reject_request_no_action(
    db: AsyncSession,
    setup_office_with_staff: Tuple[UUID, UUID, UUID]
):
    """却下時はアクションが実行されない"""
    office_id, manager_id, employee_id = setup_office_with_staff

    # リクエスト作成
    request_data = EmployeeActionRequestCreate(
        resource_type=ResourceType.welfare_recipient,
        action_type=ActionType.create,
        request_data={
            "first_name": "新規",
            "last_name": "利用者",
            "first_name_furigana": "シンキ",
            "last_name_furigana": "リヨウシャ",
            "birth_day": "2000-01-01",
            "gender": "male"
        }
    )

    request = await employee_action_service.create_request(
        db=db,
        requester_staff_id=employee_id,
        office_id=office_id,
        obj_in=request_data
    )

    # 却下処理
    rejected_request = await employee_action_service.reject_request(
        db=db,
        request_id=request.id,
        approver_staff_id=manager_id,
        approver_notes="却下します"
    )

    assert rejected_request.status == RequestStatus.rejected
    assert rejected_request.execution_result is None


# ===== エラーハンドリングテスト =====

async def test_approval_execution_error_stored(
    db: AsyncSession,
    setup_office_with_staff: Tuple[UUID, UUID, UUID]
):
    """アクション実行エラーがリクエストに記録される"""
    office_id, manager_id, employee_id = setup_office_with_staff

    # 不正なデータでリクエスト作成（birth_dayが不正な形式）
    request_data = EmployeeActionRequestCreate(
        resource_type=ResourceType.welfare_recipient,
        action_type=ActionType.create,
        request_data={
            "first_name": "新規",
            "last_name": "利用者",
            # 必須フィールドが不足している
        }
    )

    request = await employee_action_service.create_request(
        db=db,
        requester_staff_id=employee_id,
        office_id=office_id,
        obj_in=request_data
    )

    # 承認処理（エラーが発生するはず）
    approved_request = await employee_action_service.approve_request(
        db=db,
        request_id=request.id,
        approver_staff_id=manager_id
    )

    # エラーが記録されているか確認
    assert approved_request.execution_result is not None
    assert approved_request.execution_result.get("success") is False
    assert approved_request.execution_result.get("error") is not None


# ===== MissingGreenlet対策テスト =====

async def test_no_missing_greenlet_after_approve_action(
    db: AsyncSession,
    setup_office_with_staff: Tuple[UUID, UUID, UUID]
):
    """
    承認後にオブジェクトの属性にアクセスしてもMissingGreenletエラーが発生しない
    （コミット・リフレッシュ処理が正しく行われているか確認）
    """
    office_id, manager_id, employee_id = setup_office_with_staff

    # リクエスト作成
    request_data = EmployeeActionRequestCreate(
        resource_type=ResourceType.welfare_recipient,
        action_type=ActionType.create,
        request_data={
            "first_name": "新規",
            "last_name": "利用者",
            "first_name_furigana": "シンキ",
            "last_name_furigana": "リヨウシャ",
            "birth_day": "2000-01-01",
            "gender": "male"
        }
    )

    request = await employee_action_service.create_request(
        db=db,
        requester_staff_id=employee_id,
        office_id=office_id,
        obj_in=request_data
    )

    # 承認処理
    approved_request = await employee_action_service.approve_request(
        db=db,
        request_id=request.id,
        approver_staff_id=manager_id,
        approver_notes="承認します"
    )

    # コミット後にリレーションシップにアクセスしてもエラーが発生しないことを確認
    assert approved_request.requester is not None
    assert approved_request.requester.id == employee_id
    assert approved_request.approver is not None
    assert approved_request.approver.id == manager_id
    assert approved_request.office is not None
    assert approved_request.office.id == office_id

    # 実行結果が正しく記録されているか確認
    assert approved_request.execution_result is not None
    assert approved_request.execution_result.get("success") is True


async def test_no_missing_greenlet_after_reject_action(
    db: AsyncSession,
    setup_office_with_staff: Tuple[UUID, UUID, UUID]
):
    """
    却下後にオブジェクトの属性にアクセスしてもMissingGreenletエラーが発生しない
    """
    office_id, manager_id, employee_id = setup_office_with_staff

    # リクエスト作成
    request_data = EmployeeActionRequestCreate(
        resource_type=ResourceType.welfare_recipient,
        action_type=ActionType.create,
        request_data={
            "first_name": "新規",
            "last_name": "利用者",
            "first_name_furigana": "シンキ",
            "last_name_furigana": "リヨウシャ",
            "birth_day": "2000-01-01",
            "gender": "male"
        }
    )

    request = await employee_action_service.create_request(
        db=db,
        requester_staff_id=employee_id,
        office_id=office_id,
        obj_in=request_data
    )

    # 却下処理
    rejected_request = await employee_action_service.reject_request(
        db=db,
        request_id=request.id,
        approver_staff_id=manager_id,
        approver_notes="却下します"
    )

    # コミット後にリレーションシップにアクセスしてもエラーが発生しないことを確認
    assert rejected_request.requester is not None
    assert rejected_request.requester.id == employee_id
    assert rejected_request.approver is not None
    assert rejected_request.approver.id == manager_id
    assert rejected_request.office is not None
    assert rejected_request.office.id == office_id


# ===== 通知機能テスト =====

async def test_create_employee_action_request_creates_notification(
    db: AsyncSession,
    setup_office_with_staff: Tuple[UUID, UUID, UUID]
):
    """
    Employee制限リクエスト作成時に承認者（manager/owner）への通知が作成される
    """
    office_id, manager_id, employee_id = setup_office_with_staff

    # リクエスト作成
    request_data = EmployeeActionRequestCreate(
        resource_type=ResourceType.welfare_recipient,
        action_type=ActionType.create,
        request_data={
            "first_name": "新規",
            "last_name": "利用者",
            "first_name_furigana": "シンキ",
            "last_name_furigana": "リヨウシャ",
            "birth_day": "2000-01-01",
            "gender": "male"
        }
    )

    request = await employee_action_service.create_request(
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
    assert notice.notice_type == NoticeType.employee_action_pending
    assert notice.recipient_staff_id == manager_id
    assert notice.office_id == office_id
    assert notice.is_read is False
    # 詳細情報（利用者名）が含まれていることを確認
    assert "利用者" in notice.content
    assert "作成" in notice.content
    assert "リクエスト" in notice.content


async def test_approve_employee_action_request_creates_notification(
    db: AsyncSession,
    setup_office_with_staff: Tuple[UUID, UUID, UUID]
):
    """
    Employee制限リクエスト承認時にリクエスト作成者への通知が作成される
    """
    office_id, manager_id, employee_id = setup_office_with_staff

    # リクエスト作成
    request_data = EmployeeActionRequestCreate(
        resource_type=ResourceType.welfare_recipient,
        action_type=ActionType.create,
        request_data={
            "first_name": "新規",
            "last_name": "利用者",
            "first_name_furigana": "シンキ",
            "last_name_furigana": "リヨウシャ",
            "birth_day": "2000-01-01",
            "gender": "male"
        }
    )

    request = await employee_action_service.create_request(
        db=db,
        requester_staff_id=employee_id,
        office_id=office_id,
        obj_in=request_data
    )

    # 承認処理
    await employee_action_service.approve_request(
        db=db,
        request_id=request.id,
        approver_staff_id=manager_id,
        approver_notes="承認します"
    )

    # 通知が作成されているか確認
    from app.crud.crud_notice import crud_notice
    from app.models.enums import NoticeType

    # Employee（リクエスト作成者）宛の通知を確認
    employee_notices = await crud_notice.get_unread_by_staff_id(db, staff_id=employee_id)

    # 承認通知を探す
    approval_notices = [n for n in employee_notices if n.notice_type == NoticeType.employee_action_approved]
    assert len(approval_notices) > 0

    # 通知の内容を確認
    notice = approval_notices[0]
    assert notice.recipient_staff_id == employee_id
    assert notice.office_id == office_id
    assert notice.is_read is False
    assert "承認" in notice.content or "approved" in notice.content.lower()


async def test_reject_employee_action_request_creates_notification(
    db: AsyncSession,
    setup_office_with_staff: Tuple[UUID, UUID, UUID]
):
    """
    Employee制限リクエスト却下時にリクエスト作成者への通知が作成される
    """
    office_id, manager_id, employee_id = setup_office_with_staff

    # リクエスト作成
    request_data = EmployeeActionRequestCreate(
        resource_type=ResourceType.welfare_recipient,
        action_type=ActionType.create,
        request_data={
            "first_name": "新規",
            "last_name": "利用者",
            "first_name_furigana": "シンキ",
            "last_name_furigana": "リヨウシャ",
            "birth_day": "2000-01-01",
            "gender": "male"
        }
    )

    request = await employee_action_service.create_request(
        db=db,
        requester_staff_id=employee_id,
        office_id=office_id,
        obj_in=request_data
    )

    # 却下処理
    await employee_action_service.reject_request(
        db=db,
        request_id=request.id,
        approver_staff_id=manager_id,
        approver_notes="却下します"
    )

    # 通知が作成されているか確認
    from app.crud.crud_notice import crud_notice
    from app.models.enums import NoticeType

    # Employee（リクエスト作成者）宛の通知を確認
    employee_notices = await crud_notice.get_unread_by_staff_id(db, staff_id=employee_id)

    # 却下通知を探す
    rejection_notices = [n for n in employee_notices if n.notice_type == NoticeType.employee_action_rejected]
    assert len(rejection_notices) > 0

    # 通知の内容を確認
    notice = rejection_notices[0]
    assert notice.recipient_staff_id == employee_id
    assert notice.office_id == office_id
    assert notice.is_read is False
    assert "却下" in notice.content or "rejected" in notice.content.lower()


# ===== 通知詳細情報テスト =====

async def test_notification_includes_welfare_recipient_full_name_for_create(
    db: AsyncSession,
    setup_office_with_staff: Tuple[UUID, UUID, UUID]
):
    """
    利用者作成リクエストの通知に利用者のフルネームが含まれる
    """
    office_id, manager_id, employee_id = setup_office_with_staff

    # リクエスト作成（利用者のフルネーム情報を含む）
    request_data = EmployeeActionRequestCreate(
        resource_type=ResourceType.welfare_recipient,
        action_type=ActionType.create,
        request_data={
            "first_name": "太郎",
            "last_name": "山田",
            "full_name": "山田 太郎",  # フルネームを含める
            "first_name_furigana": "タロウ",
            "last_name_furigana": "ヤマダ",
            "birth_day": "1990-05-15",
            "gender": "male"
        }
    )

    request = await employee_action_service.create_request(
        db=db,
        requester_staff_id=employee_id,
        office_id=office_id,
        obj_in=request_data
    )

    # 通知を取得
    from app.crud.crud_notice import crud_notice

    manager_notices = await crud_notice.get_unread_by_staff_id(db, staff_id=manager_id)
    assert len(manager_notices) > 0

    notice = manager_notices[0]

    # 通知contentに利用者のフルネームが含まれていることを確認
    assert "山田 太郎" in notice.content or "山田太郎" in notice.content, \
        f"Expected full_name '山田 太郎' in notice content, but got: {notice.content}"

    # 基本的な通知内容も確認
    assert "利用者" in notice.content
    assert "作成" in notice.content


async def test_notification_includes_welfare_recipient_full_name_for_update(
    db: AsyncSession,
    setup_office_with_staff: Tuple[UUID, UUID, UUID],
    setup_welfare_recipient: UUID
):
    """
    利用者更新リクエストの通知に利用者のフルネームが含まれる
    """
    office_id, manager_id, employee_id = setup_office_with_staff
    recipient_id = setup_welfare_recipient

    # リクエスト作成
    request_data = EmployeeActionRequestCreate(
        resource_type=ResourceType.welfare_recipient,
        action_type=ActionType.update,
        resource_id=recipient_id,
        request_data={
            "first_name": "次郎",
            "last_name": "鈴木",
            "full_name": "鈴木 次郎"
        }
    )

    request = await employee_action_service.create_request(
        db=db,
        requester_staff_id=employee_id,
        office_id=office_id,
        obj_in=request_data
    )

    # 通知を取得
    from app.crud.crud_notice import crud_notice

    manager_notices = await crud_notice.get_unread_by_staff_id(db, staff_id=manager_id)
    assert len(manager_notices) > 0

    notice = manager_notices[0]

    # 通知contentに利用者のフルネームが含まれていることを確認
    assert "鈴木 次郎" in notice.content or "鈴木次郎" in notice.content, \
        f"Expected full_name '鈴木 次郎' in notice content, but got: {notice.content}"

    # 基本的な通知内容も確認
    assert "利用者" in notice.content
    assert "更新" in notice.content or "編集" in notice.content


async def test_notification_without_full_name_shows_basic_info(
    db: AsyncSession,
    setup_office_with_staff: Tuple[UUID, UUID, UUID]
):
    """
    full_nameが無い場合でも通知が生成される（基本情報のみ）
    """
    office_id, manager_id, employee_id = setup_office_with_staff

    # full_nameを含まないリクエスト
    request_data = EmployeeActionRequestCreate(
        resource_type=ResourceType.welfare_recipient,
        action_type=ActionType.create,
        request_data={
            "first_name": "花子",
            "last_name": "佐藤",
            "first_name_furigana": "ハナコ",
            "last_name_furigana": "サトウ",
            "birth_day": "1995-03-20",
            "gender": "female"
            # full_nameは含まれていない
        }
    )

    request = await employee_action_service.create_request(
        db=db,
        requester_staff_id=employee_id,
        office_id=office_id,
        obj_in=request_data
    )

    # 通知を取得
    from app.crud.crud_notice import crud_notice

    manager_notices = await crud_notice.get_unread_by_staff_id(db, staff_id=manager_id)
    assert len(manager_notices) > 0

    notice = manager_notices[0]

    # 基本的な通知内容を確認（full_nameが無くてもエラーにならない）
    assert "利用者" in notice.content
    assert "作成" in notice.content
    assert notice.content is not None
    assert len(notice.content) > 0


async def test_notification_includes_support_plan_status_details_for_create(
    db: AsyncSession,
    setup_office_with_staff: Tuple[UUID, UUID, UUID],
    setup_welfare_recipient: UUID
):
    """
    サポート計画ステータス作成リクエストの通知に利用者名とステップタイプが含まれる

    修正前: "あ あさんがサポート計画ステータスの作成をリクエストしました。"
    修正後: "あ あさんが山田 太郎さんのアセスメント情報の作成をリクエストしました。"
    """
    office_id, manager_id, employee_id = setup_office_with_staff
    recipient_id = setup_welfare_recipient

    # サポート計画ステータス作成リクエスト（アセスメント）
    request_data = EmployeeActionRequestCreate(
        resource_type=ResourceType.support_plan_status,
        action_type=ActionType.create,
        request_data={
            "welfare_recipient_id": str(recipient_id),
            "welfare_recipient_full_name": "山田 太郎",
            "step_type": "assessment"  # アセスメント
        }
    )

    request = await employee_action_service.create_request(
        db=db,
        requester_staff_id=employee_id,
        office_id=office_id,
        obj_in=request_data
    )

    # 通知を取得
    from app.crud.crud_notice import crud_notice

    manager_notices = await crud_notice.get_unread_by_staff_id(db, staff_id=manager_id)
    assert len(manager_notices) > 0

    notice = manager_notices[0]

    # 通知contentに利用者名が含まれていることを確認
    assert "山田 太郎" in notice.content or "山田太郎" in notice.content, \
        f"Expected recipient name '山田 太郎' in notice content, but got: {notice.content}"

    # ステップタイプの日本語名が含まれていることを確認
    assert "アセスメント" in notice.content, \
        f"Expected step type 'アセスメント' in notice content, but got: {notice.content}"

    # 基本的な通知内容も確認
    assert "作成" in notice.content


async def test_notification_includes_support_plan_status_step_type_variations(
    db: AsyncSession,
    setup_office_with_staff: Tuple[UUID, UUID, UUID],
    setup_welfare_recipient: UUID
):
    """
    サポート計画ステータスの各ステップタイプが適切に日本語化される
    """
    office_id, manager_id, employee_id = setup_office_with_staff
    recipient_id = setup_welfare_recipient

    # 異なるステップタイプでテスト
    step_type_tests = [
        ("assessment", "アセスメント"),
        ("draft_plan", "計画案"),
        ("staff_meeting", "職員会議"),
        ("final_plan_signed", "最終計画"),
        ("monitoring", "モニタリング")
    ]

    from app.crud.crud_notice import crud_notice

    for step_type, expected_ja in step_type_tests:
        # リクエスト作成
        request_data = EmployeeActionRequestCreate(
            resource_type=ResourceType.support_plan_status,
            action_type=ActionType.create,
            request_data={
                "welfare_recipient_id": str(recipient_id),
                "welfare_recipient_full_name": "テスト 利用者",
                "step_type": step_type
            }
        )

        request = await employee_action_service.create_request(
            db=db,
            requester_staff_id=employee_id,
            office_id=office_id,
            obj_in=request_data
        )

        # 通知を取得
        manager_notices = await crud_notice.get_unread_by_staff_id(db, staff_id=manager_id)

        # 最新の通知を確認
        latest_notice = manager_notices[0]

        # ステップタイプの日本語名が含まれていることを確認
        assert expected_ja in latest_notice.content, \
            f"Expected '{expected_ja}' for step_type '{step_type}' in notice content, but got: {latest_notice.content}"

        # 利用者名も含まれていることを確認
        assert "テスト 利用者" in latest_notice.content or "テスト利用者" in latest_notice.content
