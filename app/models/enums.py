import enum

class StaffRole(str, enum.Enum):
    employee = 'employee'
    manager = 'manager'
    owner = 'owner'

class OfficeType(str, enum.Enum):
    transition_to_employment = 'transition_to_employment'
    type_B_office = 'type_B_office'
    type_A_office = 'type_A_office'

class GenderType(str, enum.Enum):
    male = 'male'
    female = 'female'
    other = 'other'

class SupportPlanStep(str, enum.Enum):
    assessment = 'assessment'
    draft_plan = 'draft_plan'
    staff_meeting = 'staff_meeting'
    final_plan_signed = 'final_plan_signed'
    monitoring = 'monitoring'

class DeliverableType(str, enum.Enum):
    assessment_sheet = 'assessment_sheet'
    draft_plan_pdf = 'draft_plan_pdf'
    staff_meeting_minutes = 'staff_meeting_minutes'
    final_plan_signed_pdf = 'final_plan_signed_pdf'
    monitoring_report_pdf = 'monitoring_report_pdf'

class AssessmentSheetType(str, enum.Enum):
    """アセスメントシートの種類"""
    basic_info = '1-1.基本情報'
    employment_info = '1-2.就労関係'
    issue_analysis = '2.課題分析'

class BillingStatus(str, enum.Enum):
    free = 'free'          # 無料プラン
    active = 'active'        # 課金中
    past_due = 'past_due'    # 支払い延滞
    canceled = 'canceled'    # キャンセル済み

class FormOfResidence(str, enum.Enum):
    """居住形態"""
    home_with_family = "home_with_family"
    home_alone = "home_alone"
    group_home = "group_home"
    institution = "institution"
    hospital = "hospital"
    other = "other"

class MeansOfTransportation(str, enum.Enum):
    """交通手段"""
    walk = "walk"
    bicycle = "bicycle"
    motorbike = "motorbike"
    car_self = "car_self"
    car_transport = "car_transport"
    public_transport = "public_transport"
    welfare_transport = "welfare_transport"
    other = "other"

class LivelihoodProtection(str, enum.Enum):
    """生活保護受給状況"""
    not_receiving = "not_receiving"
    receiving_with_allowance = "receiving_with_allowance"
    receiving_without_allowance = "receiving_without_allowance"
    applying = "applying"
    planning = "planning"

class ApplicationStatus(str, enum.Enum):
    """手帳・制度の申請・取得状況"""
    acquired = "acquired"
    applying = "applying"
    planning = "planning"
    not_applicable = "not_applicable"

class PhysicalDisabilityGrade(str, enum.Enum):
    """身体障害者手帳の等級"""
    grade_1 = "1"
    grade_2 = "2"
    grade_3 = "3"
    grade_4 = "4"
    grade_5 = "5"
    grade_6 = "6"

class PhysicalDisabilityType(str, enum.Enum):
    """身体障害の種別"""
    visual = "visual"
    hearing = "hearing"
    limb = "limb"
    internal = "internal"
    other = "other"

class IntellectualDisabilityGrade(str, enum.Enum):
    """療育手帳の等級区分"""
    a = "A"
    b = "B"

class MentalHealthDisabilityGrade(str, enum.Enum):
    """精神障害者保健福祉手帳の等級"""
    grade_1 = "1"
    grade_2 = "2"
    grade_3 = "3"

class DisabilityBasicPensionGrade(str, enum.Enum):
    """障害基礎年金の等級"""
    grade_1 = "1"
    grade_2 = "2"

class OtherDisabilityPensionGrade(str, enum.Enum):
    """その他の障害年金等級"""
    grade_1 = "1"
    grade_2 = "2"
    grade_3 = "3"

class PublicAssistanceStatus(str, enum.Enum):
    """生活保護の受給状況"""
    receiving_with_care_allowance = "receiving_with_care"
    receiving_without_care_allowance = "receiving_without_care"
    not_receiving = "not_receiving"

class DisabilityCategory(str, enum.Enum):
    """障害・制度のカテゴリ"""
    physical_handbook = "physical_handbook"
    intellectual_handbook = "intellectual_handbook"
    mental_health_handbook = "mental_health_handbook"
    disability_basic_pension = "disability_basic_pension"
    other_disability_pension = "other_disability_pension"
    public_assistance = "public_assistance"

class CalendarConnectionStatus(str, enum.Enum):
    """カレンダー連携状態"""
    not_connected = "not_connected"  # 未連携
    connected = "connected"          # 連携済み
    error = "error"                  # エラー状態
    suspended = "suspended"          # 一時停止

class NotificationTiming(str, enum.Enum):
    """通知タイミング設定"""
    early = "early"        # 早め (30日前、14日前、7日前、3日前、1日前)
    standard = "standard"  # 標準 (30日前、7日前、1日前)
    minimal = "minimal"    # 最小限 (7日前、1日前)
    custom = "custom"      # カスタム

class CalendarEventType(str, enum.Enum):
    """カレンダーイベントタイプ"""
    renewal_deadline = "renewal_deadline"       # 更新期限
    monitoring_deadline = "monitoring_deadline" # モニタリング期限
    custom = "custom"                           # カスタムイベント

class CalendarSyncStatus(str, enum.Enum):
    """カレンダー同期ステータス"""
    pending = "pending"     # 同期待ち
    synced = "synced"       # 同期済み
    failed = "failed"       # 同期失敗
    cancelled = "cancelled" # キャンセル済み

class ReminderPatternType(str, enum.Enum):
    """リマインダーパターンタイプ"""
    single = "single"               # 単発イベント
    multiple_fixed = "multiple_fixed" # 固定日程の複数イベント
    recurring_rule = "recurring_rule" # RRULEによる繰り返し

class EventInstanceStatus(str, enum.Enum):
    """イベントインスタンスステータス"""
    pending = "pending"       # 作成予定
    created = "created"       # 作成済み
    modified = "modified"     # 変更済み
    cancelled = "cancelled"   # キャンセル済み
    completed = "completed"   # 完了
