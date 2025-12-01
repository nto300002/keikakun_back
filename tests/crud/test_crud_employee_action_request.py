"""
EmployeeActionRequest (Employee制限リクエスト) CRUDのテスト
TDD方式でテストを先に作成

注意: このテストは非推奨です。統合approval_requests CRUDテストを使用してください。
テストは tests/crud/test_crud_approval_request.py に移行済み（13テスト全てパス）
"""
from sqlalchemy.ext.asyncio import AsyncSession
import pytest
import uuid

from app import crud
from app.models.enums import RequestStatus, ActionType, ResourceType
from app.schemas.employee_action_request import EmployeeActionRequestCreate

# 旧employee_action_requests CRUDは非推奨。統合approval_request CRUDを使用
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skip(reason="旧employee_action_requests CRUDは削除済み。tests/crud/test_crud_approval_request.py を使用")
]


async def test_create_employee_action_request_welfare_recipient_create(
    db_session: AsyncSession,
    employee_user_factory
) -> None:
    """
    WelfareRecipient作成のEmployee制限リクエスト作成テスト
    """
    employee = await employee_user_factory()
    office = employee.office_associations[0].office

    # WelfareRecipient作成リクエストデータ
    request_data = EmployeeActionRequestCreate(
        resource_type=ResourceType.welfare_recipient,
        action_type=ActionType.create,
        resource_id=None,  # createの場合はNone
        request_data={
            "last_name": "山田",
            "first_name": "太郎",
            "birth_day": "1990-01-01",
            "gender": "male"
        }
    )

    # リクエスト作成
    created_request = await crud.employee_action_request.create(
        db=db_session,
        obj_in=request_data,
        requester_staff_id=employee.id,
        office_id=office.id
    )

    assert created_request.id is not None
    assert created_request.requester_staff_id == employee.id
    assert created_request.office_id == office.id
    assert created_request.resource_type == ResourceType.welfare_recipient
    assert created_request.action_type == ActionType.create
    assert created_request.resource_id is None
    assert created_request.request_data["last_name"] == "山田"
    assert created_request.status == RequestStatus.pending


async def test_create_employee_action_request_welfare_recipient_update(
    db_session: AsyncSession,
    employee_user_factory
) -> None:
    """
    WelfareRecipient更新のEmployee制限リクエスト作成テスト
    """
    employee = await employee_user_factory()
    office = employee.office_associations[0].office

    resource_id = uuid.uuid4()

    # WelfareRecipient更新リクエストデータ
    request_data = EmployeeActionRequestCreate(
        resource_type=ResourceType.welfare_recipient,
        action_type=ActionType.update,
        resource_id=resource_id,
        request_data={"last_name": "田中"}
    )

    created_request = await crud.employee_action_request.create(
        db=db_session,
        obj_in=request_data,
        requester_staff_id=employee.id,
        office_id=office.id
    )

    assert created_request.action_type == ActionType.update
    assert created_request.resource_id == resource_id
    assert created_request.request_data["last_name"] == "田中"


async def test_create_employee_action_request_welfare_recipient_delete(
    db_session: AsyncSession,
    employee_user_factory
) -> None:
    """
    WelfareRecipient削除のEmployee制限リクエスト作成テスト
    """
    employee = await employee_user_factory()
    office = employee.office_associations[0].office

    resource_id = uuid.uuid4()

    # WelfareRecipient削除リクエストデータ
    request_data = EmployeeActionRequestCreate(
        resource_type=ResourceType.welfare_recipient,
        action_type=ActionType.delete,
        resource_id=resource_id,
        request_data=None  # deleteの場合はNone
    )

    created_request = await crud.employee_action_request.create(
        db=db_session,
        obj_in=request_data,
        requester_staff_id=employee.id,
        office_id=office.id
    )

    assert created_request.action_type == ActionType.delete
    assert created_request.resource_id == resource_id
    assert created_request.request_data is None


async def test_get_employee_action_request_by_id(
    db_session: AsyncSession,
    employee_user_factory
) -> None:
    """
    IDでEmployee制限リクエストを取得するテスト
    """
    employee = await employee_user_factory()
    office = employee.office_associations[0].office

    request_data = EmployeeActionRequestCreate(
        resource_type=ResourceType.support_plan_cycle,
        action_type=ActionType.create,
        request_data={
            "welfare_recipient_id": str(uuid.uuid4()),
            "cycle_start_date": "2025-01-01",
            "cycle_end_date": "2025-12-31"
        }
    )

    created_request = await crud.employee_action_request.create(
        db=db_session,
        obj_in=request_data,
        requester_staff_id=employee.id,
        office_id=office.id
    )

    # 取得
    retrieved_request = await crud.employee_action_request.get(
        db=db_session,
        id=created_request.id
    )

    assert retrieved_request is not None
    assert retrieved_request.id == created_request.id
    assert retrieved_request.resource_type == ResourceType.support_plan_cycle


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
    for action in [ActionType.create, ActionType.update, ActionType.delete]:
        request_data = EmployeeActionRequestCreate(
            resource_type=ResourceType.welfare_recipient,
            action_type=action,
            resource_id=uuid.uuid4() if action != ActionType.create else None,
            request_data={"test": "data"} if action != ActionType.delete else None
        )
        await crud.employee_action_request.create(
            db=db_session,
            obj_in=request_data,
            requester_staff_id=employee.id,
            office_id=office.id
        )

    # リクエスト作成者でリクエスト一覧を取得
    requests = await crud.employee_action_request.get_by_requester(
        db=db_session,
        requester_staff_id=employee.id
    )

    assert len(requests) == 3
    assert all(req.requester_staff_id == employee.id for req in requests)


async def test_get_pending_requests_for_approver(
    db_session: AsyncSession,
    employee_user_factory,
    manager_user_factory
) -> None:
    """
    Manager権限で承認可能なpendingリクエスト一覧を取得するテスト
    """
    employee = await employee_user_factory()
    office = employee.office_associations[0].office
    manager = await manager_user_factory(office=office)

    # employeeがCREATEリクエスト作成（managerが承認可能）
    request_data = EmployeeActionRequestCreate(
        resource_type=ResourceType.welfare_recipient,
        action_type=ActionType.create,
        request_data={"last_name": "山田", "first_name": "太郎"}
    )
    await crud.employee_action_request.create(
        db=db_session,
        obj_in=request_data,
        requester_staff_id=employee.id,
        office_id=office.id
    )

    # managerが承認可能なpendingリクエストを取得
    pending_requests = await crud.employee_action_request.get_pending_for_approver(
        db=db_session,
        office_id=office.id
    )

    assert len(pending_requests) >= 1
    assert all(req.status == RequestStatus.pending for req in pending_requests)
    assert all(req.office_id == office.id for req in pending_requests)


async def test_approve_employee_action_request(
    db_session: AsyncSession,
    employee_user_factory,
    manager_user_factory
) -> None:
    """
    Employee制限リクエスト承認テスト
    """
    employee = await employee_user_factory()
    office = employee.office_associations[0].office
    manager = await manager_user_factory(office=office)

    # リクエスト作成
    request_data = EmployeeActionRequestCreate(
        resource_type=ResourceType.welfare_recipient,
        action_type=ActionType.create,
        request_data={"last_name": "山田", "first_name": "太郎"}
    )
    created_request = await crud.employee_action_request.create(
        db=db_session,
        obj_in=request_data,
        requester_staff_id=employee.id,
        office_id=office.id
    )

    assert created_request.status == RequestStatus.pending

    # 承認処理（実際のアクション実行を含む）
    execution_result = {
        "success": True,
        "resource_id": str(uuid.uuid4()),
        "message": "正常に作成されました"
    }

    approved_request = await crud.employee_action_request.approve(
        db=db_session,
        request_id=created_request.id,
        approver_staff_id=manager.id,
        approver_notes="承認しました",
        execution_result=execution_result
    )

    assert approved_request.status == RequestStatus.approved
    assert approved_request.approved_by_staff_id == manager.id
    assert approved_request.approved_at is not None
    assert approved_request.approver_notes == "承認しました"
    assert approved_request.execution_result["success"] is True
    assert "resource_id" in approved_request.execution_result


async def test_reject_employee_action_request(
    db_session: AsyncSession,
    employee_user_factory,
    manager_user_factory
) -> None:
    """
    Employee制限リクエスト却下テスト
    """
    employee = await employee_user_factory()
    office = employee.office_associations[0].office
    manager = await manager_user_factory(office=office)

    # リクエスト作成
    request_data = EmployeeActionRequestCreate(
        resource_type=ResourceType.welfare_recipient,
        action_type=ActionType.delete,
        resource_id=uuid.uuid4()
    )
    created_request = await crud.employee_action_request.create(
        db=db_session,
        obj_in=request_data,
        requester_staff_id=employee.id,
        office_id=office.id
    )

    assert created_request.status == RequestStatus.pending

    # 却下処理
    rejected_request = await crud.employee_action_request.reject(
        db=db_session,
        request_id=created_request.id,
        approver_staff_id=manager.id,
        approver_notes="削除は承認できません"
    )

    assert rejected_request.status == RequestStatus.rejected
    assert rejected_request.approved_by_staff_id == manager.id
    assert rejected_request.approved_at is not None
    assert rejected_request.approver_notes == "削除は承認できません"
    assert rejected_request.execution_result is None  # 却下時は実行されない


async def test_get_requests_by_resource_type(
    db_session: AsyncSession,
    employee_user_factory
) -> None:
    """
    リソースタイプでフィルタリングしてリクエストを取得するテスト
    """
    employee = await employee_user_factory()
    office = employee.office_associations[0].office

    # 異なるリソースタイプのリクエストを作成
    for resource_type in [
        ResourceType.welfare_recipient,
        ResourceType.support_plan_cycle,
        ResourceType.support_plan_status
    ]:
        request_data = EmployeeActionRequestCreate(
            resource_type=resource_type,
            action_type=ActionType.create,
            request_data={"test": "data"}
        )
        await crud.employee_action_request.create(
            db=db_session,
            obj_in=request_data,
            requester_staff_id=employee.id,
            office_id=office.id
        )

    # welfare_recipientタイプのみ取得
    welfare_requests = await crud.employee_action_request.get_by_resource_type(
        db=db_session,
        office_id=office.id,
        resource_type=ResourceType.welfare_recipient
    )

    assert len(welfare_requests) >= 1
    assert all(req.resource_type == ResourceType.welfare_recipient for req in welfare_requests)


async def test_get_requests_by_action_type(
    db_session: AsyncSession,
    employee_user_factory
) -> None:
    """
    アクションタイプでフィルタリングしてリクエストを取得するテスト
    """
    employee = await employee_user_factory()
    office = employee.office_associations[0].office

    # 異なるアクションタイプのリクエストを作成
    for action_type in [ActionType.create, ActionType.update, ActionType.delete]:
        request_data = EmployeeActionRequestCreate(
            resource_type=ResourceType.welfare_recipient,
            action_type=action_type,
            resource_id=uuid.uuid4() if action_type != ActionType.create else None,
            request_data={"test": "data"} if action_type != ActionType.delete else None
        )
        await crud.employee_action_request.create(
            db=db_session,
            obj_in=request_data,
            requester_staff_id=employee.id,
            office_id=office.id
        )

    # createタイプのみ取得
    create_requests = await crud.employee_action_request.get_by_action_type(
        db=db_session,
        office_id=office.id,
        action_type=ActionType.create
    )

    assert len(create_requests) >= 1
    assert all(req.action_type == ActionType.create for req in create_requests)


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
    pending_request_data = EmployeeActionRequestCreate(
        resource_type=ResourceType.welfare_recipient,
        action_type=ActionType.create,
        request_data={"test": "pending"}
    )
    await crud.employee_action_request.create(
        db=db_session,
        obj_in=pending_request_data,
        requester_staff_id=employee.id,
        office_id=office.id
    )

    # approved リクエスト作成と承認
    approved_request_data = EmployeeActionRequestCreate(
        resource_type=ResourceType.welfare_recipient,
        action_type=ActionType.create,
        request_data={"test": "approved"}
    )
    approved_request = await crud.employee_action_request.create(
        db=db_session,
        obj_in=approved_request_data,
        requester_staff_id=employee.id,
        office_id=office.id
    )
    await crud.employee_action_request.approve(
        db=db_session,
        request_id=approved_request.id,
        approver_staff_id=manager.id,
        approver_notes="承認",
        execution_result={"success": True}
    )

    # pending ステータスのリクエストのみ取得
    pending_requests = await crud.employee_action_request.get_by_status(
        db=db_session,
        office_id=office.id,
        status=RequestStatus.pending
    )

    assert len(pending_requests) >= 1
    assert all(req.status == RequestStatus.pending for req in pending_requests)


async def test_delete_employee_action_request(
    db_session: AsyncSession,
    employee_user_factory
) -> None:
    """
    Employee制限リクエスト削除テスト（pending状態のみ削除可能）
    """
    employee = await employee_user_factory()
    office = employee.office_associations[0].office

    request_data = EmployeeActionRequestCreate(
        resource_type=ResourceType.welfare_recipient,
        action_type=ActionType.create,
        request_data={"test": "delete"}
    )
    created_request = await crud.employee_action_request.create(
        db=db_session,
        obj_in=request_data,
        requester_staff_id=employee.id,
        office_id=office.id
    )

    request_id = created_request.id

    # 削除
    removed_request = await crud.employee_action_request.remove(
        db=db_session,
        id=request_id
    )

    assert removed_request is not None
    assert removed_request.id == request_id

    # 削除後に取得できないことを確認
    deleted_request = await crud.employee_action_request.get(
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
    request_data = EmployeeActionRequestCreate(
        resource_type=ResourceType.welfare_recipient,
        action_type=ActionType.create,
        request_data={"test": "duplicate"}
    )
    created_request = await crud.employee_action_request.create(
        db=db_session,
        obj_in=request_data,
        requester_staff_id=employee.id,
        office_id=office.id
    )

    # 1回目の承認
    await crud.employee_action_request.approve(
        db=db_session,
        request_id=created_request.id,
        approver_staff_id=manager.id,
        approver_notes="1回目の承認",
        execution_result={"success": True}
    )

    # 2回目の承認（エラーになるべき）
    with pytest.raises(Exception):  # 適切な例外型に置き換える
        await crud.employee_action_request.approve(
            db=db_session,
            request_id=created_request.id,
            approver_staff_id=manager.id,
            approver_notes="2回目の承認",
            execution_result={"success": True}
        )
