import pytest
from pydantic import ValidationError
from datetime import datetime
import uuid

from app.schemas.employee_action_request import (
    EmployeeActionRequestBase,
    EmployeeActionRequestCreate,
    EmployeeActionRequestRead,
    EmployeeActionRequestApprove,
    EmployeeActionRequestReject,
)
from app.models.enums import (
    RequestStatus,
    ActionType,
    ResourceType,
)


class TestEmployeeActionRequestBase:
    """EmployeeActionRequestBaseスキーマのテスト"""

    def test_employee_action_request_base_valid(self):
        """正常なデータでEmployeeActionRequestBaseモデルが作成できることをテスト"""
        valid_data = {
            "resource_type": ResourceType.welfare_recipient,
            "action_type": ActionType.create,
            "resource_id": None,
            "request_data": {"last_name": "山田", "first_name": "太郎"}
        }
        schema = EmployeeActionRequestBase(**valid_data)
        assert schema.resource_type == ResourceType.welfare_recipient
        assert schema.action_type == ActionType.create
        assert schema.resource_id is None
        assert schema.request_data == {"last_name": "山田", "first_name": "太郎"}

    def test_employee_action_request_base_with_resource_id(self):
        """resource_idありでEmployeeActionRequestBaseモデルが作成できることをテスト"""
        resource_id = uuid.uuid4()
        valid_data = {
            "resource_type": ResourceType.welfare_recipient,
            "action_type": ActionType.update,
            "resource_id": resource_id,
            "request_data": {"last_name": "田中"}
        }
        schema = EmployeeActionRequestBase(**valid_data)
        assert schema.resource_id == resource_id
        assert schema.action_type == ActionType.update

    def test_employee_action_request_base_delete_action(self):
        """DELETE actionの場合のEmployeeActionRequestBaseモデルテスト"""
        resource_id = uuid.uuid4()
        valid_data = {
            "resource_type": ResourceType.welfare_recipient,
            "action_type": ActionType.delete,
            "resource_id": resource_id,
            "request_data": None
        }
        schema = EmployeeActionRequestBase(**valid_data)
        assert schema.action_type == ActionType.delete
        assert schema.request_data is None

    def test_employee_action_request_base_invalid_resource_type(self):
        """無効なresource_typeでValidationErrorが発生することをテスト"""
        invalid_data = {
            "resource_type": "invalid_type",
            "action_type": ActionType.create
        }
        with pytest.raises(ValidationError) as exc_info:
            EmployeeActionRequestBase(**invalid_data)
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("resource_type",) for error in errors)

    def test_employee_action_request_base_invalid_action_type(self):
        """無効なaction_typeでValidationErrorが発生することをテスト"""
        invalid_data = {
            "resource_type": ResourceType.welfare_recipient,
            "action_type": "invalid_action"
        }
        with pytest.raises(ValidationError) as exc_info:
            EmployeeActionRequestBase(**invalid_data)
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("action_type",) for error in errors)


class TestEmployeeActionRequestCreate:
    """EmployeeActionRequestCreateスキーマのテスト"""

    def test_employee_action_request_create_welfare_recipient(self):
        """WelfareRecipient作成リクエストのテスト"""
        valid_data = {
            "resource_type": ResourceType.welfare_recipient,
            "action_type": ActionType.create,
            "request_data": {
                "last_name": "山田",
                "first_name": "太郎",
                "birth_day": "1990-01-01",
                "gender": "male"
            }
        }
        schema = EmployeeActionRequestCreate(**valid_data)
        assert schema.resource_type == ResourceType.welfare_recipient
        assert schema.action_type == ActionType.create
        assert schema.request_data["last_name"] == "山田"

    def test_employee_action_request_create_support_plan_cycle(self):
        """SupportPlanCycle作成リクエストのテスト"""
        valid_data = {
            "resource_type": ResourceType.support_plan_cycle,
            "action_type": ActionType.create,
            "request_data": {
                "welfare_recipient_id": str(uuid.uuid4()),
                "cycle_start_date": "2025-01-01",
                "cycle_end_date": "2025-12-31"
            }
        }
        schema = EmployeeActionRequestCreate(**valid_data)
        assert schema.resource_type == ResourceType.support_plan_cycle
        assert "welfare_recipient_id" in schema.request_data

    def test_employee_action_request_create_support_plan_status(self):
        """SupportPlanStatus更新リクエストのテスト"""
        resource_id = uuid.uuid4()
        valid_data = {
            "resource_type": ResourceType.support_plan_status,
            "action_type": ActionType.update,
            "resource_id": resource_id,
            "request_data": {"status": "completed"}
        }
        schema = EmployeeActionRequestCreate(**valid_data)
        assert schema.resource_type == ResourceType.support_plan_status
        assert schema.action_type == ActionType.update
        assert schema.resource_id == resource_id

    def test_employee_action_request_create_missing_required_field(self):
        """必須フィールドが不足している場合にValidationErrorが発生することをテスト"""
        invalid_data = {
            "action_type": ActionType.create
            # resource_typeが欠落
        }
        with pytest.raises(ValidationError) as exc_info:
            EmployeeActionRequestCreate(**invalid_data)
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("resource_type",) for error in errors)


class TestEmployeeActionRequestRead:
    """EmployeeActionRequestReadスキーマのテスト"""

    def test_employee_action_request_read_pending(self):
        """pending状態のEmployeeActionRequestReadモデルが作成できることをテスト"""
        valid_data = {
            "id": str(uuid.uuid4()),
            "requester_staff_id": str(uuid.uuid4()),
            "office_id": str(uuid.uuid4()),
            "resource_type": ResourceType.welfare_recipient,
            "action_type": ActionType.create,
            "resource_id": None,
            "request_data": {"last_name": "山田", "first_name": "太郎"},
            "status": RequestStatus.pending,
            "reviewed_by_staff_id": None,
            "reviewed_at": None,
            "reviewer_notes": None,
            "execution_result": None,
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        }
        schema = EmployeeActionRequestRead(**valid_data)
        assert schema.status == RequestStatus.pending
        assert schema.reviewed_by_staff_id is None
        assert schema.execution_result is None

    def test_employee_action_request_read_approved(self):
        """approved状態のEmployeeActionRequestReadモデルが作成できることをテスト"""
        approver_id = uuid.uuid4()
        approved_at = datetime.now()
        valid_data = {
            "id": str(uuid.uuid4()),
            "requester_staff_id": str(uuid.uuid4()),
            "office_id": str(uuid.uuid4()),
            "resource_type": ResourceType.welfare_recipient,
            "action_type": ActionType.create,
            "resource_id": None,
            "request_data": {"last_name": "山田", "first_name": "太郎"},
            "status": RequestStatus.approved,
            "reviewed_by_staff_id": str(approver_id),
            "reviewed_at": approved_at,
            "reviewer_notes": "承認しました",
            "execution_result": {
                "success": True,
                "resource_id": str(uuid.uuid4()),
                "message": "正常に作成されました"
            },
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        }
        schema = EmployeeActionRequestRead(**valid_data)
        assert schema.status == RequestStatus.approved
        assert schema.reviewed_by_staff_id == approver_id
        assert schema.execution_result["success"] is True
        assert "resource_id" in schema.execution_result

    def test_employee_action_request_read_rejected(self):
        """rejected状態のEmployeeActionRequestReadモデルが作成できることをテスト"""
        valid_data = {
            "id": str(uuid.uuid4()),
            "requester_staff_id": str(uuid.uuid4()),
            "office_id": str(uuid.uuid4()),
            "resource_type": ResourceType.welfare_recipient,
            "action_type": ActionType.delete,
            "resource_id": str(uuid.uuid4()),
            "request_data": None,
            "status": RequestStatus.rejected,
            "reviewed_by_staff_id": str(uuid.uuid4()),
            "reviewed_at": datetime.now(),
            "reviewer_notes": "削除は承認できません",
            "execution_result": None,
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        }
        schema = EmployeeActionRequestRead(**valid_data)
        assert schema.status == RequestStatus.rejected
        assert schema.reviewer_notes == "削除は承認できません"
        assert schema.execution_result is None

    def test_employee_action_request_read_from_attributes(self):
        """from_attributes=Trueが設定されていることをテスト"""
        assert EmployeeActionRequestRead.model_config.get("from_attributes") is True


class TestEmployeeActionRequestApprove:
    """EmployeeActionRequestApproveスキーマのテスト"""

    def test_employee_action_request_approve_with_notes(self):
        """approver_notesありでEmployeeActionRequestApproveモデルが作成できることをテスト"""
        valid_data = {
            "approver_notes": "承認しました"
        }
        schema = EmployeeActionRequestApprove(**valid_data)
        assert schema.approver_notes == "承認しました"

    def test_employee_action_request_approve_without_notes(self):
        """approver_notesなしでEmployeeActionRequestApproveモデルが作成できることをテスト"""
        valid_data = {}
        schema = EmployeeActionRequestApprove(**valid_data)
        assert schema.approver_notes is None

    def test_employee_action_request_approve_empty_notes(self):
        """空のapprover_notesでもEmployeeActionRequestApproveモデルが作成できることをテスト"""
        valid_data = {
            "approver_notes": ""
        }
        schema = EmployeeActionRequestApprove(**valid_data)
        assert schema.approver_notes == ""


class TestEmployeeActionRequestReject:
    """EmployeeActionRequestRejectスキーマのテスト"""

    def test_employee_action_request_reject_with_notes(self):
        """approver_notesありでEmployeeActionRequestRejectモデルが作成できることをテスト"""
        valid_data = {
            "approver_notes": "データが不正確なため承認できません"
        }
        schema = EmployeeActionRequestReject(**valid_data)
        assert schema.approver_notes == "データが不正確なため承認できません"

    def test_employee_action_request_reject_without_notes(self):
        """approver_notesなしでEmployeeActionRequestRejectモデルが作成できることをテスト"""
        valid_data = {}
        schema = EmployeeActionRequestReject(**valid_data)
        assert schema.approver_notes is None

    def test_employee_action_request_reject_detailed_notes(self):
        """詳細なapprover_notesでEmployeeActionRequestRejectモデルが作成できることをテスト"""
        valid_data = {
            "approver_notes": "入力されたデータに不備があります。生年月日と住所を確認してください。"
        }
        schema = EmployeeActionRequestReject(**valid_data)
        assert schema.approver_notes == "入力されたデータに不備があります。生年月日と住所を確認してください。"


class TestEmployeeActionRequestValidation:
    """EmployeeActionRequestの複雑なバリデーションテスト"""

    def test_create_action_without_resource_id(self):
        """CREATE actionではresource_idがNoneであることをテスト"""
        valid_data = {
            "resource_type": ResourceType.welfare_recipient,
            "action_type": ActionType.create,
            "resource_id": None,
            "request_data": {"last_name": "山田"}
        }
        schema = EmployeeActionRequestCreate(**valid_data)
        assert schema.resource_id is None

    def test_update_action_with_resource_id(self):
        """UPDATE actionではresource_idが必要であることをテスト"""
        resource_id = uuid.uuid4()
        valid_data = {
            "resource_type": ResourceType.welfare_recipient,
            "action_type": ActionType.update,
            "resource_id": resource_id,
            "request_data": {"last_name": "田中"}
        }
        schema = EmployeeActionRequestCreate(**valid_data)
        assert schema.resource_id == resource_id

    def test_delete_action_with_resource_id_without_data(self):
        """DELETE actionではresource_idが必要でrequest_dataは不要であることをテスト"""
        resource_id = uuid.uuid4()
        valid_data = {
            "resource_type": ResourceType.welfare_recipient,
            "action_type": ActionType.delete,
            "resource_id": resource_id,
            "request_data": None
        }
        schema = EmployeeActionRequestCreate(**valid_data)
        assert schema.resource_id == resource_id
        assert schema.request_data is None

    def test_complex_request_data(self):
        """複雑なrequest_dataの保存テスト"""
        complex_data = {
            "last_name": "山田",
            "first_name": "太郎",
            "birth_day": "1990-01-01",
            "gender": "male",
            "address": {
                "postal_code": "123-4567",
                "prefecture": "東京都",
                "city": "渋谷区"
            },
            "disabilities": [
                {"type": "physical", "grade": "1"},
                {"type": "mental", "grade": "2"}
            ]
        }
        valid_data = {
            "resource_type": ResourceType.welfare_recipient,
            "action_type": ActionType.create,
            "request_data": complex_data
        }
        schema = EmployeeActionRequestCreate(**valid_data)
        assert schema.request_data["address"]["city"] == "渋谷区"
        assert len(schema.request_data["disabilities"]) == 2
