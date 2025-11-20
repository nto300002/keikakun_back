# tests/schemas/test_dashboard_schema.py

import pytest
from pydantic import ValidationError
from datetime import date, datetime, timedelta
import uuid

from app.schemas.dashboard import (
    DashboardData,
    DashboardSummary,
    DashboardBase,
    DashboardDataCreate
)
from app.models.enums import StaffRole, BillingStatus, SupportPlanStep

# Pytestに非同期テストであることを認識させる
pytestmark = pytest.mark.asyncio


class TestDashboardSummarySchema:
    """DashboardSummaryスキーマのテスト"""
    
    def test_dashboard_recipient_valid_data(self):
        """正常系: 有効なデータでDashboardSummaryが作成される"""
        valid_data = {
            "id": str(uuid.uuid4()),
            "full_name": "田中 太郎",
            "last_name": "田中",
            "first_name": "太郎",
            "furigana": "たなか たろう",
            "current_cycle_number": 2,
            "latest_step": "draft_plan",
            "next_renewal_deadline": "2024-06-15",
            "monitoring_due_date": "2024-02-28"
        }
        
        # テスト実行
        recipient = DashboardSummary(**valid_data)
        
        # 検証
        assert recipient.id == valid_data["id"]
        assert recipient.full_name == "田中 太郎"
        assert recipient.furigana == "たなか たろう"
        assert recipient.current_cycle_number == 2
        assert recipient.latest_step == "draft_plan"
        assert recipient.next_renewal_deadline == date(2024, 6, 15)
        assert recipient.monitoring_due_date == date(2024, 2, 28)
    
    def test_dashboard_recipient_minimal_data(self):
        """正常系: 必須フィールドのみでDashboardSummaryが作成される"""
        minimal_data = {
            "id": str(uuid.uuid4()),
            "full_name": "山田 花子",
            "last_name": "山田",
            "first_name": "花子",
            "furigana": "やまだ はなこ",
            "current_cycle_number": 0,
            "latest_step": None,
            "next_renewal_deadline": None,
            "monitoring_due_date": None
        }
        
        # テスト実行
        recipient = DashboardSummary(**minimal_data)
        
        # 検証
        assert str(recipient.id) == minimal_data["id"]
        assert recipient.full_name == "山田 花子"
        assert recipient.furigana == "やまだ はなこ"
        assert recipient.current_cycle_number == 0
        assert recipient.latest_step is None
        assert recipient.next_renewal_deadline is None
        assert recipient.monitoring_due_date is None
    
    def test_dashboard_recipient_invalid_id(self):
        """異常系: 無効なUUID形式のID"""
        invalid_data = {
            "id": "invalid-uuid",
            "full_name": "テスト 太郎",
            "last_name": "テスト",
            "first_name": "太郎",
            "furigana": "てすと たろう",
            "current_cycle_number": 1,
            "latest_step": "assessment",
            "next_renewal_deadline": None,
            "monitoring_due_date": None
        }
        
        # テスト実行・検証
        with pytest.raises(ValidationError) as exc_info:
            DashboardSummary(**invalid_data)
        
        # エラー詳細確認
        errors = exc_info.value.errors()
        assert any("id" in str(error["loc"]) for error in errors)
    
    def test_dashboard_recipient_invalid_cycle_number(self):
        """異常系: 負のサイクル番号"""
        invalid_data = {
            "id": str(uuid.uuid4()),
            "full_name": "テスト 太郎",
            "last_name": "テスト",
            "first_name": "太郎",
            "furigana": "てすと たろう",
            "current_cycle_number": -1,  # 負の値
            "latest_step": "assessment",
            "next_renewal_deadline": None,
            "monitoring_due_date": None
        }
        
        # テスト実行・検証
        with pytest.raises(ValidationError) as exc_info:
            DashboardSummary(**invalid_data)
        
        # エラー詳細確認
        errors = exc_info.value.errors()
        assert any("current_cycle_number" in str(error["loc"]) for error in errors)
    
    def test_dashboard_recipient_empty_name(self):
        """異常系: 空の氏名"""
        invalid_data = {
            "id": str(uuid.uuid4()),
            "full_name": "",  # 空文字列
            "last_name": "テスト",
            "first_name": "太郎",
            "furigana": "てすと たろう",
            "current_cycle_number": 1,
            "latest_step": "assessment",
            "next_renewal_deadline": None,
            "monitoring_due_date": None
        }
        
        # テスト実行・検証
        with pytest.raises(ValidationError) as exc_info:
            DashboardSummary(**invalid_data)
        
        # エラー詳細確認
        errors = exc_info.value.errors()
        assert any("full_name" in str(error["loc"]) for error in errors)
    
    def test_dashboard_recipient_invalid_step(self):
        """異常系: 無効なステップ値"""
        invalid_data = {
            "id": str(uuid.uuid4()),
            "full_name": "テスト 太郎",
            "last_name": "テスト",
            "first_name": "太郎",
            "furigana": "てすと たろう",
            "current_cycle_number": 1,
            "latest_step": "invalid_step",  # 無効なステップ
            "next_renewal_deadline": None,
            "monitoring_due_date": None
        }
        
        # テスト実行・検証
        with pytest.raises(ValidationError) as exc_info:
            DashboardSummary(**invalid_data)
        
        # エラー詳細確認
        errors = exc_info.value.errors()
        assert any("latest_step" in str(error["loc"]) for error in errors)
    
    def test_dashboard_recipient_invalid_date_format(self):
        """異常系: 無効な日付形式"""
        invalid_data = {
            "id": str(uuid.uuid4()),
            "full_name": "テスト 太郎",
            "last_name": "テスト",
            "first_name": "太郎",
            "furigana": "てすと たろう",
            "current_cycle_number": 1,
            "latest_step": "assessment",
            "next_renewal_deadline": "2024/06/15",  # 無効な形式
            "monitoring_due_date": None
        }
        
        # テスト実行・検証
        with pytest.raises(ValidationError) as exc_info:
            DashboardSummary(**invalid_data)
        
        # エラー詳細確認
        errors = exc_info.value.errors()
        assert any("next_renewal_deadline" in str(error["loc"]) for error in errors)


class TestDashboardDataSchema:
    """DashboardDataスキーマのテスト"""
    
    def test_dashboard_data_valid_full_data(self):
        """正常系: 完全なデータでDashboardDataが作成される"""
        recipients = [
            {
                "id": str(uuid.uuid4()),
                "full_name": "田中 太郎",
                "last_name": "田中",
                "first_name": "太郎",
                "furigana": "たなか たろう",
                "current_cycle_number": 1,
                "latest_step": "assessment",
                "next_renewal_deadline": "2024-06-15",
                "monitoring_due_date": None
            },
            {
                "id": str(uuid.uuid4()),
                "full_name": "山田 花子",
                "last_name": "山田",
                "first_name": "花子",
                "furigana": "やまだ はなこ",
                "current_cycle_number": 2,
                "latest_step": "monitoring",
                "next_renewal_deadline": "2024-07-20",
                "monitoring_due_date": "2024-03-05"
            }
        ]
        
        valid_data = {
            "staff_name": "管理者 太郎",
            "staff_role": StaffRole.owner,
            "office_id": str(uuid.uuid4()),
            "office_name": "テスト事業所",
            "current_user_count": 2,
            "max_user_count": 10,
            "billing_status": BillingStatus.free,
            "recipients": recipients
        }
        
        # テスト実行
        dashboard = DashboardData(**valid_data)
        
        # 検証
        assert dashboard.staff_name == "管理者 太郎"
        assert dashboard.staff_role == StaffRole.owner
        assert str(dashboard.office_id) == valid_data["office_id"]
        assert dashboard.office_name == "テスト事業所"
        assert dashboard.current_user_count == 2
        assert dashboard.max_user_count == 10
        assert dashboard.billing_status == BillingStatus.free
        assert len(dashboard.recipients) == 2
        assert isinstance(dashboard.recipients[0], DashboardSummary)
    
    def test_dashboard_data_empty_recipients(self):
        """正常系: 利用者が0人のDashboardData"""
        valid_data = {
            "staff_name": "管理者 花子",
            "staff_role": StaffRole.manager,
            "office_id": str(uuid.uuid4()),
            "office_name": "空の事業所",
            "current_user_count": 0,
            "max_user_count": 10,
            "billing_status": BillingStatus.active,
            "recipients": []
        }
        
        # テスト実行
        dashboard = DashboardData(**valid_data)
        
        # 検証
        assert dashboard.current_user_count == 0
        assert len(dashboard.recipients) == 0
    
    def test_dashboard_data_invalid_staff_role(self):
        """異常系: 無効なスタッフ権限"""
        invalid_data = {
            "staff_name": "テスト管理者",
            "staff_role": "invalid_role",  # 無効な権限
            "office_id": str(uuid.uuid4()),
            "office_name": "テスト事業所",
            "current_user_count": 1,
            "max_user_count": 10,
            "billing_status": BillingStatus.free,
            "recipients": []
        }
        
        # テスト実行・検証
        with pytest.raises(ValidationError) as exc_info:
            DashboardData(**invalid_data)
        
        # エラー詳細確認
        errors = exc_info.value.errors()
        assert any("staff_role" in str(error["loc"]) for error in errors)
    
    def test_dashboard_data_invalid_billing_status(self):
        """異常系: 無効な課金ステータス"""
        invalid_data = {
            "staff_name": "テスト管理者",
            "staff_role": StaffRole.employee,
            "office_id": str(uuid.uuid4()),
            "office_name": "テスト事業所",
            "current_user_count": 1,
            "max_user_count": 10,
            "billing_status": "invalid_status",  # 無効なステータス
            "recipients": []
        }
        
        # テスト実行・検証
        with pytest.raises(ValidationError) as exc_info:
            DashboardData(**invalid_data)
        
        # エラー詳細確認
        errors = exc_info.value.errors()
        assert any("billing_status" in str(error["loc"]) for error in errors)
    
    def test_dashboard_data_negative_user_count(self):
        """異常系: 負の利用者数"""
        invalid_data = {
            "staff_name": "テスト管理者",
            "staff_role": StaffRole.owner,
            "office_id": str(uuid.uuid4()),
            "office_name": "テスト事業所",
            "current_user_count": -1,  # 負の値
            "max_user_count": 10,
            "billing_status": BillingStatus.free,
            "recipients": []
        }
        
        # テスト実行・検証
        with pytest.raises(ValidationError) as exc_info:
            DashboardData(**invalid_data)
        
        # エラー詳細確認
        errors = exc_info.value.errors()
        assert any("current_user_count" in str(error["loc"]) for error in errors)
    
    def test_dashboard_data_user_count_exceeds_max(self):
        """データ整合性: 現在の利用者数が上限を超過"""
        # この場合はバリデーションエラーにせず、ビジネスロジックで処理
        data = {
            "staff_name": "テスト管理者",
            "staff_role": StaffRole.owner,
            "office_id": str(uuid.uuid4()),
            "office_name": "テスト事業所",
            "current_user_count": 15,  # 上限を超過
            "max_user_count": 10,
            "billing_status": BillingStatus.free,
            "recipients": []
        }
        
        # テスト実行（エラーにならないことを確認）
        dashboard = DashboardData(**data)
        
        # 検証: データは作成されるが、ビジネスロジックで判定する
        assert dashboard.current_user_count == 15
        assert dashboard.max_user_count == 10
        assert dashboard.current_user_count > dashboard.max_user_count
    
    def test_dashboard_data_empty_staff_name(self):
        """異常系: 空のスタッフ名"""
        invalid_data = {
            "staff_name": "",  # 空文字列
            "staff_role": StaffRole.owner,
            "office_id": str(uuid.uuid4()),
            "office_name": "テスト事業所",
            "current_user_count": 1,
            "max_user_count": 10,
            "billing_status": BillingStatus.free,
            "recipients": []
        }
        
        # テスト実行・検証
        with pytest.raises(ValidationError) as exc_info:
            DashboardData(**invalid_data)
        
        # エラー詳細確認
        errors = exc_info.value.errors()
        assert any("staff_name" in str(error["loc"]) for error in errors)
    
    def test_dashboard_data_invalid_office_id(self):
        """異常系: 無効な事業所ID形式"""
        invalid_data = {
            "staff_name": "テスト管理者",
            "staff_role": StaffRole.owner,
            "office_id": "invalid-office-id",  # 無効なUUID
            "office_name": "テスト事業所",
            "current_user_count": 1,
            "max_user_count": 10,
            "billing_status": BillingStatus.free,
            "recipients": []
        }
        
        # テスト実行・検証
        with pytest.raises(ValidationError) as exc_info:
            DashboardData(**invalid_data)
        
        # エラー詳細確認
        errors = exc_info.value.errors()
        assert any("office_id" in str(error["loc"]) for error in errors)


class TestDashboardSchemaEdgeCases:
    """ダッシュボードスキーマのエッジケーステスト"""
    
    def test_dashboard_recipient_very_long_names(self):
        """エッジケース: 非常に長い名前での処理"""
        long_name = "あ" * 100  # 100文字の長い名前
        long_furigana = "あ" * 100  # 100文字の長いふりがな
        
        valid_data = {
            "id": str(uuid.uuid4()),
            "full_name": long_name,
            "last_name": "あ" * 50,
            "first_name": "あ" * 50,
            "furigana": long_furigana,
            "current_cycle_number": 1,
            "latest_step": "assessment",
            "next_renewal_deadline": None,
            "monitoring_due_date": None
        }
        
        # テスト実行
        recipient = DashboardSummary(**valid_data)
        
        # 検証: 長い名前も受け入れられる
        assert recipient.full_name == long_name
        assert recipient.furigana == long_furigana
    
    def test_dashboard_data_maximum_recipients(self):
        """エッジケース: 大量の利用者データ"""
        # 1000人の利用者を作成
        recipients = []
        for i in range(1000):
            recipient_data = {
                "id": str(uuid.uuid4()),
                "full_name": f"テスト{i:04d} 利用者",
                "last_name": f"テスト{i:04d}",
                "first_name": "利用者",
                "furigana": f"てすと{i:04d} りようしゃ",
                "current_cycle_number": i % 5,  # 0-4のサイクル番号
                "latest_step": ["assessment", "draft_plan", "staff_meeting", "monitoring"][i % 4],
                "next_renewal_deadline": None,
                "monitoring_due_date": None
            }
            recipients.append(recipient_data)
        
        dashboard_data = {
            "staff_name": "大量データテスト管理者",
            "staff_role": StaffRole.owner,
            "office_id": str(uuid.uuid4()),
            "office_name": "大規模テスト事業所",
            "current_user_count": 1000,
            "max_user_count": 999999,
            "billing_status": BillingStatus.active,
            "recipients": recipients
        }
        
        # テスト実行
        dashboard = DashboardData(**dashboard_data)
        
        # 検証
        assert len(dashboard.recipients) == 1000
        assert dashboard.current_user_count == 1000
        assert all(isinstance(recipient, DashboardSummary) for recipient in dashboard.recipients)
    
    def test_dashboard_recipient_special_characters(self):
        """エッジケース: 特殊文字を含む名前"""
        special_data = {
            "id": str(uuid.uuid4()),
            "full_name": "田中♪ 太郎★",
            "last_name": "田中♪",
            "first_name": "太郎★",
            "furigana": "たなか♫ たろう☆",
            "current_cycle_number": 1,
            "latest_step": "assessment",
            "next_renewal_deadline": None,
            "monitoring_due_date": None
        }
        
        # テスト実行
        recipient = DashboardSummary(**special_data)
        
        # 検証: 特殊文字も受け入れられる
        assert recipient.full_name == "田中♪ 太郎★"
        assert recipient.furigana == "たなか♫ たろう☆"
    
    def test_dashboard_data_unicode_office_name(self):
        """エッジケース: Unicode文字を含む事業所名"""
        unicode_data = {
            "staff_name": "テスト管理者",
            "staff_role": StaffRole.owner,
            "office_id": str(uuid.uuid4()),
            "office_name": "🏢事業所🌸",  # 絵文字を含む
            "current_user_count": 1,
            "max_user_count": 10,
            "billing_status": BillingStatus.free,
            "recipients": []
        }
        
        # テスト実行
        dashboard = DashboardData(**unicode_data)
        
        # 検証: Unicode文字も正しく処理される
        assert dashboard.office_name == "🏢事業所🌸"
    
    def test_dashboard_recipient_boundary_dates(self):
        """エッジケース: 境界値の日付"""
        # 遠い未来と遠い過去の日付
        far_future = date(2099, 12, 31)
        far_past = date(1900, 1, 1)
        
        boundary_data = {
            "id": str(uuid.uuid4()),
            "full_name": "境界値 テスト",
            "last_name": "境界値",
            "first_name": "テスト",
            "furigana": "きょうかいち てすと",
            "current_cycle_number": 999,  # 大きなサイクル番号
            "latest_step": "monitoring",
            "next_renewal_deadline": far_future.isoformat(),
            "monitoring_due_date": far_past.isoformat()
        }
        
        # テスト実行
        recipient = DashboardSummary(**boundary_data)
        
        # 検証: 境界値の日付も正しく処理される
        assert recipient.next_renewal_deadline == far_future
        assert recipient.monitoring_due_date == far_past
        assert recipient.current_cycle_number == 999


class TestDashboardSchemaValidation:
    """ダッシュボードスキーマのバリデーション詳細テスト"""
    
    def test_dashboard_recipient_missing_required_fields(self):
        """異常系: 必須フィールド不足"""
        incomplete_data = {
            "id": str(uuid.uuid4()),
            # full_nameが不足
            "furigana": "てすと たろう",
            "current_cycle_number": 1,
        }
        
        # テスト実行・検証
        with pytest.raises(ValidationError) as exc_info:
            DashboardSummary(**incomplete_data)
        
        # エラー詳細確認
        errors = exc_info.value.errors()
        assert any(error["type"] == "missing" for error in errors)
    
    def test_dashboard_data_missing_required_fields(self):
        """異常系: DashboardDataの必須フィールド不足"""
        incomplete_data = {
            "staff_name": "テスト管理者",
            # staff_roleが不足
            "office_id": str(uuid.uuid4()),
            "office_name": "テスト事業所",
            "current_user_count": 1,
            "max_user_count": 10,
            "billing_status": BillingStatus.free,
            "recipients": []
        }
        
        # テスト実行・検証
        with pytest.raises(ValidationError) as exc_info:
            DashboardData(**incomplete_data)
        
        # エラー詳細確認
        errors = exc_info.value.errors()
        assert any(error["type"] == "missing" for error in errors)
    
    def test_dashboard_recipient_extra_fields_ignored(self):
        """正常系: 余分なフィールドは無視される"""
        data_with_extra = {
            "id": str(uuid.uuid4()),
            "full_name": "テスト 太郎",
            "last_name": "テスト",
            "first_name": "太郎",
            "furigana": "てすと たろう",
            "current_cycle_number": 1,
            "latest_step": "assessment",
            "next_renewal_deadline": None,
            "monitoring_due_date": None,
            "extra_field": "これは無視される"  # 余分なフィールド
        }
        
        # テスト実行
        recipient = DashboardSummary(**data_with_extra)
        
        # 検証: 余分なフィールドは無視され、正常に作成される
        assert recipient.full_name == "テスト 太郎"
        assert not hasattr(recipient, "extra_field")
    
    def test_dashboard_data_serialization(self):
        """正常系: DashboardDataのシリアライゼーション"""
        recipients = [
            {
                "id": str(uuid.uuid4()),
                "full_name": "田中 太郎",
                "last_name": "田中",
                "first_name": "太郎",
                "furigana": "たなか たろう",
                "current_cycle_number": 1,
                "latest_step": "assessment",
                "next_renewal_deadline": "2024-06-15",
                "monitoring_due_date": None
            }
        ]
        
        dashboard_data = {
            "staff_name": "管理者 太郎",
            "staff_role": StaffRole.owner,
            "office_id": str(uuid.uuid4()),
            "office_name": "テスト事業所",
            "current_user_count": 1,
            "max_user_count": 10,
            "billing_status": BillingStatus.free,
            "recipients": recipients
        }
        
        # スキーマ作成
        dashboard = DashboardData(**dashboard_data)
        
        # JSON形式での出力テスト
        json_data = dashboard.model_dump()
        
        # 検証
        assert isinstance(json_data, dict)
        assert json_data["staff_name"] == "管理者 太郎"
        assert json_data["staff_role"] == "owner"  # Enumが文字列に変換される
        assert json_data["billing_status"] == "free"  # Enumが文字列に変換される
        assert len(json_data["recipients"]) == 1
        assert json_data["recipients"][0]["next_renewal_deadline"] == date(2024, 6, 15)