import pytest
from pydantic import ValidationError
from datetime import datetime
import uuid

from app.schemas.role_change_request import (
    RoleChangeRequestBase,
    RoleChangeRequestCreate,
    RoleChangeRequestRead,
    RoleChangeRequestApprove,
    RoleChangeRequestReject,
)
from app.models.enums import StaffRole, RequestStatus


class TestRoleChangeRequestBase:
    """RoleChangeRequestBaseスキーマのテスト"""

    def test_role_change_request_base_valid(self):
        """正常なデータでRoleChangeRequestBaseモデルが作成できることをテスト"""
        valid_data = {
            "requested_role": StaffRole.manager,
            "request_notes": "マネージャーへの昇格を希望します"
        }
        schema = RoleChangeRequestBase(**valid_data)
        assert schema.requested_role == StaffRole.manager
        assert schema.request_notes == "マネージャーへの昇格を希望します"

    def test_role_change_request_base_without_notes(self):
        """request_notesなしでRoleChangeRequestBaseモデルが作成できることをテスト"""
        valid_data = {
            "requested_role": StaffRole.owner
        }
        schema = RoleChangeRequestBase(**valid_data)
        assert schema.requested_role == StaffRole.owner
        assert schema.request_notes is None

    def test_role_change_request_base_invalid_role(self):
        """無効なroleでValidationErrorが発生することをテスト"""
        invalid_data = {
            "requested_role": "invalid_role"
        }
        with pytest.raises(ValidationError) as exc_info:
            RoleChangeRequestBase(**invalid_data)
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("requested_role",) for error in errors)


class TestRoleChangeRequestCreate:
    """RoleChangeRequestCreateスキーマのテスト"""

    def test_role_change_request_create_valid(self):
        """正常なデータでRoleChangeRequestCreateモデルが作成できることをテスト"""
        valid_data = {
            "requested_role": StaffRole.manager,
            "request_notes": "マネージャーへの昇格を希望します"
        }
        schema = RoleChangeRequestCreate(**valid_data)
        assert schema.requested_role == StaffRole.manager
        assert schema.request_notes == "マネージャーへの昇格を希望します"

    def test_role_change_request_create_employee_to_manager(self):
        """employee → managerのリクエストテスト"""
        valid_data = {
            "requested_role": StaffRole.manager
        }
        schema = RoleChangeRequestCreate(**valid_data)
        assert schema.requested_role == StaffRole.manager

    def test_role_change_request_create_employee_to_owner(self):
        """employee → ownerのリクエストテスト"""
        valid_data = {
            "requested_role": StaffRole.owner
        }
        schema = RoleChangeRequestCreate(**valid_data)
        assert schema.requested_role == StaffRole.owner

    def test_role_change_request_create_missing_required_field(self):
        """必須フィールドが不足している場合にValidationErrorが発生することをテスト"""
        invalid_data = {}
        with pytest.raises(ValidationError) as exc_info:
            RoleChangeRequestCreate(**invalid_data)
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("requested_role",) for error in errors)


class TestRoleChangeRequestRead:
    """RoleChangeRequestReadスキーマのテスト"""

    def test_role_change_request_read_pending(self):
        """pending状態のRoleChangeRequestReadモデルが作成できることをテスト"""
        valid_data = {
            "id": str(uuid.uuid4()),
            "requester_staff_id": str(uuid.uuid4()),
            "office_id": str(uuid.uuid4()),
            "from_role": StaffRole.employee,
            "requested_role": StaffRole.manager,
            "status": RequestStatus.pending,
            "request_notes": "マネージャーへの昇格を希望します",
            "reviewed_by_staff_id": None,
            "reviewed_at": None,
            "reviewer_notes": None,
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        }
        schema = RoleChangeRequestRead(**valid_data)
        assert schema.status == RequestStatus.pending
        assert schema.reviewed_by_staff_id is None
        assert schema.reviewed_at is None

    def test_role_change_request_read_approved(self):
        """approved状態のRoleChangeRequestReadモデルが作成できることをテスト"""
        reviewer_id = uuid.uuid4()
        reviewed_at = datetime.now()
        valid_data = {
            "id": str(uuid.uuid4()),
            "requester_staff_id": str(uuid.uuid4()),
            "office_id": str(uuid.uuid4()),
            "from_role": StaffRole.employee,
            "requested_role": StaffRole.manager,
            "status": RequestStatus.approved,
            "request_notes": "マネージャーへの昇格を希望します",
            "reviewed_by_staff_id": str(reviewer_id),
            "reviewed_at": reviewed_at,
            "reviewer_notes": "承認しました",
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        }
        schema = RoleChangeRequestRead(**valid_data)
        assert schema.status == RequestStatus.approved
        assert schema.reviewed_by_staff_id == reviewer_id
        assert schema.reviewed_at == reviewed_at
        assert schema.reviewer_notes == "承認しました"

    def test_role_change_request_read_rejected(self):
        """rejected状態のRoleChangeRequestReadモデルが作成できることをテスト"""
        valid_data = {
            "id": str(uuid.uuid4()),
            "requester_staff_id": str(uuid.uuid4()),
            "office_id": str(uuid.uuid4()),
            "from_role": StaffRole.manager,
            "requested_role": StaffRole.owner,
            "status": RequestStatus.rejected,
            "request_notes": "オーナーへの昇格を希望します",
            "reviewed_by_staff_id": str(uuid.uuid4()),
            "reviewed_at": datetime.now(),
            "reviewer_notes": "現時点では承認できません",
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        }
        schema = RoleChangeRequestRead(**valid_data)
        assert schema.status == RequestStatus.rejected
        assert schema.reviewer_notes == "現時点では承認できません"

    def test_role_change_request_read_from_attributes(self):
        """from_attributes=Trueが設定されていることをテスト"""
        assert RoleChangeRequestRead.model_config.get("from_attributes") is True


class TestRoleChangeRequestApprove:
    """RoleChangeRequestApproveスキーマのテスト"""

    def test_role_change_request_approve_with_notes(self):
        """reviewer_notesありでRoleChangeRequestApproveモデルが作成できることをテスト"""
        valid_data = {
            "reviewer_notes": "承認しました"
        }
        schema = RoleChangeRequestApprove(**valid_data)
        assert schema.reviewer_notes == "承認しました"

    def test_role_change_request_approve_without_notes(self):
        """reviewer_notesなしでRoleChangeRequestApproveモデルが作成できることをテスト"""
        valid_data = {}
        schema = RoleChangeRequestApprove(**valid_data)
        assert schema.reviewer_notes is None

    def test_role_change_request_approve_empty_notes(self):
        """空のreviewer_notesでもRoleChangeRequestApproveモデルが作成できることをテスト"""
        valid_data = {
            "reviewer_notes": ""
        }
        schema = RoleChangeRequestApprove(**valid_data)
        assert schema.reviewer_notes == ""


class TestRoleChangeRequestReject:
    """RoleChangeRequestRejectスキーマのテスト"""

    def test_role_change_request_reject_with_notes(self):
        """reviewer_notesありでRoleChangeRequestRejectモデルが作成できることをテスト"""
        valid_data = {
            "reviewer_notes": "現時点では承認できません"
        }
        schema = RoleChangeRequestReject(**valid_data)
        assert schema.reviewer_notes == "現時点では承認できません"

    def test_role_change_request_reject_without_notes(self):
        """reviewer_notesなしでRoleChangeRequestRejectモデルが作成できることをテスト"""
        valid_data = {}
        schema = RoleChangeRequestReject(**valid_data)
        assert schema.reviewer_notes is None

    def test_role_change_request_reject_detailed_notes(self):
        """詳細なreviewer_notesでRoleChangeRequestRejectモデルが作成できることをテスト"""
        valid_data = {
            "reviewer_notes": "現在の業務実績が不足しているため、承認できません。半年後に再申請してください。"
        }
        schema = RoleChangeRequestReject(**valid_data)
        assert schema.reviewer_notes == "現在の業務実績が不足しているため、承認できません。半年後に再申請してください。"
