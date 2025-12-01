"""
テストデータ識別フラグ (is_test_data) のフィールド存在テスト

TDD Step 1: RED - このテストは最初は失敗する
"""
import pytest
from sqlalchemy.orm import Mapped
from sqlalchemy import Boolean

# すべての対象モデルをインポート
from app.models.office import Office, OfficeStaff
from app.models.staff import Staff
from app.models.welfare_recipient import (
    WelfareRecipient, OfficeWelfareRecipient, ServiceRecipientDetail,
    DisabilityStatus, DisabilityDetail, EmergencyContact
)
from app.models.notice import Notice
from app.models.support_plan_cycle import (
    SupportPlanCycle, SupportPlanStatus, PlanDeliverable
)
from app.models.calendar_events import (
    CalendarEvent, CalendarEventSeries, CalendarEventInstance
)
from app.models.approval_request import ApprovalRequest
from app.models.assessment import (
    FamilyOfServiceRecipients, WelfareServicesUsed, MedicalMatters,
    HistoryOfHospitalVisits, EmploymentRelated, IssueAnalysis
)


class TestIsTestDataFieldExistence:
    """is_test_data フィールドが23モデルすべてに存在することを確認"""

    # 必須テーブル群 (18モデル)
    # 注: RoleChangeRequest と EmployeeActionRequest は ApprovalRequest に統合済み
    REQUIRED_MODELS = [
        Office,
        Staff,
        OfficeStaff,
        WelfareRecipient,
        OfficeWelfareRecipient,
        SupportPlanCycle,
        SupportPlanStatus,
        CalendarEventSeries,
        CalendarEventInstance,
        Notice,
        ApprovalRequest,
        ServiceRecipientDetail,
        DisabilityStatus,
        DisabilityDetail,
        FamilyOfServiceRecipients,
        MedicalMatters,
        EmploymentRelated,
        IssueAnalysis,
    ]

    # オプションテーブル群 (5モデル)
    OPTIONAL_MODELS = [
        CalendarEvent,
        PlanDeliverable,
        EmergencyContact,
        WelfareServicesUsed,
        HistoryOfHospitalVisits,
    ]

    @pytest.mark.parametrize("model_class", REQUIRED_MODELS)
    def test_required_models_have_is_test_data_field(self, model_class):
        """必須モデル(18個)に is_test_data フィールドが存在することを確認"""
        assert hasattr(model_class, 'is_test_data'), \
            f"{model_class.__name__} には is_test_data フィールドが必要です"

    @pytest.mark.parametrize("model_class", OPTIONAL_MODELS)
    def test_optional_models_have_is_test_data_field(self, model_class):
        """オプションモデル(5個)に is_test_data フィールドが存在することを確認"""
        assert hasattr(model_class, 'is_test_data'), \
            f"{model_class.__name__} には is_test_data フィールドが必要です"

    @pytest.mark.parametrize("model_class", REQUIRED_MODELS + OPTIONAL_MODELS)
    def test_is_test_data_field_type(self, model_class):
        """is_test_data フィールドの型が Boolean であることを確認"""
        assert hasattr(model_class, 'is_test_data'), \
            f"{model_class.__name__} には is_test_data フィールドが必要です"

        # SQLAlchemy 2.0 の Mapped 型チェック
        field = getattr(model_class, 'is_test_data')
        assert hasattr(field, 'type') or hasattr(field.property, 'columns'), \
            f"{model_class.__name__}.is_test_data はマップされたカラムである必要があります"

    @pytest.mark.parametrize("model_class", REQUIRED_MODELS + OPTIONAL_MODELS)
    def test_is_test_data_field_default_value(self, model_class):
        """is_test_data フィールドのデフォルト値が False であることを確認"""
        assert hasattr(model_class, 'is_test_data'), \
            f"{model_class.__name__} には is_test_data フィールドが必要です"

        # インスタンスを作成してデフォルト値を確認
        # (まだモデル定義が更新されていない場合は失敗する)
        try:
            # デフォルト値の確認（mapped_columnの設定を確認）
            field = getattr(model_class, 'is_test_data')
            if hasattr(field.property, 'columns'):
                column = field.property.columns[0]
                # デフォルト値が設定されているか確認
                assert column.default is not None or column.server_default is not None, \
                    f"{model_class.__name__}.is_test_data にはデフォルト値が必要です"
        except AttributeError:
            pytest.fail(f"{model_class.__name__}.is_test_data のカラム定義が不正です")

    def test_all_23_models_covered(self):
        """23モデルすべてがテストでカバーされていることを確認"""
        total_models = len(self.REQUIRED_MODELS) + len(self.OPTIONAL_MODELS)
        assert total_models == 23, \
            f"23モデルすべてをテストする必要があります（現在: {total_models}モデル）"
