import pytest
from app.models.enums import (
    StaffRole,
    RequestStatus,
    NoticeType,
    ActionType,
    ResourceType,
)


class TestStaffRole:
    """StaffRole enumのテスト"""

    def test_staff_role_values(self):
        """StaffRoleの値が正しいことを確認"""
        assert StaffRole.employee.value == 'employee'
        assert StaffRole.manager.value == 'manager'
        assert StaffRole.owner.value == 'owner'

    def test_staff_role_members(self):
        """StaffRoleのメンバーが3つであることを確認"""
        assert len(StaffRole) == 3

    def test_staff_role_comparison(self):
        """StaffRoleの比較テスト"""
        assert StaffRole.employee == StaffRole.employee
        assert StaffRole.employee != StaffRole.manager


class TestRequestStatus:
    """RequestStatus enumのテスト（新規）"""

    def test_request_status_values(self):
        """RequestStatusの値が正しいことを確認"""
        assert RequestStatus.pending.value == 'pending'
        assert RequestStatus.approved.value == 'approved'
        assert RequestStatus.rejected.value == 'rejected'

    def test_request_status_members(self):
        """RequestStatusのメンバーが3つであることを確認"""
        assert len(RequestStatus) == 3

    def test_request_status_from_string(self):
        """文字列からRequestStatusを取得できることを確認"""
        assert RequestStatus('pending') == RequestStatus.pending
        assert RequestStatus('approved') == RequestStatus.approved
        assert RequestStatus('rejected') == RequestStatus.rejected

    def test_request_status_invalid_value(self):
        """無効な値でRequestStatusを作成しようとするとエラー"""
        with pytest.raises(ValueError):
            RequestStatus('invalid')


class TestNoticeType:
    """NoticeType enumのテスト（新規）"""

    def test_notice_type_values(self):
        """NoticeTypeの値が正しいことを確認"""
        assert NoticeType.role_change_pending.value == 'role_change_pending'
        assert NoticeType.role_change_approved.value == 'role_change_approved'
        assert NoticeType.role_change_rejected.value == 'role_change_rejected'
        assert NoticeType.role_change_request_sent.value == 'role_change_request_sent'
        assert NoticeType.employee_action_pending.value == 'employee_action_pending'
        assert NoticeType.employee_action_approved.value == 'employee_action_approved'
        assert NoticeType.employee_action_rejected.value == 'employee_action_rejected'
        assert NoticeType.employee_action_request_sent.value == 'employee_action_request_sent'

    def test_notice_type_members(self):
        """NoticeTypeのメンバーが8つであることを確認"""
        assert len(NoticeType) == 8

    def test_notice_type_from_string(self):
        """文字列からNoticeTypeを取得できることを確認"""
        assert NoticeType('role_change_pending') == NoticeType.role_change_pending
        assert NoticeType('employee_action_approved') == NoticeType.employee_action_approved

    def test_notice_type_invalid_value(self):
        """無効な値でNoticeTypeを作成しようとするとエラー"""
        with pytest.raises(ValueError):
            NoticeType('invalid_type')


class TestActionType:
    """ActionType enumのテスト（新規）"""

    def test_action_type_values(self):
        """ActionTypeの値が正しいことを確認"""
        assert ActionType.create.value == 'create'
        assert ActionType.update.value == 'update'
        assert ActionType.delete.value == 'delete'

    def test_action_type_members(self):
        """ActionTypeのメンバーが3つであることを確認"""
        assert len(ActionType) == 3

    def test_action_type_from_string(self):
        """文字列からActionTypeを取得できることを確認"""
        assert ActionType('create') == ActionType.create
        assert ActionType('update') == ActionType.update
        assert ActionType('delete') == ActionType.delete

    def test_action_type_invalid_value(self):
        """無効な値でActionTypeを作成しようとするとエラー"""
        with pytest.raises(ValueError):
            ActionType('invalid')


class TestResourceType:
    """ResourceType enumのテスト（新規）"""

    def test_resource_type_values(self):
        """ResourceTypeの値が正しいことを確認"""
        assert ResourceType.welfare_recipient.value == 'welfare_recipient'
        assert ResourceType.support_plan_cycle.value == 'support_plan_cycle'
        assert ResourceType.support_plan_status.value == 'support_plan_status'

    def test_resource_type_members(self):
        """ResourceTypeのメンバーが3つであることを確認"""
        assert len(ResourceType) == 3

    def test_resource_type_from_string(self):
        """文字列からResourceTypeを取得できることを確認"""
        assert ResourceType('welfare_recipient') == ResourceType.welfare_recipient
        assert ResourceType('support_plan_cycle') == ResourceType.support_plan_cycle
        assert ResourceType('support_plan_status') == ResourceType.support_plan_status

    def test_resource_type_invalid_value(self):
        """無効な値でResourceTypeを作成しようとするとエラー"""
        with pytest.raises(ValueError):
            ResourceType('invalid_resource')
